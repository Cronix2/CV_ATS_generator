"""Remote CAPTCHA solving: a private virtual screen (Xvfb) shown through VNC (x11vnc) for one job.

In Docker there is no screen: the scraper runs headless. When LinkedIn puts a CAPTCHA in front of the
login, the API opens a session on the isolated `captcha-browser` service (browser_host.py): a fresh
Chromium on a private Xvfb display, in its own container (no secrets, no LinkedIn sessions, no network
but an HTTPS allowlist proxy). The scraper logs in there over CDP; once the CAPTCHA is on screen,
x11vnc exposes that display on a Unix socket in a 0700 directory of a volume shared with the API (never
a TCP port). The API bridges an authenticated WebSocket to that socket (what websockify would do) and
the UI shows it with noVNC. A human solves the CAPTCHA; the scraper only resumes once LinkedIn itself
has left its checkpoint page, and only LinkedIn's cookies come back. Everything is removed afterwards.
"""

import json
import logging
import os
import re
import select
import shutil
import signal
import socket
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from app.security import PublicError

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 1280, 900  # small framebuffer (~4.5 MB): fine for a Raspberry Pi
START_TIMEOUT = 10
# Volume shared by the API and captcha-browser: only the VNC Unix sockets of the running session.
RUN_DIR = Path(os.getenv("CAPTCHA_RUN_DIR", "/run/pf-captcha"))
SESSION_ID = re.compile(r"[A-Za-z0-9_-]{16,64}")
UNAVAILABLE = "Navigateur de résolution des CAPTCHA indisponible (service captcha-browser) : réessayez plus tard."
BUSY = "Une autre résolution de CAPTCHA est déjà en cours sur ce serveur : réessayez dans quelques minutes."


def available() -> bool:
    """Remote CAPTCHA solving needs the isolated captcha-browser service (docker compose sets
    CAPTCHA_BROWSER_URL). Never in the API process itself. INTERACTIVE_CAPTCHA=0 disables it."""
    return os.getenv("INTERACTIVE_CAPTCHA", "1") != "0" and bool(os.getenv("CAPTCHA_BROWSER_URL"))


def timeout() -> int:
    """Seconds left to the user to solve a CAPTCHA once it is shown."""
    return max(60, int(os.getenv("CAPTCHA_TIMEOUT", "300")))


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)  # own process group (start_new_session): children too
        proc.wait(5)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(5)
    except ProcessLookupError:
        pass


class VirtualDisplay:
    """Context manager: a private X display for one browser, with an on-demand VNC server on a Unix socket.

    Runs in the captcha-browser container (and in browser_check), never next to the API's secrets."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.display = ""
        self.dir: Path | None = None
        self.base_dir = base_dir
        self._xvfb: subprocess.Popen | None = None
        self._vnc: subprocess.Popen | None = None

    def __enter__(self) -> "VirtualDisplay":
        try:
            self.dir = Path(tempfile.mkdtemp(prefix="pf-captcha-", dir=self.base_dir))  # mode 0700: only this user
            self._start_xvfb()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _spawn(self, name: str, args: list[str], **kwargs) -> subprocess.Popen:
        assert self.dir is not None
        with open(self.dir / f"{name}.log", "wb") as log_file:
            return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log_file, stderr=log_file,
                                    start_new_session=True, **kwargs)

    def _log_tail(self, name: str) -> str:
        try:
            return (self.dir / f"{name}.log").read_text(errors="replace")[-500:]  # type: ignore[operator]
        except OSError:
            return ""

    def _start_xvfb(self) -> None:
        # -displayfd: Xvfb picks a free display number itself (no race between jobs) and writes it once ready.
        read, write = os.pipe()
        try:
            self._xvfb = self._spawn("xvfb", ["Xvfb", "-displayfd", str(write), "-screen", "0", f"{WIDTH}x{HEIGHT}x24",
                                              "-nolisten", "tcp"], pass_fds=(write,))
        finally:
            os.close(write)
        try:
            ready, _, _ = select.select([read], [], [], START_TIMEOUT)
            number = os.read(read, 16).decode().strip() if ready else ""
        finally:
            os.close(read)
        if not number.isdigit():
            raise RuntimeError(f"Xvfb did not start: {self._log_tail('xvfb')}")
        self.display = f":{number}"

    @property
    def vnc_socket(self) -> str | None:
        """Unix socket of the running VNC server, None when none is running."""
        if self._vnc is None or self._vnc.poll() is not None or self.dir is None:
            return None
        return str(self.dir / "vnc.sock")

    def start_vnc(self) -> None:
        """Expose the display over VNC, only on a Unix socket in the private directory, no TCP port."""
        if self.vnc_socket:
            return
        assert self.dir is not None
        sock = self.dir / "vnc.sock"
        sock.unlink(missing_ok=True)
        self._vnc = self._spawn("x11vnc", [
            "x11vnc", "-display", self.display, "-unixsock", str(sock),
            # No TCP at all. -rfbport 0 only stops the IPv4 listener; LibVNCServer also opens an IPv6 one
            # (ipv6port, default 5900, on ::1 because of -localhost) unless -rfbportv6 0, and x11vnc has its
            # own IPv6 listener, on by default in Debian, that only -no6 turns off. -localhost / -noipv6 stay
            # as a safety net. browser_check fails if any TCP port appears.
            "-rfbport", "0", "-rfbportv6", "0", "-no6", "-noipv6", "-localhost",
            "-nopw",          # access control is done by the API (ticket + Origin) before the socket is reached
            "-forever",       # the user may close the viewer and reopen it
            "-nevershared",   # a new viewer replaces the previous one
            "-nosel",         # no clipboard exchange between the server's browser and the user's machine
            "-norc", "-nolookup", "-noxdamage", "-xkb", "-quiet",
        ])
        deadline = time.monotonic() + START_TIMEOUT
        while not sock.exists():
            if self._vnc.poll() is not None or time.monotonic() > deadline:
                tail = self._log_tail("x11vnc")
                self.stop_vnc()
                raise RuntimeError(f"x11vnc did not start: {tail}")
            time.sleep(0.1)

    def stop_vnc(self) -> None:
        _stop(self._vnc)
        self._vnc = None
        if self.dir is not None:
            (self.dir / "vnc.sock").unlink(missing_ok=True)

    def close(self) -> None:
        self.stop_vnc()
        _stop(self._xvfb)
        self._xvfb = None
        if self.dir is not None:
            shutil.rmtree(self.dir, ignore_errors=True)
            self.dir = None


class RemoteBrowser:
    """API side of one session on the isolated captcha-browser service (see browser_host.py).

    Same interface as VirtualDisplay for the scraper and the WebSocket bridge (start_vnc, stop_vnc,
    vnc_socket), plus `cdp_url` to drive the remote Chromium with StealthySession(cdp_url=...)."""

    def __init__(self) -> None:
        self.base = os.environ["CAPTCHA_BROWSER_URL"].rstrip("/")
        self.id = ""
        self.cdp_url = ""
        self._socket: str | None = None

    def _call(self, method: str, path: str = "") -> dict:
        request = urllib.request.Request(f"{self.base}/session{path}", method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code == 409:
                raise PublicError(BUSY) from None
            log.error("captcha-browser %s %s: HTTP %s", method, path or "/session", e.code)
        except (OSError, ValueError) as e:
            log.error("captcha-browser connection failed")
        raise PublicError(UNAVAILABLE)

    def __enter__(self) -> "RemoteBrowser":
        data = self._call("POST")
        session_id, port = str(data.get("id", "")), data.get("cdp_port")
        if not SESSION_ID.fullmatch(session_id) or not isinstance(port, int):
            raise PublicError(UNAVAILABLE)
        self.id = session_id
        try:
            # Chromium's DevTools only accepts a Host header that is an IP (or localhost): no service name.
            host = socket.gethostbyname(urlparse(self.base).hostname or "")
        except OSError:
            self.close()
            raise PublicError(UNAVAILABLE) from None
        self.cdp_url = f"http://{host}:{port}"
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @staticmethod
    def context_options() -> dict:
        """Browser context for a human: page as large as the virtual screen, 1:1 pixels, TLS errors NOT ignored."""
        return {"viewport": {"width": WIDTH, "height": HEIGHT - 100}, "screen": {"width": WIDTH, "height": HEIGHT},
                "device_scale_factor": 1, "ignore_https_errors": False}

    @property
    def vnc_socket(self) -> str | None:
        return self._socket

    def start_vnc(self) -> None:
        if self._socket:
            return
        path = Path(str(self._call("POST", f"/{self.id}/vnc").get("socket", "")))
        self._socket = str(path) if _is_session_socket(path) else None
        if not self._socket:
            log.error("captcha-browser returned an unexpected VNC socket path")
            raise PublicError(UNAVAILABLE)

    def stop_vnc(self) -> None:
        if self._socket is None:
            return
        self._socket = None
        try:
            self._call("DELETE", f"/{self.id}/vnc")
        except PublicError:
            pass  # logged; the session is closed right after anyway

    def close(self) -> None:
        self._socket = None
        if self.id:
            try:
                self._call("DELETE", f"/{self.id}")
            except PublicError:
                pass  # logged; captcha-browser also reaps sessions that are too old
            self.id = ""


def _is_session_socket(path: Path) -> bool:
    """Only a Unix socket inside the shared run directory: the API never connects anywhere else."""
    try:
        real = path.resolve(strict=True)
        return real.is_relative_to(RUN_DIR.resolve()) and stat.S_ISSOCK(real.stat().st_mode)
    except (OSError, ValueError):
        return False
