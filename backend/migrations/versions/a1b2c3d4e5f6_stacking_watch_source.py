"""stacking watch source

Phase 5 of the stacking rebuild (``initial_plan/12_STACKING_REBUILD.md``):
folder-watch ingest - ``source`` distinguishes a UI upload from a watch-folder
stack, ``updated_at`` drives the watch idle timeout.

(``drizzle_factor`` was originally added here too, but that broke DBs that had
already run this revision - it now lives in ``c3d4e5f6a7b8``.)

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


def downgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("source")
