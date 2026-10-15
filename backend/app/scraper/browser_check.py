"""Real browser smoke test for the API image.

Scrapling's StealthySession (the LinkedIn scraper) drives Chromium through *Patchright*, not
Playwright. Both libraries are installed (Scrapling depends on both) and each pins its own Chromium
revision, so the image must contain the revision Patchright expects. This check proves it does,
then starts that browser for real through StealthySession and loads a local page.

    python -m app.scraper.browser_check           # full check: launch + navigation (CI, deploy)
    python -m app.scraper.browser_check --static  # only the expected executable (image build)

Exit code 0 on success, 1 on failure. No network access is needed (the page is served on
127.0.0.1) and nothing outside a temporary profile directory is written.
"""

import argparse
import http.server
import os
import platform
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
    nodes = page.css("#marker")
    text = str(nodes[0].get_all_text()) if nodes else ""
    if page.status != 200 or MARKER not in text:
        raise RuntimeError(f"unexpected page (status {page.status}, marker found: {MARKER in text})")


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
