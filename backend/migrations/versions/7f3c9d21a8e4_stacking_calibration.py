"""stacking calibration

Phase 2 of the stacking rebuild (``initial_plan/12_STACKING_REBUILD.md``): master
dark / flat / bias frames are calibrated into each light before debayer, and a
bad-pixel map from the master dark/flat drives a cosmetic (neighbour-median)
repair. The calibration frames themselves live on disk under
``DATA_DIR/images/stacks/{id}/cal/``; this only adds the one toggle that belongs
in the row.

Revision ID: 7f3c9d21a8e4
Revises: 6d2e04b81f39
Create Date: 2026-09-08 14:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f3c9d21a8e4"
down_revision: str | None = "6d2e04b81f39"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "cosmetic_correction",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.drop_column("cosmetic_correction")
