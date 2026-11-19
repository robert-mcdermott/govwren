"""Scheduled work: jobs, their runs, and reminders sent

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("claimed_until", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("last_started_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=16), nullable=True),
        sa.Column("last_summary", sa.String(length=300), nullable=True),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_job")),
    )
    op.create_table(
        "job_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_key", sa.String(length=40), nullable=False),
        sa.Column("started_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("finished_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("counts", govwren.db.types.JsonType, nullable=False),
        sa.Column("error", sa.String(length=600), nullable=True),
        sa.CheckConstraint("status IN ('ok', 'failed')", name=op.f("ck_job_run_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_run")),
    )
    op.create_index("ix_job_run_job_key", "job_run", ["job_key", "id"], unique=False)

    op.create_table(
        "reminder",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("sent_on", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminder")),
        sa.UniqueConstraint(
            "subject_type", "subject_id", "stage", name="uq_reminder_subject_stage"
        ),
    )


def downgrade() -> None:
    op.drop_table("reminder")
    op.drop_index("ix_job_run_job_key", table_name="job_run")

    op.drop_table("job_run")
    op.drop_table("job")
