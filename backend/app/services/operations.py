"""Reusable operations; all engines live in their existing modules."""
from app.llm import agents, supervisor, tools
from app.scraper import linkedin
from app.security import PublicError


def extract(profile_url, email, password, hooks, **options):
    if not email.strip() or not password:
        raise PublicError("Identifiants LinkedIn requis.")
    return linkedin.scrape_profile(linkedin.normalize_profile_url(profile_url), email, password, hooks, **options)


def forget(email, password):
    return linkedin.forget_session(email, password)


def offer(url):
    return tools.fetch_page_text(url)


def enhance(llm, cv, job_description, selected, callbacks=None):
    return agents.enhance(llm, cv, job_description, selected, callbacks=callbacks)


def converse(llm, cv, instruction, history, hooks):
    if not instruction.strip():
        raise PublicError("Décrivez ce que l'agent doit faire.")
    return supervisor.run_agent(llm, cv, instruction, history, hooks)


def test_llm(llm):
    return agents.test_connection(llm)
