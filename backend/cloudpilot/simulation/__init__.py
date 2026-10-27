"""Fleet simulation: synthetic usage, real prices.

Usage (node counts, running hours, gigabytes) is simulated. Cost is always derived
from the published rate card in :mod:`cloudpilot.pricing`, never invented.
"""

from cloudpilot.simulation.engine import (
    EVENTS,
    HISTORY_DAYS,
    METRIC_DAYS,
    FleetEvent,
    daily_cost,
    daily_costs,
    metric_samples,
    monthly_run_rate,
)
from cloudpilot.simulation.fleet import FLEET, FleetResource, UsageProfile, fleet_for

__all__ = [
    "EVENTS",
    "FLEET",
    "HISTORY_DAYS",
    "METRIC_DAYS",
    "FleetEvent",
    "FleetResource",
    "UsageProfile",
    "daily_cost",
    "daily_costs",
    "fleet_for",
    "metric_samples",
    "monthly_run_rate",
]
