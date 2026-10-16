"""Isolated browser for remote CAPTCHA solving: the `captcha-browser` service (docker-compose.yml).

The only Chromium a human drives (through noVNC) runs here, in its own container, never in the API:
- no secrets (no env_file), no LinkedIn sessions volume, no Linux capabilities, a minimal environment;
- network: only the internal `captcha` network (no gateway: no host, no LAN, no internet). Web pages go
  through captcha-egress (egress.py), which only tunnels HTTPS to an allowlist of public hosts;
- a fresh temporary profile per session, deleted with its Xvfb display, VNC socket and processes.

The API drives it through this small control interface (internal network only) and over CDP:
    POST   /session            -> {"id", "cdp_port"}   Xvfb + Chromium, one session at a time
    POST   /session/<id>/vnc   -> {"socket"}           x11vnc on a Unix socket in the shared volume
    DELETE /session/<id>/vnc                           stop x11vnc
    DELETE /session/<id>                               kill everything, delete the profile
    GET    /health

    python -m app.scraper.browser_host
"""

import json
import logging
import os
import secrets
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.scraper import captcha
from app.scraper.captcha import HEIGHT, RUN_DIR, WIDTH, VirtualDisplay, _stop

log = logging.getLogger("captcha-browser")

CONTROL_PORT = 9300
CDP_PORT = 9222
PROXY = os.getenv("CAPTCHA_PROXY", "http://captcha-egress:3128")
START_TIMEOUT = 30  # Chromium on a Raspberry Pi
PROFILE_PREFIX = "pf-profile-"


def chromium_args(profile: Path, proxy: str | None) -> list[str]:
    """The scraper's stealth flags (Scrapling's), a window filling the virtual screen, CDP on loopback."""
    from scrapling.engines.constants import DEFAULT_ARGS, STEALTH_ARGS

    args = [*DEFAULT_ARGS, *STEALTH_ARGS,
            "--disable-blink-features=AutomationControlled",
            "--webrtc-ip-handling-policy=disable_non_proxied_udp", "--force-webrtc-ip-handling-policy",
            "--lang=en-US", "--accept-lang=en-US,en", f"--window-size={WIDTH},{HEIGHT}",
            # Chromium's own sandbox needs user namespaces, refused by Docker's seccomp profile: the
            # container is the security boundary (docs/deployment-serveurcasa.md §13).
            "--no-sandbox",
            f"--user-data-dir={profile}", "--remote-debugging-port=0"]  # DevTools on 127.0.0.1, random port
    if proxy:  # every request through the egress proxy, loopback included (no implicit bypass)
        args += [f"--proxy-server={proxy}", "--proxy-bypass-list=<-loopback>"]
    return [*args, "about:blank"]


def _pump(source: socket.socket, target: socket.socket) -> None:
    try:
        while data := source.recv(65536):
            target.sendall(data)
    except OSError:
        pass
    finally:
        try:
            target.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class _Pipe(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        with socket.create_connection(("127.0.0.1", self.server.target_port), 5) as upstream:  # type: ignore[attr-defined]
            upstream.settimeout(None)
            back = threading.Thread(target=_pump, args=(upstream, self.request), daemon=True)
            back.start()
            _pump(self.request, upstream)
            back.join()


class _Relay(socketserver.ThreadingTCPServer):
    """Chromium only listens on 127.0.0.1: relay the CDP port to the internal network for the API."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], target_port: int) -> None:
        self.target_port = target_port
        super().__init__(address, _Pipe)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.shutdown()
        self.server_close()


class Session:
    """One Xvfb display + one Chromium with a fresh profile, all removed together by close()."""

    def __init__(self, executable: str, proxy: str | None = PROXY, run_dir: Path | None = RUN_DIR) -> None:
        self.id = secrets.token_urlsafe(24)
        self.started = time.monotonic()
        self.display = VirtualDisplay(base_dir=run_dir)
        self.profile: Path | None = None
        self.devtools_port = 0
        self._chrome: subprocess.Popen | None = None
        self._relay: _Relay | None = None
        try:
            self.display.__enter__()
            self.profile = Path(tempfile.mkdtemp(prefix=PROFILE_PREFIX))  # this container's /tmp, 0700
            # Minimal environment: nothing inherited but PATH.
            env = {"DISPLAY": self.display.display, "HOME": str(self.profile),
                   "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}
            with open(self.profile / "chrome.log", "wb") as out:
                self._chrome = subprocess.Popen([executable, *chromium_args(self.profile, proxy)], env=env,
                                                stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                                                start_new_session=True)
            self.devtools_port = self._wait_devtools()
        except BaseException:
            self.close()
            raise

    def _wait_devtools(self) -> int:
        assert self.profile is not None and self._chrome is not None
        active = self.profile / "DevToolsActivePort"
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline and self._chrome.poll() is None:
            try:
                port = active.read_text().split("\n", 1)[0].strip()
            except OSError:
                port = ""
            if port.isdigit():
                return int(port)
            time.sleep(0.2)
        try:
            tail = (self.profile / "chrome.log").read_text(errors="replace")[-500:]
        except OSError:
            tail = ""
        raise RuntimeError(f"Chromium did not start: {tail}")

    def expose(self, port: int) -> None:
        self._relay = _Relay(("0.0.0.0", port), self.devtools_port)

    def close(self) -> None:
        if self._relay is not None:
            self._relay.close()
            self._relay = None
        _stop(self._chrome)  # whole process group: renderers, GPU process, zygote
        self._chrome = None
        self.display.close()  # x11vnc, Xvfb, VNC socket directory
        if self.profile is not None:
            shutil.rmtree(self.profile, ignore_errors=True)
            self.profile = None


class Busy(Exception):
    pass


class Host:
    """At most one session (memory of the Raspberry Pi), reaped if the API forgets it."""

    def __init__(self, executable: str, proxy: str | None = PROXY, max_age: float | None = None) -> None:
        self.executable, self.proxy = executable, proxy
        self.max_age = max_age if max_age is not None else captcha.timeout() + 600
        self.session: Session | None = None
        self.lock = threading.Lock()

    def open(self) -> Session:
        with self.lock:
            if self.session is not None:
                raise Busy
            session = Session(self.executable, self.proxy)
            try:
                session.expose(CDP_PORT)
            except BaseException:
                session.close()
                raise
            self.session = session
            return session

    def get(self, session_id: str) -> Session | None:
        session = self.session
        if session is None or not secrets.compare_digest(session.id.encode(), session_id.encode(errors="replace")):
            return None
        return session

    def close(self, session_id: str | None = None) -> bool:
        with self.lock:
            session = self.session if session_id is None else self.get(session_id)
            if session is None:
                return False
            self.session = None
        session.close()
        return True

    def reap(self) -> None:
        session = self.session
        if session is not None and time.monotonic() - session.started > self.max_age:
            log.warning("closing a CAPTCHA session older than %ss", int(self.max_age))
            self.close(session.id)


class Control(BaseHTTPRequestHandler):
    server: "ControlServer"

    def _reply(self, code: int, body: dict | None = None) -> None:
        data = json.dumps(body or {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _route(self) -> tuple[list[str], Session | None]:
        parts = self.path.split("?", 1)[0].strip("/").split("/")
        session = self.server.host.get(parts[1]) if len(parts) > 1 and parts[0] == "session" else None
        return parts, session

    def do_GET(self) -> None:
        if self.path == "/health":
            return self._reply(200, {"ok": True, "sessions": int(self.server.host.session is not None)})
        self._reply(404)

    def do_POST(self) -> None:
        parts, session = self._route()
        if parts == ["session"]:
            try:
                session = self.server.host.open()
            except Busy:
                return self._reply(409, {"error": "busy"})
            except Exception:
                log.exception("CAPTCHA session start failed")
                return self._reply(500, {"error": "start failed"})
            log.info("CAPTCHA session opened")
            return self._reply(201, {"id": session.id, "cdp_port": CDP_PORT})
        if len(parts) == 3 and parts[2] == "vnc" and session is not None:
            try:
                session.display.start_vnc()
            except Exception:
                log.exception("VNC start failed")
                return self._reply(500, {"error": "vnc failed"})
            return self._reply(200, {"socket": session.display.vnc_socket})
        self._reply(404)

    def do_DELETE(self) -> None:
        parts, session = self._route()
        if session is None:
            return self._reply(404)
        if len(parts) == 3 and parts[2] == "vnc":
            session.display.stop_vnc()
            return self._reply(200)
        if len(parts) == 2:
            self.server.host.close(session.id)
            log.info("CAPTCHA session closed")
            return self._reply(200)
        self._reply(404)

    def log_message(self, *args) -> None:
        pass


class ControlServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], host: Host) -> None:
        self.host = host
        super().__init__(address, Control)


def _clean_leftovers() -> None:
    """A restarted container keeps its /tmp, and the run volume outlives it: start from nothing."""
    for folder, prefix in ((RUN_DIR, "pf-captcha-"), (Path(tempfile.gettempdir()), PROFILE_PREFIX)):
        for path in folder.glob(f"{prefix}*"):
            shutil.rmtree(path, ignore_errors=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from app.scraper.browser_check import expected_executable

    _clean_leftovers()
    host = Host(expected_executable())
    server = ControlServer(("0.0.0.0", CONTROL_PORT), host)

    def reaper() -> None:
        while True:
            time.sleep(10)
            host.reap()

    threading.Thread(target=reaper, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    log.info("listening on :%s (CDP relay :%s, proxy %s)", CONTROL_PORT, CDP_PORT, PROXY)
    try:
        server.serve_forever()
    finally:
        host.close()
        server.server_close()


if __name__ == "__main__":
    main()
