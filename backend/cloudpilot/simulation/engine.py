"""The simulation engine — usage in, real cost out.

The rule this module enforces: **CloudPilot never invents a price.** It invents
*usage* (how many nodes ran, for how many hours, how many gigabytes were stored) and
then multiplies by the provider's published rate. So a cost anomaly is not a magic
``cost *= 4.4``; it is fourteen extra Kubernetes nodes for three days, and the dollar
figure is whatever fourteen ``Standard_D4s_v3`` nodes actually cost in West Europe.

That matters for the agents: CostAgent's root-cause explanation is *true* of the
simulated estate, and RightSizingAgent's saving is the genuine delta between two
published rates.

Everything is deterministic — seeded per resource name — so a re-seed reproduces the
same estate, and a demo shows the same numbers twice.
"""

from __future__ import annotations

import calendar
import math
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from cloudpilot.pricing import PriceUnit, get_catalog
from cloudpilot.simulation.fleet import FleetResource, UsageProfile

#: Window of history the simulator generates.
HISTORY_DAYS = 90
#: Days of CPU/RAM samples (RightSizingAgent looks back 14).
METRIC_DAYS = 14
#: Sampling interval for metrics, in hours.
METRIC_INTERVAL_HOURS = 1


# ─────────────────────────────────────────────────────────────
# Events — the physical causes behind the cost anomalies
# ─────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class FleetEvent:
    """A physical change to the estate that shows up in the bill as a consequence.

    ``quantity_factor`` multiplies the resource's billable quantity (node count) for
    the duration of the event. The cost delta is *derived* from the rate card, never
    stated — which is what makes the anomaly explainable.
    """

    resource_name: str
    #: Days before "today" the event starts.
    days_ago: int
    duration_days: int
    quantity_factor: float
    cause: str

    def covers(self, day: date, today: date) -> bool:
        start = today - timedelta(days=self.days_ago)
        return start <= day < start + timedelta(days=self.duration_days)


EVENTS: list[FleetEvent] = [
    FleetEvent(
        resource_name="aks-prod-cluster",
        days_ago=45,
        duration_days=3,
        quantity_factor=4.5,  # 4 nodes -> 18
        cause=(
            "A misconfigured HPA target drove the cluster autoscaler from 4 to 18 "
            "nodes and it stayed scaled out for three days before the limit was capped."
        ),
    ),
    FleetEvent(
        resource_name="rds-production",
        days_ago=12,
        duration_days=2,
        quantity_factor=4.0,  # 1 instance -> 1 primary + 3 read replicas
        cause=(
            "A load test provisioned three read replicas against the production "
            "database and they were not torn down when the test finished."
        ),
    ),
]


def events_for(resource_name: str) -> list[FleetEvent]:
    return [e for e in EVENTS if e.resource_name == resource_name]


# ─────────────────────────────────────────────────────────────
# Usage
# ─────────────────────────────────────────────────────────────
def _rng(resource: FleetResource, salt: str = "") -> random.Random:
    """A generator seeded per-resource, so the estate is reproducible."""
    return random.Random(f"{resource.name}:{salt}")


def billable_hours(resource: FleetResource, day: date) -> float:
    """Hours the resource actually ran on ``day``.

    Dev and staging resources are idle out of hours. This is what produces the
    weekday/weekend shape in the bill — as a consequence of behaviour, rather than
    the arbitrary ``1.2 weekday / 0.85 weekend`` factor it replaces.
    """
    if resource.profile is UsageProfile.DEV:
        # Left on through the working day, off at night and over the weekend.
        return 0.0 if day.weekday() >= 5 else 12.0
    return 24.0


def billable_quantity(resource: FleetResource, day: date, today: date) -> float:
    """Nodes (compute) or gigabytes (storage) billed on ``day``.

    Applies steady growth across the window and any event in force that day.
    """
    days_elapsed = (day - (today - timedelta(days=HISTORY_DAYS - 1))).days
    months = max(0.0, days_elapsed / 30.0)
    quantity = resource.quantity * (1.0 + resource.growth * months)

    for event in events_for(resource.name):
        if event.covers(day, today):
            quantity *= event.quantity_factor
    return quantity


def utilization(resource: FleetResource, moment: datetime) -> tuple[float, float]:
    """Return ``(cpu_percent, memory_percent)`` at a point in time.

    The profile determines the shape, and the shape is what the agents key off:
    ``OVERSIZED`` stays under the P95 thresholds so RightSizingAgent flags it, while
    ``BURSTY`` has a low mean but a high P95 so it is correctly left alone.
    """
    rng = _rng(resource, moment.isoformat())
    hour = moment.hour
    weekend = moment.weekday() >= 5
    # A working-hours bell curve peaking around 14:00.
    diurnal = math.exp(-(((hour - 14) / 5.0) ** 2))

    if resource.profile is UsageProfile.OVERSIZED:
        # Comfortably under RightSizingAgent's 40% CPU / 60% RAM thresholds.
        cpu = 16.0 + 8.0 * diurnal + rng.uniform(-3, 3)
        mem = 38.0 + 6.0 * diurnal + rng.uniform(-3, 3)
    elif resource.profile is UsageProfile.BURSTY:
        # Idle most of the day, then pinned during the nightly batch window.
        burst = hour in (2, 3, 4)
        cpu = (92.0 + rng.uniform(-4, 5)) if burst else 12.0 + rng.uniform(-4, 6)
        mem = (85.0 + rng.uniform(-5, 6)) if burst else 30.0 + rng.uniform(-5, 6)
    elif resource.profile is UsageProfile.DEV:
        working = (not weekend) and 9 <= hour < 19
        cpu = (42.0 + rng.uniform(-8, 8)) if working else 2.0 + rng.uniform(0, 2)
        mem = (55.0 + rng.uniform(-8, 8)) if working else 12.0 + rng.uniform(0, 3)
    else:  # STEADY
        weekend_damp = 0.65 if weekend else 1.0
        cpu = (52.0 + 18.0 * diurnal) * weekend_damp + rng.uniform(-4, 4)
        mem = (61.0 + 12.0 * diurnal) * weekend_damp + rng.uniform(-4, 4)

    return _clamp(cpu), _clamp(mem)


def _clamp(value: float, low: float = 0.5, high: float = 99.5) -> float:
    return max(low, min(high, value))


def metric_samples(
    resource: FleetResource, today: date, days: int = METRIC_DAYS
) -> list[tuple[str, datetime, float, str]]:
    """Generate ``(metric_name, timestamp, value, unit)`` rows for a resource."""
    if resource.profile is UsageProfile.STORAGE:
        return []  # storage has no CPU/RAM to report
    rows: list[tuple[str, datetime, float, str]] = []
    start = datetime.combine(today - timedelta(days=days), time(0, 0), tzinfo=UTC)
    steps = days * 24 // METRIC_INTERVAL_HOURS
    for step in range(steps):
        moment = start + timedelta(hours=step * METRIC_INTERVAL_HOURS)
        cpu, mem = utilization(resource, moment)
        rows.append(("cpu_percent", moment, round(cpu, 2), "percent"))
        rows.append(("memory_percent", moment, round(mem, 2), "percent"))
    return rows


# ─────────────────────────────────────────────────────────────
# Costing — the only place a dollar figure is produced
# ─────────────────────────────────────────────────────────────
def daily_cost(resource: FleetResource, day: date, today: date) -> float:
    """The cost of one resource on one day, priced from the published rate card.

    Compute is ``rate x nodes x running_hours``. Storage is ``rate x GB`` spread over
    the days in that month, because storage rates are quoted per GB-month.
    Returns 0.0 for a SKU with no rate — an unpriced resource contributes nothing
    rather than contributing a guess.
    """
    price = get_catalog().get(resource.price_sku)
    if price is None:
        return 0.0

    quantity = billable_quantity(resource, day, today)

    if price.unit is PriceUnit.HOUR:
        return price.amount * quantity * billable_hours(resource, day)

    days_in_month = calendar.monthrange(day.year, day.month)[1]
    return price.amount * quantity / days_in_month


def daily_costs(
    resource: FleetResource, today: date, days: int = HISTORY_DAYS
) -> list[tuple[date, float]]:
    """The full daily cost series for a resource across the history window."""
    start = today - timedelta(days=days - 1)
    return [
        (
            start + timedelta(days=offset),
            daily_cost(resource, start + timedelta(days=offset), today),
        )
        for offset in range(days)
    ]


def monthly_run_rate(resource: FleetResource, today: date | None = None) -> float:
    """A resource's steady-state monthly cost, ignoring events and growth."""
    price = get_catalog().get(resource.price_sku)
    if price is None:
        return 0.0
    if price.unit is PriceUnit.HOUR:
        # Average billable hours across a week, annualised to a 730-hour month.
        ref = today or date.today()
        week = [billable_hours(resource, ref + timedelta(days=d)) for d in range(7)]
        duty_cycle = sum(week) / (7 * 24.0)
        return price.amount * resource.quantity * 730.0 * duty_cycle
    return price.amount * resource.quantity
