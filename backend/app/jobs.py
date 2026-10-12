"""In-memory background jobs for scraping (a scrape takes ~1 min and may need a 2FA code)."""

import threading
import time
from typing import Any, Callable
from uuid import uuid4

JOB_TTL = 3600


class Job:
    def __init__(self) -> None:
        self.id = uuid4().hex
        self.created = time.time()
        self.status = "running"  # running | needs_code | done | error
        self.percent = 0
        self.messages: list[str] = []
        self.prompt = ""
        self.result: Any = None
        self.error = ""
        self._code: str | None = None
        self._code_event = threading.Event()

    # Hooks used by the scraper
    def progress(self, message: str, percent: int | None = None) -> None:
        self.messages.append(message)
        if percent is not None:
            self.percent = percent

    def ask_code(self, message: str) -> str | None:
        self._code, self.prompt, self.status = None, message, "needs_code"
        self._code_event.clear()
        self._code_event.wait(timeout=300)
        self.status, self.prompt = "running", ""
        return self._code

    def submit_code(self, code: str) -> None:
        self._code = code
        self._code_event.set()

    def to_dict(self) -> dict:
        return {
            "id": self.id, "status": self.status, "percent": self.percent,
            "messages": self.messages[-20:], "prompt": self.prompt,
            "error": self.error, "result": self.result,
        }


_jobs: dict[str, Job] = {}


def start(target: Callable[[Job], Any]) -> Job:
    for jid in [j for j, job in _jobs.items() if time.time() - job.created > JOB_TTL]:
        _jobs.pop(jid, None)
    job = Job()
    _jobs[job.id] = job

    def run() -> None:
        try:
            job.result = target(job)
            job.status = "done"
        except Exception as e:
            job.error, job.status = str(e) or e.__class__.__name__, "error"

    threading.Thread(target=run, daemon=True).start()
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)
