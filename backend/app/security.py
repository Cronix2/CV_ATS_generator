"""API access control: token, allowed hosts and origins, network-mode safety checks, audit log."""

import hashlib
import ipaddress
import logging
import os
import secrets
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import HTTPConnection, Request
from starlette.responses import JSONResponse, Response

# Reachable without the token: the UI needs them to know whether a token is required.
PUBLIC_PATHS = {"/api/health", "/api/config"}
TOKEN_HEADER = "X-PasseFiltre-Token"
JOB_KEY_HEADER = "X-PasseFiltre-Job-Key"  # per-job owner secret (see jobs.Job.key)
MIN_NETWORK_TOKEN_LENGTH = 32
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",  # responses carry personal data
}
LOCAL_NAMES = {"localhost", "127.0.0.1", "::1"}

audit_log = logging.getLogger("passefiltre.audit")


class PublicError(Exception):
    """An error whose message is written for the user and safe to return (no internals)."""


# --------------------------------------------------------------------------- configuration

def api_token() -> str:
    return os.getenv("PASSEFILTRE_TOKEN", "").strip()


def cors_origins() -> list[str]:
    return [o.strip() for o in (os.getenv("CORS_ORIGINS") or "http://localhost:3000,http://127.0.0.1:3000").split(",")
            if o.strip()]


def allowed_hosts() -> list[str]:
    """Host headers the API answers to (blocks DNS rebinding). ALLOWED_HOSTS=* disables the check."""
    api_host = urlparse(os.getenv("NEXT_PUBLIC_API_URL", "")).hostname
    extra = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
    return sorted({"localhost", "127.0.0.1", *([api_host] if api_host else []), *extra})


def _is_loopback(host: str) -> bool:
    host = host.strip().strip("[]")
    if host in LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def network_exposed() -> bool:
    """True as soon as the configuration lets other machines reach PasseFiltre."""
    binds = [os.getenv("BIND_ADDRESS", ""), os.getenv("BACKEND_HOST", "")]
    return (any(b and not _is_loopback(b) for b in binds)
            or any(h == "*" or not _is_loopback(h) for h in allowed_hosts()))


def assert_safe_config() -> None:
    """Refuse to start an API reachable from the network without a strong access token."""
    if not network_exposed():
        return
    token = api_token()
    if len(token) < MIN_NETWORK_TOKEN_LENGTH:
        raise RuntimeError(
            "PasseFiltre est configuré pour être accessible depuis le réseau (BIND_ADDRESS, BACKEND_HOST, "
            f"ALLOWED_HOSTS ou NEXT_PUBLIC_API_URL) : définissez PASSEFILTRE_TOKEN (au moins {MIN_NETWORK_TOKEN_LENGTH} "
            "caractères aléatoires, ex. `python -c \"import secrets; print(secrets.token_urlsafe(32))\"`).")


# --------------------------------------------------------------------------- request helpers

def client_ip(request: HTTPConnection) -> str:
    # Behind the HTTPS proxy, uvicorn --proxy-headers already puts the real client in request.client.
    return request.client.host if request.client else "?"


def is_local_client(request: Request) -> bool:
    return _is_loopback(client_ip(request))


def token_required(request: HTTPConnection) -> bool:
    """The token protects against the outside world, not the home network: clients on a private network
    (LAN, this machine) skip it unless TRUST_LAN=0. Behind Caddy the client IP is reliable (it overwrites
    X-Forwarded-For). ponytail: trusts every private range; set TRUST_LAN=0 before adding a tunnel/VPN proxy."""
    if not api_token():
        return False
    if os.getenv("TRUST_LAN", "1") == "0":
        return True
    try:
        ip = ipaddress.ip_address(client_ip(request))
    except ValueError:
        return True
    return not (ip.is_private or ip.is_loopback)


def pseudonym(value: str) -> str:
    """Stable, non-reversible tag for audit logs (never log raw emails)."""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()[:12]


def audit(request: HTTPConnection, action: str, **details: object) -> None:
    """One line per sensitive action. Never pass passwords, API keys or CV content here."""
    # Only bounded technical metadata; URLs, profile handles and client IPs are personal data.
    safe = {k: v for k, v in details.items() if k in {"job", "removed", "show_browser", "origin_ok", "instruction_chars", "account"}}
    fields = " ".join(f"{k}={v}" for k, v in safe.items())
    audit_log.info("action=%s client_ref=%s %s", action, pseudonym(client_ip(request)), fields)


# --------------------------------------------------------------------------- middleware

class SecurityMiddleware(BaseHTTPMiddleware):
    """Token check, cross-site request blocking and security headers for every API route."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path, method = request.url.path, request.method
        if path.startswith("/api/") and method != "OPTIONS":
            # Cross-site requests: a browser always sends Origin on POST/DELETE; only our UI may call the API.
            origin = request.headers.get("origin")
            if method in ("POST", "PUT", "PATCH", "DELETE") and origin and origin not in cors_origins():
                return self._deny(403, "Origine non autorisée.")
            # A JSON content type forces the CORS preflight, so "simple" cross-site POSTs are impossible.
            if method == "POST" and not request.headers.get("content-type", "").startswith("application/json"):
                return self._deny(415, "Content-Type application/json requis.")
            if path not in PUBLIC_PATHS and not (os.getenv("API_V1_ENABLED") == "1" and (path == "/api/v1" or path.startswith("/api/v1/"))) and token_required(request):
                given = request.headers.get(TOKEN_HEADER, "")
                if not secrets.compare_digest(given.encode(), api_token().encode()):
                    audit(request, "token_refused", path=path)
                    return self._deny(401, "Jeton d'accès manquant ou invalide.")
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    @staticmethod
    def _deny(status: int, message: str) -> JSONResponse:
        return JSONResponse({"detail": message}, status_code=status, headers=SECURITY_HEADERS)


TokenMiddleware = SecurityMiddleware  # previous name
