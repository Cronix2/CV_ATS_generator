"""Remote CAPTCHA solving: a private virtual screen (Xvfb) shown through VNC (x11vnc) for one job.

In Docker there is no screen: the scraper runs headless. When LinkedIn puts a CAPTCHA in front of the
login, the scraper reopens its browser *headful* on a private Xvfb display; once the CAPTCHA is on
screen, x11vnc exposes that same display on a Unix socket inside a private 0700 directory (never a
TCP port). The API bridges an authenticated WebSocket to that socket (what websockify would do) and
the UI shows it with noVNC. A human solves the CAPTCHA; the scraper only resumes once LinkedIn itself
has left its checkpoint page. Every process and file is removed when the display is closed.
"""

import logging
import os
import select
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from app.security import PublicError

log = logging.getLogger(__name__)

WIDTH, HEIGHT = 1280, 900  # small framebuffer (~4.5 MB): fine for a Raspberry Pi
START_TIMEOUT = 10

# One virtual screen + headful Chromium at a time by default: memory on the Raspberry Pi.
_sessions = threading.BoundedSemaphore(max(1, int(os.getenv("MAX_CAPTCHA_SESSIONS", "1"))))


def available() -> bool:
    """Remote CAPTCHA solving needs Xvfb and x11vnc (installed in the Docker image). INTERACTIVE_CAPTCHA=0 disables it."""
    return os.getenv("INTERACTIVE_CAPTCHA", "1") != "0" and all(shutil.which(b) for b in ("Xvfb", "x11vnc"))


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
    """Context manager: a private X display for one browser, with an on-demand VNC server on a Unix socket."""

    def __init__(self) -> None:
        self.display = ""
        self.dir: Path | None = None
        self._xvfb: subprocess.Popen | None = None
        self._vnc: subprocess.Popen | None = None
        self._slot: threading.BoundedSemaphore | None = None

    def __enter__(self) -> "VirtualDisplay":
        slots = _sessions
        if not slots.acquire(blocking=False):
            raise PublicError("Une autre résolution de CAPTCHA est déjà en cours sur ce serveur : réessayez dans quelques minutes.")
        self._slot = slots
        try:
            self.dir = Path(tempfile.mkdtemp(prefix="pf-captcha-"))  # mode 0700: only this user
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

    def browser_options(self) -> dict:
        """StealthySession options that put Chromium on this display, headful, filling the screen."""
        return {
            "additional_args": {"env": {**os.environ, "DISPLAY": self.display}},
            "extra_flags": ["--window-position=0,0", f"--window-size={WIDTH},{HEIGHT}"],
        }

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
            # No TCP at all: -rfbport 0 only stops the IPv4 listener; Debian builds x11vnc with its own IPv6
            # listener on by default (port 5900, on ::1 because of -localhost), which only -no6 turns off.
            # -localhost / -noipv6 stay as a safety net. browser_check fails if any TCP port appears.
            "-rfbport", "0", "-no6", "-noipv6", "-localhost",
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
        if self._slot is not None:
            self._slot.release()
            self._slot = None
