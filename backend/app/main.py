import os
import unicodedata

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from app import jobs
from app.export.content import build
from app.export.docx_export import render_docx
from app.export.pdf_export import render_pdf
from app.llm.agents import AGENTS, LLMConfig, enhance, explain_error, test_connection
from app.llm.supervisor import run_agent
from app.llm.tools import fetch_page_text
from app.models import CV
from app.scraper.linkedin import normalize_profile_url, scrape_profile

app = FastAPI(title="CV ATS Generator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


class ScrapeRequest(BaseModel):
    profile_url: str
    email: str
    password: str
    show_browser: bool = False


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


@app.get("/api/health")
def health():
    return {"ok": True, "agents": list(AGENTS)}


@app.post("/api/scrape")
def start_scrape(req: ScrapeRequest):
    try:
        url = normalize_profile_url(req.profile_url)
    except Exception as e:
        raise HTTPException(400, str(e))
    if not req.email.strip() or not req.password:
        raise HTTPException(400, "Identifiants LinkedIn requis.")
    debug = os.getenv("DEBUG_SCRAPE") == "1"
    # Credentials only live in this closure for the duration of the job: never stored nor logged.
    job = jobs.start(lambda j: scrape_profile(
        url, req.email, req.password, j, headless=not req.show_browser, debug=debug).model_dump())
    return job.to_dict()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Tâche inconnue ou expirée.")
    return job.to_dict()


@app.post("/api/jobs/{job_id}/code")
def job_code(job_id: str, req: CodeRequest):
    job = jobs.get(job_id)
    if not job or job.status != "needs_code":
        raise HTTPException(409, "Aucun code attendu pour cette tâche.")
    job.submit_code(req.code)
    return {"ok": True}


@app.post("/api/agent")
def start_agent(req: AgentRequest):
    if not req.instruction.strip():
        raise HTTPException(400, "Décrivez ce que l'agent doit faire.")

    def run(job):
        try:
            return run_agent(req.llm, req.cv, req.instruction, req.history, job)
        except Exception as e:
            raise RuntimeError(explain_error(e)) from e

    return jobs.start(run).to_dict()


@app.post("/api/offer")
def import_offer(req: OfferRequest):
    try:
        return {"text": fetch_page_text(req.url)}
    except Exception as e:
        raise HTTPException(400, f"Impossible de lire l'offre : {e}")


@app.post("/api/llm/test")
def llm_test(cfg: LLMConfig):
    try:
        return {"ok": True, "reply": test_connection(cfg)}
    except Exception as e:
        raise HTTPException(400, f"Connexion au LLM impossible : {explain_error(e)}")


@app.post("/api/enhance")
def llm_enhance(req: EnhanceRequest):
    try:
        return enhance(req.llm, req.cv, req.job_description, req.agents)
    except Exception as e:
        raise HTTPException(502, f"Erreur LLM : {explain_error(e)}")


@app.post("/api/export/{fmt}")
def export(fmt: str, cv: CV):
    layout = build(cv)
    ascii_name = unicodedata.normalize("NFKD", layout.name).encode("ascii", "ignore").decode()
    slug = "-".join(ascii_name.split()) or "cv"
    if fmt == "pdf":
        data, mime = render_pdf(layout), "application/pdf"
    elif fmt == "docx":
        data, mime = render_docx(layout), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        raise HTTPException(404, "Format inconnu (pdf ou docx).")
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="CV-{slug}.{fmt}"'})
