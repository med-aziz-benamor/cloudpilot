"""Add organizations.monthly_budget_usd.

Revision ID: 003_org_monthly_budget
Revises: 002_resource_node_count
Create Date: 2026-07-14

The budget ForecastAgent alerted against was a module constant (`_DEFAULT_BUDGET =
45_000`), identical for every tenant. It is a property of the tenant, not of the
codebase. NULL means no budget is set, and no overrun alert is raised.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_org_monthly_budget"
down_revision: str | None = "002_resource_node_count"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("monthly_budget_usd", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "monthly_budget_usd")
