"""Add resources.node_count.

Revision ID: 002_resource_node_count
Revises: 001_initial_schema
Create Date: 2026-07-14

A resource row previously described only *what* SKU it ran, never *how many*. That is
fine for a single VM, but a Kubernetes node pool bills its node count — so the
right-sizing saving for a four-node pool was computed as though it were one node, and
under-reported the saving by 4x.

Defaults to 1, which is correct for every non-pool resource.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_resource_node_count"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resources",
        sa.Column("node_count", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("resources", "node_count")
