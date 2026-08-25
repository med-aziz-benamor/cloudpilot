"""Cloud account model — a connected Azure subscription / AWS account / GCP project."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cloudpilot.database import BaseModel

if TYPE_CHECKING:
    from cloudpilot.models.organization import Organization
    from cloudpilot.models.resource import Resource


class CloudProvider(enum.StrEnum):
    AZURE = "azure"
    AWS = "aws"
    GCP = "gcp"


class CloudAccountStatus(enum.StrEnum):
    ACTIVE = "active"
    ERROR = "error"
    PAUSED = "paused"


class CloudAccount(BaseModel):
    """A connected cloud account. Provider credentials are stored Fernet-encrypted
    in ``credentials_enc`` — never in plaintext, never logged, never returned by the API."""

    __tablename__ = "cloud_accounts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "account_identifier",
            name="uq_cloud_account_identity",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[CloudProvider] = mapped_column(
        SAEnum(CloudProvider, name="cloud_provider", native_enum=False), nullable=False
    )
    account_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    credentials_enc: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CloudAccountStatus] = mapped_column(
        SAEnum(CloudAccountStatus, name="cloud_account_status", native_enum=False),
        default=CloudAccountStatus.ACTIVE,
        nullable=False,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="cloud_accounts")
    resources: Mapped[list[Resource]] = relationship(
        back_populates="cloud_account", cascade="all, delete-orphan"
    )
