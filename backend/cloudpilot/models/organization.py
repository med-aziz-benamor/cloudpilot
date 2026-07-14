"""Organization model — the tenant boundary of the platform."""

from __future__ import annotations

import enum
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cloudpilot.database import BaseModel

if TYPE_CHECKING:
    from cloudpilot.models.cloud_account import CloudAccount
    from cloudpilot.models.user import User


class OrgPlan(enum.StrEnum):
    """Subscription tier."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class Organization(BaseModel):
    """A tenant. Every other domain object ultimately belongs to one organization."""

    __tablename__ = "organizations"
    __table_args__ = (Index("ix_organizations_name", "name"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    plan: Mapped[OrgPlan] = mapped_column(
        SAEnum(OrgPlan, name="org_plan", native_enum=False),
        default=OrgPlan.FREE,
        nullable=False,
    )
    #: The tenant's monthly cloud budget. ForecastAgent raises an overrun alert when
    #: projected month-end spend exceeds this. NULL means "no budget set", in which
    #: case no alert is raised — an alert against a budget the tenant never agreed to
    #: is noise, which is what a single hardcoded figure produced for every org.
    monthly_budget_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    users: Mapped[list[User]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    cloud_accounts: Mapped[list[CloudAccount]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
