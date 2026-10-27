"""Crypto convenience helpers + Fernet key rotation runbook support.

The low-level encrypt/decrypt primitives live in ``core.security``. This module adds
operational helpers (key generation, bulk re-encryption) used by the key-rotation
procedure documented in ``docs/security.md``.
"""

from __future__ import annotations

from typing import Any

from cryptography.fernet import Fernet, MultiFernet

from cloudpilot.core.security import decrypt_credential, encrypt_credential, rotate_key

__all__ = [
    "decrypt_credential",
    "encrypt_credential",
    "generate_fernet_key",
    "reencrypt_blob",
    "rotate_key",
    "verify_with_multi",
]


def generate_fernet_key() -> str:
    """Generate a fresh base64url Fernet key (for ``FERNET_MASTER_KEY``)."""
    return Fernet.generate_key().decode("utf-8")


def reencrypt_blob(blob: str, old_key: str, new_key: str) -> str:
    """Re-encrypt one credential blob from ``old_key`` to ``new_key``."""
    return rotate_key(old_key.encode(), new_key.encode(), blob)


def verify_with_multi(blob: str, keys: list[str]) -> dict[str, Any]:
    """Decrypt using a MultiFernet (supports a window where both old+new keys are
    accepted during rotation step 2)."""
    import json

    mf = MultiFernet([Fernet(k.encode()) for k in keys])
    creds: dict[str, Any] = json.loads(mf.decrypt(blob.encode()).decode())
    return creds
