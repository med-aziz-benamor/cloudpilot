"""Compute SKU pricing catalog + downsize mapping.

In production this is refreshed weekly into Redis from the provider pricing APIs
(Azure SKU list, AWS EC2 pricing JSON, GCP Cloud Pricing API). For the demo a
curated static catalog of common SKUs across the three providers is sufficient and
deterministic. The catalog is intentionally read-only.
"""

from __future__ import annotations

# Approximate on-demand USD/hour for common SKUs (demo catalog).
HOURLY_PRICE: dict[str, float] = {
    # Azure
    "Standard_D2s_v3": 0.096,
    "Standard_D4s_v3": 0.192,
    "Standard_D8s_v3": 0.384,
    "GP_Gen5_4": 0.74,
    "P1v3": 0.146,
    "C1": 0.055,
    # AWS
    "t3.medium": 0.0416,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "db.m5.large": 0.171,
    "cache.m5.large": 0.156,
    # GCP
    "n2-standard-2": 0.0971,
    "n2-standard-4": 0.1942,
    "n2-standard-8": 0.3885,
    "db-n1-standard-2": 0.1010,
}

# Next-smaller SKU within the same family.
DOWNSIZE_MAP: dict[str, str] = {
    "Standard_D8s_v3": "Standard_D4s_v3",
    "Standard_D4s_v3": "Standard_D2s_v3",
    "m5.2xlarge": "m5.xlarge",
    "m5.xlarge": "m5.large",
    "m5.large": "t3.medium",
    "n2-standard-8": "n2-standard-4",
    "n2-standard-4": "n2-standard-2",
}


def sku_hourly_price(sku: str | None) -> float:
    """Return the catalog hourly price for a SKU (0.0 if unknown)."""
    if not sku:
        return 0.0
    return HOURLY_PRICE.get(sku, 0.0)


def next_smaller_sku(sku: str | None) -> str | None:
    """Return the next-smaller SKU in the same family, or None."""
    if not sku:
        return None
    return DOWNSIZE_MAP.get(sku)
