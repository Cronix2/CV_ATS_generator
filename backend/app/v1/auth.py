import hashlib
import re
from dataclasses import dataclass

from fastapi import Header, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.v1 import store
from app.v1.db import sql, transaction
from app.v1.errors import APIError
from app.v1.settings import setting

SCOPES = {
    f"{domain}:{action}"
    for domain, actions in {
        "profiles": ["read", "write"],
        "cvs": ["read", "write"],
        "offers": ["read", "write"],
        "linkedin": ["read", "write"],
        "ai": ["run"],
        "ats": ["read"],
        "exports": ["read", "write"],
        "jobs": ["read", "write"],
        "workflows": ["read", "write", "approve"],
        "conversations": ["read", "write"],
    }.items()
    for action in actions
}


@dataclass(frozen=True)
class Actor:
    tenant: str
    user: str
    key_id: str
    scopes: frozenset[str]

    def require(self, scope):
        if scope not in self.scopes:
            raise APIError(403, "forbidden", "Permission insuffisante.")


def authenticate(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(
        HTTPBearer(auto_error=False)
    ),
    x_passefiltre_user_id: str | None = Header(None),
) -> Actor:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or len(authorization) > 512:
        raise APIError(401, "unauthorized", "Clé de service manquante ou invalide.")
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with transaction() as conn:
        row = (
            sql(
                conn,
                """SELECT id,tenant,scopes FROM pf_keys WHERE digest=:digest AND NOT revoked
            AND (expires_at IS NULL OR expires_at>now())""",
                digest=digest,
            )
            .mappings()
            .first()
        )
        if not row:
            raise APIError(401, "unauthorized", "Clé de service manquante ou invalide.")
        user = request.headers.get("x-passefiltre-user-id", "")
        if not re.fullmatch(r"[A-Za-z0-9_.:@-]{1,128}", user):
            raise APIError(422, "invalid_input", "X-PasseFiltre-User-Id opaque requis.")
        actor = Actor(row["tenant"], user, str(row["id"]), frozenset(row["scopes"]))
        store.counter(
            conn,
            ["rate-service", actor.key_id],
            setting("V1_RATE_SERVICE_PER_MINUTE"),
            60,
        )
        store.counter(
            conn,
            ["rate-user", actor.tenant, user],
            setting("V1_RATE_USER_PER_MINUTE"),
            60,
        )
    request.state.actor = actor
    return actor


def still_authorized(conn, actor, scope):
    row = sql(
        conn,
        """SELECT scopes FROM pf_keys WHERE id=:id AND tenant=:tenant AND NOT revoked
        AND (expires_at IS NULL OR expires_at>now())""",
        id=actor.key_id,
        tenant=actor.tenant,
    ).first()
    if not row or scope not in row.scopes:
        raise APIError(
            403, "authorization_revoked", "Autorisation révoquée ou expirée."
        )
