"""Email: an outbox, each person's preference, and what became of each notice (PLT-13).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_message",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("to_address", sa.String(length=254), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("digest_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("send_after", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("sent_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'sending', 'sent', 'failed')",
            name=op.f("ck_outbox_message_status"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("fk_outbox_message_account_id_account")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_message")),
        sa.UniqueConstraint("account_id", "digest_on", name="uq_outbox_message_digest"),
    )
    op.create_index(
        "ix_outbox_message_status", "outbox_message", ["status", "send_after"], unique=False
    )

    with op.batch_alter_table("account", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "email_notices", sa.String(length=16), nullable=False, server_default="immediate"
            )
        )

    with op.batch_alter_table("notification", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mail_state", sa.String(length=16), nullable=True))
        batch_op.create_index("ix_notification_mail_state", ["mail_state"], unique=False)

    # Notices from before email existed are not sent now.
    op.execute("UPDATE notification SET mail_state = 'skipped'")


def downgrade() -> None:
    with op.batch_alter_table("notification", schema=None) as batch_op:
        batch_op.drop_index("ix_notification_mail_state")
        batch_op.drop_column("mail_state")

    with op.batch_alter_table("account", schema=None) as batch_op:
        batch_op.drop_column("email_notices")

    op.drop_index("ix_outbox_message_status", table_name="outbox_message")

    op.drop_table("outbox_message")
