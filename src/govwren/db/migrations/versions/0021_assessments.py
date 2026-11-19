"""Assessments: impact assessments and vendor due diligence

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assessment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_key", sa.String(length=60), nullable=False),
        sa.Column("template_version", sa.String(length=24), nullable=True),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=True),
        sa.Column("answers", govwren.db.types.JsonType, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("submitted_by", sa.Integer(), nullable=True),
        sa.Column("submitted_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("updated_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'reviewed')", name=op.f("ck_assessment_status")
        ),
        sa.ForeignKeyConstraint(
            ["review_id"], ["review.id"], name=op.f("fk_assessment_review_id_review")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment")),
    )
    op.create_index(
        "ix_assessment_subject",
        "assessment",
        ["subject_type", "subject_id", "template_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_assessment_subject", table_name="assessment")

    op.drop_table("assessment")
