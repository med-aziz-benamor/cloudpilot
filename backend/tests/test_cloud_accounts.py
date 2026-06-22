"""Tests for credential encryption and cloud adapter mock behavior."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from cloudpilot.cloud.base import get_adapter
from cloudpilot.core.security import decrypt_credential, encrypt_credential
from cloudpilot.models.cloud_account import CloudProvider


def test_credential_encryption_roundtrip() -> None:
    creds = {"client_id": "abc", "client_secret": "super-secret", "tenant_id": "t"}
    blob = encrypt_credential(creds)
    assert "super-secret" not in blob  # not stored in plaintext
    assert decrypt_credential(blob) == creds


def test_encryption_is_non_deterministic() -> None:
    creds = {"k": "v"}
    assert encrypt_credential(creds) != encrypt_credential(creds)


@pytest.mark.parametrize(
    "provider,expected_min",
    [
        (CloudProvider.AZURE, 22),
        (CloudProvider.AWS, 18),
        (CloudProvider.GCP, 10),
    ],
)
async def test_adapter_mock_resources(provider, expected_min) -> None:
    adapter = get_adapter(provider, {})  # no creds → demo mode
    resources = await adapter.get_resources()
    assert len(resources) >= expected_min
    assert all(r.provider_resource_id for r in resources)


async def test_adapter_billing_window() -> None:
    adapter = get_adapter(CloudProvider.AZURE, {})
    end = date.today()
    start = end - timedelta(days=30)
    entries = await adapter.get_billing(start, end)
    assert entries
    assert all(start <= e.usage_date <= end for e in entries)
    assert all(e.cost_usd >= 0 for e in entries)


async def test_adapter_validate_demo_mode() -> None:
    adapter = get_adapter(CloudProvider.AWS, {})
    assert await adapter.validate_credentials() is True
