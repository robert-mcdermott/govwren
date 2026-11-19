"""Requests to evaluate a tool that is not in the catalog (FDR-06).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("system_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("closed_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'answered')", name=op.f("ck_evaluation_request_status")
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["account.id"],
            name=op.f("fk_evaluation_request_requested_by_account"),
        ),
        sa.ForeignKeyConstraint(
            ["system_id"], ["ai_system.id"], name=op.f("fk_evaluation_request_system_id_ai_system")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_request")),
    )
    op.create_index(
        "ix_evaluation_request_system_id", "evaluation_request", ["system_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_request_system_id", table_name="evaluation_request")

    op.drop_table("evaluation_request")
