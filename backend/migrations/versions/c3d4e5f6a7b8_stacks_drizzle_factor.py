"""stacks.drizzle_factor (split out of a1b2c3d4e5f6)

``drizzle_factor`` was originally appended to the ``a1b2c3d4e5f6`` migration
*after* that revision had already run on some databases, so ``alembic upgrade``
never added the column there (see docs/DEPLOYMENT.md "Schema drift"). This
revision owns the column on its own and is idempotent - it skips the add when the
column is already present (a DB that ran the later ``a1b2c3d4e5f6``, or a fresh
``create_all``).

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-09-09 07:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("stacks", "drizzle_factor"):
        with op.batch_alter_table("stacks", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("drizzle_factor", sa.Integer(), nullable=False, server_default="1")
            )


def downgrade() -> None:
    if _has_column("stacks", "drizzle_factor"):
        with op.batch_alter_table("stacks", schema=None) as batch_op:
            batch_op.drop_column("drizzle_factor")
