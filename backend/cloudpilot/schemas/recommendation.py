"""Recommendation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from cloudpilot.models.recommendation import AgentType, RecommendationStatus
from cloudpilot.schemas.common import APISchema, ResponseSchema


class RecommendationResponse(ResponseSchema):
    id: uuid.UUID
    agent: AgentType
    title: str
    description: str
    estimated_saving_usd: float | None = None
    confidence: float
    status: RecommendationStatus
    snoozed_until: datetime | None = None
    affected_resource_ids: list[uuid.UUID] = []
    affected_resource_names: list[str] = []
    # ``validation_alias``, not ``alias``: the ORM column is ``metadata_json``, but
    # FastAPI serialises response models by alias, so a plain alias would also leak
    # that column name onto the wire as the field clients see. Matches chat.py.
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias="metadata_json"
    )
    created_at: datetime


class RecommendationStatusUpdate(APISchema):
    status: RecommendationStatus
    snooze_hours: int | None = Field(default=None, ge=1, le=720)


class SavingsSummary(ResponseSchema):
    total_potential_usd: float
    accepted_usd: float
    pending_count: int
    accepted_count: int
    rejected_count: int
    snoozed_count: int
