"""An agreement names the models it covers, and an exception the rule it departs from

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agreement", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "covered_models", govwren.db.types.JsonType, server_default="[]", nullable=False
            )
        )

    with op.batch_alter_table("exception", schema=None) as batch_op:
        batch_op.add_column(sa.Column("rule", sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("exception", schema=None) as batch_op:
        batch_op.drop_column("rule")

    with op.batch_alter_table("agreement", schema=None) as batch_op:
        batch_op.drop_column("covered_models")
