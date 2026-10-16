"""Real browser smoke test for the API image.

Scrapling's StealthySession (the LinkedIn scraper) drives Chromium through *Patchright*, not
Playwright. Both libraries are installed (Scrapling depends on both) and each pins its own Chromium
revision, so the image must contain the revision Patchright expects. This check proves it does,
then starts that browser for real through StealthySession and loads a local page.

    python -m app.scraper.browser_check           # full check: launch + navigation (CI, deploy)
    python -m app.scraper.browser_check --static  # only the expected executable (image build)

When Xvfb and x11vnc are installed (Docker image), the full check also runs the remote CAPTCHA path of
the captcha-browser service (browser_host.py): a headful Chromium with a fresh profile on a private
virtual display, driven over CDP, then the VNC server on its Unix socket (RFB banner read, no TCP port
opened), then checks that every process and temporary file is gone. Its network isolation needs the
compose services: python -m app.scraper.isolation_check.

Exit code 0 on success, 1 on failure. No network access is needed (the page is served on
127.0.0.1) and nothing outside a temporary profile directory is written.
"""

import argparse
import http.server
import os
import platform
import shutil
import socket
import sys
import tempfile
import threading
from importlib.metadata import version

MARKER = "passefiltre-browser-check-ok"


def expected_executable() -> str:
    """Chromium executable that Patchright (hence StealthySession) will launch."""
    from patchright.sync_api import sync_playwright

    with sync_playwright() as p:
        return p.chromium.executable_path


def _serve() -> tuple[http.server.HTTPServer, str]:
    body = f"<!doctype html><title>check</title><p id='marker'>{MARKER}</p>".encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def _check_page(page) -> None:
    nodes = page.css("#marker")
    text = str(nodes[0].get_all_text()) if nodes else ""
    if page.status != 200 or MARKER not in text:
        raise RuntimeError(f"unexpected page (status {page.status}, marker found: {MARKER in text})")


def launch_check() -> None:
    """Start Chromium exactly like the scraper does (StealthySession, persistent profile)."""
    from scrapling.fetchers import StealthySession

    server, url = _serve()
    try:
        with tempfile.TemporaryDirectory(prefix="pf-browser-check-") as profile, StealthySession(
            headless=True, user_data_dir=profile, timeout=60_000, retries=1, google_search=False,
        ) as session:
            page = session.fetch(url)
    finally:
        server.shutdown()
    _check_page(page)


def _readable(entry: str) -> str:
    """'0100007F:170C' / '000...01000000:170C' from /proc/net/tcp* -> '127.0.0.1:5900' / '[::1]:5900'."""
    addr, port = entry.split(":")
    raw = bytes.fromhex(addr)
    raw = b"".join(raw[i:i + 4][::-1] for i in range(0, len(raw), 4))  # 32-bit words, host byte order
    host = socket.inet_ntop(socket.AF_INET6 if len(raw) == 16 else socket.AF_INET, raw)
    return f"[{host}]:{int(port, 16)}" if len(raw) == 16 else f"{host}:{int(port, 16)}"


def _tcp_listeners() -> set[str]:
    """Listening TCP sockets of this network namespace (Linux /proc).

    Any new one fails the check, loopback included: the VNC server has no password (access control
    is the API ticket in front of the Unix socket), so even 127.0.0.1 / ::1 would let any local
    process bypass it.
    """
    found = set()
    for name in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(name) as f:
                found |= {line.split()[1] for line in f.readlines()[1:] if line.split()[3] == "0A"}
        except OSError:
            pass
    return found


def display_check(executable: str) -> None:
    """Remote CAPTCHA path, as in captcha-browser: headful Chromium on a private Xvfb display, driven over
    CDP, shown by x11vnc on a Unix socket. No proxy here: the page is served on 127.0.0.1."""
    from scrapling.fetchers import StealthySession

    from app.scraper.browser_host import Session
    from app.scraper.captcha import RemoteBrowser

    server, url = _serve()
    session = None
    try:
        session = Session(executable, proxy=None, run_dir=None)
        workdir, profile = session.display.dir, session.profile
        with StealthySession(cdp_url=f"http://127.0.0.1:{session.devtools_port}", timeout=60_000, retries=1,
                             google_search=False, additional_args=RemoteBrowser.context_options()) as browser:
            _check_page(browser.fetch(url))
        before = _tcp_listeners()
        session.display.start_vnc()
        opened = _tcp_listeners() - before
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as vnc:
            vnc.settimeout(10)
            vnc.connect(session.display.vnc_socket)
            banner = vnc.recv(12)
        if not banner.startswith(b"RFB "):
            raise RuntimeError(f"no VNC banner on the Unix socket (got {banner!r})")
        if opened:
            raise RuntimeError(f"the VNC server opened TCP ports: {sorted(map(_readable, opened))}")
    finally:
        server.shutdown()
        if session is not None:
            session.close()
    if (workdir is not None and workdir.exists()) or (profile is not None and profile.exists()):
        raise RuntimeError("the virtual display or the browser profile was not removed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--static", action="store_true", help="only check the expected executable, do not launch")
    args = parser.parse_args(argv)

    print(f"arch={platform.machine()} patchright={version('patchright')} "
          f"playwright={version('playwright')} scrapling={version('scrapling')}")
    try:
        path = expected_executable()
    except Exception as e:
        print(f"FAIL: cannot query Patchright for its Chromium: {e}", file=sys.stderr)
        return 1
    print(f"patchright expects: {path}")
    if not (os.path.isfile(path) and os.access(path, os.X_OK)):
        print("FAIL: this Chromium is missing. Install it with the driver StealthySession uses: "
              "`python -m patchright install --with-deps chromium` (NOT `playwright install`).", file=sys.stderr)
        return 1
    if args.static:
        print("OK: Patchright's Chromium is installed.")
        return 0
    try:
        launch_check()
    except Exception as e:
        print(f"FAIL: Chromium did not start or render through StealthySession: {e}", file=sys.stderr)
        return 1
    print("OK: Chromium started through StealthySession and rendered a page.")
    if not (shutil.which("Xvfb") and shutil.which("x11vnc")):
        print("SKIP: remote CAPTCHA display (Xvfb/x11vnc missing).")
        return 0
    try:
        display_check(path)
    except Exception as e:
        print(f"FAIL: remote CAPTCHA browser (Xvfb + headful Chromium over CDP + x11vnc): {e}", file=sys.stderr)
        return 1
    print("OK: isolated CAPTCHA browser: fresh profile, private Xvfb display, CDP, VNC on a Unix socket only, "
          "cleaned up after use.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
