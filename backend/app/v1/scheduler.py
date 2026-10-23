"""Outbox delivery and expiry run independently of busy processing queues."""

import logging
import signal
import threading

from app.v1.crypto import key
from app.v1.db import check
from app.v1.settings import validate
from app.v1.worker import dispatch, purge

log = logging.getLogger(__name__)


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    check()
    key()
    validate()
    tick = 0
    while not stop.is_set():
        # Failures contain no request bodies or connection URLs in logs. Outbox stays in PostgreSQL.
        try:
            dispatch()
        except Exception:
            log.error("v1 outbox dispatch failed; pending jobs retained")
        if tick % 12 == 0:
            try:
                purge()
            except Exception:
                log.error("v1 retention maintenance failed")
        tick += 1
        stop.wait(5)


if __name__ == "__main__":
    main()
