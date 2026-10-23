"""Container health: database role/schema and broker, without printing connection details."""

import os
import sys

from redis import Redis

from app.v1.crypto import key
from app.v1.db import check
from app.v1.settings import validate

if __name__ == "__main__":
    try:
        check()
        key()
        validate()
        Redis.from_url(
            os.environ["V1_REDIS_URL"], socket_timeout=2, socket_connect_timeout=2
        ).ping()
    except Exception:
        print("v1 dependencies unavailable", file=sys.stderr)
        sys.exit(1)
