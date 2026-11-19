"""The control library and how each control stands

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "control",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("category_label", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("applies_to", govwren.db.types.JsonType, nullable=False),
        sa.Column("applies_when", govwren.db.types.JsonType, nullable=True),
        sa.Column("check_months", sa.Integer(), nullable=False),
        sa.Column("risk_keys", govwren.db.types.JsonType, nullable=False),
        sa.Column("pack_version", sa.String(length=24), nullable=True),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.CheckConstraint("scope IN ('program', 'record')", name=op.f("ck_control_scope")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_control")),
        sa.UniqueConstraint("key", name=op.f("uq_control_key")),
    )
    op.create_table(
        "control_implementation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("control_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=True),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("next_check_on", sa.Date(), nullable=True),
        sa.Column("checked_by", sa.Integer(), nullable=True),
        sa.Column("checked_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("updated_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('not_started', 'in_progress', 'implemented', 'not_applicable')",
            name=op.f("ck_control_implementation_status"),
        ),
        sa.ForeignKeyConstraint(
            ["control_id"],
            ["control.id"],
            name=op.f("fk_control_implementation_control_id_control"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["account.id"], name=op.f("fk_control_implementation_owner_id_account")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_control_implementation")),
        sa.UniqueConstraint("control_id", "subject_type", "subject_id", name="uq_control_subject"),
    )
    op.create_index(
        "ix_control_implementation_subject",
        "control_implementation",
        ["subject_type", "subject_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_control_implementation_subject", table_name="control_implementation")

    op.drop_table("control_implementation")
    op.drop_table("control")
