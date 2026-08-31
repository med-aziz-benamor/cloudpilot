"""Pricing catalog endpoints — the rate card every saving is derived from.

The catalog is public rate-card data, identical for every tenant, so these
endpoints are deliberately *not* org-scoped: there is nothing here that belongs to
one organization. They are still authenticated, because the set of SKUs CloudPilot
prices is a hint about the estate it was built for.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from cloudpilot.api.deps import get_current_user
from cloudpilot.models.user import User
from cloudpilot.pricing import get_catalog
from cloudpilot.pricing.models import STALE_AFTER_DAYS
from cloudpilot.schemas.pricing import PriceEntry, PricingCatalogResponse

router = APIRouter()


@router.get("/catalog", response_model=PricingCatalogResponse)
async def get_pricing_catalog(
    _: User = Depends(get_current_user),
) -> PricingCatalogResponse:
    """Return the whole rate card, with per-rate and snapshot-level provenance."""
    catalog = get_catalog()
    meta = catalog.meta
    return PricingCatalogResponse(
        generated_at=meta.generated_at,
        age_days=meta.age_days,
        is_stale=meta.is_stale,
        stale_after_days=STALE_AFTER_DAYS,
        regions=meta.regions,
        total_count=meta.total_count,
        api_verified_count=meta.api_verified_count,
        api_verified_pct=round(meta.api_verified_pct, 1),
        rates=[
            PriceEntry(
                sku=p.sku,
                provider=p.provider,
                amount=p.amount,
                unit=p.unit,
                region=p.region,
                source=p.source,
                api_verified=p.source.is_api_verified,
                meter=p.meter,
                currency=p.currency,
            )
            for p in catalog.entries()
        ],
    )
