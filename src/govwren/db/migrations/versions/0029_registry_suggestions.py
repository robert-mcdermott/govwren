"""A model's registry name, and suggestions waiting for a person

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suggestion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(length=60), nullable=False),
        sa.Column("proposed", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suggestion")),
    )
    op.create_index(
        "ix_suggestion_subject",
        "suggestion",
        ["subject_type", "subject_id", "status"],
        unique=False,
    )

    with op.batch_alter_table("model", schema=None) as batch_op:
        batch_op.add_column(sa.Column("registry_name", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("model", schema=None) as batch_op:
        batch_op.drop_column("registry_name")

    op.drop_index("ix_suggestion_subject", table_name="suggestion")

    op.drop_table("suggestion")
