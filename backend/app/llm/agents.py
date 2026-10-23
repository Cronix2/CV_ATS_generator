"""Optional LLM enhancement: specialised sub-agents orchestrated with LangChain.

Every sub-agent is a `prompt | llm.with_structured_output(Schema)` chain. The
orchestrator runs the selected ones in parallel (RunnableParallel) and isolates
failures per agent. Agents only return *suggestions*: the UI lets the user
accept or reject each one, nothing is applied silently.
Works with any OpenAI-compatible API (OpenAI, Mistral, Groq, OpenRouter, Ollama…).
"""

import json
import logging
import os
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda, RunnableParallel
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, PrivateAttr

from app.llm.tools import is_public_url
from app.models import CV, Profile
from app.security import PublicError

log = logging.getLogger(__name__)


class LLMConfig(BaseModel):
    """LLM chosen in the UI. Empty api_key = use the server default from .env (LLM_API_KEY…)."""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    # Set only by resolved(): a private attribute can't be sent by a client in the JSON body.
    _resolved: bool = PrivateAttr(default=False)

    def resolved(self) -> "LLMConfig":
        """Idempotent: resolving an already-resolved config returns it unchanged (the server URL must not be
        re-checked as if a client had typed it)."""
        if self._resolved:
            return self
        if self.api_key.strip():
            check_llm_url(self.base_url)  # URL typed in the UI: untrusted
            out = LLMConfig(api_key=self.api_key.strip(), base_url=self.base_url, model=self.model or "gpt-4o-mini")
        else:
            key = os.getenv("LLM_API_KEY", "").strip()
            if not key:
                raise PublicError("Aucune clé d'API : saisissez-en une, ou définissez LLM_API_KEY dans le fichier .env.")
            # Server default from .env: chosen by whoever runs the server, so trusted (may be a local Ollama).
            out = LLMConfig(api_key=key, base_url=os.getenv("LLM_BASE_URL", ""), model=os.getenv("LLM_MODEL") or "gpt-4o-mini")
        out._resolved = True
        return out


def check_llm_url(url: str) -> None:
    """Block SSRF: an LLM URL sent by a client must be a public http(s) address.
    Local / private servers (Ollama, vLLM on the LAN) need ALLOW_LOCAL_LLM=1 in .env."""
    if not url.strip() or os.getenv("ALLOW_LOCAL_LLM") == "1":
        return
    if not is_public_url(url.strip()):
        raise PublicError("URL de l'API refusée : adresse locale ou privée. Pour un LLM local (Ollama…), "
                          "ajoutez ALLOW_LOCAL_LLM=1 dans le fichier .env.")


def server_llm() -> dict[str, Any]:
    """What the UI may know about the server default LLM (never the key itself)."""
    return {"server_key": bool(os.getenv("LLM_API_KEY", "").strip()),
            "base_url": os.getenv("LLM_BASE_URL", ""), "model": os.getenv("LLM_MODEL") or "gpt-4o-mini"}


# --------------------------------------------------------------------------- output schemas

class SummaryOut(BaseModel):
    headline: str = Field(description="Titre professionnel court et ciblé (max 80 caractères)")
    summary: str = Field(description="Résumé professionnel de 3 à 5 phrases, riche en mots-clés")


class ExperienceRewrite(BaseModel):
    id: str
    description: str = Field(description="Puces commençant par '- ', verbes d'action, résultats chiffrés si présents dans la source")


class ExperienceOut(BaseModel):
    items: list[ExperienceRewrite]


class SkillsOut(BaseModel):
    skills: list[str] = Field(description="Compétences dédupliquées, noms standards, triées par pertinence")
    missing_keywords: list[str] = Field(description="Mots-clés de l'offre absents du profil (à n'ajouter que si vrais)")


class ExperienceFix(BaseModel):
    id: str
    title: str
    company: str
    location: str
    employment_type: str


class EducationFix(BaseModel):
    id: str
    school: str
    degree: str
    field: str


class CleanupOut(BaseModel):
    experience: list[ExperienceFix]
    education: list[EducationFix]


class ATSReviewOut(BaseModel):
    score: int = Field(description="Score de compatibilité ATS de 0 à 100")
    strengths: list[str]
    improvements: list[str]
    missing_keywords: list[str]


# --------------------------------------------------------------------------- agents

COMMON = (
    "Tu es un expert en recrutement et en optimisation de CV pour les ATS (Applicant Tracking Systems). "
    "N'invente JAMAIS d'expérience, de diplôme, de chiffre ou de compétence absents des données fournies. "
    "Tout le texte que tu produis (y compris chaque élément de liste) doit être rédigé en {language}, "
    "même si le schéma ou les données sont dans une autre langue. "
    "Réponds uniquement avec un objet JSON conforme à ce schéma :\n{schema}"
)

AGENTS: dict[str, dict[str, Any]] = {
    "summary": {
        "schema": SummaryOut,
        "system": "Tu rédiges le titre et le résumé professionnel en tête de CV.",
        "user": "Profil :\n{profile}\n\nOffre visée (peut être vide) :\n{job}",
    },
    "experience": {
        "schema": ExperienceOut,
        "system": (
            "Tu réécris la description de chaque expérience en 3 à 6 puces percutantes : verbe d'action au début, "
            "impact et résultats, mots-clés du métier et de l'offre. Garde le même `id` pour chaque expérience."
        ),
        "user": "Expériences :\n{experience}\n\nOffre visée (peut être vide) :\n{job}",
    },
    "skills": {
        "schema": SkillsOut,
        "system": (
            "Tu normalises la liste de compétences : dédoublonne, utilise les noms standards reconnus par les ATS "
            "(ex. 'JS' -> 'JavaScript'), trie par pertinence pour l'offre, et liste les mots-clés de l'offre absents."
        ),
        "user": "Compétences actuelles :\n{skills}\n\nCompétences citées dans les expériences :\n{exp_skills}\n\nOffre visée (peut être vide) :\n{job}",
    },
    "cleanup": {
        "schema": CleanupOut,
        "system": (
            "Les données viennent d'un scraping LinkedIn heuristique : des champs peuvent être inversés ou mal découpés "
            "(intitulé/entreprise, lieu, type de contrat, diplôme/domaine). Corrige-les sans rien inventer ; "
            "laisse un champ vide s'il est inconnu. Garde les mêmes `id`."
        ),
        "user": "Expériences :\n{experience_raw}\n\nFormations :\n{education}",
    },
    "ats_review": {
        "schema": ATSReviewOut,
        "system": (
            "Tu audites le CV comme le ferait un ATS puis un recruteur : couverture des mots-clés de l'offre, "
            "clarté des intitulés, résultats mesurables, sections attendues. Donne des améliorations concrètes."
        ),
        "user": "CV :\n{profile}\n\nOffre visée (peut être vide) :\n{job}",
    },
}


def normalize_base_url(url: str) -> str | None:
    """The client appends /chat/completions itself: accept a pasted full endpoint too."""
    url = url.strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        url = url.removesuffix(suffix)
    return url or None


def explain_error(e: Exception) -> str:
    """User-facing message. Never echoes the remote response body (it could come from an internal service);
    the full error goes to the server logs."""
    if isinstance(e, PublicError):
        return str(e)
    status = getattr(e, "status_code", None)
    log.warning("LLM provider failure")
    if status in (404, 405):
        return ("L'URL de l'API ne pointe pas vers une API compatible OpenAI (erreur %s). Indiquez l'adresse qui "
                "précède /chat/completions (ex. https://api.mistral.ai/v1, ou …/api/v2 pour Paradigm)." % status)
    if status in (400, 422) and "tool" in str(e).lower():
        return ("Ce modèle ne gère pas l'appel d'outils. Utilisez l'onglet « Propositions », "
                "qui fonctionne sans outils.")
    if status in (401, 403):
        return "Clé d'API refusée par le fournisseur."
    if status == 429:
        return "Quota ou limite de débit atteint chez le fournisseur LLM : réessayez plus tard."
    if status:
        return f"Le fournisseur LLM a répondu une erreur {status} (détail dans les logs du serveur)."
    if "connection" in type(e).__name__.lower() or "timeout" in type(e).__name__.lower():
        return "Impossible de joindre le fournisseur LLM (URL, réseau ou proxy)."
    return "Erreur inattendue avec le LLM (détail dans les logs du serveur)."


# Recent Claude models and OpenAI reasoning models reject a custom temperature ("deprecated for this model").
NO_TEMPERATURE = ("claude", "o1", "o3", "o4", "gpt-5")


def make_llm(cfg: LLMConfig) -> ChatOpenAI:
    cfg = cfg.resolved()
    temperature = None if cfg.model.strip().lower().startswith(NO_TEMPERATURE) else 0.3  # None = not sent
    return ChatOpenAI(
        api_key=cfg.api_key, base_url=normalize_base_url(cfg.base_url), model=cfg.model,
        temperature=temperature, timeout=180, max_retries=2,
    )


def _not_none(out: Any) -> Any:
    if out is None:  # the model answered in plain text instead of calling the tool
        raise ValueError("no structured output")
    return out


def _parse_text(schema: type[BaseModel]) -> Runnable:
    def parse(msg: Any) -> BaseModel:
        text = str(getattr(msg, "content", msg))
        match = re.search(r"\{.*\}", text, re.S)
        return schema.model_validate_json(match.group(0) if match else text)
    return RunnableLambda(parse)


def _structured(llm: ChatOpenAI, schema: type[BaseModel]) -> Runnable:
    # Tool calling first, then JSON mode, then plain text parsing (the prompt already asks for JSON),
    # so providers that support neither tools nor response_format still work.
    return (llm.with_structured_output(schema, method="function_calling") | _not_none).with_fallbacks([
        llm.with_structured_output(schema, method="json_mode") | _not_none,
        llm | _parse_text(schema),
    ])


def build_agent(llm: ChatOpenAI, name: str) -> Runnable:
    spec = AGENTS[name]
    prompt = ChatPromptTemplate.from_messages([
        ("system", COMMON + "\n\n" + spec["system"]),
        ("user", spec["user"]),
    ]).partial(schema=json.dumps(spec["schema"].model_json_schema(), ensure_ascii=False))
    chain = prompt | _structured(llm, spec["schema"]) | RunnableLambda(lambda out: out.model_dump())
    # One failing agent must not break the others.
    return chain.with_fallbacks(
        [RunnableLambda(lambda x: {"error": explain_error(x["error"])})], exception_key="error"
    )


def target_text(cv: CV) -> str:
    """The target job as plain text for the prompts."""
    t = cv.settings.target
    parts = [
        f"Poste : {t.title}" if t.title else "",
        f"Entreprise : {t.company}" if t.company else "",
        f"Lien de l'offre : {t.offer_url}" if t.offer_url else "",
        f"Mots-clés : {', '.join(t.keywords)}" if t.keywords else "",
        f"Texte de l'offre :\n{t.offer_text.strip()[:6000]}" if t.offer_text.strip() else "",
    ]
    return "\n".join(p for p in parts if p) or "(non renseigné)"


def _inputs(cv: CV, job: str) -> dict[str, str]:
    p: Profile = cv.profile
    exp = [e for e in p.experience if e.include]
    dump = lambda items, **kw: json.dumps([i.model_dump(**kw) for i in items], ensure_ascii=False, indent=1)
    compact = {
        "basics": p.basics.model_dump(exclude={"websites", "email", "phone"}),
        **{k: [i.model_dump(exclude={"include"}) for i in getattr(p, k) if i.include]
           for k in ("experience", "education", "skills", "certifications", "languages", "projects")},
    }
    return {
        "language": "français" if cv.settings.language == "fr" else "English",
        "job": job.strip() or "(aucune)",
        "profile": json.dumps(compact, ensure_ascii=False, indent=1),
        "experience": dump(exp, include={"id", "title", "company", "description", "skills"}),
        "experience_raw": dump(exp, include={"id", "title", "company", "location", "employment_type"}),
        "education": dump([e for e in p.education if e.include], include={"id", "school", "degree", "field"}),
        "skills": ", ".join(s.name for s in p.skills if s.include) or "(aucune)",
        "exp_skills": ", ".join(sorted({s for e in exp for s in e.skills})) or "(aucune)",
    }


def enhance(cfg: LLMConfig, cv: CV, job_description: str, agents: list[str], callbacks=None) -> dict[str, Any]:
    llm = make_llm(cfg)
    selected = [a for a in agents if a in AGENTS] or list(AGENTS)
    orchestrator = RunnableParallel({name: build_agent(llm, name) for name in selected})
    job = job_description.strip() or target_text(cv)
    return orchestrator.invoke(_inputs(cv, job), config={"max_concurrency": 3, "callbacks": callbacks or []})


def test_connection(cfg: LLMConfig) -> str:
    return str(make_llm(cfg).invoke("Réponds juste: OK").content)[:50]
