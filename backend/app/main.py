import asyncio
import logging
import os
import re
import unicodedata
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect

from app import jobs
from app.export.content import build
from app.export.docx_export import render_docx
from app.export.pdf_export import render_pdf
from app.llm.agents import AGENTS, LLMConfig, enhance, explain_error, server_llm, test_connection
from app.llm.supervisor import run_agent
from app.llm.tools import fetch_page_text
from app.models import CV
from app.scraper import captcha
from app.scraper.linkedin import forget_session, normalize_profile_url, scrape_profile
from app.security import (
    JOB_KEY_HEADER, TOKEN_HEADER, PublicError, SecurityMiddleware, allowed_hosts, api_token, assert_safe_config,
    audit, cors_origins, is_local_client, pseudonym,
)

log = logging.getLogger(__name__)

# Fails fast (the server does not start) if the API is reachable from the network without a strong token.
assert_safe_config()

# Interactive API docs only when explicitly enabled (the launcher does it in dev mode).
_docs = os.getenv("API_DOCS") == "1"
app = FastAPI(title="PasseFiltre API", docs_url="/docs" if _docs else None, redoc_url=None,
              openapi_url="/openapi.json" if _docs else None)
# Last added = outermost: CORS first (so even 401/403 answers carry CORS headers), then Host check, then security.
app.add_middleware(SecurityMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", TOKEN_HEADER, JOB_KEY_HEADER],
    expose_headers=["Content-Disposition"],
)


class ScrapeRequest(BaseModel):
    profile_url: str
    email: str
    password: str
    show_browser: bool = False


class Credentials(BaseModel):
    email: str
    password: str


class CodeRequest(BaseModel):
    code: str


class AgentRequest(BaseModel):
    llm: LLMConfig
    cv: CV
    instruction: str
    history: list[dict[str, str]] = []


class OfferRequest(BaseModel):
    url: str


class EnhanceRequest(BaseModel):
    llm: LLMConfig
    cv: CV
    job_description: str = ""
    agents: list[str] = list(AGENTS)


def _start(target) -> dict:
    try:
        job = jobs.start(target)
    except jobs.Busy as e:
        raise HTTPException(429, str(e))
    return {**job.to_dict(), "key": job.key}  # the owner key is only ever sent here, to the job's creator


def _owned_job(job_id: str, request: Request) -> jobs.Job:
    """The job, only for the client that started it (same answer for unknown and not-yours: no oracle)."""
    job = jobs.get(job_id)
    if not job or not job.owned_by(request.headers.get(JOB_KEY_HEADER, "")):
        raise HTTPException(404, "Tâche inconnue ou expirée.")
    return job


def _llm_source(cfg: LLMConfig) -> str:
    """For the audit log: which LLM is used, never the key."""
    if cfg.api_key.strip():
        return f"ui:{urlparse(cfg.base_url).hostname or 'openai'}"
    return "server"


@app.get("/api/health")
def health():
    return {"ok": True, "agents": list(AGENTS)}


@app.get("/api/config")
def config():
    """Server-side defaults the UI adapts to (never exposes secrets)."""
    return {"llm": server_llm(), "docker": os.path.exists("/.dockerenv"), "auth_required": bool(api_token()),
            "remote_captcha": captcha.available()}


@app.post("/api/scrape")
def start_scrape(req: ScrapeRequest, request: Request):
    try:
        url = normalize_profile_url(req.profile_url)
    except PublicError as e:
        raise HTTPException(400, str(e))
    if not req.email.strip() or not req.password:
        raise HTTPException(400, "Identifiants LinkedIn requis.")
    # A visible browser opens on the screen of the machine running the API: only its own user may ask for it.
    if req.show_browser and not is_local_client(request):
        raise HTTPException(400, "« Afficher le navigateur » n'est possible que sur la machine qui héberge PasseFiltre.")
    audit(request, "scrape", profile=url.rstrip("/").rsplit("/", 1)[-1], account=pseudonym(req.email),
          show_browser=req.show_browser)
    debug = os.getenv("DEBUG_SCRAPE") == "1"
    remote = captcha.available()
    # Credentials only live in this closure for the duration of the job: never stored nor logged.
    return _start(lambda j: scrape_profile(
        url, req.email, req.password, j, headless=not req.show_browser, debug=debug,
        remote_captcha=remote).model_dump())


@app.post("/api/linkedin/logout")
def linkedin_logout(req: Credentials, request: Request):
    """Forget the saved LinkedIn session of this account. Requires its credentials: nobody else can wipe it."""
    removed = forget_session(req.email, req.password)
    audit(request, "linkedin_logout", account=pseudonym(req.email), removed=removed)
    return {"ok": True, "removed": removed}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, request: Request):
    return _owned_job(job_id, request).to_dict()


@app.delete("/api/jobs/{job_id}")
def job_cancel(job_id: str, request: Request):
    """Stop a job: pending code / CAPTCHA abandoned, browser and virtual display closed by the job itself."""
    job = _owned_job(job_id, request)
    job.cancel()
    audit(request, "job_cancel", job=job.id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/code")
def job_code(job_id: str, req: CodeRequest, request: Request):
    job = _owned_job(job_id, request)
    if job.status != "needs_code":
        raise HTTPException(409, "Aucun code attendu pour cette tâche.")
    job.submit_code(req.code)
    return {"ok": True}


# --------------------------------------------------------------------------- CAPTCHA viewer

TICKET_PROTOCOL = "pf-ticket."  # the ticket travels as a WebSocket sub-protocol: never in a URL (logs)


@app.post("/api/jobs/{job_id}/captcha/ticket")
def captcha_ticket(job_id: str, request: Request):
    """Single-use, short-lived ticket to open the CAPTCHA viewer of this job (token + job key checked here)."""
    job = _owned_job(job_id, request)
    if job.status != "needs_captcha":
        raise HTTPException(409, "Aucun CAPTCHA à résoudre pour cette tâche.")
    audit(request, "captcha_ticket", job=job.id)
    return {"ticket": job.issue_ticket(), "protocol": TICKET_PROTOCOL, "expires_in": jobs.TICKET_TTL}


@app.websocket("/api/jobs/{job_id}/captcha/vnc")
async def captcha_vnc(ws: WebSocket, job_id: str):
    """WebSocket <-> VNC bridge (the websockify role) to the job's private virtual display.

    HTTP middlewares do not see WebSockets: the checks are done here. Host is still checked by
    TrustedHostMiddleware. Access needs a ticket from captcha_ticket (so the token and the job key),
    sent from one of our UI origins (no cross-site WebSocket hijacking)."""
    offered = ws.scope.get("subprotocols") or []
    ticket = next((p[len(TICKET_PROTOCOL):] for p in offered if p.startswith(TICKET_PROTOCOL)), "")
    job = jobs.get(job_id)
    origin_ok = ws.headers.get("origin") in cors_origins()
    if not origin_ok or not job or not job.redeem_ticket(ticket):
        audit(ws, "captcha_vnc_refused", job=job_id[:32], origin_ok=origin_ok)
        await ws.close(code=1008)
        return
    display = job.display
    sock = display.vnc_socket if display else None
    try:
        if not sock:
            raise OSError("no VNC server")
        reader, writer = await asyncio.open_unix_connection(sock)
    except (OSError, AttributeError, NotImplementedError):
        await ws.close(code=1011)
        return
    await ws.accept(subprotocol="binary" if "binary" in offered else None)
    audit(ws, "captcha_vnc_open", job=job.id)

    async def to_vnc() -> None:
        while True:
            data = await ws.receive_bytes()
            writer.write(data)
            await writer.drain()

    async def to_browser() -> None:
        while data := await reader.read(65536):
            await ws.send_bytes(data)

    async def until_closed() -> None:  # solved, expired or cancelled: cut the viewer even if VNC lingers
        while job.status == "needs_captcha" and job.display is display:
            await asyncio.sleep(1)

    tasks = [asyncio.create_task(t()) for t in (to_vnc, to_browser, until_closed)]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        writer.close()
        try:
            await ws.close()
        except (RuntimeError, WebSocketDisconnect):
            pass
        audit(ws, "captcha_vnc_close", job=job.id)


@app.post("/api/agent")
def start_agent(req: AgentRequest, request: Request):
    if not req.instruction.strip():
        raise HTTPException(400, "Décrivez ce que l'agent doit faire.")

    def run(job):
        try:
            return run_agent(req.llm, req.cv, req.instruction, req.history, job)
        except Exception as e:
            log.exception("Agent run failed")
            raise PublicError(explain_error(e)) from e

    started = _start(run)
    audit(request, "agent", job=started["id"], llm=_llm_source(req.llm), instruction_chars=len(req.instruction))
    return started


@app.post("/api/offer")
def import_offer(req: OfferRequest, request: Request):
    audit(request, "offer_import", host=urlparse(req.url).hostname)
    try:
        return {"text": fetch_page_text(req.url)}
    except PublicError as e:
        raise HTTPException(400, f"Impossible de lire l'offre : {e}")
    except Exception:
        log.exception("Offer import failed for %s", req.url)
        raise HTTPException(400, "Impossible de lire l'offre (page inaccessible). Collez plutôt son texte.")


@app.post("/api/llm/test")
def llm_test(cfg: LLMConfig, request: Request):
    audit(request, "llm_test", llm=_llm_source(cfg))
    try:
        return {"ok": True, "reply": test_connection(cfg)}
    except Exception as e:
        log.warning("LLM test failed: %s", e)
        raise HTTPException(400, f"Connexion au LLM impossible : {explain_error(e)}")


@app.post("/api/enhance")
def llm_enhance(req: EnhanceRequest, request: Request):
    audit(request, "enhance", llm=_llm_source(req.llm), agents=",".join(req.agents))
    try:
        return enhance(req.llm, req.cv, req.job_description, req.agents)
    except Exception as e:
        log.exception("Enhance failed")
        raise HTTPException(502, f"Erreur LLM : {explain_error(e)}")


def download_name(full_name: str, fmt: str) -> str:
    """ASCII-only, header-safe file name: « Jérôme "J" O'Neil » -> CV-Jerome-J-ONeil.pdf"""
    ascii_name = unicodedata.normalize("NFKD", full_name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_name.replace("'", "")).strip("-")[:60] or "cv"
    return f"CV-{slug}.{fmt}"


@app.post("/api/export/{fmt}")
def export(fmt: str, cv: CV):
    layout = build(cv)
    if fmt == "pdf":
        data, mime = render_pdf(layout), "application/pdf"
    elif fmt == "docx":
        data, mime = render_docx(layout), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise HTTPException(404, "Format inconnu (pdf ou docx).")
    return Response(data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{download_name(layout.name, fmt)}"'})
