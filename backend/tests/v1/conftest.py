import base64
import hashlib
import json
import os
from uuid import uuid4

import pytest
from app.v1.auth import SCOPES, Actor
from app.v1.db import engine
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


@pytest.fixture
def db_env(monkeypatch):
    admin_url = os.getenv("PF_TEST_ADMIN_URL")
    app_url = os.getenv("PF_TEST_APP_URL")
    if not admin_url or not app_url:
        if os.getenv("PF_REQUIRE_V1_TESTS") == "1":
            pytest.fail("Required v1 PostgreSQL configuration missing")
        pytest.skip(
            "Dedicated PostgreSQL required: PF_TEST_ADMIN_URL and PF_TEST_APP_URL"
        )
    admin = create_engine(admin_url, hide_parameters=True)
    assert admin.url.database.endswith("_test"), (
        "Refusing to modify a non-test database"
    )
    monkeypatch.setenv("V1_DATABASE_URL", app_url)
    monkeypatch.setenv("V1_ENCRYPTION_KEY", base64.b64encode(b"t" * 32).decode())
    monkeypatch.setenv(
        "V1_REDIS_URL", os.getenv("PF_TEST_REDIS_URL", "redis://127.0.0.1:56379/0")
    )
    engine.cache_clear()
    with admin.begin() as conn:
        conn.execute(text("TRUNCATE pf_keys,pf_records,pf_outbox,pf_counters,pf_audit"))
    yield admin
    engine().dispose()
    engine.cache_clear()
    admin.dispose()


@pytest.fixture
def clients(db_env):
    from app.v1 import captcha  # noqa: F401 -- register HTTP/WebSocket routes
    from app.v1.api import app

    clients = []
    for tenant, user, scopes in [
        ("tenant-a", "alice", SCOPES),
        ("tenant-a", "bob", SCOPES),
        ("tenant-b", "alice", SCOPES),
        ("tenant-a", "reader", {"cvs:read"}),
    ]:
        secret = str(uuid4())
        ident = str(uuid4())
        with db_env.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO pf_keys(id,tenant,service,digest,scopes) VALUES(:id,:tenant,:service,:digest,CAST(:scopes AS jsonb))"
                ),
                dict(
                    id=ident,
                    tenant=tenant,
                    service="test",
                    digest=hashlib.sha256(secret.encode()).hexdigest(),
                    scopes=json.dumps(sorted(scopes)),
                ),
            )
        client = TestClient(app)
        client.headers.update(
            {
                "Authorization": "Bearer " + secret,
                "X-PasseFiltre-User-Id": user,
                "Idempotency-Key": str(uuid4()),
            }
        )
        client.actor = Actor(tenant, user, ident, frozenset(scopes))
        clients.append(client)
    yield clients
    for client in clients:
        client.close()
