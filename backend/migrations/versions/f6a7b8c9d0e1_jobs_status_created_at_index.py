"""jobs.status/created_at index

The admin job-history view (``GET /api/admin/jobs``) filters by status and
orders by ``created_at`` - no index existed on ``jobs`` beyond the primary
key, and the table has no bound on its own growth (every debounced slider
edit inserts a row).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-11 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_jobs_status_created_at"


def _has_index(table: str, name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(ix["name"] == name for ix in inspector.get_indexes(table))


def upgrade() -> None:
    if not _has_index("jobs", _INDEX_NAME):
        op.create_index(_INDEX_NAME, "jobs", ["status", "created_at"])


def downgrade() -> None:
    if _has_index("jobs", _INDEX_NAME):
        op.drop_index(_INDEX_NAME, table_name="jobs")
