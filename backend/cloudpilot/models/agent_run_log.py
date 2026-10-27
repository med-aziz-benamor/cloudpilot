"""Agent run log model — execution telemetry for scheduled and on-demand agents."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cloudpilot.database import BaseModel
from cloudpilot.models.recommendation import AgentType


class AgentRunStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class AgentRunLog(BaseModel):
    """One execution of an agent. Used by the orchestrator and the admin endpoints."""

    __tablename__ = "agent_run_logs"
    __table_args__ = (
        Index("ix_agent_run_logs_agent_org_started", "agent", "organization_id", "started_at"),
    )

    agent: Mapped[AgentType] = mapped_column(
        SAEnum(AgentType, name="agent_type", native_enum=False), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        SAEnum(AgentRunStatus, name="agent_run_status", native_enum=False),
        default=AgentRunStatus.RUNNING,
        nullable=False,
    )
    recommendations_created: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
