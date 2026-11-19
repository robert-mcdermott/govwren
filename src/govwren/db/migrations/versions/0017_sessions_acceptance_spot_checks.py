"""Committee sessions, risk acceptance, and spot checks

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "committee_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("held_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attendees", sa.Text(), nullable=True),
        sa.Column("minutes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("closed_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('planned', 'closed')", name=op.f("ck_committee_session_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_committee_session")),
        sa.UniqueConstraint("ref", name=op.f("uq_committee_session_ref")),
    )
    op.create_table(
        "risk_acceptance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("statement", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("requested_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("answered_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('requested', 'accepted', 'declined', 'replaced')",
            name=op.f("ck_risk_acceptance_status"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("fk_risk_acceptance_account_id_account")
        ),
        sa.ForeignKeyConstraint(
            ["review_id"], ["review.id"], name=op.f("fk_risk_acceptance_review_id_review")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_acceptance")),
    )
    op.create_index(
        "ix_risk_acceptance_account_id", "risk_acceptance", ["account_id", "status"], unique=False
    )
    op.create_index("ix_risk_acceptance_review_id", "risk_acceptance", ["review_id"], unique=False)

    op.create_table(
        "session_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["review_id"], ["review.id"], name=op.f("fk_session_item_review_id_review")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["committee_session.id"],
            name=op.f("fk_session_item_session_id_committee_session"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_item")),
        sa.UniqueConstraint("session_id", "review_id", name="uq_session_item"),
    )
    op.create_index("ix_session_item_review_id", "session_item", ["review_id"], unique=False)

    op.create_table(
        "spot_check",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sampled_by", sa.Integer(), nullable=True),
        sa.Column("sampled_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("checked_by", sa.Integer(), nullable=True),
        sa.Column("checked_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("followup_review_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'agreed', 'disagreed')", name=op.f("ck_spot_check_status")
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"], ["decision.id"], name=op.f("fk_spot_check_decision_id_decision")
        ),
        sa.ForeignKeyConstraint(
            ["review_id"], ["review.id"], name=op.f("fk_spot_check_review_id_review")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_spot_check")),
        sa.UniqueConstraint("decision_id", name=op.f("uq_spot_check_decision_id")),
    )
    op.create_index("ix_spot_check_status", "spot_check", ["status"], unique=False)

    with op.batch_alter_table("decision", schema=None) as batch_op:
        batch_op.add_column(sa.Column("session_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_decision_session_id_committee_session"),
            "committee_session",
            ["session_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("decision", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_decision_session_id_committee_session"), type_="foreignkey"
        )
        batch_op.drop_column("session_id")

    op.drop_index("ix_spot_check_status", table_name="spot_check")

    op.drop_table("spot_check")
    op.drop_index("ix_session_item_review_id", table_name="session_item")

    op.drop_table("session_item")
    op.drop_index("ix_risk_acceptance_review_id", table_name="risk_acceptance")
    op.drop_index("ix_risk_acceptance_account_id", table_name="risk_acceptance")

    op.drop_table("risk_acceptance")
    op.drop_table("committee_session")
