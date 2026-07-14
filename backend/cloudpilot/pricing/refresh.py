"""Regenerate the committed pricing snapshot from the public rate-card APIs.

    python -m cloudpilot.pricing.refresh

Needs no cloud credentials — the Azure Retail Prices API and the AWS Price List
are both public and unauthenticated. The AWS offer files are tens of MB, so a full
refresh takes a few minutes on a slow link; use ``--skip-aws`` to refresh only the
cheap Azure queries during development.
"""

from __future__ import annotations

import argparse

from loguru import logger

from cloudpilot.pricing import sources
from cloudpilot.pricing.catalog import DOWNSIZE_MAP, SNAPSHOT_PATH, PricingCatalog
from cloudpilot.pricing.models import Price, PriceUnit


def fetch_azure(client: sources.httpx.Client) -> dict[str, Price]:
    """Fetch every Azure SKU the demo fleet uses."""
    out: dict[str, Price] = {}
    for arm_sku in ("Standard_D2s_v3", "Standard_D4s_v3", "Standard_D8s_v3"):
        if (price := sources.fetch_azure_vm(client, arm_sku)) is not None:
            out[arm_sku] = price

    # Both tiers, so the 4-vCore database has a priced downsize target.
    for sql_sku, vcores in (("GP_Gen5_4", 4), ("GP_Gen5_2", 2)):
        if (price := sources.fetch_azure_sql_vcore(client, sql_sku, vcores)) is not None:
            out[sql_sku] = price

    app = sources.fetch_azure_metered(
        client,
        sku="P1v3",
        service_name="Azure App Service",
        sku_filter="P1 v3",
        product_filter="Azure App Service Premium v3 Plan - Linux",
        unit=PriceUnit.HOUR,
    )
    if app is not None:
        out["P1v3"] = app

    redis = sources.fetch_azure_metered(
        client,
        sku="C1",
        service_name="Redis Cache",
        sku_filter="C1",
        product_filter="Azure Redis Cache Basic",
        unit=PriceUnit.HOUR,
    )
    if redis is not None:
        out["C1"] = redis

    blob = sources.fetch_azure_metered(
        client,
        sku="blob_hot_lrs",
        service_name="Storage",
        sku_filter="Hot LRS",
        product_filter="General Block Blob v2",
        unit=PriceUnit.GB_MONTH,
        meter_filter="Hot LRS Data Stored",
    )
    if blob is not None:
        out["blob_hot_lrs"] = blob

    return out


def fetch_aws(client: sources.httpx.Client, deep: bool = False) -> dict[str, Price]:
    """Return the AWS rate card.

    Defaults to the transcribed list prices, because the bulk offer files are far too
    large to download on every refresh. ``deep`` fetches them for real and upgrades the
    provenance of everything it resolves.
    """
    # Start from the transcribed rates; anything fetched below overwrites them.
    out: dict[str, Price] = dict(sources.aws_list_prices())
    if not deep:
        logger.info(
            "AWS: using {} published list prices (pass --deep to fetch the offer files).",
            len(out),
        )
        return out

    for service, wanted, unit in (
        ("AmazonEC2", sources.AWS_EC2_WANTED, PriceUnit.HOUR),
        ("AmazonRDS", sources.AWS_RDS_WANTED, PriceUnit.HOUR),
        ("AmazonElastiCache", sources.AWS_CACHE_WANTED, PriceUnit.HOUR),
    ):
        offer = sources._aws_offer(client, service)
        if offer is None:
            continue
        found = sources.extract_aws_prices(offer, wanted, unit)
        logger.info("AWS {}: resolved {}/{} SKUs", service, len(found), len(wanted))
        out.update(found)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh the CloudPilot pricing snapshot")
    parser.add_argument(
        "--skip-aws",
        action="store_true",
        help="Skip the AWS offer-file download entirely (keeps existing AWS rates).",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help=(
            "Also fetch the RDS and ElastiCache offer files (hundreds of MB) instead of "
            "using their published list prices. Slow, but upgrades their provenance."
        ),
    )
    args = parser.parse_args()

    prices: dict[str, Price] = {}

    # Keep any existing rates so a partial refresh degrades gracefully rather than
    # dropping SKUs out of the catalog entirely.
    if SNAPSHOT_PATH.exists():
        existing = PricingCatalog.from_snapshot()
        prices.update({sku: existing.get(sku) for sku in existing.skus()})  # type: ignore[misc]

    with sources.http_client() as client:
        logger.info("Fetching Azure Retail Prices (public, no auth)...")
        prices.update(fetch_azure(client))

        if args.skip_aws:
            logger.info("Skipping AWS offer files (--skip-aws).")
        else:
            prices.update(fetch_aws(client, deep=args.deep))

    prices.update(sources.gcp_prices())

    # Every downsize target must be priced, or the right-sizing saving is fiction.
    for source_sku, target_sku in DOWNSIZE_MAP.items():
        if source_sku in prices and target_sku not in prices:
            logger.warning(
                "Downsize target {} for {} is unpriced — the pair will be skipped.",
                target_sku,
                source_sku,
            )

    regions = {
        "azure": sources.AZURE_REGION,
        "aws": sources.AWS_REGION,
        "gcp": sources.GCP_REGION,
    }
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(PricingCatalog.to_snapshot(prices, regions))

    verified = sum(1 for p in prices.values() if p.source.is_api_verified)
    logger.info(
        "Wrote {} ({} SKUs, {} API-verified, {} published-list).",
        SNAPSHOT_PATH,
        len(prices),
        verified,
        len(prices) - verified,
    )
    for sku, price in sorted(prices.items()):
        logger.info("  {:<20} {}", sku, price.describe())


if __name__ == "__main__":
    main()
