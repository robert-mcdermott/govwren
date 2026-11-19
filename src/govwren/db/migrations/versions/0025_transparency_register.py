"""The transparency register

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "register_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("use_case_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("show_unit", sa.Boolean(), nullable=False),
        sa.Column("added_by", sa.Integer(), nullable=True),
        sa.Column("added_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_register_entry")),
        sa.UniqueConstraint("use_case_id", name=op.f("uq_register_entry_use_case_id")),
    )


def downgrade() -> None:
    op.drop_table("register_entry")
