"""SKU pricing lookups used by the agents.

This module is a thin facade over :mod:`cloudpilot.pricing`, which holds the real
rate card fetched from the providers' public pricing APIs. It exists so the agents
keep a small, stable surface (``sku_hourly_price`` / ``next_smaller_sku``) that does
not shift when the catalog's internals do.

Rates are no longer hand-typed constants: refresh them with
``python -m cloudpilot.pricing.refresh``.
"""

from __future__ import annotations

from cloudpilot.pricing import Price, get_catalog


def sku_hourly_price(sku: str | None) -> float:
    """Return the on-demand hourly rate for a compute SKU (0.0 if unknown)."""
    return get_catalog().hourly(sku)


def next_smaller_sku(sku: str | None) -> str | None:
    """Return the next-smaller SKU in the same family, or None.

    Only returns a target that is actually priced — recommending a downsize whose
    saving cannot be computed from a published rate would defeat the point.
    """
    return get_catalog().next_smaller(sku)


def sku_price(sku: str | None) -> Price | None:
    """Return the full rate entry, including its unit and provenance."""
    return get_catalog().get(sku)


def pricing_provenance(sku: str | None) -> dict[str, str | float] | None:
    """Return a serialisable provenance record for a SKU's rate.

    Attached to recommendations so a reviewer can trace a saving back to the
    publisher and the date it was quoted, rather than taking the number on faith.
    """
    catalog = get_catalog()
    price = catalog.get(sku)
    if price is None:
        return None
    return {
        "rate": price.amount,
        "unit": price.unit.value,
        "currency": price.currency,
        "region": price.region,
        "source": price.source.value,
        "meter": price.meter,
        "as_of": catalog.meta.generated_at.date().isoformat(),
    }
