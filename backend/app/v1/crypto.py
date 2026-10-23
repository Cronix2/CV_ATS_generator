"""Authenticated encryption: keys are configuration, never database values."""

import base64
import hashlib
import hmac
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def key():
    value = base64.b64decode(os.environ["V1_ENCRYPTION_KEY"], validate=True)
    if len(value) != 32:
        raise ValueError("V1_ENCRYPTION_KEY must encode 32 random bytes")
    return value


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def secret_fingerprint(value):
    """A database leak must not enable offline guessing of LinkedIn passwords."""
    return hmac.new(
        key(), b"idempotency-secret\0" + canonical(value).encode(), hashlib.sha256
    ).hexdigest()


def seal(value, context):
    nonce = os.urandom(12)
    return base64.b64encode(
        nonce
        + AESGCM(key()).encrypt(nonce, canonical(value).encode(), context.encode())
    ).decode()


def unseal(value, context):
    raw = base64.b64decode(value, validate=True)
    return json.loads(AESGCM(key()).decrypt(raw[:12], raw[12:], context.encode()))
