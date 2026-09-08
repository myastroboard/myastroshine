"""stacking post process

Phase 4 of the stacking rebuild (``initial_plan/12_STACKING_REBUILD.md``):
a post-stack cleanup step on the linear composite - crop the field-rotation
wedge, subtract a low-order background gradient, neutralise and balance the
colour - before it becomes an editable session.

Revision ID: 9c4f2a7e610b
Revises: 8a1e5c47b93f
Create Date: 2026-09-08 19:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c4f2a7e610b"
down_revision: str | None = "8a1e5c47b93f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("post_process", sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.drop_column("post_process")
