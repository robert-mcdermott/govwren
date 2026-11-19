"""Policies, their versions, and acknowledgments

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("review_on", sa.Date(), nullable=True),
        sa.Column("control_keys", govwren.db.types.JsonType, nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'in_force', 'retired')", name=op.f("ck_policy_status")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["account.id"], name=op.f("fk_policy_owner_id_account")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy")),
        sa.UniqueConstraint("ref", name=op.f("uq_policy_ref")),
    )
    op.create_table(
        "policy_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("policy_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("published_by", sa.Integer(), nullable=True),
        sa.Column("published_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'published')", name=op.f("ck_policy_version_status")
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"], ["policy.id"], name=op.f("fk_policy_version_policy_id_policy")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_version")),
        sa.UniqueConstraint("policy_id", "version", name="uq_policy_version"),
    )
    op.create_table(
        "policy_acknowledgment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("policy_id", sa.Integer(), nullable=False),
        sa.Column("policy_version_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("org_unit_id", sa.Integer(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("asked_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("fk_policy_acknowledgment_account_id_account")
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"], ["policy.id"], name=op.f("fk_policy_acknowledgment_policy_id_policy")
        ),
        sa.ForeignKeyConstraint(
            ["policy_version_id"],
            ["policy_version.id"],
            name=op.f("fk_policy_acknowledgment_policy_version_id_policy_version"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_acknowledgment")),
        sa.UniqueConstraint("policy_version_id", "account_id", name="uq_policy_acknowledgment"),
    )
    op.create_index(
        "ix_policy_acknowledgment_account",
        "policy_acknowledgment",
        ["account_id", "acknowledged_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_policy_acknowledgment_account", table_name="policy_acknowledgment")

    op.drop_table("policy_acknowledgment")
    op.drop_table("policy_version")
    op.drop_table("policy")
