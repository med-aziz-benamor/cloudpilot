"""Billing entry model — a daily per-service cost line item."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cloudpilot.database import BaseModel

if TYPE_CHECKING:
    from cloudpilot.models.resource import Resource


class BillingEntry(BaseModel):
    """A single day's cost for a (cloud account, service[, resource]) tuple.

    ``cost_usd`` is the normalized USD amount used for all analytics; the raw
    provider currency/amount is retained for auditability.
    """

    __tablename__ = "billing_entries"
    __table_args__ = (
        Index("ix_billing_account_date", "cloud_account_id", "usage_date"),
        Index("ix_billing_resource_date", "resource_id", "usage_date"),
    )

    cloud_account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="SET NULL"),
        nullable=True,
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    service: Mapped[str] = mapped_column(String(80), nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    raw_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="USD")
    raw_amount: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    resource: Mapped[Resource | None] = relationship(back_populates="billing_entries")
