"""Security primitives: JWT, password hashing, and credential encryption.

This module is the single home for all cryptographic operations. Nothing else in
the codebase calls bcrypt, PyJWT or Fernet directly.

Token strategy
--------------
* Access token  — short-lived (60 min) HS256 JWT carrying user/org/role claims.
                  ``aud`` is pinned to ``cloudpilot`` and the algorithm whitelist
                  rejects ``none`` and asymmetric algorithms.
* Refresh token — opaque 64-char hex string (NOT a JWT). Rotated on every use and
                  revoked in Redis. The rotation/revocation bookkeeping lives in
                  ``services/auth_service.py``; this module only mints/parses tokens.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from cloudpilot.config import settings


# ─────────────────────────────────────────────────────────────
# JWT
# ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TokenPayload:
    """Decoded access-token claims."""

    user_id: uuid.UUID
    org_id: uuid.UUID
    role: str
    jti: str
    exp: int


def create_access_token(user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> str:
    """Mint a signed access token for the given principal."""
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "org": str(org_id),
        "role": role,
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()
        ),
        "aud": settings.JWT_AUDIENCE,
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> str:  # noqa: ARG001 — user binding handled by caller
    """Generate a cryptographically random opaque refresh token."""
    return secrets.token_hex(32)  # 64 hex chars


def verify_token(token: str) -> TokenPayload:
    """Verify and decode an access token.

    Raises:
        jwt.InvalidTokenError: if the signature, audience, or expiry is invalid.
    """
    decoded = jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],  # strict whitelist — no 'none', no RS256
        audience=settings.JWT_AUDIENCE,
        options={"require": ["exp", "sub", "org", "role", "jti"]},
    )
    return TokenPayload(
        user_id=uuid.UUID(decoded["sub"]),
        org_id=uuid.UUID(decoded["org"]),
        role=decoded["role"],
        jti=decoded["jti"],
        exp=decoded["exp"],
    )


def rotate_refresh_token(old_token: str) -> tuple[str, str]:
    """Return ``(old_token, new_token)``. The caller is responsible for revoking
    ``old_token`` in Redis and persisting the new one."""
    return old_token, secrets.token_hex(32)


# ─────────────────────────────────────────────────────────────
# Passwords
# ─────────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt (configurable cost factor)."""
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verification of a plaintext password against its hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def check_password_strength(plain: str) -> tuple[bool, str]:
    """Validate password strength. Returns ``(ok, message)``."""
    if len(plain) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isalpha() for c in plain):
        return False, "Password must contain at least one letter."
    if not any(c.isdigit() for c in plain):
        return False, "Password must contain at least one digit."
    return True, "Password is strong."


# ─────────────────────────────────────────────────────────────
# Credential encryption (Fernet / AES-128-CBC + HMAC)
# ─────────────────────────────────────────────────────────────
def _fernet(key: bytes | None = None) -> Fernet:
    return Fernet(key or settings.fernet_key_bytes)


def encrypt_credential(data: dict[str, Any]) -> str:
    """Encrypt a credentials dict to an opaque token string."""
    return _fernet().encrypt(json.dumps(data).encode("utf-8")).decode("utf-8")


def decrypt_credential(blob: str) -> dict[str, Any]:
    """Decrypt a credentials token back into a dict.

    Raises:
        InvalidToken: if the blob is tampered or the key is wrong.
    """
    creds: dict[str, Any] = json.loads(
        _fernet().decrypt(blob.encode("utf-8")).decode("utf-8")
    )
    return creds


def rotate_key(old_key: bytes, new_key: bytes, blob: str) -> str:
    """Re-encrypt a credential blob from ``old_key`` to ``new_key`` without ever
    exposing plaintext outside this function (zero-downtime key rotation step 3)."""
    try:
        plaintext = Fernet(old_key).decrypt(blob.encode("utf-8"))
    except InvalidToken as exc:  # pragma: no cover - defensive
        raise ValueError("Cannot decrypt with the provided old key.") from exc
    return Fernet(new_key).encrypt(plaintext).decode("utf-8")
