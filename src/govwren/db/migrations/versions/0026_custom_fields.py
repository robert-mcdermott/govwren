"""Custom fields on records

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_system", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("custom", govwren.db.types.JsonType, server_default="{}", nullable=False)
        )

    with op.batch_alter_table("dataset", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("custom", govwren.db.types.JsonType, server_default="{}", nullable=False)
        )

    with op.batch_alter_table("model", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("custom", govwren.db.types.JsonType, server_default="{}", nullable=False)
        )

    with op.batch_alter_table("use_case", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("custom", govwren.db.types.JsonType, server_default="{}", nullable=False)
        )

    with op.batch_alter_table("vendor", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("custom", govwren.db.types.JsonType, server_default="{}", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("vendor", schema=None) as batch_op:
        batch_op.drop_column("custom")

    with op.batch_alter_table("use_case", schema=None) as batch_op:
        batch_op.drop_column("custom")

    with op.batch_alter_table("model", schema=None) as batch_op:
        batch_op.drop_column("custom")

    with op.batch_alter_table("dataset", schema=None) as batch_op:
        batch_op.drop_column("custom")

    with op.batch_alter_table("ai_system", schema=None) as batch_op:
        batch_op.drop_column("custom")
