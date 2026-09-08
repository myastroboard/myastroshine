"""stacking frame quality

Phase 3 of the stacking rebuild (``initial_plan/12_STACKING_REBUILD.md``):
per-frame quality scoring with auto-reject. Adds the ``quality_filter`` strength
setting and the ``included_frames`` list (frames the user has rescued from the
auto-reject). Per-frame metrics themselves live in the existing
``quality_report`` JSON.

Revision ID: 8a1e5c47b93f
Revises: 7f3c9d21a8e4
Create Date: 2026-09-08 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8a1e5c47b93f"
down_revision: str | None = "7f3c9d21a8e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "quality_filter",
                sa.String(length=12),
                nullable=False,
                server_default="moderate",
            )
        )
        batch_op.add_column(
            sa.Column("included_frames", sa.JSON(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.drop_column("included_frames")
        batch_op.drop_column("quality_filter")
