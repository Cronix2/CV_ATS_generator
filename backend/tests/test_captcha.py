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
    url = f"/api/jobs/{job.id}/captcha/vnc"
    for protocols, headers, target in [
        (ticket(client, job), {"origin": "https://evil.example"}, url),   # cross-site WebSocket hijacking
        (ticket(client, job), {}, url),                                   # no Origin
        (["binary"], {"origin": UI}, url),                                # no ticket
        (ticket(client, other), {"origin": UI}, url),                     # someone else's ticket
        (ticket(client, job), {"origin": UI}, f"/api/jobs/{other.id}/captcha/vnc"),
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
    with client.websocket_connect(f"/api/jobs/{job.id}/captcha/vnc", subprotocols=ticket(client, job),
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


class FakeVirtualDisplay(FakeDisplay):
    opened = closed = 0

    def __enter__(self):
        FakeVirtualDisplay.opened += 1
        return self

    def __exit__(self, *exc):
        FakeVirtualDisplay.closed += 1


@pytest.fixture
def scrape_env(monkeypatch, tmp_path):
    monkeypatch.setattr(linkedin, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(captcha, "VirtualDisplay", FakeVirtualDisplay)
    FakeVirtualDisplay.opened = FakeVirtualDisplay.closed = 0
    calls = []

    def fake_scrape(base, email, password, hooks, user_data_dir, headless, debug, display=None):
        calls.append((headless, display))
        if display is None:
            raise linkedin.CaptchaRequired("captcha")
        return Profile()

    monkeypatch.setattr(linkedin, "_scrape", fake_scrape)
    return calls


def test_scrape_retries_on_a_virtual_display_after_a_headless_captcha(scrape_env):
    profile = linkedin.scrape_profile("https://www.linkedin.com/in/jane/", "j@x.fr", "p", jobs.Job(),
                                      remote_captcha=True)
    assert isinstance(profile, Profile)
    assert [h for h, _ in scrape_env] == [True, False] and isinstance(scrape_env[1][1], FakeVirtualDisplay)
    assert FakeVirtualDisplay.opened == FakeVirtualDisplay.closed == 1


def test_scrape_keeps_the_previous_behaviour_without_remote_captcha(scrape_env):
    with pytest.raises(linkedin.CaptchaRequired):
        linkedin.scrape_profile("https://www.linkedin.com/in/jane/", "j@x.fr", "p", jobs.Job())
    assert len(scrape_env) == 1 and FakeVirtualDisplay.opened == 0


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


def test_virtual_displays_are_capped(monkeypatch):
    monkeypatch.setattr(captcha, "_sessions", threading.BoundedSemaphore(1))
    captcha._sessions.acquire()
    with pytest.raises(PublicError, match="déjà en cours"):
        captcha.VirtualDisplay().__enter__()


def test_remote_captcha_can_be_disabled(monkeypatch, client):
    monkeypatch.setenv("INTERACTIVE_CAPTCHA", "0")
    assert captcha.available() is False
    assert client.get("/api/config").json()["remote_captcha"] is False
