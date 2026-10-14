import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# One .env at the repository root configures everything (ports, CORS, default LLM...).
# Real environment variables (e.g. from Docker) take precedence.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Audit trail (who started which scrape / agent run, refused tokens…): stderr, plus a file if AUDIT_LOG_FILE is set.
_audit = logging.getLogger("passefiltre.audit")
if not _audit.handlers:
    _audit.setLevel(logging.INFO)
    _audit.propagate = False
    _format = logging.Formatter("%(asctime)s AUDIT %(message)s")
    _handlers: list[logging.Handler] = [logging.StreamHandler()]
    if os.getenv("AUDIT_LOG_FILE"):
        _handlers.append(logging.FileHandler(os.environ["AUDIT_LOG_FILE"], encoding="utf-8"))
    for _handler in _handlers:
        _handler.setFormatter(_format)
        _audit.addHandler(_handler)
