"""Isolation test of the remote CAPTCHA browser, with the real compose services (CI: docker and docker-arm64).

    # in captcha-browser: what a compromised browser process could reach
    python -m app.scraper.isolation_check sidecar --forbid HOST:PORT ...
    # in api: end to end through the control interface, CDP, the egress proxy and the VNC socket
    python -m app.scraper.isolation_check api --forbid-url URL ...

Needs internet access for the positive controls (www.linkedin.com through the proxy).
Exit code 0 on success, 1 on failure.
"""

import argparse
import os
import socket
import sys
from pathlib import Path

ALLOWED_URL = "https://www.linkedin.com/robots.txt"
# Must never load in the human-driven browser: other services, private/LAN, metadata, non-allowlisted.
FORBIDDEN_URLS = [
    "http://api:8000/api/health",
    "http://captcha-browser:9300/health",
    "http://127.0.0.1:9300/health",
    "http://localhost:9222/json/version",
    "http://169.254.169.254/latest/meta-data/",
    "http://192.168.1.1/",
    "https://10.0.0.1/",
    "https://example.com/",
    "http://www.linkedin.com/",  # plain HTTP
    "file:///etc/passwd",
]
# Raw TCP from the sidecar (what a compromised Chromium could try): internet, metadata, LAN, host.
FORBIDDEN_ADDRESSES = ["1.1.1.1:443", "8.8.8.8:53", "169.254.169.254:80", "192.168.1.1:80"]
SECRETS = ("PASSEFILTRE_TOKEN",)


def _failures_sidecar(forbid: list[str]) -> list[str]:
    failures = []
    leaked = [k for k in os.environ if k in SECRETS or k.endswith("_API_KEY")]
    if leaked:
        failures.append(f"secrets in the environment: {leaked}")
    sessions = Path("/app/.sessions")
    if sessions.exists() and any(sessions.iterdir()):
        failures.append("/app/.sessions is not empty")
    if "/app/.sessions" in Path("/proc/self/mountinfo").read_text():
        failures.append("the LinkedIn sessions volume is mounted")
    status = Path("/proc/self/status").read_text()
    if "CapEff:\t0000000000000000" not in status or "NoNewPrivs:\t1" not in status:
        failures.append("capabilities left or no-new-privileges missing")
    for target in FORBIDDEN_ADDRESSES + forbid:
        host, _, port = target.rpartition(":")
        try:
            socket.create_connection((host, int(port)), 3).close()
            failures.append(f"reached {target} directly")
        except OSError:
            pass
    # The proxy is the only way out: allowlisted HTTPS yes, anything internal no.
    for target, expected in [("www.linkedin.com:443", b" 200 "), ("api:8000", b" 403 "),
                             ("10.0.0.1:443", b" 403 "), ("localhost:443", b" 403 "),
                             ("example.com:443", b" 403 ")]:
        try:
            with socket.create_connection(("captcha-egress", 3128), 5) as s:
                s.settimeout(15)
                s.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
                answer = s.recv(200).split(b"\r\n", 1)[0] + b" "
        except OSError as e:
            answer = repr(e).encode()
        if expected not in answer:
            failures.append(f"egress CONNECT {target}: {answer!r}, expected {expected!r}")
    return failures


def _failures_api(forbid_urls: list[str]) -> list[str]:
    from scrapling.fetchers import StealthySession

    from app.scraper import captcha

    failures = []
    with captcha.RemoteBrowser() as remote:
        with StealthySession(cdp_url=remote.cdp_url, timeout=30_000, retries=1, google_search=False,
                             additional_args=remote.context_options()) as session:
            page = session.context.new_page()
            for url in FORBIDDEN_URLS + forbid_urls:
                try:
                    response = page.goto(url, timeout=15_000)
                except Exception:
                    continue  # tunnel refused / unreachable: expected
                if response is not None and response.headers.get("x-passefiltre-egress") != "refused":
                    failures.append(f"the CAPTCHA browser loaded {url} (HTTP {response.status})")
            try:
                response = page.goto(ALLOWED_URL, timeout=30_000)
                if response is None or response.headers.get("x-passefiltre-egress"):
                    failures.append(f"{ALLOWED_URL} was not loaded through the proxy")
            except Exception as e:
                failures.append(f"{ALLOWED_URL} unreachable through the proxy: {e}")
        remote.start_vnc()
        workdir = Path(remote.vnc_socket or "").parent
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as vnc:
            vnc.settimeout(10)
            vnc.connect(remote.vnc_socket)
            if not vnc.recv(12).startswith(b"RFB "):
                failures.append("no VNC banner on the shared Unix socket")
        remote.stop_vnc()
    if workdir.exists():
        failures.append("the session directory was not removed from the shared volume")
    with captcha.RemoteBrowser() as again:  # the single slot was released
        if not again.id:
            failures.append("a new session could not be opened after closing the first one")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("side", choices=["sidecar", "api"])
    parser.add_argument("--forbid", action="append", default=[], help="HOST:PORT the sidecar must not reach")
    parser.add_argument("--forbid-url", action="append", default=[], help="URL the CAPTCHA browser must not load")
    args = parser.parse_args(argv)
    failures = _failures_sidecar(args.forbid) if args.side == "sidecar" else _failures_api(args.forbid_url)
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    if not failures:
        print(f"OK: CAPTCHA browser isolation ({args.side}).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
