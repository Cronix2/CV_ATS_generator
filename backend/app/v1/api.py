import base64
import hashlib
import os
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.ats import analyse, extract_keywords
from app.services.cv import render
from app.v1 import VERSION, business, store, tasks
from app.v1.auth import Actor, authenticate
from app.v1.crypto import digest, seal, secret_fingerprint
from app.v1.db import check, transaction
from app.v1.errors import APIError
from app.v1.schemas import (
    Approval,
    ATSResult,
    CodeInput,
    ConversationInput,
    CVInput,
    ErrorResponse,
    ImportOffer,
    JobView,
    MessageInput,
    OfferInput,
    ProfileInput,
    RenderInput,
    ResourcePage,
    ResourceView,
    ReviewInput,
    ScrapeInput,
    WorkflowInput,
)
from app.v1.settings import setting

app = FastAPI(
    title="PasseFiltre API v1",
    version=VERSION,
    docs_url="/docs" if os.getenv("API_DOCS") == "1" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if os.getenv("API_DOCS") == "1" else None,
    responses={
        s: {"model": ErrorResponse}
        for s in (401, 403, 404, 409, 412, 413, 415, 422, 428, 429, 500, 502, 503)
    },
)

EXPORT_RESPONSE = {
    200: {
        "description": "PDF or DOCX bytes; X-Content-SHA256 is the SHA-256 of this body.",
        "content": {
            mime: {"schema": {"type": "string", "format": "binary"}}
            for mime in (
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        "headers": {
            "X-Content-SHA256": {"schema": {"type": "string"}},
            "Content-Disposition": {"schema": {"type": "string"}},
        },
    }
}


@app.middleware("http")
async def envelope(request: Request, call_next):
    request.state.request_id = uuid4().hex
    # Bound streamed bodies too; Content-Length is not a trust boundary.
    if request.method in ("POST", "PUT", "PATCH"):
        if not request.headers.get("content-type", "").startswith("application/json"):
            return problem(
                request,
                415,
                "unsupported_media_type",
                "Content-Type application/json requis.",
            )
        data = bytearray()
        async for part in request.stream():
            data.extend(part)
            if len(data) > 2 * 1024 * 1024:
                return problem(
                    request, 413, "payload_too_large", "Requête trop volumineuse."
                )
        request._body = bytes(data)
    try:
        response = await call_next(request)
    except SQLAlchemyError:
        response = problem(
            request, 503, "storage_unavailable", "Stockage temporairement indisponible."
        )
    except Exception:
        # Neither exception text nor traceback: provider errors may carry PII and credentials.
        response = problem(request, 500, "internal", "Erreur interne.")
    response.headers.update(
        {"X-Request-Id": request.state.request_id, "Cache-Control": "no-store"}
    )
    return response


def problem(request, status, code, message, retry_after=None):
    request_id = getattr(request.state, "request_id", None) or uuid4().hex
    headers = {"Cache-Control": "no-store", "X-Request-Id": request_id}
    if retry_after:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(
        dict(code=code, message=message, request_id=request_id),
        status_code=status,
        headers=headers,
    )


@app.exception_handler(APIError)
async def api_error(request, exc):
    return problem(request, exc.status, exc.code, exc.message, exc.retry_after)


@app.exception_handler(RequestValidationError)
async def invalid(request, exc):
    return problem(
        request, 422, "invalid_input", "Requête invalide. Consultez le schéma OpenAPI."
    )


@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    return problem(
        request,
        exc.status_code,
        "not_found" if exc.status_code == 404 else "invalid_input",
        "Requête refusée.",
    )


@app.get("/health", tags=["operations"])
def health():
    return dict(ok=True, version=VERSION, schema_version="1")


@app.get("/ready", tags=["operations"])
def ready(actor: Actor = Depends(authenticate)):
    check()
    from redis import Redis

    try:
        Redis.from_url(os.environ["V1_REDIS_URL"], socket_timeout=2).ping()
    except Exception:
        raise APIError(
            503, "queue_unavailable", "File de tâches indisponible."
        ) from None
    return dict(ok=True)


def expected(value):
    if value is None:
        raise APIError(428, "precondition_required", "If-Match requis.")
    try:
        result = int(value.strip('"'))
        if result < 1:
            raise ValueError()
        return result
    except ValueError:
        raise APIError(422, "invalid_input", "If-Match invalide.") from None


def tag(response, row):
    response.headers["ETag"] = f'"{row["version"]}"'
    return row


def history(conn, actor, row):
    if row["kind"] == "cv":
        store.create(
            conn,
            actor,
            "cv_version",
            dict(cv_id=row["id"], version=row["version"], cv=row["data"]["cv"]),
        )


def resource_routes(path, kind, schema, permission):
    def create(
        body: schema,
        response: Response,
        actor: Actor = Depends(authenticate),
        idempotency_key: str = Header(...),
    ):
        actor.require(permission + ":write")
        with transaction(actor) as conn:

            def execute():
                row = store.create(conn, actor, kind, body.model_dump(mode="json"))
                history(conn, actor, row)
                store.audit(conn, actor, kind + ".created", row["id"])
                return row

            row = store.idempotent(
                conn,
                actor,
                idempotency_key,
                path,
                body.model_dump(mode="json"),
                execute,
            )
            return tag(response, row)

    def read(ident: UUID, response: Response, actor: Actor = Depends(authenticate)):
        actor.require(permission + ":read")
        with transaction(actor) as conn:
            return tag(response, store.get(conn, kind, ident))

    def listing(
        actor: Actor = Depends(authenticate),
        cursor: UUID | None = None,
        limit: int = Query(50, ge=1, le=100),
    ):
        actor.require(permission + ":read")
        with transaction(actor) as conn:
            rows = store.listing(conn, kind, cursor, limit + 1)
            return dict(
                items=rows[:limit],
                next_cursor=rows[limit - 1]["id"] if len(rows) > limit else None,
            )

    def replace(
        ident: UUID,
        body: schema,
        response: Response,
        actor: Actor = Depends(authenticate),
        if_match: str | None = Header(None),
    ):
        actor.require(permission + ":write")
        with transaction(actor) as conn:
            row = store.update(
                conn, kind, ident, body.model_dump(mode="json"), expected(if_match)
            )
            history(conn, actor, row)
            store.audit(conn, actor, kind + ".updated", str(ident))
            return tag(response, row)

    def remove(ident: UUID, actor: Actor = Depends(authenticate)):
        actor.require(permission + ":write")
        with transaction(actor) as conn:
            store.delete(conn, kind, ident)
            if kind == "cv":
                store.sql(
                    conn,
                    "DELETE FROM pf_records WHERE kind='cv_version' AND data->>'cv_id'=:id",
                    id=str(ident),
                )
            store.audit(conn, actor, kind + ".deleted", str(ident))
        return Response(status_code=204)

    for handler, methods, suffix, status in [
        (create, ["POST"], "", 201),
        (listing, ["GET"], "", 200),
        (read, ["GET"], "/{ident}", 200),
        (replace, ["PUT"], "/{ident}", 200),
        (remove, ["DELETE"], "/{ident}", 204),
    ]:
        app.add_api_route(
            path + suffix,
            handler,
            methods=methods,
            status_code=status,
            tags=[permission],
            name=kind + "_" + handler.__name__,
            response_model=None
            if status == 204
            else ResourcePage
            if handler is listing
            else ResourceView,
        )


resource_routes("/profiles", "profile", ProfileInput, "profiles")
resource_routes("/cvs", "cv", CVInput, "cvs")
resource_routes("/offers", "offer", OfferInput, "offers")


@app.get("/cvs/{ident}/versions", tags=["cvs"])
def versions(ident: UUID, actor: Actor = Depends(authenticate)):
    actor.require("cvs:read")
    with transaction(actor) as conn:
        store.get(conn, "cv", ident)
        return [
            store.public(r)
            for r in store.sql(
                conn,
                "SELECT * FROM pf_records WHERE kind='cv_version' AND data->>'cv_id'=:id ORDER BY (data->>'version')::integer",
                id=str(ident),
            ).mappings()
        ]


def schedule(kind, body, actor, key, secrets_payload=None):
    actor.require(tasks.SCOPES[kind])
    with transaction(actor) as conn:
        return store.idempotent(
            conn,
            actor,
            key,
            kind,
            body,
            lambda: tasks.enqueue(conn, actor, kind, body, secrets_payload),
        )


def accepted(response, result):
    response.headers["Location"] = f"/api/v1/jobs/{result['id']}"
    return result


@app.post("/offers/import", status_code=202, response_model=JobView, tags=["offers"])
def import_offer(
    body: ImportOffer,
    response: Response,
    actor: Actor = Depends(authenticate),
    idempotency_key: str = Header(...),
):
    return accepted(
        response, schedule("offer_import", body.model_dump(), actor, idempotency_key)
    )


@app.post("/offers/{ident}/analysis", tags=["offers"])
def offer_analysis(ident: UUID, actor: Actor = Depends(authenticate)):
    actor.require("offers:read")
    with transaction(actor) as conn:
        row = store.get(conn, "offer", ident)
        return dict(keywords=extract_keywords(row["data"]["text"]))


@app.post("/ats/analyses", tags=["ats"], response_model=ATSResult)
def ats(body: CVInput, actor: Actor = Depends(authenticate)):
    actor.require("ats:read")
    return analyse(body.cv)


def charge_sync(actor):
    # Commit admission independently: a failed provider may already have consumed resources.
    # Called after acquiring capacity and only on an idempotency cache miss.
    with transaction(actor) as quota:
        store.counter(
            quota,
            ["heavy", actor.tenant, actor.user],
            setting("V1_HEAVY_PER_DAY"),
            86400,
        )


@app.post("/render", tags=["jct"], response_class=Response, responses=EXPORT_RESPONSE)
def render_facade(
    body: RenderInput,
    actor: Actor = Depends(authenticate),
    idempotency_key: str = Header(...),
):
    actor.require("exports:write")
    with transaction(actor) as conn:

        def execute():
            from app.v1.worker import capacity

            with capacity():
                charge_sync(actor)
                result = render(body.cv, body.format)
            store.audit(conn, actor, "render")
            return dict(
                content=base64.b64encode(result.data).decode(),
                mime=result.mime,
                filename=result.filename,
            )

        result = store.idempotent(
            conn, actor, idempotency_key, "render", body.model_dump(), execute
        )
    data = base64.b64decode(result["content"])
    return Response(
        data,
        media_type=result["mime"],
        headers={
            "Content-Disposition": f'attachment; filename="{result["filename"]}"',
            "X-Content-SHA256": hashlib.sha256(data).hexdigest(),
            "X-PasseFiltre-Version": VERSION,
        },
    )


@app.post("/review", tags=["jct"])
def review_facade(
    body: ReviewInput,
    actor: Actor = Depends(authenticate),
    idempotency_key: str = Header(...),
):
    actor.require("ai:run")
    with transaction(actor) as conn:

        def execute():
            # Shared cross-process admission locks also used by workers.
            from app.v1.worker import capacity

            with capacity():
                charge_sync(actor)
                try:
                    result = business.review(body.model_dump(), actor)
                except APIError:
                    raise
                except Exception:
                    raise APIError(
                        502, "llm_error", "Le fournisseur IA a échoué."
                    ) from None
            store.audit(conn, actor, "review")
            return result

        return store.idempotent(
            conn, actor, idempotency_key, "review", body.model_dump(), execute
        )


@app.post("/enhancements", status_code=202, response_model=JobView, tags=["ai"])
def enhancement(
    body: ReviewInput,
    response: Response,
    actor: Actor = Depends(authenticate),
    idempotency_key: str = Header(...),
):
    return accepted(
        response, schedule("enhance", body.model_dump(), actor, idempotency_key)
    )


@app.post("/exports", status_code=202, response_model=JobView, tags=["exports"])
def export(
    body: RenderInput,
    response: Response,
    actor: Actor = Depends(authenticate),
    idempotency_key: str = Header(...),
):
    return accepted(
        response, schedule("export", body.model_dump(), actor, idempotency_key)
    )


@app.get("/exports/{ident}", tags=["exports"])
def export_info(ident: UUID, actor: Actor = Depends(authenticate)):
    actor.require("exports:read")
    with transaction(actor) as conn:
        row = store.get(conn, "export", ident)
        row["data"] = {k: v for k, v in row["data"].items() if k != "content"}
        return row


@app.get(
    "/exports/{ident}/download",
    tags=["exports"],
    response_class=Response,
    responses=EXPORT_RESPONSE,
)
def download(ident: UUID, actor: Actor = Depends(authenticate)):
    actor.require("exports:read")
    with transaction(actor) as conn:
        d = store.get(conn, "export", ident)["data"]
        if d.get("workflow_id"):
            wf = store.get(conn, "workflow", d["workflow_id"])["data"]
            if (
                not wf.get("approval")
                or wf["digest"] != d["approved_digest"]
                or wf["status"] != "approved"
            ):
                raise APIError(409, "approval_required", "Validation du CV requise.")
        return Response(
            base64.b64decode(d["content"]),
            media_type=d["mime"],
            headers={
                "Content-Disposition": f'attachment; filename="{d["filename"]}"',
                "X-Content-SHA256": d["sha256"],
            },
        )


@app.get("/jobs", tags=["jobs"])
def jobs(
    actor: Actor = Depends(authenticate),
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
):
    actor.require("jobs:read")
    with transaction(actor) as conn:
        rows = store.listing(conn, "job", cursor, limit + 1)
        return dict(
            items=[tasks.view(r) for r in rows[:limit]],
            next_cursor=rows[limit - 1]["id"] if len(rows) > limit else None,
        )


@app.get("/jobs/{ident}", tags=["jobs"], response_model=JobView)
def job(ident: UUID, actor: Actor = Depends(authenticate)):
    actor.require("jobs:read")
    with transaction(actor) as conn:
        return tasks.view(store.get(conn, "job", ident))


@app.get("/jobs/{ident}/result", tags=["jobs"])
def job_result(ident: UUID, actor: Actor = Depends(authenticate)):
    row = job(ident, actor)
    if row["status"] != "succeeded":
        raise APIError(409, "result_unavailable", "Résultat non disponible.")
    return row["result"]


@app.delete("/jobs/{ident}", tags=["jobs"])
def cancel_job(ident: UUID, actor: Actor = Depends(authenticate)):
    actor.require("jobs:write")
    with transaction(actor) as conn:
        return tasks.cancel(conn, actor, ident)


@app.post("/jobs/{ident}/resume", status_code=202, tags=["jobs"])
def resume_job(ident: UUID, actor: Actor = Depends(authenticate)):
    actor.require("jobs:write")
    with transaction(actor) as conn:
        row = store.get(conn, "job", ident, lock=True)
        d = row["data"]
        actor.require(tasks.SCOPES[d["kind"]])
        if d["status"] != "failed" or d["attempt"] >= 3 or d["kind"] == "scrape":
            raise APIError(
                409,
                "not_resumable",
                "Créer une nouvelle tâche avec des entrées valides.",
            )
        d.update(status="queued", error=None, lease=None)
        store.update(conn, "job", ident, d)
        return tasks.view(store.get(conn, "job", ident))


@app.post("/jobs/{ident}/code", tags=["linkedin"])
def code(ident: UUID, body: CodeInput, actor: Actor = Depends(authenticate)):
    actor.require("linkedin:write")
    with transaction(actor) as conn:
        row = store.get(conn, "job", ident, lock=True)
        if row["data"]["status"] != "needs_code":
            raise APIError(409, "no_code_expected", "Aucun code attendu.")
        value = body.code.get_secret_value()
        if not 1 <= len(value) <= 32:
            raise APIError(422, "invalid_input", "Code invalide.")
        row["data"]["code"] = seal(value, str(ident))
        store.update(conn, "job", ident, row["data"])
    return dict(ok=True)


@app.post(
    "/linkedin/extractions", status_code=202, response_model=JobView, tags=["linkedin"]
)
def scrape(
    body: ScrapeInput,
    response: Response,
    actor: Actor = Depends(authenticate),
    idempotency_key: str = Header(...),
):
    actor.require("linkedin:write")
    from app.scraper.linkedin import normalize_profile_url
    from app.security import PublicError

    try:
        url = normalize_profile_url(body.profile_url)
    except PublicError:
        raise APIError(422, "invalid_input", "URL LinkedIn invalide.") from None
    secret_payload = None
    if body.session_id:
        with transaction(actor) as conn:
            store.get(conn, "linkedin_session", body.session_id)
    elif (
        body.email
        and body.password
        and body.email.get_secret_value().strip()
        and body.password.get_secret_value()
    ):
        secret_payload = dict(
            email=body.email.get_secret_value(),
            password=body.password.get_secret_value(),
        )
    else:
        raise APIError(422, "invalid_input", "Session ou identifiants LinkedIn requis.")
    payload = dict(
        profile_url=url, session_id=str(body.session_id) if body.session_id else None
    )
    # Fingerprint includes credentials without persisting their plaintext.
    with transaction(actor) as conn:
        result = store.idempotent(
            conn,
            actor,
            idempotency_key,
            "scrape",
            dict(payload=payload, credentials=secret_fingerprint(secret_payload)),
            lambda: tasks.enqueue(conn, actor, "scrape", payload, secret_payload),
        )
    return accepted(response, result)


@app.get("/linkedin/sessions", tags=["linkedin"])
def sessions(actor: Actor = Depends(authenticate)):
    actor.require("linkedin:read")
    with transaction(actor) as conn:
        return [
            dict(id=r["id"], expires_at=r["expires_at"])
            for r in store.listing(conn, "linkedin_session")
        ]


@app.get("/linkedin/sessions/{ident}", tags=["linkedin"])
def session_info(ident: UUID, actor: Actor = Depends(authenticate)):
    actor.require("linkedin:read")
    with transaction(actor) as conn:
        r = store.get(conn, "linkedin_session", ident)
        return dict(id=r["id"], expires_at=r["expires_at"])


@app.delete("/linkedin/sessions/{ident}", status_code=204, tags=["linkedin"])
def session_delete(ident: UUID, actor: Actor = Depends(authenticate)):
    actor.require("linkedin:write")
    with transaction(actor) as conn:
        # Same advisory lock as extraction: never destroy/recreate a session in use.
        if not store.sql(
            conn,
            "SELECT pg_try_advisory_xact_lock(:lock)",
            lock=int(digest(str(ident))[:15], 16),
        ).scalar():
            raise APIError(409, "session_busy", "Session en cours d’utilisation.")
        store.delete(conn, "linkedin_session", ident)
        store.audit(conn, actor, "linkedin.forgotten", str(ident))
    return Response(status_code=204)


@app.post("/conversations", status_code=201, tags=["conversations"])
def conversation_create(
    body: ConversationInput,
    actor: Actor = Depends(authenticate),
    idempotency_key: str = Header(...),
):
    actor.require("conversations:write")
    with transaction(actor) as conn:
        return store.idempotent(
            conn,
            actor,
            idempotency_key,
            "conversation",
            body.model_dump(),
            lambda: store.create(
                conn,
                actor,
                "conversation",
                dict(cv=body.cv.model_dump(), history=[], active_job=None),
            ),
        )


@app.get("/conversations/{ident}", tags=["conversations"])
def conversation(ident: UUID, actor: Actor = Depends(authenticate)):
    actor.require("conversations:read")
    with transaction(actor) as conn:
        return store.get(conn, "conversation", ident)


@app.post("/conversations/{ident}/messages", status_code=202, tags=["conversations"])
def message(
    ident: UUID,
    body: MessageInput,
    response: Response,
    actor: Actor = Depends(authenticate),
    idempotency_key: str = Header(...),
):
    actor.require("conversations:write")
    actor.require("ai:run")
    with transaction(actor) as conn:

        def execute():
            row = store.get(conn, "conversation", ident, lock=True)
            if row["data"]["active_job"]:
                try:
                    previous = store.get(conn, "job", row["data"]["active_job"])
                except APIError as exc:
                    if exc.status != 404:
                        raise
                    previous = None  # The conversation outlives its expiring jobs.
                if previous and previous["data"]["status"] not in tasks.TERMINAL:
                    raise APIError(
                        409, "conversation_busy", "Un message est déjà en cours."
                    )
            result = tasks.enqueue(
                conn,
                actor,
                "agent",
                dict(
                    conversation_id=str(ident),
                    **body.model_dump(),
                    cv=row["data"]["cv"],
                    history=row["data"]["history"][-20:],
                ),
            )
            row["data"]["active_job"] = result["id"]
            store.update(conn, "conversation", ident, row["data"])
            return result

        result = store.idempotent(
            conn,
            actor,
            idempotency_key,
            "message:" + str(ident),
            body.model_dump(),
            execute,
        )
    return accepted(response, result)


@app.delete("/conversations/{ident}", status_code=204, tags=["conversations"])
def conversation_delete(ident: UUID, actor: Actor = Depends(authenticate)):
    actor.require("conversations:write")
    with transaction(actor) as conn:
        row = store.get(conn, "conversation", ident, lock=True)
        if row["data"]["active_job"]:
            try:
                tasks.cancel(conn, actor, row["data"]["active_job"])
            except APIError as exc:
                if exc.status != 404:
                    raise
        store.delete(conn, "conversation", ident)
    return Response(status_code=204)


@app.post("/workflows", status_code=202, response_model=JobView, tags=["workflows"])
def workflow_create(
    body: WorkflowInput,
    response: Response,
    actor: Actor = Depends(authenticate),
    idempotency_key: str = Header(...),
):
    if body.use_ai:
        actor.require("ai:run")
    return accepted(
        response, schedule("workflow", body.model_dump(), actor, idempotency_key)
    )


@app.get("/workflows/{ident}", tags=["workflows"], response_model=ResourceView)
def workflow(ident: UUID, response: Response, actor: Actor = Depends(authenticate)):
    actor.require("workflows:read")
    with transaction(actor) as conn:
        return tag(response, store.get(conn, "workflow", ident))


@app.put("/workflows/{ident}/draft", tags=["workflows"])
def workflow_edit(
    ident: UUID,
    body: CVInput,
    response: Response,
    actor: Actor = Depends(authenticate),
    if_match: str | None = Header(None),
):
    actor.require("workflows:write")
    with transaction(actor) as conn:
        row = store.get(conn, "workflow", ident, lock=True)
        d = row["data"]
        if d["status"] in ("cancelled", "rejected"):
            raise APIError(409, "workflow_closed", "Workflow terminé.")
        d.update(
            draft=body.cv.model_dump(),
            digest=digest(body.cv.model_dump()),
            approval=None,
            status="awaiting_review",
            after_ats=analyse(body.cv),
        )
        d["changes"].append(
            dict(path="human_edit", before=row["version"], after=row["version"] + 1)
        )
        return tag(
            response, store.update(conn, "workflow", ident, d, expected(if_match))
        )


@app.post("/workflows/{ident}/approve", tags=["workflows"])
def approve(
    ident: UUID,
    body: Approval,
    actor: Actor = Depends(authenticate),
    idempotency_key: str = Header(...),
):
    actor.require("workflows:approve")
    actor.require("exports:write")
    with transaction(actor) as conn:

        def execute():
            row = store.get(conn, "workflow", ident, lock=True)
            d = row["data"]
            if (
                d["status"] != "awaiting_review"
                or row["version"] != body.version
                or digest(d["draft"]) != body.digest
            ):
                raise APIError(
                    409,
                    "approval_conflict",
                    "Le brouillon doit être relu avant validation.",
                )
            d.update(
                status="approved",
                approval=dict(
                    version=body.version, digest=body.digest, actor=actor.user
                ),
            )
            store.update(conn, "workflow", ident, d)
            exports = [
                tasks.enqueue(
                    conn,
                    actor,
                    "export",
                    dict(
                        cv=d["draft"],
                        format=fmt,
                        workflow_id=str(ident),
                        approved_digest=body.digest,
                    ),
                )
                for fmt in ("pdf", "docx")
            ]
            store.audit(conn, actor, "workflow.approved", str(ident))
            return dict(workflow_id=str(ident), status="approved", jobs=exports)

        return store.idempotent(
            conn,
            actor,
            idempotency_key,
            "approve:" + str(ident),
            body.model_dump(),
            execute,
        )


def close_workflow(ident, actor, status):
    actor.require("workflows:write")
    with transaction(actor) as conn:
        row = store.get(conn, "workflow", ident, lock=True)
        row["data"].update(status=status, approval=None)
        store.audit(conn, actor, "workflow." + status, str(ident))
        return store.update(conn, "workflow", ident, row["data"])


@app.post("/workflows/{ident}/reject", tags=["workflows"])
def reject(ident: UUID, actor: Actor = Depends(authenticate)):
    return close_workflow(ident, actor, "rejected")


@app.delete("/workflows/{ident}", tags=["workflows"])
def cancel_workflow(ident: UUID, actor: Actor = Depends(authenticate)):
    return close_workflow(ident, actor, "cancelled")
