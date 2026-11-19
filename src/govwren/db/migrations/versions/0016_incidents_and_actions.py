"""Incidents, the records they involve, and actions

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=24), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("subject_type", sa.String(length=24), nullable=True),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("closed_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'done', 'cancelled')", name=op.f("ck_action_status")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["account.id"], name=op.f("fk_action_owner_id_account")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action")),
        sa.UniqueConstraint("ref", name=op.f("uq_action_ref")),
    )
    op.create_index("ix_action_owner", "action", ["owner_id", "status"], unique=False)
    op.create_index("ix_action_source", "action", ["source_type", "source_id"], unique=False)

    op.create_table(
        "incident",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column("org_unit_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column("lead_id", sa.Integer(), nullable=True),
        sa.Column("containment", sa.Text(), nullable=True),
        sa.Column("cause", sa.Text(), nullable=True),
        sa.Column("lessons", sa.Text(), nullable=True),
        sa.Column("reported_by", sa.Integer(), nullable=True),
        sa.Column("reported_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("triaged_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("closed_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "category IS NULL OR category IN ('wrong_output', 'data_exposure', 'misuse', 'unapproved_use', 'outage', 'near_miss', 'other')",
            name=op.f("ck_incident_category"),
        ),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('low', 'moderate', 'high', 'critical')",
            name=op.f("ck_incident_severity"),
        ),
        sa.CheckConstraint(
            "status IN ('reported', 'open', 'contained', 'closed', 'dismissed')",
            name=op.f("ck_incident_status"),
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["account.id"], name=op.f("fk_incident_lead_id_account")
        ),
        sa.ForeignKeyConstraint(
            ["org_unit_id"], ["org_unit.id"], name=op.f("fk_incident_org_unit_id_org_unit")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident")),
        sa.UniqueConstraint("ref", name=op.f("uq_incident_ref")),
    )
    op.create_index("ix_incident_status", "incident", ["status"], unique=False)

    op.create_table(
        "incident_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("suspended", sa.Boolean(), nullable=False),
        sa.Column("prior_status", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["incident.id"], name=op.f("fk_incident_record_incident_id_incident")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_record")),
        sa.UniqueConstraint("incident_id", "subject_type", "subject_id", name="uq_incident_record"),
    )
    op.create_index(
        "ix_incident_record_subject",
        "incident_record",
        ["subject_type", "subject_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_incident_record_subject", table_name="incident_record")

    op.drop_table("incident_record")
    op.drop_index("ix_incident_status", table_name="incident")

    op.drop_table("incident")
    op.drop_index("ix_action_source", table_name="action")
    op.drop_index("ix_action_owner", table_name="action")

    op.drop_table("action")
