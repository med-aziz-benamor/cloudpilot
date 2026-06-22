"""Tests for the security primitives: passwords, JWT, strength checks."""

from __future__ import annotations

import uuid

import jwt
import pytest

from cloudpilot.core.security import (
    check_password_strength,
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("demo1234")
    assert hashed != "demo1234"
    assert verify_password("demo1234", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_password_handles_garbage() -> None:
    assert not verify_password("x", "not-a-real-hash")


@pytest.mark.parametrize(
    "pwd,ok",
    [
        ("short", False),
        ("allletters", False),
        ("12345678", False),
        ("demo1234", True),
        ("Str0ngPass", True),
    ],
)
def test_password_strength(pwd: str, ok: bool) -> None:
    valid, _ = check_password_strength(pwd)
    assert valid is ok


def test_access_token_roundtrip() -> None:
    user_id, org_id = uuid.uuid4(), uuid.uuid4()
    token = create_access_token(user_id, org_id, "admin")
    payload = verify_token(token)
    assert payload.user_id == user_id
    assert payload.org_id == org_id
    assert payload.role == "admin"
    assert payload.jti


def test_token_rejects_wrong_audience() -> None:
    # A token signed for a different audience must be rejected.
    bad = jwt.encode(
        {"sub": str(uuid.uuid4()), "org": str(uuid.uuid4()), "role": "admin",
         "jti": "x", "exp": 9999999999, "aud": "someone-else"},
        "test-secret-key-at-least-32-chars-long!!",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidTokenError):
        verify_token(bad)


def test_refresh_token_is_opaque_hex() -> None:
    token = create_refresh_token(uuid.uuid4())
    assert len(token) == 64
    int(token, 16)  # parses as hex
