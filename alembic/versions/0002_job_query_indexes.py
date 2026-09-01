"""job query indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-01

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"], unique=False)
    op.create_index(
        "ix_jobs_status_source_finished_at",
        "jobs",
        ["status", "source", "finished_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_status_source_finished_at", table_name="jobs")
    op.drop_index("ix_jobs_created_at", table_name="jobs")
