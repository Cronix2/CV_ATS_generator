"""Bounded operator settings; invalid configuration fails closed."""

import os

DEFAULTS = {
    "V1_MAX_JOBS": (2, 16),
    "V1_RATE_SERVICE_PER_MINUTE": (120, 10000),
    "V1_RATE_USER_PER_MINUTE": (60, 10000),
    "V1_HEAVY_PER_DAY": (20, 10000),
    "V1_RESULT_TTL_SECONDS": (86400, 2592000),
    "V1_SECRET_TTL_SECONDS": (1800, 3600),
    "V1_SESSION_TTL_SECONDS": (2592000, 31536000),
    "V1_REVIEW_TTL_SECONDS": (604800, 2592000),
}


def setting(name):
    default, maximum = DEFAULTS[name]
    try:
        value = int(os.getenv(name, str(default)))
        if not 1 <= value <= maximum:
            raise ValueError()
    except ValueError:
        raise RuntimeError("Invalid configuration: " + name) from None
    return value


def validate():
    for name in DEFAULTS:
        setting(name)
