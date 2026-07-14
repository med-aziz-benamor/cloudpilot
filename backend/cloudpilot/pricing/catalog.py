"""The pricing catalog — a cached, provenance-carrying rate card.

The catalog is read from a snapshot committed to the repo
(``data/pricing_snapshot.json``) rather than fetched at import time, for three
reasons: the AWS offer files are tens of MB, the demo must work offline, and a
pinned rate card makes the seeded dataset reproducible.

Refresh it with::

    python -m cloudpilot.pricing.refresh

Downsize pairs are declared here, not fetched: "the next size down in the same
family" is a modelling decision about the fleet, not a fact about the rate card.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from loguru import logger

from cloudpilot.pricing.models import CatalogMeta, Price, PriceSource, PriceUnit

SNAPSHOT_PATH = Path(__file__).parent / "data" / "pricing_snapshot.json"

#: The next-smaller SKU in the same family. Right-sizing walks one step down this
#: chain, so each hop must be a genuine halving of the same instance family —
#: never a cross-family jump, which would change performance characteristics.
DOWNSIZE_MAP: dict[str, str] = {
    # Azure
    "Standard_D8s_v3": "Standard_D4s_v3",
    "Standard_D4s_v3": "Standard_D2s_v3",
    "GP_Gen5_4": "GP_Gen5_2",
    # AWS
    "m5.2xlarge": "m5.xlarge",
    "m5.xlarge": "m5.large",
    "db.m5.xlarge": "db.m5.large",
    "cache.m5.xlarge": "cache.m5.large",
    # GCP
    "n2-standard-8": "n2-standard-4",
    "n2-standard-4": "n2-standard-2",
    "db-n1-standard-2": "db-n1-standard-1",
}


class PricingCatalog:
    """An immutable rate card keyed by SKU."""

    def __init__(self, prices: dict[str, Price], meta: CatalogMeta) -> None:
        self._prices = prices
        self.meta = meta

    # ─── lookup ───
    def get(self, sku: str | None) -> Price | None:
        """Return the rate for a SKU, or None if it is not in the catalog."""
        if not sku:
            return None
        return self._prices.get(sku)

    def hourly(self, sku: str | None) -> float:
        """Hourly rate for a compute SKU, 0.0 if unknown or not hour-billed."""
        price = self.get(sku)
        if price is None or price.unit is not PriceUnit.HOUR:
            return 0.0
        return price.amount

    def next_smaller(self, sku: str | None) -> str | None:
        """The next-smaller SKU in the same family, if one is priced."""
        if not sku:
            return None
        target = DOWNSIZE_MAP.get(sku)
        # Never recommend a downsize we cannot price — the saving would be fiction.
        return target if target and target in self._prices else None

    def skus(self) -> list[str]:
        return sorted(self._prices)

    def __len__(self) -> int:
        return len(self._prices)

    # ─── (de)serialisation ───
    @classmethod
    def from_snapshot(cls, path: Path = SNAPSHOT_PATH) -> PricingCatalog:
        """Load the committed snapshot."""
        if not path.exists():
            raise FileNotFoundError(
                f"No pricing snapshot at {path}. CloudPilot will not invent rates — "
                "generate one with:  python -m cloudpilot.pricing.refresh"
            )
        raw = json.loads(path.read_text())
        prices = {
            sku: Price(
                sku=sku,
                provider=entry["provider"],
                amount=float(entry["amount"]),
                unit=PriceUnit(entry["unit"]),
                region=entry["region"],
                source=PriceSource(entry["source"]),
                meter=entry.get("meter", ""),
                currency=entry.get("currency", "USD"),
            )
            for sku, entry in raw["prices"].items()
        }
        verified = sum(1 for p in prices.values() if p.source.is_api_verified)
        meta = CatalogMeta(
            generated_at=datetime.fromisoformat(raw["generated_at"]),
            regions=raw.get("regions", {}),
            api_verified_count=verified,
            total_count=len(prices),
        )
        return cls(prices, meta)

    @staticmethod
    def to_snapshot(prices: dict[str, Price], regions: dict[str, str]) -> str:
        """Serialise a freshly-fetched rate card to snapshot JSON."""
        payload = {
            "generated_at": datetime.now().astimezone().isoformat(),
            "regions": regions,
            "prices": {
                sku: {
                    "provider": p.provider,
                    "amount": round(p.amount, 6),
                    "unit": p.unit.value,
                    "region": p.region,
                    "source": p.source.value,
                    "meter": p.meter,
                    "currency": p.currency,
                }
                for sku, p in sorted(prices.items())
            },
        }
        return json.dumps(payload, indent=2) + "\n"


@lru_cache(maxsize=1)
def get_catalog() -> PricingCatalog:
    """Return the process-wide catalog singleton."""
    catalog = PricingCatalog.from_snapshot()
    logger.info(
        "Pricing catalog loaded: {} SKUs, {:.0f}% API-verified, as of {:%Y-%m-%d}",
        len(catalog),
        catalog.meta.api_verified_pct,
        catalog.meta.generated_at,
    )
    return catalog
