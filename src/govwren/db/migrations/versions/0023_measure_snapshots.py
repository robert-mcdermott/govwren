"""Daily snapshots of the measures

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "measure_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("taken_on", sa.Date(), nullable=False),
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("numerator", sa.Integer(), nullable=True),
        sa.Column("denominator", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_measure_snapshot")),
        sa.UniqueConstraint("taken_on", "key", name="uq_measure_snapshot"),
    )


def downgrade() -> None:
    op.drop_table("measure_snapshot")
