"""Initial CloudPilot schema — all tables, enums, indexes, partitions.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-06-18

This migration creates the complete database schema. The ``metric_samples`` table
is created as a RANGE-partitioned table on ``timestamp`` with monthly partitions
spanning the current demo window.

Enum columns are stored as VARCHAR (native_enum=False) to avoid asyncpg codec
incompatibilities with Python enum serialisation.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    """The id / created_at / updated_at columns inherited by most tables."""
    return [
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ─── organizations ───
    op.create_table(
        "organizations",
        *_base_columns(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"])

    # ─── users ───
    op.create_table(
        "users",
        *_base_columns(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("role", sa.String(20), nullable=False, server_default="analyst"),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("mfa_secret_enc", sa.Text, nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_users_org_email", "users", ["organization_id", "email"])

    # ─── cloud_accounts ───
    op.create_table(
        "cloud_accounts",
        *_base_columns(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("account_identifier", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("credentials_enc", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "account_identifier",
            name="uq_cloud_account_identity",
        ),
    )

    # ─── resources ───
    op.create_table(
        "resources",
        *_base_columns(),
        sa.Column(
            "cloud_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_resource_id", sa.String(512), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("service", sa.String(80), nullable=False),
        sa.Column("region", sa.String(40), nullable=False),
        sa.Column("sku", sa.String(120), nullable=True),
        sa.Column(
            "tags_json",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_resources_account_service", "resources", ["cloud_account_id", "service"]
    )
    op.create_index(
        "ix_resources_account_region", "resources", ["cloud_account_id", "region"]
    )

    # ─── metric_samples (RANGE-partitioned by timestamp) ───
    op.execute(
        """
        CREATE TABLE metric_samples (
            resource_id  UUID NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
            metric_name  VARCHAR(80) NOT NULL,
            timestamp    TIMESTAMPTZ NOT NULL,
            value        DOUBLE PRECISION NOT NULL,
            unit         VARCHAR(20) NOT NULL,
            PRIMARY KEY (resource_id, metric_name, timestamp)
        ) PARTITION BY RANGE (timestamp);
        """
    )
    op.execute(
        "CREATE INDEX ix_metric_samples_resource_metric "
        "ON metric_samples (resource_id, metric_name);"
    )
    for start, end, suffix in (
        ("2026-05-01", "2026-06-01", "2026_05"),
        ("2026-06-01", "2026-07-01", "2026_06"),
        ("2026-07-01", "2026-08-01", "2026_07"),
        ("2026-08-01", "2026-09-01", "2026_08"),
        ("2026-09-01", "2026-10-01", "2026_09"),
    ):
        op.execute(
            f"CREATE TABLE cloudpilot_metrics_{suffix} PARTITION OF metric_samples "
            f"FOR VALUES FROM ('{start}') TO ('{end}');"
        )
    op.execute(
        "CREATE TABLE cloudpilot_metrics_default PARTITION OF metric_samples DEFAULT;"
    )

    # ─── billing_entries ───
    op.create_table(
        "billing_entries",
        *_base_columns(),
        sa.Column(
            "cloud_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resource_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("resources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("usage_date", sa.Date, nullable=False),
        sa.Column("service", sa.String(80), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 4), nullable=False),
        sa.Column("raw_currency", sa.CHAR(3), nullable=False, server_default="USD"),
        sa.Column("raw_amount", sa.Numeric(12, 4), nullable=False),
    )
    op.create_index(
        "ix_billing_account_date", "billing_entries", ["cloud_account_id", "usage_date"]
    )
    op.create_index(
        "ix_billing_resource_date", "billing_entries", ["resource_id", "usage_date"]
    )

    # ─── recommendations ───
    op.create_table(
        "recommendations",
        *_base_columns(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cloud_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("agent", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("estimated_saving_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "affected_resource_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_recommendations_org_status", "recommendations", ["organization_id", "status"]
    )
    op.create_index(
        "ix_recommendations_org_agent", "recommendations", ["organization_id", "agent"]
    )
    op.create_index(
        "ix_recommendations_org_created",
        "recommendations",
        ["organization_id", "created_at"],
    )

    # ─── forecast_snapshots ───
    op.create_table(
        "forecast_snapshots",
        *_base_columns(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("horizon_days", sa.Integer, nullable=False),
        sa.Column("forecast_json", postgresql.JSONB, nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "snapshot_date",
            "horizon_days",
            name="uq_forecast_org_date_horizon",
        ),
    )

    # ─── chat_sessions ───
    op.create_table(
        "chat_sessions",
        *_base_columns(),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "title", sa.String(255), nullable=False, server_default="New Conversation"
        ),
        sa.Column(
            "is_archived", sa.Boolean, nullable=False, server_default=sa.false()
        ),
    )
    op.create_index(
        "ix_chat_sessions_user_created", "chat_sessions", ["user_id", "created_at"]
    )

    # ─── chat_messages ───
    op.create_table(
        "chat_messages",
        *_base_columns(),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("citations_json", postgresql.JSONB, nullable=True),
        sa.Column("tool_calls_json", postgresql.JSONB, nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
    )
    op.create_index(
        "ix_chat_messages_session_created", "chat_messages", ["session_id", "created_at"]
    )

    # ─── audit_log ───
    op.create_table(
        "audit_log",
        *_base_columns(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(40), nullable=True),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column(
            "payload_json",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("signature", sa.CHAR(64), nullable=False),
    )
    op.create_index(
        "ix_audit_org_event_created",
        "audit_log",
        ["organization_id", "event_type", "created_at"],
    )

    # ─── agent_run_logs ───
    op.create_table(
        "agent_run_logs",
        *_base_columns(),
        sa.Column("agent", sa.String(20), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column(
            "recommendations_created", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_agent_run_logs_agent_org_started",
        "agent_run_logs",
        ["agent", "organization_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("agent_run_logs")
    op.drop_index("ix_audit_org_event_created", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("forecast_snapshots")
    op.drop_table("recommendations")
    op.drop_table("billing_entries")
    op.execute("DROP TABLE IF EXISTS metric_samples CASCADE;")
    op.drop_table("resources")
    op.drop_table("cloud_accounts")
    op.drop_table("users")
    op.drop_table("organizations")
