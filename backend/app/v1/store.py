"""Owner-scoped resource repository. RLS independently enforces every query."""

from uuid import uuid4

from app.v1.crypto import canonical, digest
from app.v1.db import sql
from app.v1.errors import APIError, missing
from app.v1.settings import setting


def create(conn, actor, kind, data, ttl=None, ident=None):
    ident = ident or str(uuid4())
    row = (
        sql(
            conn,
            """INSERT INTO pf_records(id, tenant, owner_id, kind, data, expires_at)
        VALUES (:id, :tenant, :owner, :kind, CAST(:data AS jsonb),
            CASE WHEN CAST(:ttl AS integer) IS NULL THEN NULL ELSE now() + (:ttl * interval '1 second') END)
        RETURNING *""",
            id=ident,
            tenant=actor.tenant,
            owner=actor.user,
            kind=kind,
            data=canonical(data),
            ttl=ttl,
        )
        .mappings()
        .one()
    )
    return public(row)


def public(row):
    return {
        k: str(v) if k == "id" else v
        for k, v in row.items()
        if k not in ("tenant", "owner_id")
    }


def get(conn, kind, ident, lock=False):
    row = (
        sql(
            conn,
            """SELECT * FROM pf_records WHERE id=:id AND kind=:kind
        AND (expires_at IS NULL OR expires_at>now())"""
            + (" FOR UPDATE" if lock else ""),
            id=str(ident),
            kind=kind,
        )
        .mappings()
        .first()
    )
    if not row:
        raise missing()
    return public(row)


def listing(conn, kind, cursor=None, limit=50):
    return [
        public(r)
        for r in sql(
            conn,
            """SELECT * FROM pf_records WHERE kind=:kind
       AND (expires_at IS NULL OR expires_at>now()) AND (CAST(:cursor AS uuid) IS NULL OR id>CAST(:cursor AS uuid))
       ORDER BY id LIMIT :limit""",
            kind=kind,
            cursor=str(cursor) if cursor else None,
            limit=limit,
        ).mappings()
    ]


def update(conn, kind, ident, data, expected=None):
    row = get(conn, kind, ident, lock=True)
    if expected is not None and row["version"] != expected:
        raise APIError(412, "version_conflict", "La ressource a été modifiée.")
    result = (
        sql(
            conn,
            """UPDATE pf_records SET data=CAST(:data AS jsonb), version=version+1, updated_at=now()
        WHERE id=:id RETURNING *""",
            data=canonical(data),
            id=str(ident),
        )
        .mappings()
        .one()
    )
    return public(result)


def delete(conn, kind, ident):
    get(conn, kind, ident, lock=True)
    sql(conn, "DELETE FROM pf_records WHERE id=:id", id=str(ident))


def audit(conn, actor, action, resource=None, outcome="ok"):
    sql(
        conn,
        """INSERT INTO pf_audit(actor,action,resource,outcome) VALUES (:actor,:action,:resource,:outcome)""",
        actor=digest([actor.tenant, actor.user, actor.key_id]),
        action=action,
        resource=resource,
        outcome=outcome,
    )


def counter(conn, ident, maximum, seconds):
    value = sql(
        conn,
        """INSERT INTO pf_counters(id,count,expires_at) VALUES(:id,1,now()+(:seconds*interval '1 second'))
      ON CONFLICT(id) DO UPDATE SET count=CASE WHEN pf_counters.expires_at<=now() THEN 1 ELSE pf_counters.count+1 END,
      expires_at=CASE WHEN pf_counters.expires_at<=now() THEN EXCLUDED.expires_at ELSE pf_counters.expires_at END
      RETURNING count""",
        id=digest(ident),
        seconds=seconds,
    ).scalar_one()
    if value > maximum:
        raise APIError(
            429, "quota_exceeded", "Quota atteint. Réessayez plus tard.", seconds
        )


def idempotent(conn, actor, key, operation, body, execute, ttl=None):
    if not key or len(key) > 128:
        raise APIError(
            422, "invalid_input", "Idempotency-Key requis (128 caractères maximum)."
        )
    marker = digest([actor.tenant, actor.user, operation, key])
    # Scoped transaction lock serializes identical keys across processes, including synchronous facades.
    sql(conn, "SELECT pg_advisory_xact_lock(:lock)", lock=int(marker[:15], 16))
    found = (
        sql(
            conn,
            "SELECT * FROM pf_records WHERE kind='idempotency' AND data->>'marker'=:marker AND expires_at>now()",
            marker=marker,
        )
        .mappings()
        .first()
    )
    fingerprint = digest(body)
    if found:
        if found["data"]["fingerprint"] != fingerprint:
            raise APIError(
                409,
                "idempotency_conflict",
                "Clé déjà utilisée avec un contenu différent.",
            )
        return found["data"]["response"]
    response = execute()
    create(
        conn,
        actor,
        "idempotency",
        dict(marker=marker, fingerprint=fingerprint, response=response),
        ttl or setting("V1_RESULT_TTL_SECONDS"),
    )
    return response
