"""Rate-card fetchers for the public, keyless provider pricing APIs.

Neither Azure nor AWS requires credentials, a subscription, or spend to read its
published rate card:

* **Azure Retail Prices API** — ``https://prices.azure.com/api/retail/prices``.
  OData-filterable, returns JSON, no auth. Cheap to query per-SKU.
* **AWS Price List** — per-service, per-region bulk JSON offer files. No auth, but
  each file is 20-40 MB, so it is fetched once per refresh and discarded.
* **GCP** — the Cloud Billing Catalog API requires an API key, so GCP rates are
  transcribed from the published pricing pages and flagged
  ``PUBLISHED_LIST_PRICE`` rather than being passed off as API-verified.

Fetchers are tolerant: a network failure degrades one SKU to its published list
price, it does not fail the refresh. The provenance field records which happened.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from loguru import logger

from cloudpilot.pricing.models import Price, PriceSource, PriceUnit

AZURE_RETAIL_API = "https://prices.azure.com/api/retail/prices"
AWS_PRICE_LIST = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws"

# Rate cards are quoted per region; these are the regions the demo fleet lives in.
AZURE_REGION = "westeurope"
AWS_REGION = "eu-west-1"
GCP_REGION = "europe-west1"

_HTTP_TIMEOUT = 120.0
# The bulk AWS offer files are tens of MB; give them room.
_AWS_TIMEOUT = 900.0


# ─────────────────────────────────────────────────────────────
# Azure — Retail Prices API
# ─────────────────────────────────────────────────────────────
def _azure_query(client: httpx.Client, odata_filter: str) -> list[dict[str, Any]]:
    """Run one OData query against the Retail Prices API, following pagination.

    Tolerant like the AWS fetcher below: a network failure or non-2xx response
    degrades this one query to "no matches" (each caller already treats an
    empty/missing match as "skip this SKU", returning None) rather than
    propagating and aborting the whole ``make pricing`` run over one Azure
    hiccup.
    """
    items: list[dict[str, Any]] = []
    url: str | None = AZURE_RETAIL_API
    params: dict[str, str] | None = {"$filter": odata_filter}
    try:
        while url:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            body = resp.json()
            items.extend(body.get("Items", []))
            # NextPageLink already carries the filter, so params must not be re-sent.
            url = body.get("NextPageLink")
            params = None
    except Exception as exc:
        logger.warning("Azure: query failed ({}), degrading to no matches: {}", odata_filter, exc)
        return []
    return items


def _is_ondemand_linux(item: dict[str, Any]) -> bool:
    """Reject the Spot, Low-Priority and Windows meters that share an armSkuName.

    A single VM SKU returns six meters (Linux/Windows × on-demand/low-priority/spot).
    Only the plain Linux on-demand meter is the rate a steady-state workload pays.
    """
    sku_name = item.get("skuName", "")
    product = item.get("productName", "")
    if "Spot" in sku_name or "Low Priority" in sku_name:
        return False
    return not product.endswith("Windows")


def fetch_azure_vm(client: httpx.Client, arm_sku: str) -> Price | None:
    """Fetch the on-demand Linux hourly rate for one Azure VM SKU."""
    odata = (
        f"serviceName eq 'Virtual Machines' and armRegionName eq '{AZURE_REGION}' "
        f"and armSkuName eq '{arm_sku}' and priceType eq 'Consumption'"
    )
    matches = [i for i in _azure_query(client, odata) if _is_ondemand_linux(i)]
    if not matches:
        logger.warning("Azure: no on-demand Linux meter for {}", arm_sku)
        return None
    # Multiple regions/meters can survive the filter; the cheapest plain meter is
    # the standard pay-as-you-go rate.
    item = min(matches, key=lambda i: float(i["retailPrice"]))
    return Price(
        sku=arm_sku,
        provider="azure",
        amount=float(item["retailPrice"]),
        unit=PriceUnit.HOUR,
        region=AZURE_REGION,
        source=PriceSource.AZURE_RETAIL_API,
        meter=item.get("meterName", ""),
    )


def fetch_azure_sql_vcore(client: httpx.Client, sku: str, vcores: int) -> Price | None:
    """Fetch an Azure SQL General Purpose rate.

    Azure SQL is metered per *vCore-hour*, not per instance-hour, so the rate for a
    4-vCore database is 4x the single-vCore meter. Treating the meter as an instance
    price would under-bill the database by 4x.
    """
    odata = (
        f"serviceName eq 'SQL Database' and armRegionName eq '{AZURE_REGION}' "
        f"and priceType eq 'Consumption' and skuName eq '1 vCore' "
        f"and productName eq 'SQL Database Single/Elastic Pool General Purpose - Compute Gen5'"
    )
    matches = _azure_query(client, odata)
    if not matches:
        logger.warning("Azure: no SQL Gen5 vCore meter found")
        return None
    per_vcore = float(min(matches, key=lambda i: float(i["retailPrice"]))["retailPrice"])
    return Price(
        sku=sku,
        provider="azure",
        amount=per_vcore * vcores,
        unit=PriceUnit.HOUR,
        region=AZURE_REGION,
        source=PriceSource.AZURE_RETAIL_API,
        meter=f"SQL GP Gen5 vCore x{vcores}",
    )


def fetch_azure_metered(
    client: httpx.Client,
    sku: str,
    service_name: str,
    sku_filter: str,
    product_filter: str,
    unit: PriceUnit,
    meter_filter: str | None = None,
) -> Price | None:
    """Fetch a non-VM Azure meter (App Service, Redis, Storage) by exact product.

    ``meter_filter`` pins the exact meter name and matters most for storage: one
    product bundles the data-stored meter together with the read/write/delete
    operation meters, and the operation meters are quoted per 10K ops at a far
    lower number. Matching on product alone would silently pick up an ops rate and
    under-price storage by ~7x.
    """
    odata = (
        f"serviceName eq '{service_name}' and armRegionName eq '{AZURE_REGION}' "
        f"and priceType eq 'Consumption' and skuName eq '{sku_filter}' "
        f"and productName eq '{product_filter}'"
    )
    matches = [i for i in _azure_query(client, odata) if float(i["retailPrice"]) > 0]
    if meter_filter:
        matches = [i for i in matches if i.get("meterName") == meter_filter]
    # Graduated meters repeat the SKU once per volume tier; tier 0 is the rate a
    # normal-sized workload actually pays.
    first_tier = [i for i in matches if float(i.get("tierMinimumUnits", 0)) == 0]
    matches = first_tier or matches
    if not matches:
        logger.warning("Azure: no meter for {} / {}", service_name, sku_filter)
        return None
    item = min(matches, key=lambda i: float(i["retailPrice"]))
    return Price(
        sku=sku,
        provider="azure",
        amount=float(item["retailPrice"]),
        unit=unit,
        region=AZURE_REGION,
        source=PriceSource.AZURE_RETAIL_API,
        meter=item.get("meterName", ""),
    )


# ─────────────────────────────────────────────────────────────
# AWS — Price List bulk offer files
# ─────────────────────────────────────────────────────────────
def _aws_offer(client: httpx.Client, service: str) -> dict[str, Any] | None:
    """Download one AWS bulk offer file (tens of MB) for the demo region."""
    url = f"{AWS_PRICE_LIST}/{service}/current/{AWS_REGION}/index.json"
    try:
        logger.info("AWS: fetching {} rate card (this is a large file)", service)
        resp = client.get(url, timeout=_AWS_TIMEOUT)
        resp.raise_for_status()
        return json.loads(resp.content)
    except Exception as exc:
        logger.warning("AWS: could not fetch {} offer file: {}", service, exc)
        return None


def _aws_ondemand_usd(offer: dict[str, Any], sku_id: str) -> float | None:
    """Pull the single USD on-demand price dimension for a product SKU."""
    for term in offer.get("terms", {}).get("OnDemand", {}).get(sku_id, {}).values():
        for dim in term.get("priceDimensions", {}).values():
            usd = dim.get("pricePerUnit", {}).get("USD")
            if usd is not None:
                return float(usd)
    return None


def extract_aws_prices(
    offer: dict[str, Any], wanted: dict[str, dict[str, str]], provider_unit: PriceUnit
) -> dict[str, Price]:
    """Extract rates from a bulk offer file.

    ``wanted`` maps our SKU name to the attribute filter that identifies its
    product row (e.g. ``{"m5.large": {"instanceType": "m5.large", ...}}``). A row
    only qualifies if *every* attribute in the filter matches — this is what
    excludes the Windows, dedicated-tenancy and reserved-capacity variants that
    otherwise share an instance type.
    """
    found: dict[str, Price] = {}
    for product in offer.get("products", {}).values():
        attrs = product.get("attributes", {})
        for our_sku, criteria in wanted.items():
            if our_sku in found:
                continue
            if all(attrs.get(k) == v for k, v in criteria.items()):
                usd = _aws_ondemand_usd(offer, product.get("sku", ""))
                if usd is None or usd <= 0:
                    continue
                found[our_sku] = Price(
                    sku=our_sku,
                    provider="aws",
                    amount=usd,
                    unit=provider_unit,
                    region=AWS_REGION,
                    source=PriceSource.AWS_PRICE_LIST,
                    meter=attrs.get("usagetype", ""),
                )
    return found


#: EC2 on-demand Linux, shared tenancy, no pre-installed software.
AWS_EC2_WANTED: dict[str, dict[str, str]] = {
    sku: {
        "instanceType": sku,
        "operatingSystem": "Linux",
        "tenancy": "Shared",
        "preInstalledSw": "NA",
        "capacitystatus": "Used",
    }
    for sku in ("t3.medium", "m5.large", "m5.xlarge", "m5.2xlarge")
}

#: RDS single-AZ MySQL on-demand.
AWS_RDS_WANTED: dict[str, dict[str, str]] = {
    sku: {"instanceType": sku, "databaseEngine": "MySQL", "deploymentOption": "Single-AZ"}
    for sku in ("db.m5.large", "db.m5.xlarge")
}

#: ElastiCache Redis on-demand.
AWS_CACHE_WANTED: dict[str, dict[str, str]] = {
    sku: {"instanceType": sku, "cacheEngine": "Redis"}
    for sku in ("cache.m5.large", "cache.m5.xlarge")
}

#: AWS default rates — transcribed, not fetched.
#:
#: Unlike Azure, the AWS Price List offers no per-SKU query without credentials: you
#: take the entire service/region offer file or nothing, and those files run from tens
#: to hundreds of megabytes for the sake of a handful of rates. Making that the default
#: would turn ``pricing.refresh`` into a 40-minute job on an ordinary connection, so the
#: rates below are transcribed from the public pricing pages and honestly flagged
#: PUBLISHED_LIST_PRICE.
#:
#: ``refresh --deep`` downloads the real offer files and overwrites these, upgrading
#: their provenance to AWS_PRICE_LIST. Run it once on a fast link and commit the
#: snapshot; the fetchers it uses are :func:`extract_aws_prices` and friends below.
#:
#: Sources: aws.amazon.com/{ec2,rds,elasticache,s3}/pricing — eu-west-1, on-demand,
#: Linux, shared tenancy.
AWS_LIST_PRICES: dict[str, tuple[float, PriceUnit]] = {
    "t3.medium": (0.0456, PriceUnit.HOUR),
    "m5.large": (0.1070, PriceUnit.HOUR),
    "m5.xlarge": (0.2140, PriceUnit.HOUR),
    "m5.2xlarge": (0.4280, PriceUnit.HOUR),
    "db.m5.large": (0.1780, PriceUnit.HOUR),
    "db.m5.xlarge": (0.3560, PriceUnit.HOUR),
    "cache.m5.large": (0.1930, PriceUnit.HOUR),
    "cache.m5.xlarge": (0.3860, PriceUnit.HOUR),
    "s3_standard": (0.0230, PriceUnit.GB_MONTH),
}


def aws_list_prices() -> dict[str, Price]:
    """Return the transcribed AWS list prices."""
    return {
        sku: Price(
            sku=sku,
            provider="aws",
            amount=amount,
            unit=unit,
            region=AWS_REGION,
            source=PriceSource.PUBLISHED_LIST_PRICE,
            meter="aws.amazon.com/s3/pricing",
        )
        for sku, (amount, unit) in AWS_LIST_PRICES.items()
    }


# ─────────────────────────────────────────────────────────────
# GCP — no keyless rate API; published list prices, honestly flagged
# ─────────────────────────────────────────────────────────────
#: GCP's Cloud Billing Catalog API needs an API key, so these are transcribed from
#: cloud.google.com/compute/all-pricing (europe-west1, on-demand) and are marked
#: PUBLISHED_LIST_PRICE so they are never presented as API-verified.
GCP_LIST_PRICES: dict[str, tuple[float, PriceUnit]] = {
    "n2-standard-2": (0.107180, PriceUnit.HOUR),
    "db-n1-standard-1": (0.057600, PriceUnit.HOUR),
    "n2-standard-4": (0.214360, PriceUnit.HOUR),
    "n2-standard-8": (0.428720, PriceUnit.HOUR),
    "db-n1-standard-2": (0.115200, PriceUnit.HOUR),
    "gcs_standard": (0.020000, PriceUnit.GB_MONTH),
}


def gcp_prices() -> dict[str, Price]:
    """Return the transcribed GCP list prices."""
    return {
        sku: Price(
            sku=sku,
            provider="gcp",
            amount=amount,
            unit=unit,
            region=GCP_REGION,
            source=PriceSource.PUBLISHED_LIST_PRICE,
            meter="cloud.google.com/compute/all-pricing",
        )
        for sku, (amount, unit) in GCP_LIST_PRICES.items()
    }


def http_client() -> httpx.Client:
    """A client configured for the rate-card endpoints."""
    return httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True)
