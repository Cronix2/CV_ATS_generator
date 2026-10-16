"""Isolation test of the remote CAPTCHA browser, with the real compose services (CI: docker and docker-arm64).

    # in captcha-browser: what a compromised browser process could reach
    python -m app.scraper.isolation_check sidecar --forbid HOST:PORT ...
    # in api: end to end through the control interface, CDP, the egress proxy and the VNC socket
    python -m app.scraper.isolation_check api --forbid-url URL ...

Needs internet access for the positive controls (www.linkedin.com through the proxy).
Exit code 0 on success, 1 on failure. Every step is logged with its duration and has a time budget:
past it, faulthandler dumps the stacks and exits 1 (an unfinished check is a failure, never a pass).
"""

import argparse
import errno
import faulthandler
import os
import socket
import sys
import time
from contextlib import contextmanager
from pathlib import Path

# Plain HTTP on purpose: Chromium must upgrade it (HSTS) since the proxy only tunnels HTTPS.
ALLOWED_URL = "http://www.linkedin.com/"
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
    "file:///etc/passwd",
]
# Raw TCP from the sidecar (what a compromised Chromium could try): internet, metadata, LAN, host.
FORBIDDEN_ADDRESSES = ["1.1.1.1:443", "8.8.8.8:53", "169.254.169.254:80", "192.168.1.1:80"]
# The internal network has no route at all: anything else (refused = reachable, timeout = unknown) fails.
NO_ROUTE = {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EACCES, errno.EPERM}
# Chromium errors that prove a block: proxy refused the tunnel, or the file:// policy.
BLOCKED_ERRORS = ("net::ERR_TUNNEL_CONNECTION_FAILED", "net::ERR_BLOCKED_BY_ADMINISTRATOR")
SECRETS = ("PASSEFILTRE_TOKEN",)
_started = time.monotonic()


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')} +{time.monotonic() - _started:6.1f}s] {message}", flush=True)


@contextmanager
def step(name: str, budget: float):
    """Log the step and its duration; past `budget` seconds dump every stack and exit 1."""
    log(f"{name} (limit {budget:.0f}s)")
    start = time.monotonic()
    faulthandler.dump_traceback_later(budget, exit=True)
    try:
        yield
    except BaseException as e:
        log(f"{name}: error after {time.monotonic() - start:.1f}s: {type(e).__name__}")
        raise
    finally:
        faulthandler.cancel_dump_traceback_later()
    log(f"{name}: done in {time.monotonic() - start:.1f}s")


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
        with step(f"direct TCP {target}", 15):
            try:
                socket.create_connection((host, int(port)), 5).close()
                failures.append(f"reached {target} directly")
            except OSError as e:
                log(f"  -> {e!r}")
                if e.errno not in NO_ROUTE:  # incl. timeout: not proven unreachable
                    failures.append(f"direct TCP {target}: {e!r}, expected no route")
    # The proxy is the only way out: allowlisted HTTPS yes, anything internal no.
    for target, expected in [("www.linkedin.com:443", b" 200 "), ("api:8000", b" 403 "),
                             ("10.0.0.1:443", b" 403 "), ("localhost:443", b" 403 "),
                             ("example.com:443", b" 403 ")]:
        with step(f"egress CONNECT {target}", 30):
            try:
                with socket.create_connection(("captcha-egress", 3128), 5) as s:
                    s.settimeout(15)
                    s.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
                    answer = s.recv(200).split(b"\r\n", 1)[0] + b" "
            except OSError as e:
                answer = repr(e).encode()
            log(f"  -> {answer.strip()!r}")
            if expected not in answer:
                failures.append(f"egress CONNECT {target}: {answer!r}, expected {expected!r}")
    return failures


def _failures_api(forbid_urls: list[str]) -> list[str]:
    from scrapling.fetchers import StealthySession

    from app.scraper import captcha

    failures = []
    with step("open an isolated browser session", 90):
        remote = captcha.RemoteBrowser().__enter__()
    try:
        with step("connect over CDP", 60):
            session = StealthySession(cdp_url=remote.cdp_url, timeout=30_000, retries=1, google_search=False,
                                      additional_args=remote.context_options()).__enter__()
            session.context.set_default_timeout(20_000)
        try:
            with step("new page", 30):
                page = session.context.new_page()
            for url in FORBIDDEN_URLS + forbid_urls:
                with step(f"must not load {url}", 25):
                    try:
                        response = page.goto(url, timeout=15_000)
                    except Exception as e:
                        reason = str(e).splitlines()[0]
                        log(f"  -> {reason}")
                        if not any(b in reason for b in BLOCKED_ERRORS):  # incl. timeout: not proven blocked
                            failures.append(f"could not verify that {url} is blocked: {reason}")
                        continue
                    refused = response is not None and response.headers.get("x-passefiltre-egress") == "refused"
                    log(f"  -> HTTP {response.status if response else None}, refused by egress: {refused}")
                    if not refused:
                        failures.append(f"the CAPTCHA browser loaded {url} (HTTP {response and response.status})")
            for attempt in (1, 2):  # LinkedIn itself may reset a runner's connection once
                # Same page: a second new_page() (no timeout in Playwright) hung on the CI runners.
                with step(f"must load {ALLOWED_URL} (attempt {attempt})", 60):
                    try:
                        response = page.goto(ALLOWED_URL, timeout=30_000)
                    except Exception as e:
                        error = f"{ALLOWED_URL} unreachable through the proxy: {str(e).splitlines()[0]}"
                        log(f"  -> {error}")
                        continue
                    log(f"  -> HTTP {response and response.status} {response and response.url}")
                    error = None
                    if response is None or response.headers.get("x-passefiltre-egress"):
                        error = f"{ALLOWED_URL} was not loaded through the proxy"
                    elif not response.url.startswith("https://"):
                        error = f"{ALLOWED_URL} was loaded over plain HTTP"
                    break
            if error:
                failures.append(error)
        finally:
            with step("disconnect CDP", 60):
                session.__exit__(None, None, None)
        with step("VNC over the shared Unix socket", 90):
            remote.start_vnc()
            workdir = Path(remote.vnc_socket or "").parent
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as vnc:
                vnc.settimeout(10)
                vnc.connect(remote.vnc_socket)
                if not vnc.recv(12).startswith(b"RFB "):
                    failures.append("no VNC banner on the shared Unix socket")
            remote.stop_vnc()
    finally:
        with step("close the isolated browser session", 90):
            remote.__exit__(None, None, None)
    if workdir.exists():
        failures.append("the session directory was not removed from the shared volume")
    with step("open and close a second session", 180):
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
    log(f"isolation check ({args.side})")
    failures = _failures_sidecar(args.forbid) if args.side == "sidecar" else _failures_api(args.forbid_url)
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    if not failures:
        print(f"OK: CAPTCHA browser isolation ({args.side}).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
