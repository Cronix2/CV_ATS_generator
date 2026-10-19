"""Regression tests for the security fixes (OWASP audit)."""

import socket
import threading

import pytest
from fastapi.testclient import TestClient

from app import jobs
from app.llm import tools
from app.llm.agents import LLMConfig, explain_error
from app.llm.tools import WebAccess, Workspace, is_public_url
from app.main import app, download_name
from app.models import CV
from app.scraper import linkedin
from app.security import PublicError


def fake_dns(monkeypatch, ip: str):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(family, 1, 6, "", (ip, 0))])


@pytest.fixture
def client():
    return TestClient(app, base_url="http://localhost")


# --- n°2 : session LinkedIn liée au mot de passe -------------------------------------------------

def test_session_dir_is_bound_to_password(monkeypatch, tmp_path):
    monkeypatch.setattr(linkedin, "SESSIONS_DIR", tmp_path)
    good = linkedin._session_dir("Jane@Example.com", "secret-1")
    assert linkedin._session_dir("jane@example.com ", "secret-1") == good  # same account, same session
    assert linkedin._session_dir("jane@example.com", "wrong") != good       # an email alone is not enough
    assert "jane" not in good.lower()                                        # no email in the path


# --- n°3 : SSRF via l'URL du LLM, pas d'écho du corps distant --------------------------------------

@pytest.mark.parametrize("ip", ["169.254.169.254", "127.0.0.1", "10.1.2.3", "100.64.0.1", "::ffff:10.0.0.1"])
def test_llm_url_to_private_network_is_refused(monkeypatch, ip):
    fake_dns(monkeypatch, ip)
    monkeypatch.delenv("ALLOW_LOCAL_LLM", raising=False)
    with pytest.raises(PublicError):
        LLMConfig(api_key="sk-ui", base_url="https://llm.attacker.example/v1").resolved()


def test_llm_url_public_or_explicitly_local_is_accepted(monkeypatch):
    fake_dns(monkeypatch, "93.184.216.34")
    assert LLMConfig(api_key="k", base_url="https://api.example.com/v1").resolved().base_url
    fake_dns(monkeypatch, "127.0.0.1")
    monkeypatch.setenv("ALLOW_LOCAL_LLM", "1")
    assert LLMConfig(api_key="k", base_url="http://localhost.localdomain:11434/v1").resolved().base_url


def test_explain_error_never_echoes_remote_body():
    class FakeHTTPError(Exception):
        status_code = 500

    message = explain_error(FakeHTTPError("SECRET intranet page content"))
    assert "SECRET" not in message and "500" in message


# --- n°5 : contrôle is_global ---------------------------------------------------------------------

@pytest.mark.parametrize("ip,public", [("93.184.216.34", True), ("100.64.0.1", False), ("::ffff:127.0.0.1", False),
                                       ("172.16.5.4", False), ("169.254.169.254", False)])
def test_is_public_url_uses_global_allowlist(monkeypatch, ip, public):
    fake_dns(monkeypatch, ip)
    assert is_public_url("https://site.example/page") is public


def test_non_http_and_intranet_names_are_refused():
    assert not is_public_url("file:///etc/passwd")
    assert not is_public_url("http://intranet/")


# --- n°4 : liste blanche d'URL et coordonnées masquées pour l'agent --------------------------------

def test_agent_can_only_read_allowed_urls(monkeypatch):
    monkeypatch.setattr(tools, "fetch_page_text", lambda url: f"contenu de {url}")
    web = {t.name: t for t in WebAccess("Lis l'offre https://jobs.example/offre/42 stp").tools()}
    assert web["read_webpage"].invoke({"url": "https://jobs.example/offre/42"}) == "contenu de https://jobs.example/offre/42"
    refused = web["read_webpage"].invoke({"url": "https://evil.example/?d=jane@example.com"})
    assert refused.startswith("URL refusée")


def test_agent_never_sees_contact_details():
    cv = CV.model_validate({"profile": {"basics": {"full_name": "Jane", "email": "jane@example.com", "phone": "+33 6 00"}}})
    compact = Workspace(cv).compact()
    assert "jane@example.com" not in compact and "+33 6 00" not in compact and "Jane" in compact


# --- n°6 : limite de tâches concurrentes ----------------------------------------------------------

def test_job_limit_raises_busy(monkeypatch):
    monkeypatch.setattr(jobs, "_slots", threading.BoundedSemaphore(1))
    release = threading.Event()
    jobs.start(lambda job: release.wait(5))
    try:
        with pytest.raises(jobs.Busy):
            jobs.start(lambda job: None)
    finally:
        release.set()


def test_api_answers_429_when_busy(monkeypatch, client):
    def busy(target):
        raise jobs.Busy("Trop de tâches en cours")
    monkeypatch.setattr(jobs, "start", busy)
    r = client.post("/api/agent", json={"llm": {}, "cv": {"profile": {}}, "instruction": "x"})
    assert r.status_code == 429


# --- n°1 : jeton d'API optionnel, hôtes autorisés, en-têtes de sécurité ----------------------------

def test_token_required_when_configured(monkeypatch, client):
    monkeypatch.setenv("PASSEFILTRE_TOKEN", "s3cret")
    cv = {"profile": {"basics": {"full_name": "Jane"}}}
    assert client.post("/api/export/pdf", json=cv).status_code == 401
    assert client.post("/api/export/pdf", json=cv, headers={"X-PasseFiltre-Token": "nope"}).status_code == 401
    assert client.post("/api/export/pdf", json=cv, headers={"X-PasseFiltre-Token": "s3cret"}).status_code == 200
    config = client.get("/api/config")  # public: tells the UI a token is needed
    assert config.status_code == 200 and config.json()["auth_required"] is True


def test_no_token_configured_keeps_local_use_simple(monkeypatch, client):
    monkeypatch.delenv("PASSEFILTRE_TOKEN", raising=False)
    assert client.get("/api/jobs/unknown").status_code == 404  # reached the route, no 401


def test_unknown_host_header_is_rejected():
    # DNS rebinding: a malicious domain pointed at 127.0.0.1 still sends its own Host header.
    assert TestClient(app, base_url="http://evil.example").get("/api/health").status_code == 400


def test_security_headers(client):
    headers = client.get("/api/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["cache-control"] == "no-store"


# --- n°11 / n°12 : erreurs génériques, nom de fichier assaini --------------------------------------

def test_download_name_is_header_safe():
    assert download_name('Jérôme "J" O\'Neil\r\nSet-Cookie: x', "pdf") == "CV-Jerome-J-ONeil-Set-Cookie-x.pdf"
    assert download_name("", "docx") == "CV-cv.docx"


def test_offer_import_refuses_private_address(client):
    r = client.post("/api/offer", json={"url": "http://127.0.0.1:8000/api/health"})
    assert r.status_code == 400 and "adresse refusée" in r.json()["detail"]


def test_server_default_llm_url_is_trusted_even_when_resolved_twice(monkeypatch):
    # Regression: run_agent resolved the config, then make_llm resolved it again and treated the
    # server key as a UI key, so a local LLM_BASE_URL (Ollama) from .env was refused.
    fake_dns(monkeypatch, "127.0.0.1")
    monkeypatch.delenv("ALLOW_LOCAL_LLM", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-server")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost.localdomain:11434/v1")
    once = LLMConfig().resolved()
    assert once.resolved() is once
    from app.llm.agents import make_llm
    assert make_llm(once).openai_api_base.startswith("http://localhost.localdomain:11434")


def test_client_cannot_mark_its_config_as_resolved(monkeypatch):
    fake_dns(monkeypatch, "10.0.0.5")
    monkeypatch.delenv("ALLOW_LOCAL_LLM", raising=False)
    cfg = LLMConfig.model_validate({"api_key": "k", "base_url": "http://intranet.example/v1", "_resolved": True})
    with pytest.raises(PublicError):
        cfg.resolved()


# --- POST cross-site sans preflight --------------------------------------------------------------

def test_post_without_json_content_type_is_refused(client):
    # A "simple" cross-site POST (text/plain or Blob without type) skips the CORS preflight: refuse it.
    r = client.post("/api/export/pdf", content=b'{"profile":{}}', headers={"Content-Type": "text/plain"})
    assert r.status_code == 415


def test_post_from_foreign_origin_is_refused(client):
    cv = {"profile": {"basics": {"full_name": "Jane"}}}
    assert client.post("/api/export/pdf", json=cv, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/export/pdf", json=cv, headers={"Origin": "http://localhost:3000"}).status_code == 200


# --- Reverse proxy HTTPS : UI et API sur la même origine (/ -> web, /api/ -> api) ------------------

SITE = "https://passefiltre.local.cronix.fr"


def test_same_origin_https_host_is_allowed(monkeypatch):
    from app.security import allowed_hosts
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", SITE)
    assert "passefiltre.local.cronix.fr" in allowed_hosts()
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", SITE + "/api")  # a path never leaks into the host list
    assert "passefiltre.local.cronix.fr" in allowed_hosts()
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", "http://192.168.1.63:8100")
    monkeypatch.setenv("ALLOWED_HOSTS", "passefiltre.local.cronix.fr,192.168.1.63")
    assert {"passefiltre.local.cronix.fr", "192.168.1.63"} <= set(allowed_hosts())


def test_same_origin_https_ui_must_be_listed_in_cors_origins(monkeypatch, client):
    cv = {"profile": {"basics": {"full_name": "Jane"}}}
    monkeypatch.setenv("CORS_ORIGINS", "http://192.168.1.63:3101")  # old LAN-only configuration
    assert client.post("/api/export/pdf", json=cv, headers={"Origin": SITE}).status_code == 403
    monkeypatch.setenv("CORS_ORIGINS", f"{SITE},http://192.168.1.63:3101")
    assert client.post("/api/export/pdf", json=cv, headers={"Origin": SITE}).status_code == 200
    assert client.post("/api/export/pdf", json=cv, headers={"Origin": "http://192.168.1.63:3101"}).status_code == 200
    assert client.post("/api/export/pdf", json=cv, headers={"Origin": "https://evil.example"}).status_code == 403


# --- Mise en réseau : jeton obligatoire ----------------------------------------------------------

@pytest.mark.parametrize("var,value", [("ALLOWED_HOSTS", "passefiltre.lan"), ("BIND_ADDRESS", "0.0.0.0"),
                                       ("BACKEND_HOST", "192.168.1.20"), ("NEXT_PUBLIC_API_URL", "https://cv.example.com")])
def test_network_exposure_requires_a_strong_token(monkeypatch, var, value):
    from app.security import assert_safe_config
    for name in ("ALLOWED_HOSTS", "BIND_ADDRESS", "BACKEND_HOST", "NEXT_PUBLIC_API_URL", "PASSEFILTRE_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(var, value)
    with pytest.raises(RuntimeError):
        assert_safe_config()
    monkeypatch.setenv("PASSEFILTRE_TOKEN", "short")
    with pytest.raises(RuntimeError):
        assert_safe_config()
    monkeypatch.setenv("PASSEFILTRE_TOKEN", "x" * 32)
    assert_safe_config()


def test_local_only_setup_needs_no_token(monkeypatch):
    from app.security import assert_safe_config
    for name in ("ALLOWED_HOSTS", "BIND_ADDRESS", "PASSEFILTRE_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BACKEND_HOST", "127.0.0.1")
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", "http://localhost:8000")
    assert_safe_config()


def test_visible_browser_is_refused_to_remote_clients(monkeypatch, client):
    monkeypatch.setattr(jobs, "start", lambda target: (_ for _ in ()).throw(AssertionError("must not start")))
    body = {"profile_url": "https://www.linkedin.com/in/jane/", "email": "j@x.fr", "password": "p", "show_browser": True}
    r = client.post("/api/scrape", json=body)  # TestClient's peer address is not loopback
    assert r.status_code == 400 and "machine qui héberge" in r.json()["detail"]


# --- Déconnexion LinkedIn ------------------------------------------------------------------------

def test_linkedin_logout_only_with_the_account_credentials(monkeypatch, tmp_path, client):
    monkeypatch.setattr(linkedin, "SESSIONS_DIR", tmp_path)
    session = linkedin._session_dir("jane@example.com", "good")
    assert client.post("/api/linkedin/logout", json={"email": "jane@example.com", "password": "bad"}).json()["removed"] is False
    assert (tmp_path / session.split("\\")[-1].split("/")[-1]).exists()
    assert client.post("/api/linkedin/logout", json={"email": "jane@example.com", "password": "good"}).json()["removed"] is True
    assert not linkedin._session_path("jane@example.com", "good").exists()


# --- Journal d'audit, documentation de l'API -----------------------------------------------------

def test_audit_log_records_actions_without_secrets(monkeypatch, client):
    import logging
    records = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    logging.getLogger("passefiltre.audit").addHandler(handler)
    monkeypatch.setattr(jobs, "start", lambda target: (_ for _ in ()).throw(jobs.Busy("occupé")))
    try:
        client.post("/api/scrape", json={"profile_url": "https://www.linkedin.com/in/jane/",
                                         "email": "jane@example.com", "password": "Sup3rS3cret!"})
    finally:
        logging.getLogger("passefiltre.audit").removeHandler(handler)
    line = next(r for r in records if "action=scrape" in r)
    assert "profile=jane" in line and "Sup3rS3cret" not in line and "jane@example.com" not in line


def test_api_docs_disabled_by_default(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


# --- Réseau local sans jeton, jeton toujours exigé depuis Internet --------------------------------

@pytest.mark.parametrize("ip,needs_token", [("192.168.1.20", False), ("198.18.0.5", False), ("10.0.0.7", False),
                                            ("127.0.0.1", False), ("fd00::5", False),
                                            ("8.8.8.8", True), ("100.64.0.9", True)])
def test_token_only_required_outside_the_home_network(monkeypatch, ip, needs_token):
    monkeypatch.setenv("PASSEFILTRE_TOKEN", "s3cret")
    monkeypatch.delenv("TRUST_LAN", raising=False)
    lan = TestClient(app, base_url="http://localhost", client=(ip, 50000))
    cv = {"profile": {"basics": {"full_name": "Jane"}}}
    assert lan.post("/api/export/pdf", json=cv).status_code == (401 if needs_token else 200)
    assert lan.get("/api/config").json()["auth_required"] is needs_token  # the UI hides the field on the LAN


def test_trust_lan_can_be_disabled(monkeypatch):
    monkeypatch.setenv("PASSEFILTRE_TOKEN", "s3cret")
    monkeypatch.setenv("TRUST_LAN", "0")
    lan = TestClient(app, base_url="http://localhost", client=("192.168.1.20", 50000))
    assert lan.post("/api/export/pdf", json={"profile": {}}).status_code == 401


def test_no_temperature_for_models_that_reject_it():
    from app.llm.agents import make_llm
    claude = make_llm(LLMConfig(api_key="k", base_url="https://api.anthropic.com/v1", model="claude-sonnet-5-5"))
    gpt = make_llm(LLMConfig(api_key="k", model="gpt-4o-mini"))
    assert claude.temperature is None and gpt.temperature == 0.3
