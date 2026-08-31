"""Tests for the pricing catalog.

The invariants here are the ones that keep a dollar figure defensible: a rate must
have a unit, a downsize must actually be cheaper, and a saving must never be quoted
against a SKU nobody priced.
"""

from __future__ import annotations

import pytest

from cloudpilot.ai.pricing import next_smaller_sku, pricing_provenance, sku_hourly_price
from cloudpilot.pricing import PriceUnit, get_catalog
from cloudpilot.pricing.catalog import DOWNSIZE_MAP


def test_catalog_loads() -> None:
    catalog = get_catalog()
    assert len(catalog) > 0
    assert catalog.meta.total_count == len(catalog)


def test_every_price_is_positive_and_typed() -> None:
    for sku in get_catalog().skus():
        price = get_catalog().get(sku)
        assert price is not None
        assert price.amount > 0, f"{sku} has a non-positive rate"
        assert isinstance(price.unit, PriceUnit)
        assert price.currency == "USD"
        assert price.provider in {"azure", "aws", "gcp"}


def test_every_downsize_target_is_priced_and_cheaper() -> None:
    """A downsize recommendation that does not save money is a bug, not advice."""
    catalog = get_catalog()
    for source_sku, target_sku in DOWNSIZE_MAP.items():
        if catalog.get(source_sku) is None:
            continue  # source not in the catalog; nothing will recommend it
        target = catalog.get(target_sku)
        assert target is not None, f"{source_sku} downsizes to unpriced {target_sku}"
        assert catalog.hourly(target_sku) < catalog.hourly(source_sku), (
            f"downsizing {source_sku} -> {target_sku} does not reduce the rate"
        )


def test_next_smaller_refuses_unpriced_targets() -> None:
    """Better to give no advice than advice whose saving cannot be computed."""
    assert next_smaller_sku("does-not-exist") is None
    assert next_smaller_sku(None) is None


def test_hourly_price_of_unknown_sku_is_zero_not_a_guess() -> None:
    assert sku_hourly_price("no-such-sku") == 0.0
    assert sku_hourly_price(None) == 0.0


def test_storage_is_not_priced_as_compute() -> None:
    """Storage is quoted per GB-month.

    ``hourly()`` must refuse to return a GB-month rate, because multiplying it by 730
    would overstate a storage bill by three orders of magnitude — the exact bug this
    guards against.
    """
    catalog = get_catalog()
    storage = [s for s in catalog.skus() if catalog.get(s).unit is PriceUnit.GB_MONTH]  # type: ignore[union-attr]
    assert storage, "expected at least one GB-month SKU in the catalog"
    for sku in storage:
        assert catalog.hourly(sku) == 0.0


def test_monthly_cost_dispatches_on_unit() -> None:
    catalog = get_catalog()
    vm = catalog.get("Standard_D4s_v3")
    assert vm is not None and vm.unit is PriceUnit.HOUR
    # 1 node for a 730-hour month.
    assert vm.monthly_cost(1) == pytest.approx(vm.amount * 730)

    blob = catalog.get("blob_hot_lrs")
    assert blob is not None and blob.unit is PriceUnit.GB_MONTH
    # 1000 GB for a month — hours must be ignored.
    assert blob.monthly_cost(1000) == pytest.approx(blob.amount * 1000)


def test_blob_rate_is_storage_not_operations() -> None:
    """Azure bundles data-stored and per-10K-operation meters under one product.

    Hot LRS data-at-rest is ~$0.02/GB-month; the operations meters are far cheaper.
    Picking up an operations meter by mistake is a silent 7x under-pricing.
    """
    blob = get_catalog().get("blob_hot_lrs")
    assert blob is not None
    assert 0.01 < blob.amount < 0.05, f"blob rate {blob.amount} looks like an ops meter"


def test_provenance_is_attached_and_traceable() -> None:
    prov = pricing_provenance("Standard_D4s_v3")
    assert prov is not None
    assert prov["source"] in {"azure_retail_api", "aws_price_list", "published_list_price"}
    assert prov["unit"] == "hour"
    assert prov["region"]
    assert prov["as_of"]  # a rate with no as-of date cannot be judged stale
    assert pricing_provenance("no-such-sku") is None


def test_every_rate_cites_a_meter() -> None:
    """A rate with no meter cannot be checked against the publisher."""
    for sku in get_catalog().skus():
        price = get_catalog().get(sku)
        assert price is not None
        assert price.meter, f"{sku} records no meter"


def test_transcribed_rates_cite_the_page_they_were_read_off() -> None:
    """A transcribed rate's provenance *is* the page it came from.

    Every AWS and GCP list price used to carry one blanket citation — the S3
    pricing page for all nine AWS SKUs, the Compute page for GCP's SQL and storage
    — so an EC2 rate pointed a reviewer at a page that does not contain it. Latent
    while nothing displayed the field; wrong the moment the rate card did.
    """
    from cloudpilot.pricing.sources import aws_list_prices, gcp_prices

    catalog = get_catalog()
    for sku, expected in {**aws_list_prices(), **gcp_prices()}.items():
        stored = catalog.get(sku)
        if stored is None:
            continue  # a --deep refresh replaced it with an API-verified rate
        if stored.source is not expected.source:
            continue
        assert stored.meter == expected.meter, (
            f"{sku} cites {stored.meter!r}, but is transcribed from {expected.meter!r}"
        )


def test_a_service_is_never_cited_against_another_services_page() -> None:
    """The check that would have caught the blanket citation on its own."""
    from cloudpilot.pricing.sources import AWS_LIST_PRICES

    services = {
        "t3.": "ec2",
        "m5.": "ec2",
        "db.": "rds",
        "cache.": "elasticache",
        "s3_": "s3",
    }
    for sku, (_, _, page) in AWS_LIST_PRICES.items():
        service = next(v for k, v in services.items() if sku.startswith(k))
        assert f"/{service}/" in page, f"{sku} is cited against {page}"
