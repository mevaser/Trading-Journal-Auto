from __future__ import annotations

import pytest

from app.auth.passwords import PasswordHashError, hash_password, verify_password


def test_hash_and_verify_password_roundtrip() -> None:
    encoded = hash_password("S3cure-passphrase")

    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_password("S3cure-passphrase", encoded) is True
    assert verify_password("wrong-password", encoded) is False


def test_password_hash_uses_random_salt() -> None:
    first = hash_password("same-password")
    second = hash_password("same-password")

    assert first != second


def test_verify_password_rejects_malformed_hash() -> None:
    with pytest.raises(PasswordHashError, match="invalid password hash format"):
        verify_password("x", "not-a-valid-hash")
