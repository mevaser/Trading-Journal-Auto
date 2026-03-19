from __future__ import annotations

import hashlib
import hmac
import os
from base64 import urlsafe_b64decode, urlsafe_b64encode

PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 16


class PasswordHashError(ValueError):
    """Raised when an encoded password hash is malformed."""


def _b64_encode(value: bytes) -> str:
    return urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return urlsafe_b64decode(value + padding)


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    if not password:
        raise ValueError("password cannot be empty")
    if iterations < 100_000:
        raise ValueError("iterations must be at least 100000")

    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(PBKDF2_ALGORITHM, password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_{PBKDF2_ALGORITHM}${iterations}${_b64_encode(salt)}${_b64_encode(digest)}"


def verify_password(password: str, encoded_hash: str) -> bool:
    if not password:
        return False

    try:
        scheme, iterations_raw, salt_raw, digest_raw = encoded_hash.split("$", maxsplit=3)
        if scheme != f"pbkdf2_{PBKDF2_ALGORITHM}":
            return False

        iterations = int(iterations_raw)
        salt = _b64_decode(salt_raw)
        expected_digest = _b64_decode(digest_raw)
    except (ValueError, TypeError):
        raise PasswordHashError("invalid password hash format")

    actual_digest = hashlib.pbkdf2_hmac(PBKDF2_ALGORITHM, password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual_digest, expected_digest)
