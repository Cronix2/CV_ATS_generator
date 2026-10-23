"""In-memory background jobs for scraping (a scrape takes ~1 min and may need a 2FA code or a CAPTCHA)."""

import logging
import os
import secrets
import threading
import time
from typing import Any, Callable
from uuid import uuid4

from app.security import PublicError

log = logging.getLogger(__name__)

JOB_TTL = 3600
TICKET_TTL = 60  # a CAPTCHA viewer ticket must be used right away, and only once
CANCELLED = "Tâche annulée."


class Job:
    def __init__(self) -> None:
        self.id = uuid4().hex
        # Owner secret, given only to whoever started the job: every /api/jobs/<id> call must present it,
        # so the shared PASSEFILTRE_TOKEN is not enough to read or control someone else's job.
        self.key = secrets.token_urlsafe(32)
        self.created = time.time()
        self.status = "running"  # running | needs_code | needs_captcha | done | error
        self.percent = 0
        self.messages: list[str] = []
        self.prompt = ""
        self.result: Any = None
        self.error = ""
        self.display: Any = None  # captcha.RemoteBrowser while a CAPTCHA is shown
        self.captcha_deadline = 0.0
        self._code: str | None = None
        self._code_event = threading.Event()
        self._cancel = threading.Event()
        self._tickets: dict[str, float] = {}
        self._lock = threading.Lock()

    def owned_by(self, key: str) -> bool:
        return secrets.compare_digest(key.encode(), self.key.encode())

    # Hooks used by the scraper
    def progress(self, message: str, percent: int | None = None) -> None:
        self.messages.append(message)
        if percent is not None:
            self.percent = percent

    def ask_code(self, message: str) -> str | None:
        self._code, self.prompt, self.status = None, message, "needs_code"
        self._code_event.clear()
        if not self.cancelled():
            self._code_event.wait(timeout=300)
        self.status, self.prompt = "running", ""
        return None if self.cancelled() else self._code

    def submit_code(self, code: str) -> None:
        self._code = code
        self._code_event.set()

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()
        self._code_event.set()  # wakes a pending ask_code

    def captcha_open(self, display: Any, deadline: float) -> None:
        self.display, self.captcha_deadline = display, deadline
        self.prompt = "LinkedIn demande un CAPTCHA : résolvez-le vous-même dans le navigateur à distance."
        self.status = "needs_captcha"

    def captcha_closed(self) -> None:
        with self._lock:
            self._tickets.clear()
        self.display = None
        if self.status == "needs_captcha":
            self.status, self.prompt = "running", ""

    # Single-use tickets that let the owner's browser open the CAPTCHA viewer WebSocket
    # (a browser WebSocket cannot send the token headers).
    def issue_ticket(self) -> str:
        ticket, now = secrets.token_urlsafe(32), time.time()
        with self._lock:
            self._tickets = {t: exp for t, exp in self._tickets.items() if exp > now}
            self._tickets[ticket] = now + TICKET_TTL
        return ticket

    def redeem_ticket(self, ticket: str) -> bool:
        with self._lock:
            expires = self._tickets.pop(ticket, 0.0) if ticket else 0.0
        return expires > time.time() and self.status == "needs_captcha"

    def to_dict(self) -> dict:
        captcha = self.status == "needs_captcha"
        return {
            "id": self.id, "status": self.status, "percent": self.percent,
            "messages": self.messages[-20:], "prompt": self.prompt,
            "error": self.error, "result": self.result,
            "captcha_expires_in": max(0, int(self.captcha_deadline - time.time())) if captcha else None,
        }


_jobs: dict[str, Job] = {}
# Each job holds a Chromium or a series of LLM calls: cap how many run at once (memory and cost).
_slots = threading.BoundedSemaphore(max(1, int(os.getenv("MAX_JOBS", "2"))))


class Busy(Exception):
    pass


def start(target: Callable[[Job], Any]) -> Job:
    slots = _slots  # release exactly the semaphore we acquired
    if not slots.acquire(blocking=False):
        raise Busy("Trop de tâches en cours (extraction ou agent IA) : réessayez dans un instant.")
    shared_capacity = None
    if os.getenv("API_V1_ENABLED") == "1":
        from app.v1.worker import capacity
        from app.v1.errors import APIError
        try:
            shared_capacity = capacity()
            shared_capacity.__enter__()
        except Exception as exc:
            slots.release()
            if isinstance(exc, APIError) and exc.code == "busy":
                raise Busy("Trop de tâches en cours : réessayez dans un instant.") from None
            raise
    for jid in [j for j, job in _jobs.items() if time.time() - job.created > JOB_TTL]:
        _jobs.pop(jid, None)
    job = Job()
    _jobs[job.id] = job

    def run() -> None:
        try:
            result = target(job)
            if job.cancelled():  # finished anyway after the cancellation: not delivered
                raise PublicError(CANCELLED)
            job.result, job.status = result, "done"
        except PublicError as e:  # written for the user
            job.error, job.status = CANCELLED if job.cancelled() else str(e), "error"
        except Exception:
            log.error("Job %s failed", job.id)
            job.error = CANCELLED if job.cancelled() else "Erreur interne (détail dans les logs du serveur)."
            job.status = "error"
        finally:
            if shared_capacity is not None:
                shared_capacity.__exit__(None, None, None)
            slots.release()

    threading.Thread(target=run, daemon=True).start()
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)
