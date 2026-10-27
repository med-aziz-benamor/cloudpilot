"""Denormalize organization_id onto resources and billing_entries.

Revision ID: 004_denormalize_organization_id
Revises: 003_org_monthly_budget
Create Date: 2026-07-20

Both tables were scoped to a tenant only *transitively*, through
``cloud_account_id -> cloud_accounts.organization_id``. The tenant listener in
``core/tenant.py`` filters by inspecting mappers for an ``organization_id`` column,
so it could never see these two — meaning the platform's two largest tables were
protected by service-level filtering alone, not by the second, independent layer the
architecture claims. See docs/session-report-2026-07-20.md.

Carrying the column directly is a denormalization, and the redundancy is the point:
it lets an ORM-level guard run without a join, so a service that forgets to scope
its query still cannot read another tenant's rows.

Three steps, deliberately in this order:
  1. add the column nullable, so existing rows stay valid;
  2. backfill from the owning cloud account, and *refuse to continue* if any row
     cannot be traced to an organization;
  3. only then apply NOT NULL, plus the FK and the indexes the filter will use.

Step 2 raising rather than defaulting is intentional. An untraceable row means the
data is already inconsistent, and silently assigning it to some organization would
be inventing a tenancy claim — exactly the kind of guess this column exists to stop.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_denormalize_organization_id"
down_revision: str | None = "003_org_monthly_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("resources", "billing_entries")


def _backfill(table: str) -> None:
    """Copy the organization down from the owning cloud account."""
    op.execute(
        sa.text(
            f"""
            UPDATE {table} AS t
               SET organization_id = ca.organization_id
              FROM cloud_accounts AS ca
             WHERE t.cloud_account_id = ca.id
               AND t.organization_id IS NULL
            """  # noqa: S608 - table name is from the module-level tuple, not user input
        )
    )


def _assert_no_orphans(table: str) -> None:
    """Refuse to apply NOT NULL while any row is untraceable.

    Reaching this means a row references a cloud account that does not exist, which
    the FK should have prevented. Report it instead of choosing an owner.
    """
    conn = op.get_bind()
    orphans = conn.execute(
        sa.text(f"SELECT count(*) FROM {table} WHERE organization_id IS NULL")  # noqa: S608
    ).scalar_one()
    if orphans:
        sample = conn.execute(
            sa.text(  # noqa: S608
                f"SELECT id, cloud_account_id FROM {table} "
                "WHERE organization_id IS NULL LIMIT 5"
            )
        ).fetchall()
        raise RuntimeError(
            f"Cannot set {table}.organization_id NOT NULL: {orphans} row(s) could not "
            f"be traced to an organization via cloud_account_id. Sample "
            f"(id, cloud_account_id): {sample}. These rows reference a missing cloud "
            "account. Resolve them deliberately — reassign or delete — and re-run; "
            "this migration will not guess an owner."
        )


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        )
        _backfill(table)
        _assert_no_orphans(table)
        op.alter_column(table, "organization_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_organization_id",
            table,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # The tenant listener appends `WHERE organization_id = :org` to essentially every
    # read of these tables, so it leads the index. The trailing columns match the
    # existing access patterns (see 001's account/date indexes).
    op.create_index(
        "ix_resources_org", "resources", ["organization_id"]
    )
    op.create_index(
        "ix_billing_org_date", "billing_entries", ["organization_id", "usage_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_billing_org_date", table_name="billing_entries")
    op.drop_index("ix_resources_org", table_name="resources")
    for table in _TABLES:
        op.drop_constraint(f"fk_{table}_organization_id", table, type_="foreignkey")
        op.drop_column(table, "organization_id")
