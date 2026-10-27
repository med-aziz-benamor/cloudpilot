"""Resource model — a discovered cloud resource (VM, cluster, DB, bucket, ...)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cloudpilot.database import BaseModel

if TYPE_CHECKING:
    from cloudpilot.models.billing_entry import BillingEntry
    from cloudpilot.models.cloud_account import CloudAccount
    from cloudpilot.models.metric_sample import MetricSample


class Resource(BaseModel):
    """A single cloud resource belonging to a cloud account."""

    __tablename__ = "resources"
    __table_args__ = (
        Index("ix_resources_account_service", "cloud_account_id", "service"),
        Index("ix_resources_account_region", "cloud_account_id", "region"),
        Index("ix_resources_org", "organization_id"),
    )

    #: Denormalized from ``cloud_account.organization_id``. Redundant on purpose: the
    #: tenant listener in ``core/tenant.py`` filters entities that declare this column,
    #: and it cannot follow a join to find one. Without it this table is guarded only
    #: by services remembering to scope their queries. Every write path must set it.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    cloud_account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_resource_id: Mapped[str] = mapped_column(String(512), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    service: Mapped[str] = mapped_column(String(80), nullable=False)
    region: Mapped[str] = mapped_column(String(40), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: How many instances of ``sku`` this resource bills for. A single VM is 1; an AKS
    #: or GKE node pool of four nodes is 4. Without this, a right-sizing saving is
    #: computed per-instance and under-reports a node pool by its node count.
    node_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    tags_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    cloud_account: Mapped[CloudAccount] = relationship(back_populates="resources")
    metrics: Mapped[list[MetricSample]] = relationship(
        back_populates="resource", cascade="all, delete-orphan"
    )
    billing_entries: Mapped[list[BillingEntry]] = relationship(
        back_populates="resource"
    )
