"""Azure rate fetchers must degrade gracefully on a network failure.

Unlike the AWS fetcher (``_aws_offer``, already wrapped in try/except with a
published-price fallback), the three Azure fetchers had no exception handling
around the API call — a single transient 5xx/timeout aborted the whole
``make pricing`` run before AWS/GCP were even reached. The fix centralizes
the guard in ``_azure_query``, which every Azure fetcher funnels through.
"""

from __future__ import annotations

import httpx

from cloudpilot.pricing.models import PriceUnit
from cloudpilot.pricing.sources import fetch_azure_metered, fetch_azure_sql_vcore, fetch_azure_vm


class _FailingClient:
    """Stands in for httpx.Client: every .get() raises, like a network outage."""

    def get(self, _url: str, params: dict | None = None) -> httpx.Response:
        raise httpx.ConnectError("connection refused")


def test_fetch_azure_vm_degrades_to_none_on_network_failure() -> None:
    assert fetch_azure_vm(_FailingClient(), "Standard_D4s_v3") is None  # type: ignore[arg-type]


def test_fetch_azure_sql_vcore_degrades_to_none_on_network_failure() -> None:
    assert fetch_azure_sql_vcore(_FailingClient(), "GP_Gen5_4", 4) is None  # type: ignore[arg-type]


def test_fetch_azure_metered_degrades_to_none_on_network_failure() -> None:
    result = fetch_azure_metered(
        _FailingClient(),  # type: ignore[arg-type]
        sku="P1v3",
        service_name="Azure App Service",
        sku_filter="P1 v3",
        product_filter="Azure App Service Premium v3 Plan - Linux",
        unit=PriceUnit.HOUR,
    )
    assert result is None
