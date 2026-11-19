"""The risk library and the risk register

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_statement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("category_label", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("treatment", sa.Text(), nullable=True),
        sa.Column("pack_version", sa.String(length=24), nullable=True),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_statement")),
        sa.UniqueConstraint("key", name=op.f("uq_risk_statement_key")),
    )
    op.create_table(
        "risk",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=True),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("org_unit_id", sa.Integer(), nullable=True),
        sa.Column("library_key", sa.String(length=80), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("inherent_likelihood", sa.Integer(), nullable=False),
        sa.Column("inherent_impact", sa.Integer(), nullable=False),
        sa.Column("treatment", sa.String(length=16), nullable=True),
        sa.Column("treatment_note", sa.Text(), nullable=True),
        sa.Column("residual_likelihood", sa.Integer(), nullable=True),
        sa.Column("residual_impact", sa.Integer(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("review_on", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("closed_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'treated', 'accepted', 'closed')", name=op.f("ck_risk_status")
        ),
        sa.CheckConstraint(
            "treatment IS NULL OR treatment IN ('mitigate', 'accept', 'transfer', 'avoid')",
            name=op.f("ck_risk_treatment"),
        ),
        sa.CheckConstraint("inherent_impact BETWEEN 1 AND 5", name=op.f("ck_risk_inherent_impact")),
        sa.CheckConstraint(
            "inherent_likelihood BETWEEN 1 AND 5", name=op.f("ck_risk_inherent_likelihood")
        ),
        sa.CheckConstraint(
            "residual_impact IS NULL OR residual_impact BETWEEN 1 AND 5",
            name=op.f("ck_risk_residual_impact"),
        ),
        sa.CheckConstraint(
            "residual_likelihood IS NULL OR residual_likelihood BETWEEN 1 AND 5",
            name=op.f("ck_risk_residual_likelihood"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["account.id"], name=op.f("fk_risk_owner_id_account")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk")),
        sa.UniqueConstraint("ref", name=op.f("uq_risk_ref")),
    )
    op.create_index("ix_risk_status", "risk", ["status"], unique=False)
    op.create_index("ix_risk_subject", "risk", ["subject_type", "subject_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_risk_subject", table_name="risk")
    op.drop_index("ix_risk_status", table_name="risk")

    op.drop_table("risk")
    op.drop_table("risk_statement")
