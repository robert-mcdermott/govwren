"""Exceptions: approved, time-limited departures

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exception",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("org_unit_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("measures", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("renews_id", sa.Integer(), nullable=True),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("requested_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("closed_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'declined', 'withdrawn', 'expired', 'revoked')",
            name=op.f("ck_exception_status"),
        ),
        sa.ForeignKeyConstraint(
            ["renews_id"], ["exception.id"], name=op.f("fk_exception_renews_id_exception")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exception")),
        sa.UniqueConstraint("ref", name=op.f("uq_exception_ref")),
    )
    op.create_index("ix_exception_status", "exception", ["status", "ends_on"], unique=False)
    op.create_index(
        "ix_exception_subject", "exception", ["subject_type", "subject_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_exception_subject", table_name="exception")
    op.drop_index("ix_exception_status", table_name="exception")

    op.drop_table("exception")
