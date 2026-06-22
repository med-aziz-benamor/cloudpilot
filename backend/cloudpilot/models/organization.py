"""Organization model — the tenant boundary of the platform."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cloudpilot.database import BaseModel

if TYPE_CHECKING:
    from cloudpilot.models.cloud_account import CloudAccount
    from cloudpilot.models.user import User


class OrgPlan(str, enum.Enum):
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
        SAEnum(OrgPlan, name="org_plan"),
        default=OrgPlan.FREE,
        nullable=False,
    )

    users: Mapped[list[User]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    cloud_accounts: Mapped[list[CloudAccount]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
