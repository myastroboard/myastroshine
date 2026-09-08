"""stacking watch source + drizzle

Phase 5/6 of the stacking rebuild (``initial_plan/12_STACKING_REBUILD.md``):
a folder-watch ingest (``source`` distinguishes a UI upload from a watch-folder
stack; ``updated_at`` drives the watch idle timeout) and a drizzle output scale
(``drizzle_factor``: 1 = off).

Revision ID: a1b2c3d4e5f6
Revises: 9c4f2a7e610b
Create Date: 2026-09-08 21:55:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "9c4f2a7e610b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(length=12), nullable=False, server_default="upload")
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch_op.add_column(
            sa.Column("drizzle_factor", sa.Integer(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.drop_column("drizzle_factor")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("source")
