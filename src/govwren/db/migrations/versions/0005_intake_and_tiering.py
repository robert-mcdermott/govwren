"""Intake: forms, responses, the scoring model, and tier assessments (INT-01, TIR-01).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "form",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_form")),
        sa.UniqueConstraint("key", name=op.f("uq_form_key")),
    )
    op.create_table(
        "scoring_model",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("definition", govwren.db.types.JsonType, nullable=False),
        sa.Column("published_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'retired')", name=op.f("ck_scoring_model_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scoring_model")),
        sa.UniqueConstraint("version", name=op.f("uq_scoring_model_version")),
    )
    op.create_table(
        "form_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("form_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("schema", govwren.db.types.JsonType, nullable=False),
        sa.Column("published_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'retired')", name=op.f("ck_form_version_status")
        ),
        sa.ForeignKeyConstraint(
            ["form_id"], ["form.id"], name=op.f("fk_form_version_form_id_form")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_form_version")),
        sa.UniqueConstraint("form_id", "version", name=op.f("uq_form_version_form_id_version")),
    )
    op.create_table(
        "form_response",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("form_version_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("answers", govwren.db.types.JsonType, nullable=False),
        sa.Column("submitted_by", sa.Integer(), nullable=True),
        sa.Column("submitted_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["form_version_id"],
            ["form_version.id"],
            name=op.f("fk_form_response_form_version_id_form_version"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_form_response")),
    )
    with op.batch_alter_table("form_response", schema=None) as batch_op:
        batch_op.create_index(
            "ix_form_response_subject", ["subject_type", "subject_id"], unique=False
        )

    op.create_table(
        "intake_draft",
        sa.Column("use_case_id", sa.Integer(), nullable=False),
        sa.Column("form_version_id", sa.Integer(), nullable=False),
        sa.Column("answers", govwren.db.types.JsonType, nullable=False),
        sa.Column("updated_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["form_version_id"],
            ["form_version.id"],
            name=op.f("fk_intake_draft_form_version_id_form_version"),
        ),
        sa.ForeignKeyConstraint(
            ["use_case_id"], ["use_case.id"], name=op.f("fk_intake_draft_use_case_id_use_case")
        ),
        sa.PrimaryKeyConstraint("use_case_id", name=op.f("pk_intake_draft")),
    )
    op.create_table(
        "tier_assessment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("scoring_model_id", sa.Integer(), nullable=False),
        sa.Column("form_response_id", sa.Integer(), nullable=True),
        sa.Column("factors", govwren.db.types.JsonType, nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("computed_tier", sa.Integer(), nullable=False),
        sa.Column("floors", govwren.db.types.JsonType, nullable=False),
        sa.Column("stops", govwren.db.types.JsonType, nullable=False),
        sa.Column("final_tier", sa.Integer(), nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("overridden_by", sa.Integer(), nullable=True),
        sa.Column("assessed_by", sa.Integer(), nullable=True),
        sa.Column("assessed_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["form_response_id"],
            ["form_response.id"],
            name=op.f("fk_tier_assessment_form_response_id_form_response"),
        ),
        sa.ForeignKeyConstraint(
            ["scoring_model_id"],
            ["scoring_model.id"],
            name=op.f("fk_tier_assessment_scoring_model_id_scoring_model"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tier_assessment")),
    )
    with op.batch_alter_table("tier_assessment", schema=None) as batch_op:
        batch_op.create_index(
            "ix_tier_assessment_subject", ["subject_type", "subject_id", "id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("tier_assessment", schema=None) as batch_op:
        batch_op.drop_index("ix_tier_assessment_subject")

    op.drop_table("tier_assessment")
    op.drop_table("intake_draft")
    with op.batch_alter_table("form_response", schema=None) as batch_op:
        batch_op.drop_index("ix_form_response_subject")

    op.drop_table("form_response")
    op.drop_table("form_version")
    op.drop_table("scoring_model")
    op.drop_table("form")
