"""Metric sample model — time-series telemetry for resources.

In production this table is RANGE-partitioned by month on ``timestamp`` for
efficient pruning and query performance. The composite primary key
``(resource_id, metric_name, timestamp)`` is partition-compatible. The Alembic
migration creates the parent table plus monthly partitions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cloudpilot.database import Base


class MetricSample(Base):
    """A single metric reading. Not a :class:`BaseModel` — uses a composite PK and
    has no surrogate ``id`` so it can participate in range partitioning."""

    __tablename__ = "metric_samples"
    __table_args__ = (
        Index("ix_metric_samples_resource_metric", "resource_id", "metric_name"),
        Index("ix_metric_samples_org_resource", "organization_id", "resource_id"),
    )

    #: Denormalized from the owning resource (migration 005). Carried directly
    #: so the ORM tenant filter in ``core/tenant.py`` engages on this table —
    #: it inspects mappers for this column and cannot follow ``resource_id``
    #: to find one. See docs/security.md.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    metric_name: Mapped[str] = mapped_column(String(80), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)

    resource = relationship("Resource", back_populates="metrics")
