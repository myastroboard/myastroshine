"""astrodex handoff link

Reshapes ``astrodex_links`` for the pull + webhook handoff model (see
``docs/API.md`` "AstroDex integration"). The old push columns
(``astrodex_image_id`` / ``callback_url`` / ``callback_token``) belonged to the
never-wired ``POST /astrodex/receive`` + ``POST /send-to-astrodex`` flow, now
removed. A link is created when MyAstroBoard hands the editor a signed handoff
token; it records where the enhanced result is sent back to.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-09 11:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("astrodex_links", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("callback_base", sa.String(length=512), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("handoff_token", sa.Text(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("astrodex_item_id", sa.String(length=64), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column(
                "astrodex_picture_id", sa.String(length=64), nullable=False, server_default=""
            )
        )
        batch_op.add_column(sa.Column("object_name", sa.String(length=255), nullable=True))
        batch_op.drop_column("astrodex_image_id")
        batch_op.drop_column("callback_url")
        batch_op.drop_column("callback_token")


def downgrade() -> None:
    with op.batch_alter_table("astrodex_links", schema=None) as batch_op:
        batch_op.add_column(sa.Column("callback_token", sa.String(length=512), nullable=True))
        batch_op.add_column(
            sa.Column("callback_url", sa.String(length=512), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("astrodex_image_id", sa.String(length=64), nullable=False, server_default="")
        )
        batch_op.drop_column("object_name")
        batch_op.drop_column("astrodex_picture_id")
        batch_op.drop_column("astrodex_item_id")
        batch_op.drop_column("handoff_token")
        batch_op.drop_column("callback_base")
