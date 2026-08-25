"""Denormalize organization_id onto metric_samples.

Revision ID: 005_metric_samples_org_id
Revises: 004_denormalize_organization_id
Create Date: 2026-08-25

(The revision id is abbreviated because ``alembic_version.version_num`` is
VARCHAR(32); the unabbreviated name would be 34 characters and fails on the
version bump *after* the DDL has run.)

The last table left on single-layer tenant isolation. ``metric_samples`` was
scoped only transitively, through ``resource_id -> resources.organization_id``,
which the ``do_orm_execute`` listener in ``core/tenant.py`` cannot follow — it
filters entities that *declare* the column. Migration 004 closed exactly this
gap for ``resources`` and ``billing_entries`` and deliberately scoped
``metric_samples`` out to keep that change small; this finishes the job, so
every org-scoped table is covered by both layers.

Same three steps as 004, and for the same reasons:
  1. add the column nullable, so existing rows stay valid;
  2. backfill from the owning resource, and *refuse to continue* if any row
     cannot be traced to an organization;
  3. only then apply NOT NULL, plus the FK and the index the filter will use.

One difference from 004: ``metric_samples`` is RANGE-partitioned by month on
``timestamp`` (see 001). Postgres propagates ADD COLUMN, SET NOT NULL and
CREATE INDEX from the partitioned parent down to every partition, and supports
a foreign key from a partitioned table to a non-partitioned one since PG12, so
the same DDL works unchanged — it just has to be applied to the parent, never
to individual partitions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_metric_samples_org_id"
down_revision: str | None = "004_denormalize_organization_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _assert_no_orphans() -> None:
    """Refuse to apply NOT NULL while any row is untraceable.

    Reaching this means a sample references a resource that does not exist,
    which the FK should have prevented. Report it rather than choosing an
    owner — assigning a guess here would invent a tenancy claim, which is the
    exact thing this column exists to prevent.
    """
    conn = op.get_bind()
    orphans = conn.execute(
        sa.text("SELECT count(*) FROM metric_samples WHERE organization_id IS NULL")
    ).scalar_one()
    if orphans:
        sample = conn.execute(
            sa.text(
                "SELECT resource_id, metric_name, timestamp FROM metric_samples "
                "WHERE organization_id IS NULL LIMIT 5"
            )
        ).fetchall()
        raise RuntimeError(
            f"Cannot set metric_samples.organization_id NOT NULL: {orphans} row(s) "
            f"could not be traced to an organization via resource_id. Sample "
            f"(resource_id, metric_name, timestamp): {sample}. These rows reference a "
            "missing resource. Resolve them deliberately — reassign or delete — and "
            "re-run; this migration will not guess an owner."
        )


def upgrade() -> None:
    op.add_column(
        "metric_samples",
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE metric_samples AS m
               SET organization_id = r.organization_id
              FROM resources AS r
             WHERE m.resource_id = r.id
               AND m.organization_id IS NULL
            """
        )
    )
    _assert_no_orphans()
    op.alter_column("metric_samples", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_metric_samples_organization_id",
        "metric_samples",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # The tenant listener appends `WHERE organization_id = :org` to essentially
    # every read, so it leads the index; resource_id trails it because the
    # existing access pattern (RightSizingAgent._p95, ResourceService) reads one
    # resource's samples at a time.
    op.create_index(
        "ix_metric_samples_org_resource",
        "metric_samples",
        ["organization_id", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_metric_samples_org_resource", table_name="metric_samples")
    op.drop_constraint(
        "fk_metric_samples_organization_id", "metric_samples", type_="foreignkey"
    )
    op.drop_column("metric_samples", "organization_id")
