"""Pricing data model.

Every price in CloudPilot carries three things beyond its amount:

* a **unit** — compute is billed per hour, storage per GB-month. Collapsing both
  into "hourly price" silently mis-prices storage by a factor of ~730, so the unit
  is explicit and the cost engine dispatches on it.
* a **provenance** — where the number came from. A rate pulled from the Azure
  Retail API is defensible; a hand-typed constant is not. Recommendations surface
  this so a reviewer can trace any dollar figure back to its publisher.
* an **as-of date** — rate cards change. A stale snapshot should be visible, not
  silently trusted.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


class PriceUnit(enum.StrEnum):
    """The billing unit a rate is quoted in."""

    HOUR = "hour"
    GB_MONTH = "gb_month"


class PriceSource(enum.StrEnum):
    """Where a rate came from — its defensibility, in one field."""

    #: Pulled live from the provider's public, unauthenticated rate-card API.
    AZURE_RETAIL_API = "azure_retail_api"
    AWS_PRICE_LIST = "aws_price_list"
    #: Transcribed from the provider's published public pricing page. Real, but
    #: not machine-verified — used where the provider has no keyless rate API.
    PUBLISHED_LIST_PRICE = "published_list_price"

    @property
    def is_api_verified(self) -> bool:
        """True when the rate was fetched from a provider API rather than transcribed."""
        return self in (PriceSource.AZURE_RETAIL_API, PriceSource.AWS_PRICE_LIST)


@dataclass(frozen=True, slots=True)
class Price:
    """One rate-card entry."""

    sku: str
    provider: str
    amount: float
    unit: PriceUnit
    region: str
    source: PriceSource
    #: Provider-side identifier for the meter this rate came from, for auditability.
    meter: str = ""
    currency: str = "USD"

    def monthly_cost(self, quantity: float, hours: float = 730.0) -> float:
        """Project a monthly cost for ``quantity`` of this SKU.

        ``quantity`` is instance-count for HOUR-priced SKUs and gigabytes for
        GB_MONTH-priced ones. ``hours`` is the billable hours in the month (730 is
        the conventional FinOps average) and is ignored for storage.
        """
        if self.unit is PriceUnit.HOUR:
            return self.amount * quantity * hours
        return self.amount * quantity

    def describe(self) -> str:
        """Human-readable provenance line, e.g. for a recommendation footnote."""
        unit = "/hr" if self.unit is PriceUnit.HOUR else "/GB-month"
        return f"${self.amount:,.4f}{unit} ({self.provider} {self.region}, {self.source.value})"


@dataclass(frozen=True, slots=True)
class CatalogMeta:
    """Provenance for a whole snapshot."""

    generated_at: datetime
    regions: dict[str, str]
    api_verified_count: int
    total_count: int

    @property
    def api_verified_pct(self) -> float:
        if not self.total_count:
            return 0.0
        return self.api_verified_count / self.total_count * 100.0
