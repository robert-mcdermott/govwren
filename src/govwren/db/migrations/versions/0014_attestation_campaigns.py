"""Attestation campaigns and their answers

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("scope_unit_id", sa.Integer(), nullable=True),
        sa.Column("record_types", govwren.db.types.JsonType, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("opened_by", sa.Integer(), nullable=True),
        sa.Column("opened_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("closed_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('owner_confirmation', 'unit_completeness')", name=op.f("ck_campaign_kind")
        ),
        sa.CheckConstraint("status IN ('open', 'closed')", name=op.f("ck_campaign_status")),
        sa.ForeignKeyConstraint(
            ["scope_unit_id"], ["org_unit.id"], name=op.f("fk_campaign_scope_unit_id_org_unit")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaign")),
        sa.UniqueConstraint("ref", name=op.f("uq_campaign_ref")),
    )
    op.create_table(
        "attestation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("org_unit_id", sa.Integer(), nullable=True),
        sa.Column("response", sa.String(length=16), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("snapshot", govwren.db.types.JsonType, nullable=True),
        sa.Column("answered_by", sa.Integer(), nullable=True),
        sa.Column("answered_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "response IS NULL OR response IN ('confirmed', 'changed', 'retired', 'attested')",
            name=op.f("ck_attestation_response"),
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaign.id"], name=op.f("fk_attestation_campaign_id_campaign")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attestation")),
    )
    op.create_index("ix_attestation_campaign_id", "attestation", ["campaign_id"], unique=False)
    op.create_index(
        "ix_attestation_subject", "attestation", ["subject_type", "subject_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_attestation_subject", table_name="attestation")
    op.drop_index("ix_attestation_campaign_id", table_name="attestation")

    op.drop_table("attestation")
    op.drop_table("campaign")
