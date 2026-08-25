"""Recommendation model — actionable output produced by the AI agents."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cloudpilot.database import BaseModel


class AgentType(enum.StrEnum):
    COST = "cost"
    RIGHTSIZING = "rightsizing"
    FORECAST = "forecast"
    ARCHITECT = "architect"


class RecommendationStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SNOOZED = "snoozed"


class Recommendation(BaseModel):
    """An optimization recommendation. The ``confidence`` is a 0–1 score and
    ``estimated_saving_usd`` is the projected monthly saving (may be null, e.g. for
    forecast budget-overrun alerts)."""

    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_org_status", "organization_id", "status"),
        Index("ix_recommendations_org_agent", "organization_id", "agent"),
        Index("ix_recommendations_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    cloud_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
        nullable=True,
    )
    agent: Mapped[AgentType] = mapped_column(
        SAEnum(AgentType, name="agent_type", native_enum=False), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_saving_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[RecommendationStatus] = mapped_column(
        SAEnum(RecommendationStatus, name="recommendation_status", native_enum=False),
        default=RecommendationStatus.PENDING,
        nullable=False,
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    affected_resource_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), default=list, nullable=False
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
