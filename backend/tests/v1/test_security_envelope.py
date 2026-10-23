from app.security import SecurityMiddleware
from app.v1.crypto import secret_fingerprint
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_parent_security_keeps_v1_errors_structured(monkeypatch):
    monkeypatch.setenv("API_V1_ENABLED", "1")
    app = FastAPI()
    app.add_middleware(SecurityMiddleware)
    with TestClient(app) as client:
        for headers, status in [({"Origin": "https://evil.invalid"}, 403), ({}, 415)]:
            response = client.post("/api/v1/cvs", content="private", headers=headers)
            assert response.status_code == status
            assert set(response.json()) == {"code", "message", "request_id"}
            assert response.headers["x-request-id"] == response.json()["request_id"]
            assert response.headers["cache-control"] == "no-store"
            assert "private" not in response.text
        legacy = client.post("/api/export", content="private")
        assert legacy.status_code == 415 and "detail" in legacy.json()


def test_credential_fingerprint_requires_server_key(monkeypatch):
    import base64

    monkeypatch.setenv("V1_ENCRYPTION_KEY", base64.b64encode(b"a" * 32).decode())
    first = secret_fingerprint({"password": "private"})
    assert first == secret_fingerprint({"password": "private"})
    monkeypatch.setenv("V1_ENCRYPTION_KEY", base64.b64encode(b"b" * 32).decode())
    assert first != secret_fingerprint({"password": "private"})
