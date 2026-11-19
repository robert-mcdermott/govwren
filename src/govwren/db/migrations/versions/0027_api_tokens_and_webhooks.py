"""API tokens, webhooks, and their deliveries

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webhook",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("secret", sa.String(length=80), nullable=False),
        sa.Column("topics", govwren.db.types.JsonType, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook")),
    )
    op.create_table(
        "webhook_cursor",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_cursor")),
    )
    op.create_table(
        "api_token",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("prefix", sa.String(length=12), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("fk_api_token_account_id_account")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_api_token_token_hash")),
    )
    op.create_table(
        "webhook_delivery",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("webhook_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=60), nullable=False),
        sa.Column("payload", govwren.db.types.JsonType, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("send_after", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("sent_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["webhook_id"], ["webhook.id"], name=op.f("fk_webhook_delivery_webhook_id_webhook")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_delivery")),
    )
    op.create_index(
        "ix_webhook_delivery_status", "webhook_delivery", ["status", "send_after"], unique=False
    )

    op.create_table(
        "webhook_state",
        sa.Column("webhook_id", sa.Integer(), nullable=False),
        sa.Column("last_status", sa.String(length=200), nullable=True),
        sa.Column("last_delivered_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["webhook_id"], ["webhook.id"], name=op.f("fk_webhook_state_webhook_id_webhook")
        ),
        sa.PrimaryKeyConstraint("webhook_id", name=op.f("pk_webhook_state")),
    )
    op.create_table(
        "api_token_use",
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("last_used_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["token_id"], ["api_token.id"], name=op.f("fk_api_token_use_token_id_api_token")
        ),
        sa.PrimaryKeyConstraint("token_id", name=op.f("pk_api_token_use")),
    )


def downgrade() -> None:
    op.drop_table("api_token_use")
    op.drop_table("webhook_state")
    op.drop_index("ix_webhook_delivery_status", table_name="webhook_delivery")

    op.drop_table("webhook_delivery")
    op.drop_table("api_token")
    op.drop_table("webhook_cursor")
    op.drop_table("webhook")
