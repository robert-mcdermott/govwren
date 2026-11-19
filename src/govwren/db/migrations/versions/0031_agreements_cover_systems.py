"""Agreements name the AI systems they cover

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types
from govwren.core.clock import utc_now

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agreement", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "covered_systems", govwren.db.types.JsonType, server_default="[]", nullable=False
            )
        )
        batch_op.add_column(sa.Column("scope_note", sa.String(length=500), nullable=True))

    with op.batch_alter_table("vendor", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "signs_health_agreement",
                sa.String(length=16),
                server_default="unknown",
                nullable=False,
            )
        )

    # The rule that health information needs a covering agreement is new. An installation
    # that already holds records keeps deciding as it did until someone turns the rule on.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM use_case LIMIT 1")).first() is not None:
        setting = sa.table(
            "setting",
            sa.column("key", sa.String),
            sa.column("value", govwren.db.types.JsonType),
            sa.column("updated_at", govwren.db.types.UtcDateTime),
        )
        op.bulk_insert(
            setting,
            [{"key": "inventory.health_agreement_rule", "value": False, "updated_at": utc_now()}],
        )


def downgrade() -> None:
    op.execute("DELETE FROM setting WHERE key = 'inventory.health_agreement_rule'")
    with op.batch_alter_table("vendor", schema=None) as batch_op:
        batch_op.drop_column("signs_health_agreement")

    with op.batch_alter_table("agreement", schema=None) as batch_op:
        batch_op.drop_column("scope_note")
        batch_op.drop_column("covered_systems")
