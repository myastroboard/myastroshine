"""drop v1.1 stacking columns

Removes ``registration_method`` / ``cosmic_ray_rejection`` /
``background_normalization`` from ``stacks`` - the linear rebuild
(``initial_plan/12_STACKING_REBUILD.md``) replaced them with
``registration_transform`` / ``rejection_algo`` / ``weighting`` (added in
``4c7a1e9b52d0``) and nothing reads the old columns any more.

Revision ID: 6d2e04b81f39
Revises: 4c7a1e9b52d0
Create Date: 2026-09-08 12:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6d2e04b81f39"
down_revision: str | None = "4c7a1e9b52d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.drop_column("background_normalization")
        batch_op.drop_column("cosmic_ray_rejection")
        batch_op.drop_column("registration_method")


def downgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "registration_method", sa.String(length=8), nullable=False, server_default="orb"
            )
        )
        batch_op.add_column(
            sa.Column(
                "cosmic_ray_rejection", sa.Boolean(), nullable=False, server_default=sa.true()
            )
        )
        batch_op.add_column(
            sa.Column(
                "background_normalization",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
