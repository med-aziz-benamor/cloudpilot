"""Forecast snapshot model — persisted Prophet output produced by ForecastAgent."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cloudpilot.database import BaseModel


class ForecastSnapshot(BaseModel):
    """A stored forecast. The ``/forecast`` endpoint reads from here rather than
    re-running Prophet on every request."""

    __tablename__ = "forecast_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "snapshot_date",
            "horizon_days",
            name="uq_forecast_org_date_horizon",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
