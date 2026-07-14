"""Tests for the fleet simulation.

Two things are being pinned down here.

First, that the simulated estate actually contains what the agents are meant to find:
if a refactor makes every resource look healthy, the demo silently shows an empty
recommendations page, and these tests fail instead.

Second, that cost is *derived* rather than invented. The event tests assert the exact
arithmetic — nodes x published rate x hours — so a stray fudge factor cannot creep
back in.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from cloudpilot.ai.cost_agent import CostAgent
from cloudpilot.pricing import PriceUnit, get_catalog
from cloudpilot.simulation import FLEET, daily_cost, fleet_for, metric_samples
from cloudpilot.simulation.engine import (
    billable_hours,
    billable_quantity,
    events_for,
)
from cloudpilot.simulation.fleet import UsageProfile, by_name

# RightSizingAgent's thresholds — duplicated deliberately, so that moving the agent's
# thresholds without re-tuning the fleet fails loudly here.
CPU_THRESHOLD = 40.0
MEM_THRESHOLD = 60.0

TODAY = date.today()


def p95(resource, metric: str) -> float:
    values = [v for name, _, v, _ in metric_samples(resource, TODAY) if name == metric]
    return float(np.percentile(values, 95))


# ─────────────────────────────────────────────────────────────
# The fleet contains what the agents should find
# ─────────────────────────────────────────────────────────────
def test_every_resource_is_priceable() -> None:
    """An unpriced resource contributes $0 and silently vanishes from the bill."""
    catalog = get_catalog()
    for resource in FLEET:
        assert catalog.get(resource.price_sku) is not None, (
            f"{resource.name} references unpriced SKU {resource.price_sku}"
        )


@pytest.mark.parametrize(
    "resource", [r for r in FLEET if r.profile is UsageProfile.OVERSIZED], ids=lambda r: r.name
)
def test_oversized_resources_are_detectable(resource) -> None:
    """Every OVERSIZED resource must sit under both thresholds, or it is never flagged."""
    assert p95(resource, "cpu_percent") < CPU_THRESHOLD
    assert p95(resource, "memory_percent") < MEM_THRESHOLD


@pytest.mark.parametrize(
    "resource",
    [r for r in FLEET if r.profile in (UsageProfile.STEADY, UsageProfile.BURSTY)],
    ids=lambda r: r.name,
)
def test_healthy_resources_are_not_flagged(resource) -> None:
    """No false positives.

    BURSTY is the interesting case: its *mean* utilization is low, so a naive detector
    would flag it, but its P95 is high because it is pinned during the batch window.
    Downsizing it would throttle the batch job.
    """
    under_both = (
        p95(resource, "cpu_percent") < CPU_THRESHOLD
        and p95(resource, "memory_percent") < MEM_THRESHOLD
    )
    assert not under_both, f"{resource.name} ({resource.profile.value}) would be flagged"


def test_every_oversized_resource_has_a_priced_downsize_path() -> None:
    """An oversized resource with no cheaper target produces no recommendation at all."""
    catalog = get_catalog()
    for resource in FLEET:
        if resource.profile is not UsageProfile.OVERSIZED:
            continue
        target = catalog.next_smaller(resource.sku)
        assert target is not None, f"{resource.name} ({resource.sku}) has no priced downsize"


# ─────────────────────────────────────────────────────────────
# Cost is derived from the rate card, never invented
# ─────────────────────────────────────────────────────────────
def test_cost_equals_rate_times_nodes_times_hours() -> None:
    aks = by_name("aks-prod-cluster")
    rate = get_catalog().hourly(aks.price_sku)
    # A quiet day, well away from the autoscaler event.
    quiet = TODAY - timedelta(days=1)
    assert daily_cost(aks, quiet, TODAY) == pytest.approx(rate * aks.quantity * 24.0)


def test_autoscaler_event_cost_is_the_extra_nodes() -> None:
    """The anomaly is 14 extra nodes, and its cost is exactly what 14 nodes cost."""
    aks = by_name("aks-prod-cluster")
    event = events_for("aks-prod-cluster")[0]
    rate = get_catalog().hourly(aks.price_sku)

    spike_day = TODAY - timedelta(days=event.days_ago)
    quiet_day = TODAY - timedelta(days=1)

    scaled_nodes = aks.quantity * event.quantity_factor
    assert billable_quantity(aks, spike_day, TODAY) == pytest.approx(scaled_nodes)
    assert daily_cost(aks, spike_day, TODAY) == pytest.approx(rate * scaled_nodes * 24.0)

    delta = daily_cost(aks, spike_day, TODAY) - daily_cost(aks, quiet_day, TODAY)
    extra_nodes = scaled_nodes - aks.quantity
    assert delta == pytest.approx(rate * extra_nodes * 24.0)


def test_storage_is_billed_per_gb_month_not_per_hour() -> None:
    """A GB-month rate divided across the month, not multiplied by 24."""
    blob = by_name("blob-media-01")
    price = get_catalog().get(blob.price_sku)
    assert price is not None and price.unit is PriceUnit.GB_MONTH

    day = date(2026, 6, 15)  # June has 30 days
    gb = billable_quantity(blob, day, TODAY)
    assert daily_cost(blob, day, TODAY) == pytest.approx(price.amount * gb / 30)


def test_dev_resources_do_not_bill_at_the_weekend() -> None:
    """The weekday/weekend shape is a consequence of behaviour, not a fudge factor."""
    dev = by_name("vm-dev-01")
    saturday = next(
        TODAY - timedelta(days=d) for d in range(1, 8) if (TODAY - timedelta(days=d)).weekday() == 5
    )
    weekday = next(
        TODAY - timedelta(days=d) for d in range(1, 8) if (TODAY - timedelta(days=d)).weekday() < 5
    )
    assert billable_hours(dev, saturday) == 0.0
    assert daily_cost(dev, saturday, TODAY) == 0.0
    assert daily_cost(dev, weekday, TODAY) > 0.0


def test_simulation_is_deterministic() -> None:
    """A re-seed must reproduce the same estate, or the demo shows different numbers."""
    vm = by_name("vm-analytics-01")
    assert metric_samples(vm, TODAY) == metric_samples(vm, TODAY)
    assert daily_cost(vm, TODAY, TODAY) == daily_cost(vm, TODAY, TODAY)


# ─────────────────────────────────────────────────────────────
# End to end: the CostAgent finds the seeded incidents
# ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "provider,service,resource_name",
    [("azure", "aks_cluster", "aks-prod-cluster"), ("aws", "rds_instance", "rds-production")],
)
def test_cost_agent_detects_the_seeded_incident(provider, service, resource_name) -> None:
    """The two injected incidents must survive aggregation to the service level.

    An anomaly on one resource can be washed out once it is summed with its peers, so
    this asserts detection on the same daily-service totals the agent actually sees.
    """
    event = events_for(resource_name)[0]
    incident_day = TODAY - timedelta(days=event.days_ago)

    totals: dict[date, float] = {}
    for resource in fleet_for(provider):
        if resource.service != service:
            continue
        for offset in range(60):
            day = TODAY - timedelta(days=59 - offset)
            totals[day] = totals.get(day, 0.0) + daily_cost(resource, day, TODAY)

    days = sorted(totals)
    values = np.array([totals[d] for d in days], dtype=float)
    flagged = CostAgent()._detect(days, values)

    assert days.index(incident_day) in flagged, f"{resource_name} incident was not detected"
