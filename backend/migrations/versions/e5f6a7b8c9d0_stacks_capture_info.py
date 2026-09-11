"""stacks.capture_info

Adds a JSON column holding acquisition info read off the source FITS headers
(object, telescope, filter, frame count, exposure) - the editor's capture info
panel reads it for a composite session. ``None`` for a plain upload or a FITS
with no usable header.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-11 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("stacks", "capture_info"):
        with op.batch_alter_table("stacks", schema=None) as batch_op:
            batch_op.add_column(sa.Column("capture_info", sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_column("stacks", "capture_info"):
        with op.batch_alter_table("stacks", schema=None) as batch_op:
            batch_op.drop_column("capture_info")
