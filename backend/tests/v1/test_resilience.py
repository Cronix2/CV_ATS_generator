import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from app.v1 import store, worker
from app.v1.db import sql, transaction
from test_api import CV, post, run


def test_same_body_without_item_ids_is_idempotent(clients):
    a = clients[0]
    key = str(uuid4())
    body = {"cv": {"profile": {"experience": [{"title": "Engineer"}]}}}
    one = post(a, "/cvs", body, key)
    two = post(a, "/cvs", body, key)
    assert one.status_code == two.status_code == 201
    assert one.json()["id"] == two.json()["id"]


def test_duplicate_ids_and_malformed_input_rejected(clients):
    a = clients[0]
    for cv in ([], "secret", {"profile": {"skills": [{"id": "a"}, {"id": "a"}]}}):
        assert post(a, "/cvs", {"cv": cv}).status_code == 422


def test_concurrent_idempotency(clients):
    a = clients[0]
    key = str(uuid4())
    with ThreadPoolExecutor(4) as pool:
        results = list(
            pool.map(lambda _: post(a, "/exports", {"cv": CV}, key), range(4))
        )
    assert all(r.status_code == 202 for r in results)
    assert len({r.json()["id"] for r in results}) == 1


def test_cancel_during_execution_discards_result(clients, monkeypatch):
    a = clients[0]
    q = post(a, "/exports", {"cv": CV}).json()
    original = worker.execute

    def execute(*args):
        result = original(*args)
        a.delete("/jobs/" + q["id"])
        return result

    monkeypatch.setattr(worker, "execute", execute)
    assert run(a, q)["status"] == "cancelled"
    with transaction(a.actor) as conn:
        assert store.listing(conn, "export") == []


def test_transient_retry_bounded(clients, monkeypatch):
    a = clients[0]
    q = post(a, "/exports", {"cv": CV}).json()
    monkeypatch.setattr(
        worker, "execute", lambda *args: (_ for _ in ()).throw(TimeoutError("secret"))
    )
    assert run(a, q)["status"] == "queued"
    assert run(a, q)["status"] == "queued"
    failed = run(a, q)
    assert failed["status"] == "failed" and failed["attempt"] == 3
    assert "secret" not in str(failed)


def test_expired_secrets_and_results_are_purged(clients, db_env):
    a = clients[0]
    q = post(
        a,
        "/linkedin/extractions",
        dict(
            profile_url="linkedin.com/in/example",
            email="private@example.test",
            password="secret",
        ),
    ).json()
    with transaction(a.actor) as conn:
        d = store.get(conn, "job", q["id"])["data"]
        d["secret_expires"] = time.time() - 1
        store.update(conn, "job", q["id"], d)
        exp = store.create(conn, a.actor, "export", {}, ttl=-1)
    worker.purge()
    with transaction(a.actor) as conn:
        assert store.get(conn, "job", q["id"])["data"]["secret"] is None
        assert (
            sql(
                conn, "SELECT count(*) FROM pf_records WHERE id=:id", id=exp["id"]
            ).scalar()
            == 0
        )
    failed = run(a, q)
    assert failed["error"]["code"] == "credentials_expired"


def test_missing_job_after_expiry_is_not_disclosed(clients):
    a, b, *_ = clients
    q = post(a, "/exports", {"cv": CV}).json()
    with transaction(a.actor) as conn:
        sql(
            conn,
            "UPDATE pf_records SET expires_at=now()-interval '1 second' WHERE id=:id",
            id=q["id"],
        )
    assert (
        a.get("/jobs/" + q["id"]).status_code
        == b.get("/jobs/" + q["id"]).status_code
        == 404
    )


def test_old_worker_cannot_publish_after_lease_replaced(clients, monkeypatch):
    a = clients[0]
    q = post(a, "/exports", {"cv": CV}).json()
    original = worker.execute

    def execute(*args):
        result = original(*args)
        with transaction(a.actor) as conn:
            d = store.get(conn, "job", q["id"])["data"]
            d.update(lease=str(uuid4()), status="queued")
            store.update(conn, "job", q["id"], d)
        return result

    monkeypatch.setattr(worker, "execute", execute)
    assert run(a, q)["status"] == "queued"
    with transaction(a.actor) as conn:
        assert store.listing(conn, "export") == []


def test_real_redis_worker_loss_and_recovery(clients, tmp_path, monkeypatch):
    redis_url = os.getenv("PF_TEST_REDIS_URL")
    if not redis_url:
        if os.getenv("PF_REQUIRE_V1_TESTS") == "1":
            pytest.fail("Required v1 Redis configuration missing")
        pytest.skip("Set PF_TEST_REDIS_URL for real Celery recovery test")
    from redis import Redis

    redis = Redis.from_url(redis_url)
    # A dedicated test Redis DB only. CI and local harness reserve it exclusively.
    redis.flushdb()
    worker.celery.conf.broker_url = redis_url
    a = clients[0]
    q = post(a, "/exports", {"cv": CV}).json()
    env = {**os.environ, "V1_REDIS_URL": redis_url}
    script = """import time
from app.v1 import worker
original=worker.execute
worker.execute=lambda *args: (time.sleep(30),original(*args))[1]
worker.celery.worker_main(['worker','--pool=solo','--concurrency=1','--loglevel=CRITICAL','--without-heartbeat','--without-gossip','--without-mingle'])
"""
    log = (tmp_path / "worker.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, "-c", script], env=env, stdout=log, stderr=log
    )

    def wait_for(status, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = a.get("/jobs/" + q["id"]).json()
            if current["status"] == status:
                return current
            time.sleep(0.2)
        pytest.fail("Worker did not reach " + status)

    try:
        worker.dispatch()
        wait_for("running")
        proc.kill()
        proc.wait(timeout=5)
        # Advance the persisted lease clock instead of sleeping for 90 seconds.
        with transaction(a.actor) as conn:
            d = store.get(conn, "job", q["id"])["data"]
            d["heartbeat"] = time.time() - 100
            store.update(conn, "job", q["id"], d)
        with worker.transaction() as conn:
            sql(conn, "UPDATE pf_outbox SET published_at=NULL")
        # Model broker data loss: the durable outbox must reconstruct delivery.
        redis.flushdb()
        worker.dispatch()
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "app.v1.worker:celery",
                "worker",
                "--pool=solo",
                "--concurrency=1",
                "--loglevel=CRITICAL",
                "--without-heartbeat",
                "--without-gossip",
                "--without-mingle",
            ],
            env=env,
            stdout=log,
            stderr=log,
        )
        done = wait_for("succeeded")
        assert done["attempt"] == 2
        with transaction(a.actor) as conn:
            assert len(store.listing(conn, "export")) == 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        log.close()
        redis.flushdb()


def test_conversation_can_continue_and_delete_after_job_expiry(clients):
    a = clients[0]
    for continue_first in (True, False):
        conversation = post(a, "/conversations", {"cv": CV}).json()
        path = "/conversations/" + conversation["id"]
        job = post(
            a, path + "/messages", {"instruction": "Review the existing facts"}
        ).json()
        with transaction(a.actor) as conn:
            sql(
                conn,
                "UPDATE pf_records SET expires_at=now()-interval '1 second' WHERE id=:id",
                id=job["id"],
            )
        if continue_first:
            assert (
                post(
                    a, path + "/messages", {"instruction": "Continue reviewing"}
                ).status_code
                == 202
            )
        assert a.delete(path).status_code == 204
