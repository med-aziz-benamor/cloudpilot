"""Pricing catalog schemas — the rate card, and where each rate came from.

Every saving CloudPilot reports is derived from this catalog. Exposing it lets a
reviewer check the arithmetic against the publisher's own number instead of
taking the figure on faith, which is the whole point of tracking provenance.
"""

from __future__ import annotations

from datetime import datetime

from cloudpilot.pricing.models import PriceSource, PriceUnit
from cloudpilot.schemas.common import ResponseSchema


class PriceEntry(ResponseSchema):
    """One rate-card entry, with its provenance."""

    sku: str
    provider: str
    amount: float
    unit: PriceUnit
    region: str
    source: PriceSource
    #: True when the rate was fetched from a provider API rather than transcribed.
    api_verified: bool
    #: Provider-side meter identifier, so the rate can be looked up at the source.
    meter: str
    currency: str


class PricingCatalogResponse(ResponseSchema):
    """The whole rate card plus snapshot-level provenance."""

    generated_at: datetime
    #: Whole days since the snapshot was generated.
    age_days: int
    #: True once the snapshot is older than the catalog's freshness window. Surfaced
    #: so a stale rate card is visible rather than silently trusted.
    is_stale: bool
    stale_after_days: int
    regions: dict[str, str]
    total_count: int
    api_verified_count: int
    api_verified_pct: float
    rates: list[PriceEntry]
