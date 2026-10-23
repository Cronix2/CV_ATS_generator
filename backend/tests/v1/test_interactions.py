import socket
import threading
import time
from uuid import uuid4

import pytest
from app.v1 import store, worker
from app.v1.auth import Actor
from app.v1.crypto import digest
from app.v1.db import transaction
from app.v1.errors import APIError
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_api import CV, post


def wait_job(client, ident, status):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = client.get("/jobs/" + ident).json()
        if value["status"] == status:
            return value
        time.sleep(0.02)
    pytest.fail("Expected job status " + status)


def test_two_factor_is_owner_scoped_and_code_not_retained(clients, monkeypatch):
    a, b, *_ = clients
    q = post(
        a,
        "/linkedin/extractions",
        dict(
            profile_url="linkedin.com/in/example",
            email="private@example.test",
            password="secret",
        ),
    ).json()

    def execute(kind, payload, actor, hooks, credentials):
        assert hooks.ask_code("Enter code") == "123456"
        return dict(
            profile=CV["profile"],
            session_id=None,
            session_cookies=[
                {"name": "li_at", "value": "cookie-secret", "domain": ".linkedin.com"}
            ],
        )

    monkeypatch.setattr(worker, "execute", execute)
    thread = threading.Thread(
        target=worker.run, args=(q["id"], a.actor.tenant, a.actor.user)
    )
    thread.start()
    wait_job(a, q["id"], "needs_code")
    assert post(b, "/jobs/" + q["id"] + "/code", {"code": "123456"}).status_code == 404
    assert post(a, "/jobs/" + q["id"] + "/code", {"code": "123456"}).status_code == 200
    thread.join(timeout=5)
    assert not thread.is_alive()
    done = wait_job(a, q["id"], "succeeded")
    assert "cookie-secret" not in str(done)
    with transaction(a.actor) as conn:
        data = store.get(conn, "job", q["id"])["data"]
        assert data["secret"] is None and data["code"] is None
    sessions = a.get("/linkedin/sessions").json()
    assert len(sessions) == 1 and "cookies" not in str(sessions)
    assert b.delete("/linkedin/sessions/" + sessions[0]["id"]).status_code == 404
    assert a.delete("/linkedin/sessions/" + sessions[0]["id"]).status_code == 204


@pytest.fixture
def vnc(tmp_path, monkeypatch):
    from app.scraper import captcha

    monkeypatch.setattr(captcha, "RUN_DIR", tmp_path)
    path = str(tmp_path / "vnc.sock")
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
                try:
                    conn.sendall(b"RFB 003.008\n")
                    while data := conn.recv(1024):
                        conn.sendall(data)
                except OSError:
                    pass

    threading.Thread(target=serve, daemon=True).start()
    yield path
    server.close()


def test_captcha_tickets_are_owner_scoped_single_use_and_origin_bound(clients, vnc):
    a, b, *_ = clients
    q = post(
        a,
        "/linkedin/extractions",
        dict(profile_url="linkedin.com/in/example", email="e", password="p"),
    ).json()
    with transaction(a.actor) as conn:
        d = store.get(conn, "job", q["id"])["data"]
        d.update(
            status="needs_captcha",
            captcha_socket=vnc,
            captcha_deadline=time.time() + 300,
        )
        store.update(conn, "job", q["id"], d)
    path = "/jobs/" + q["id"] + "/captcha"
    assert post(b, path + "/ticket", {}).status_code == 404
    ticket = post(a, path + "/ticket", {}).json()
    protocols = ["binary", ticket["protocol"] + ticket["ticket"]]
    with pytest.raises(WebSocketDisconnect):
        with a.websocket_connect(
            path + "/vnc",
            subprotocols=protocols,
            headers={"origin": "https://evil.example"},
        ):
            pass
    with a.websocket_connect(
        path + "/vnc",
        subprotocols=protocols,
        headers={"origin": "http://localhost:3000"},
    ) as ws:
        assert ws.receive_bytes() == b"RFB 003.008\n"
        ws.send_bytes(b"ping")
        assert ws.receive_bytes() == b"ping"
        a.delete("/jobs/" + q["id"])
        with pytest.raises(WebSocketDisconnect):
            ws.receive_bytes()
    with pytest.raises(WebSocketDisconnect):
        with a.websocket_connect(
            path + "/vnc",
            subprotocols=protocols,
            headers={"origin": "http://localhost:3000"},
        ):
            pass


def test_ui_uses_capability_without_exposing_service_key(clients, monkeypatch):
    a = clients[0]
    from app.v1.legacy import router

    monkeypatch.setenv("V1_UI_SERVICE_KEY", a.headers["Authorization"][7:])
    app = FastAPI()
    app.include_router(router)

    @app.exception_handler(APIError)
    async def error(request, exc):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    with TestClient(app) as ui:
        response = ui.post(
            "/api/workflows",
            json={"cv": CV, "offer": {"text": "Python"}, "use_ai": False},
        )
        assert response.status_code == 202, response.text
        q = response.json()
        assert a.headers["Authorization"][7:] not in response.text
        assert ui.get("/api/workflows/jobs/" + q["id"]).status_code == 404
        actor = Actor(
            a.actor.tenant, "ui-" + digest(q["key"]), a.actor.key_id, a.actor.scopes
        )
        worker.run(q["id"], actor.tenant, actor.user)
        headers = {"X-PasseFiltre-Job-Key": q["key"]}
        job = ui.get("/api/workflows/jobs/" + q["id"], headers=headers).json()
        assert job["status"] == "succeeded", job
        ident = job["result"]["resource_id"]
        row = ui.get("/api/workflows/" + ident, headers=headers).json()
        approved = ui.post(
            "/api/workflows/" + ident + "/approve",
            json={
                "version": row["version"],
                "digest": row["data"]["digest"],
                "confirmed": True,
            },
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
        assert approved.status_code == 200, approved.text
        assert (
            ui.get(
                "/api/workflows/" + ident, headers={"X-PasseFiltre-Job-Key": "wrong"}
            ).status_code
            == 404
        )
        assert a.get("/workflows/" + ident).status_code == 404
