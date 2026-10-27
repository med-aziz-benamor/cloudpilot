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


def test_metadata_reaches_clients_under_its_schema_name() -> None:
    """The calculation basis must serialise as ``metadata``, not ``metadata_json``.

    FastAPI dumps response models with ``by_alias=True``, so a plain ``alias`` — used
    to map the ORM column — also renames the field on the wire. That put the API's
    key at ``metadata_json`` while the frontend type declared ``metadata``, and the
    provenance the agents record simply never arrived under the name anything read.
    Nothing caught it because nothing consumed the field until the UI surfaced it.
    """
    import uuid
    from datetime import datetime

    from cloudpilot.models.recommendation import AgentType, RecommendationStatus
    from cloudpilot.schemas.recommendation import RecommendationResponse

    class Row:
        id = uuid.uuid4()
        agent = AgentType.RIGHTSIZING
        title = "Underutilized resource"
        description = ""
        estimated_saving_usd = 244.46
        confidence = 0.9
        status = RecommendationStatus.PENDING
        snoozed_until = None
        affected_resource_ids: list[uuid.UUID] = []
        affected_resource_names: list[str] = []
        metadata_json = {"pricing": {"current": {"source": "azure_retail_api"}}}
        created_at = datetime.now().astimezone()

    dumped = RecommendationResponse.model_validate(Row()).model_dump(by_alias=True)

    assert "metadata" in dumped
    assert "metadata_json" not in dumped
    assert dumped["metadata"]["pricing"]["current"]["source"] == "azure_retail_api"
