"""CostAgent sensitivity — calibrated against physically-derived anomalies.

Background: the old ``pct >= 50`` gate was set when costs were fabricated
arithmetically. Costs are now ``published_rate × simulated_usage``, so an anomaly is
a physical event on one resource, while detection groups by (account, service) —
the spike therefore arrives diluted by whatever else shares that group.

These tests are pure (no DB): they drive ``_detect`` and the materiality gates over
synthetic series shaped like the seeded incidents.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from cloudpilot.ai.cost_agent import (
    _MIN_DELTA_USD,
    _MIN_PCT_ABOVE_BASELINE,
    CostAgent,
)


def _series(baseline: float, spike_multiplier: float, n: int = 60, spike_at: int = 30):
    """A flat series with one spike, plus the dates the agent would pair with it."""
    values = np.full(n, baseline, dtype=float)
    values[spike_at] = baseline * spike_multiplier
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    return dates, values


def _surfaces(dates, values, idx: int) -> bool:
    """Replicate the agent's decision for one index: detected AND material."""
    flagged = set(CostAgent()._detect(dates, values))
    if idx not in flagged:
        return False
    actual = float(values[idx])
    baseline = float(np.mean(np.delete(values, idx)))
    if baseline <= 0:
        return False
    delta = actual - baseline
    pct = (delta / baseline) * 100.0
    return pct >= _MIN_PCT_ABOVE_BASELINE and delta >= _MIN_DELTA_USD


def test_kubernetes_scale_out_is_detected() -> None:
    """The aks-prod-cluster incident: ~+150-167% at the service-group level."""
    dates, values = _series(baseline=48.0, spike_multiplier=2.6)
    assert _surfaces(dates, values, 30)


def test_rds_replica_incident_is_detected() -> None:
    """The rds-production incident: only ~+57% once diluted by its service group."""
    dates, values = _series(baseline=23.0, spike_multiplier=1.57)
    assert _surfaces(dates, values, 30)


def test_diluted_incident_still_detected_after_estate_growth() -> None:
    """The regression this recalibration exists for.

    Same physical 4x event, but the affected resource is now a smaller share of its
    service group, so the group-level percentage drops. Under the old ``pct >= 50``
    gate this vanished at +48% even though its Z-score was unchanged at ~5.
    """
    dates, values = _series(baseline=46.0, spike_multiplier=1.48)
    assert _surfaces(dates, values, 30), (
        "a real incident disappeared because siblings diluted its percentage"
    )


def test_trivial_percentage_is_ignored() -> None:
    """Ordinary variance must not surface: below the percentage gate."""
    dates, values = _series(baseline=100.0, spike_multiplier=1.10)
    assert not _surfaces(dates, values, 30)


def test_large_percentage_on_trivial_spend_is_ignored() -> None:
    """A 3x spike on a $2/day service is noise regardless of the percentage.

    This is what the absolute floor buys: it lets the percentage gate come down
    without the agent starting to report pocket change.
    """
    dates, values = _series(baseline=2.0, spike_multiplier=3.0)
    delta = 2.0 * 3.0 - 2.0
    assert delta < _MIN_DELTA_USD  # premise of the test
    assert not _surfaces(dates, values, 30)


def test_gates_are_documented_values() -> None:
    """Guard against a silent re-tune; the values are argued for in cost_agent.py."""
    assert _MIN_PCT_ABOVE_BASELINE == 25.0
    assert _MIN_DELTA_USD == 5.0


def test_flat_series_produces_nothing() -> None:
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(60)]
    values = np.full(60, 50.0, dtype=float)
    assert not any(_surfaces(dates, values, i) for i in range(60))
