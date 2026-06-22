"""Tests for cost scoring and recommendation-related pure logic."""

from __future__ import annotations

from cloudpilot.ai.pricing import next_smaller_sku, sku_hourly_price
from cloudpilot.services.cost_service import CostService


def test_optimization_score_full_when_no_waste() -> None:
    assert CostService._optimization_score(10000, 0) == 100


def test_optimization_score_drops_with_waste() -> None:
    # 20% of spend recoverable → score ~80.
    score = CostService._optimization_score(10000, 2000)
    assert 78 <= score <= 82


def test_optimization_score_zero_spend() -> None:
    assert CostService._optimization_score(0, 0) == 100


def test_pricing_downsize_chain() -> None:
    assert next_smaller_sku("Standard_D4s_v3") == "Standard_D2s_v3"
    assert next_smaller_sku("m5.xlarge") == "m5.large"
    assert next_smaller_sku("unknown-sku") is None


def test_downsize_actually_saves() -> None:
    current = sku_hourly_price("Standard_D4s_v3")
    target = sku_hourly_price(next_smaller_sku("Standard_D4s_v3"))
    assert current > target > 0
