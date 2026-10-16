"""Remote CAPTCHA solving: job ownership, viewer tickets, WebSocket bridge, scraper lifecycle."""

import os
import socket
import tempfile
import threading
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import jobs, main
from app.main import app
from app.models import Profile
from app.scraper import captcha, linkedin
from app.security import PublicError

UI = "http://localhost:3000"  # default CORS_ORIGINS
WS = "ws://localhost"  # websocket_connect ignores base_url; the Host must be allowed
needs_unix_sockets = pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix sockets (Linux, Docker image)")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("PASSEFILTRE_TOKEN", raising=False)
    return TestClient(app, base_url="http://localhost")


class FakeDisplay:
    def __init__(self, sock: str | None = None) -> None:
        self.vnc_socket = sock
        self.started = self.stopped = 0

    def start_vnc(self) -> None:
        self.started += 1

    def stop_vnc(self) -> None:
        self.stopped += 1


def captcha_job(display=None) -> jobs.Job:
    job = jobs.Job()
    jobs._jobs[job.id] = job
    job.captcha_open(display or FakeDisplay(), time.time() + 60)
    return job


def owner(job: jobs.Job) -> dict:
    return {"X-PasseFiltre-Job-Key": job.key}


# --- Une tâche n'est visible et pilotable que par celui qui l'a lancée ----------------------------

def test_job_key_is_given_once_and_required(monkeypatch, client):
    release = threading.Event()
    monkeypatch.setattr(main, "scrape_profile", lambda *a, **k: release.wait(5) and Profile())
    body = {"profile_url": "https://www.linkedin.com/in/jane/", "email": "j@x.fr", "password": "p"}
    first, second = client.post("/api/scrape", json=body).json(), client.post("/api/scrape", json=body).json()
    try:
        assert first["key"] and first["key"] != second["key"]
        path = f"/api/jobs/{first['id']}"
        assert client.get(path).status_code == 404                                           # token alone
        assert client.get(path, headers={"X-PasseFiltre-Job-Key": second["key"]}).status_code == 404  # other job
        mine = client.get(path, headers={"X-PasseFiltre-Job-Key": first["key"]})
        assert mine.status_code == 200 and "key" not in mine.json()                        # never sent again
        assert client.delete(path, headers={"X-PasseFiltre-Job-Key": second["key"]}).status_code == 404
        assert client.post(f"{path}/code", json={"code": "1"}).status_code == 404
    finally:
        release.set()


def test_cors_preflight_allows_the_job_key_header(client):
    r = client.options("/api/jobs/x", headers={"Origin": UI, "Access-Control-Request-Method": "DELETE",
                                               "Access-Control-Request-Headers": "x-passefiltre-job-key"})
    assert r.status_code == 200 and "x-passefiltre-job-key" in r.headers["access-control-allow-headers"].lower()


def test_cancel_stops_the_job_and_drops_its_result(client):
    started, release = threading.Event(), threading.Event()

    def target(job):
        started.set()
        release.wait(5)
        return {"secret": "data"}

    job = jobs.start(target)
    started.wait(5)
    assert client.delete(f"/api/jobs/{job.id}", headers=owner(job)).json() == {"ok": True}
    release.set()
    for _ in range(50):
        if job.status != "running":
            break
        time.sleep(0.05)
    assert job.status == "error" and job.error == jobs.CANCELLED and job.result is None


def test_cancel_wakes_a_pending_code_request():
    job = jobs.Job()
    threading.Timer(0.1, job.cancel).start()
    started = time.time()
    assert job.ask_code("code ?") is None and time.time() - started < 5


# --- Tickets du visualiseur : authentifiés, propres à la tâche, à usage unique ---------------------

def test_ticket_needs_the_token_and_the_job_key(monkeypatch, client):
    job = captcha_job()
    url = f"/api/jobs/{job.id}/captcha/ticket"
    monkeypatch.setenv("PASSEFILTRE_TOKEN", "s3cret")
    assert client.post(url, json={}, headers=owner(job)).status_code == 401
    token = {"X-PasseFiltre-Token": "s3cret"}
    assert client.post(url, json={}, headers=token).status_code == 404
    r = client.post(url, json={}, headers={**token, **owner(job)})
    assert r.status_code == 200 and r.json()["protocol"] == "pf-ticket." and len(r.json()["ticket"]) >= 40


def test_no_ticket_without_a_captcha(client):
    job = jobs.Job()
    jobs._jobs[job.id] = job
    assert client.post(f"/api/jobs/{job.id}/captcha/ticket", json={}, headers=owner(job)).status_code == 409


def test_ticket_is_single_use_bound_to_its_job_and_short_lived(monkeypatch):
    a, b = captcha_job(), captcha_job()
    ticket = a.issue_ticket()
    assert not b.redeem_ticket(ticket)  # another job's ticket
    assert a.redeem_ticket(ticket)
    assert not a.redeem_ticket(ticket)  # single use
    assert not a.redeem_ticket("")
    monkeypatch.setattr(jobs, "TICKET_TTL", -1)
    assert not a.redeem_ticket(a.issue_ticket())  # expired
    monkeypatch.setattr(jobs, "TICKET_TTL", 60)
    late = a.issue_ticket()
    a.captcha_closed()  # CAPTCHA over: outstanding tickets are void
    assert not a.redeem_ticket(late)


# --- Pont WebSocket <-> VNC -------------------------------------------------------------------------

@pytest.fixture
def fake_vnc():
    """A VNC-like server on a Unix socket: sends the RFB banner, then echoes."""
    folder = tempfile.mkdtemp(prefix="pfv")
    path = os.path.join(folder, "s")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(4)

    def serve():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            with conn:
                conn.sendall(b"RFB 003.008\n")
                while data := conn.recv(1024):
                    conn.sendall(data)

    threading.Thread(target=serve, daemon=True).start()
    yield path
    server.close()
    os.unlink(path)
    os.rmdir(folder)


def ticket(client, job) -> list[str]:
    t = client.post(f"/api/jobs/{job.id}/captcha/ticket", json={}, headers=owner(job)).json()
    return ["binary", t["protocol"] + t["ticket"]]


@needs_unix_sockets
def test_viewer_reaches_only_its_own_display(client, fake_vnc):
    job, other = captcha_job(FakeDisplay(fake_vnc)), captcha_job(FakeDisplay(fake_vnc))
    url = f"{WS}/api/jobs/{job.id}/captcha/vnc"
    for protocols, headers, target in [
        (ticket(client, job), {"origin": "https://evil.example"}, url),   # cross-site WebSocket hijacking
        (ticket(client, job), {}, url),                                   # no Origin
        (["binary"], {"origin": UI}, url),                                # no ticket
        (ticket(client, other), {"origin": UI}, url),                     # someone else's ticket
        (ticket(client, job), {"origin": UI}, f"{WS}/api/jobs/{other.id}/captcha/vnc"),
    ]:
        with pytest.raises(WebSocketDisconnect) as refused:
            with client.websocket_connect(target, subprotocols=protocols, headers=headers):
                pass
        assert refused.value.code == 1008

    protocols = ticket(client, job)
    with client.websocket_connect(url, subprotocols=protocols, headers={"origin": UI}) as ws:
        assert ws.accepted_subprotocol == "binary"
        assert ws.receive_bytes() == b"RFB 003.008\n"
        ws.send_bytes(b"ping")
        assert ws.receive_bytes() == b"ping"
    with pytest.raises(WebSocketDisconnect):  # the same ticket cannot be replayed
        with client.websocket_connect(url, subprotocols=protocols, headers={"origin": UI}):
            pass


@needs_unix_sockets
def test_viewer_is_cut_when_the_captcha_session_ends(client, fake_vnc):
    job = captcha_job(FakeDisplay(fake_vnc))
    with client.websocket_connect(f"{WS}/api/jobs/{job.id}/captcha/vnc", subprotocols=ticket(client, job),
                                  headers={"origin": UI}) as ws:
        assert ws.receive_bytes().startswith(b"RFB ")
        threading.Timer(0.2, job.captcha_closed).start()  # solved / expired / cancelled
        with pytest.raises(WebSocketDisconnect):
            ws.receive_bytes()


# --- Cycle de vie côté scraper -----------------------------------------------------------------------

class FakeLocator:
    def __init__(self, n: int) -> None:
        self.n = n
        self.first = self

    def count(self) -> int:
        return self.n

    def is_visible(self) -> bool:
        return self.n > 0


class CheckpointPage:
    """LinkedIn showing a CAPTCHA until `solve_after` polls (None = never solved)."""

    def __init__(self, job: jobs.Job, solve_after: int | None) -> None:
        self.url = "https://www.linkedin.com/checkpoint/challenge/AgE"
        self.job, self.solve_after, self.polls, self.statuses = job, solve_after, 0, []

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(int(selector == linkedin.CAPTCHA and "/checkpoint" in self.url))

    def wait_for_timeout(self, ms: int) -> None:
        self.polls += 1
        self.statuses.append(self.job.status)
        if self.polls == 1:  # the user opens the viewer: that alone validates nothing
            assert self.job.redeem_ticket(self.job.issue_ticket())
        if self.solve_after is not None and self.polls >= self.solve_after:
            self.url = "https://www.linkedin.com/feed/"


def test_captcha_is_solved_only_when_linkedin_leaves_the_checkpoint():
    job, display = jobs.Job(), FakeDisplay()
    page = CheckpointPage(job, solve_after=3)
    linkedin._handle_checkpoint(page, job, headless=False, display=display)
    assert page.statuses == ["needs_captcha"] * 3            # still waiting after the viewer was opened
    assert (display.started, display.stopped) == (1, 1)
    assert job.status == "running" and job.display is None
    assert job.messages[-1].startswith("Vérification acceptée par LinkedIn")


def test_captcha_timeout_closes_the_session(monkeypatch):
    monkeypatch.setattr(captcha, "timeout", lambda: 0)
    job, display = jobs.Job(), FakeDisplay()
    with pytest.raises(linkedin.ScrapeError, match="CAPTCHA non résolu"):
        linkedin._handle_checkpoint(CheckpointPage(job, solve_after=None), job, headless=False, display=display)
    assert display.stopped == 1 and job.status == "running" and job.display is None


def test_cancel_during_captcha_closes_the_session():
    job, display = jobs.Job(), FakeDisplay()
    page = CheckpointPage(job, solve_after=None)
    threading.Timer(0.05, job.cancel).start()
    original = page.wait_for_timeout
    page.wait_for_timeout = lambda ms: (original(ms), time.sleep(0.1))
    with pytest.raises(linkedin.ScrapeError, match="annulée"):
        linkedin._handle_checkpoint(page, job, headless=False, display=display)
    assert display.stopped == 1 and job.display is None


def test_headless_captcha_without_display_asks_for_a_visible_browser():
    job = jobs.Job()
    with pytest.raises(linkedin.CaptchaRequired):
        linkedin._handle_checkpoint(CheckpointPage(job, solve_after=None), job, headless=True)
    assert job.status == "running"


@pytest.fixture
def scrape_env(monkeypatch, tmp_path):
    monkeypatch.setattr(linkedin, "SESSIONS_DIR", tmp_path)
    calls = []

    def fake_scrape(base, email, password, hooks, user_data_dir, headless, debug, cookies=None):
        calls.append(("scrape", headless, cookies))
        if not cookies:
            raise linkedin.CaptchaRequired("captcha")
        return Profile()

    def fake_remote_login(email, password, hooks, debug):
        calls.append(("remote", email))
        return [{"name": "li_at", "value": "x", "domain": ".linkedin.com"}]

    monkeypatch.setattr(linkedin, "_scrape", fake_scrape)
    monkeypatch.setattr(linkedin, "_remote_login", fake_remote_login)
    return calls


def test_headless_captcha_goes_through_the_isolated_browser(scrape_env):
    profile = linkedin.scrape_profile("https://www.linkedin.com/in/jane/", "j@x.fr", "p", jobs.Job(),
                                      remote_captcha=True)
    assert isinstance(profile, Profile)
    # Never a visible browser in the API: remote login, then headless again with LinkedIn's cookies only.
    assert scrape_env == [("scrape", True, None), ("remote", "j@x.fr"),
                          ("scrape", True, [{"name": "li_at", "value": "x", "domain": ".linkedin.com"}])]


def test_a_second_challenge_after_the_captcha_is_reported(scrape_env, monkeypatch):
    def always_captcha(*args, **kwargs):
        raise linkedin.CaptchaRequired("captcha")

    monkeypatch.setattr(linkedin, "_scrape", always_captcha)
    with pytest.raises(linkedin.ScrapeError, match="redemande une vérification"):
        linkedin.scrape_profile("https://www.linkedin.com/in/jane/", "j@x.fr", "p", jobs.Job(), remote_captcha=True)


def test_scrape_keeps_the_previous_behaviour_without_remote_captcha(scrape_env):
    with pytest.raises(linkedin.CaptchaRequired):
        linkedin.scrape_profile("https://www.linkedin.com/in/jane/", "j@x.fr", "p", jobs.Job())
    assert scrape_env == [("scrape", True, None)]


def test_only_linkedin_cookies_leave_the_isolated_browser():
    cookies = [
        {"name": "li_at", "value": "s", "domain": ".www.linkedin.com", "path": "/", "expires": 1, "httpOnly": True,
         "secure": True, "sameSite": "None", "partitionKey": "x"},
        {"name": "JSESSIONID", "value": "j", "domain": "linkedin.com"},
        {"name": "t", "value": "e", "domain": ".evil-linkedin.com"},
        {"name": "t", "value": "e", "domain": "linkedin.com.evil.com"},
        {"name": "_ga", "value": "g", "domain": ".google.com"},
        {"name": "big", "value": "x" * 5000, "domain": ".linkedin.com"},
    ]
    kept = linkedin._linkedin_cookies(cookies)
    assert [c["name"] for c in kept] == ["li_at", "JSESSIONID"]
    assert set(kept[0]) == set(linkedin.COOKIE_FIELDS)  # only what add_cookies() accepts
    with pytest.raises(linkedin.ScrapeError, match="session LinkedIn"):
        linkedin._linkedin_cookies(cookies[1:])  # not logged in: nothing to resume with


class LoginPage(CheckpointPage):
    """/login redirected straight to a CAPTCHA checkpoint: no login form at all."""

    def locator(self, selector: str) -> FakeLocator:
        if selector in (linkedin.USER_INPUT, linkedin.PASSWORD_INPUT):
            raise AssertionError("the login form must not be looked for on a checkpoint")
        return super().locator(selector)

    def screenshot(self, **kwargs) -> None:
        pass


class LoginSession:
    def __init__(self, page) -> None:
        self.page = page

    def fetch(self, url, page_action, **kwargs) -> None:
        page_action(self.page)


def test_login_redirected_to_a_captcha_asks_for_the_isolated_browser():
    job = jobs.Job()
    with pytest.raises(linkedin.CaptchaRequired):  # not "Formulaire de connexion introuvable"
        linkedin._login(LoginSession(LoginPage(job, solve_after=None)), "j@x.fr", "p", job, True, False)


def test_login_redirected_to_a_captcha_is_solved_in_the_same_browser():
    job, display = jobs.Job(), FakeDisplay()
    page = LoginPage(job, solve_after=2)
    linkedin._login(LoginSession(page), "j@x.fr", "p", job, False, False, display)
    assert page.url.endswith("/feed/") and (display.started, display.stopped) == (1, 1)


def test_one_scrape_at_a_time_per_linkedin_account(monkeypatch, tmp_path):
    monkeypatch.setattr(linkedin, "SESSIONS_DIR", tmp_path)
    inside, release = threading.Event(), threading.Event()

    def fake_scrape(base, email, *rest, **kwargs):
        if email == "j@x.fr":
            inside.set()
            release.wait(5)
        return Profile()

    monkeypatch.setattr(linkedin, "_scrape", fake_scrape)
    url = "https://www.linkedin.com/in/jane/"
    worker = threading.Thread(target=linkedin.scrape_profile, args=(url, "j@x.fr", "p", jobs.Job()))
    worker.start()
    try:
        inside.wait(5)
        with pytest.raises(linkedin.ScrapeError, match="déjà en cours"):
            linkedin.scrape_profile(url, "J@x.fr ", "p", jobs.Job())
        linkedin.scrape_profile(url, "other@x.fr", "p", jobs.Job())  # another account is not blocked
    finally:
        release.set()
        worker.join(5)
    linkedin.scrape_profile(url, "j@x.fr", "p", jobs.Job())  # free again once the first one is over


def test_remote_captcha_can_be_disabled(monkeypatch, client):
    monkeypatch.setenv("CAPTCHA_BROWSER_URL", "http://captcha-browser:9300")
    monkeypatch.setenv("INTERACTIVE_CAPTCHA", "0")
    assert captcha.available() is False
    assert client.get("/api/config").json()["remote_captcha"] is False


def test_no_remote_captcha_without_the_isolated_service(monkeypatch):
    """Never a human-driven browser inside the API container: without captcha-browser, the feature is off."""
    monkeypatch.delenv("CAPTCHA_BROWSER_URL", raising=False)
    monkeypatch.delenv("INTERACTIVE_CAPTCHA", raising=False)
    assert captcha.available() is False
    monkeypatch.setenv("CAPTCHA_BROWSER_URL", "http://captcha-browser:9300")
    assert captcha.available() is True


# --- Client du navigateur isolé (côté API) --------------------------------------------------------

@pytest.fixture
def remote(monkeypatch, tmp_path):
    monkeypatch.setenv("CAPTCHA_BROWSER_URL", "http://127.0.0.1:9300")
    monkeypatch.setattr(captcha, "RUN_DIR", tmp_path / "run")
    (tmp_path / "run").mkdir()
    answers = {"POST": {"id": "A" * 32, "cdp_port": 9222}}
    calls = []

    def fake_call(self, method, path=""):
        calls.append((method, path))
        return answers.get(method + path, answers.get(method, {}))

    monkeypatch.setattr(captcha.RemoteBrowser, "_call", fake_call)
    return answers, calls, tmp_path


def test_remote_browser_session_lifecycle(remote):
    answers, calls, _ = remote
    with captcha.RemoteBrowser() as browser:
        assert browser.cdp_url == "http://127.0.0.1:9222"  # an IP: DevTools refuses other Host headers
    assert calls == [("POST", ""), ("DELETE", "/" + "A" * 32)]


@pytest.mark.parametrize("bad", [{"id": "../../x", "cdp_port": 9222}, {"id": "A" * 32, "cdp_port": "9222"}, {}])
def test_remote_browser_rejects_odd_session_answers(remote, bad):
    answers, _, _ = remote
    answers["POST"] = bad
    with pytest.raises(PublicError, match="indisponible"):
        captcha.RemoteBrowser().__enter__()


def test_remote_browser_only_connects_to_sockets_of_the_shared_run_dir(remote):
    answers, _, tmp_path = remote
    outside = tmp_path / "elsewhere.sock"
    outside.touch()
    for path in [str(outside), str(tmp_path / "run" / ".." / "elsewhere.sock"), "/var/run/docker.sock", ""]:
        answers["POST/" + "A" * 32 + "/vnc"] = {"socket": path}
        with captcha.RemoteBrowser() as browser:
            with pytest.raises(PublicError):
                browser.start_vnc()
            assert browser.vnc_socket is None


def test_remote_browser_unreachable_is_reported(monkeypatch):
    monkeypatch.setenv("CAPTCHA_BROWSER_URL", "http://127.0.0.1:1")  # nothing listens there
    with pytest.raises(PublicError, match="indisponible"):
        captcha.RemoteBrowser().__enter__()
