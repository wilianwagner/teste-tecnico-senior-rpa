"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

job_source = sa.Enum("hockey", "oscar", "all", name="jobsource", native_enum=False, length=20)
job_status = sa.Enum(
    "pending", "running", "completed", "failed", name="jobstatus", native_enum=False, length=20
)


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", job_source, nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("records_collected", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "hockey_team_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("team_name", sa.String(length=120), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("ot_losses", sa.Integer(), nullable=True),
        sa.Column("win_pct", sa.Float(), nullable=False),
        sa.Column("goals_for", sa.Integer(), nullable=False),
        sa.Column("goals_against", sa.Integer(), nullable=False),
        sa.Column("goal_diff", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hockey_team_stats_job_id", "hockey_team_stats", ["job_id"], unique=False)
    op.create_index(
        "ix_hockey_team_stats_team_name_year",
        "hockey_team_stats",
        ["team_name", "year"],
        unique=False,
    )

    op.create_table(
        "oscar_films",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("nominations", sa.Integer(), nullable=False),
        sa.Column("awards", sa.Integer(), nullable=False),
        sa.Column("best_picture", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oscar_films_job_id", "oscar_films", ["job_id"], unique=False)
    op.create_index("ix_oscar_films_year_title", "oscar_films", ["year", "title"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_oscar_films_year_title", table_name="oscar_films")
    op.drop_index("ix_oscar_films_job_id", table_name="oscar_films")
    op.drop_table("oscar_films")
    op.drop_index("ix_hockey_team_stats_team_name_year", table_name="hockey_team_stats")
    op.drop_index("ix_hockey_team_stats_job_id", table_name="hockey_team_stats")
    op.drop_table("hockey_team_stats")
    op.drop_table("jobs")
