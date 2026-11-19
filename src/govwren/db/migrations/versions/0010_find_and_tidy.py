"""Saved views, and records folded into one another (INV-13, INV-15).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "record_merge",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("record_type", sa.String(length=24), nullable=False),
        sa.Column("from_id", sa.Integer(), nullable=False),
        sa.Column("from_ref", sa.String(length=24), nullable=False),
        sa.Column("into_id", sa.Integer(), nullable=False),
        sa.Column("into_ref", sa.String(length=24), nullable=False),
        sa.Column("merged_by", sa.Integer(), nullable=True),
        sa.Column("merged_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_record_merge")),
        sa.UniqueConstraint("from_ref", name=op.f("uq_record_merge_from_ref")),
    )
    op.create_table(
        "saved_view",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("list_key", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("params", govwren.db.types.JsonType, nullable=False),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("fk_saved_view_account_id_account")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_view")),
        sa.UniqueConstraint(
            "account_id", "list_key", "name", name=op.f("uq_saved_view_account_id_list_key_name")
        ),
    )
    op.create_index("ix_saved_view_account_id", "saved_view", ["account_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_saved_view_account_id", table_name="saved_view")

    op.drop_table("saved_view")
    op.drop_table("record_merge")
