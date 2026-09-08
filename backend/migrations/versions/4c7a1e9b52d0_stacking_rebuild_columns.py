"""stacking rebuild columns

Adds the rebuilt stacking pipeline's config to ``stacks`` (linear pipeline:
star-based registration transform, Winsorized-sigma rejection, frame weighting,
manual frame exclusions, a per-frame quality report). The v1.1 columns
(``registration_method`` / ``cosmic_ray_rejection`` / ``background_normalization``)
are left in place here and dropped in a later migration once nothing reads them.
See ``initial_plan/12_STACKING_REBUILD.md``.

Revision ID: 4c7a1e9b52d0
Revises: 623faa14df02
Create Date: 2026-09-08 10:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4c7a1e9b52d0"
down_revision: str | None = "623faa14df02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "registration_transform",
                sa.String(length=16),
                nullable=False,
                server_default="similarity",
            )
        )
        batch_op.add_column(
            sa.Column(
                "rejection_algo",
                sa.String(length=24),
                nullable=False,
                server_default="winsorized_sigma",
            )
        )
        batch_op.add_column(sa.Column("rejection_params", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("weighting", sa.String(length=12), nullable=False, server_default="noise")
        )
        batch_op.add_column(
            sa.Column("excluded_frames", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(sa.Column("quality_report", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("stacks", schema=None) as batch_op:
        batch_op.drop_column("quality_report")
        batch_op.drop_column("excluded_frames")
        batch_op.drop_column("weighting")
        batch_op.drop_column("rejection_params")
        batch_op.drop_column("rejection_algo")
        batch_op.drop_column("registration_transform")
