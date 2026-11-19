"""Inventory: use cases, AI systems, vendors, owners, and links (INV-01, INV-02).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    counter = sa.table("counter", sa.column("prefix", sa.String), sa.column("value", sa.Integer))
    op.bulk_insert(counter, [{"prefix": prefix, "value": 0} for prefix in ("UC", "SYS", "VND")])
    op.create_table(
        "record_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_type", sa.String(length=24), nullable=False),
        sa.Column("from_id", sa.Integer(), nullable=False),
        sa.Column("relation", sa.String(length=24), nullable=False),
        sa.Column("to_type", sa.String(length=24), nullable=False),
        sa.Column("to_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_record_link")),
        sa.UniqueConstraint(
            "from_type",
            "from_id",
            "relation",
            "to_type",
            "to_id",
            name=op.f("uq_record_link_from_type_from_id_relation_to_type_to_id"),
        ),
    )
    with op.batch_alter_table("record_link", schema=None) as batch_op:
        batch_op.create_index("ix_record_link_to", ["to_type", "to_id"], unique=False)

    op.create_table(
        "vendor",
        sa.Column("website", sa.String(length=300), nullable=True),
        sa.Column("contacts", govwren.db.types.JsonType, nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("due_diligence_status", sa.String(length=24), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tags", govwren.db.types.JsonType, nullable=False),
        sa.Column("restricted", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "due_diligence_status IN ('not_started', 'in_progress', 'complete')",
            name=op.f("ck_vendor_due_diligence_status"),
        ),
        sa.CheckConstraint(
            "status IN ('prospective', 'active', 'offboarding', 'former')",
            name=op.f("ck_vendor_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vendor")),
        sa.UniqueConstraint("ref", name=op.f("uq_vendor_ref")),
    )
    op.create_table(
        "ai_system",
        sa.Column("org_unit_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=True),
        sa.Column("embedded_in", sa.String(length=200), nullable=True),
        sa.Column("hosting", sa.String(length=40), nullable=True),
        sa.Column("edition", sa.String(length=120), nullable=True),
        sa.Column("access_path", sa.String(length=40), nullable=True),
        sa.Column("version_label", sa.String(length=80), nullable=True),
        sa.Column("url", sa.String(length=300), nullable=True),
        sa.Column("catalog_status", sa.String(length=32), nullable=False),
        sa.Column("permitted_data_class", sa.String(length=40), nullable=True),
        sa.Column("excluded_data_categories", govwren.db.types.JsonType, nullable=False),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("data_handling", govwren.db.types.JsonType, nullable=False),
        sa.Column("regulatory_status", sa.String(length=200), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tags", govwren.db.types.JsonType, nullable=False),
        sa.Column("restricted", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "catalog_status IN ('not_listed', 'under_evaluation', 'approved', 'approved_with_restrictions', 'not_approved', 'retired')",
            name=op.f("ck_ai_system_catalog_status"),
        ),
        sa.CheckConstraint("status IN ('active', 'retired')", name=op.f("ck_ai_system_status")),
        sa.ForeignKeyConstraint(
            ["org_unit_id"], ["org_unit.id"], name=op.f("fk_ai_system_org_unit_id_org_unit")
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"], ["vendor.id"], name=op.f("fk_ai_system_vendor_id_vendor")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_system")),
        sa.UniqueConstraint("ref", name=op.f("uq_ai_system_ref")),
    )
    with op.batch_alter_table("ai_system", schema=None) as batch_op:
        batch_op.create_index("ix_ai_system_catalog_status", ["catalog_status"], unique=False)
        batch_op.create_index("ix_ai_system_vendor_id", ["vendor_id"], unique=False)

    op.create_table(
        "record_owner",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("record_type", sa.String(length=24), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("fk_record_owner_account_id_account")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_record_owner")),
        sa.UniqueConstraint(
            "record_type",
            "record_id",
            "account_id",
            "kind",
            name=op.f("uq_record_owner_record_type_record_id_account_id_kind"),
        ),
    )
    with op.batch_alter_table("record_owner", schema=None) as batch_op:
        batch_op.create_index("ix_record_owner_account_id", ["account_id"], unique=False)

    op.create_table(
        "use_case",
        sa.Column("org_unit_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(length=40), nullable=True),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=True),
        sa.Column("tier_source", sa.String(length=16), nullable=True),
        sa.Column("decision_role", sa.String(length=40), nullable=True),
        sa.Column("human_oversight", sa.Text(), nullable=True),
        sa.Column("affected_groups", govwren.db.types.JsonType, nullable=False),
        sa.Column("data_class", sa.String(length=40), nullable=True),
        sa.Column("data_categories", govwren.db.types.JsonType, nullable=False),
        sa.Column("outputs_used_for", govwren.db.types.JsonType, nullable=False),
        sa.Column("approved_until", sa.Date(), nullable=True),
        sa.Column("next_review_on", sa.Date(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tags", govwren.db.types.JsonType, nullable=False),
        sa.Column("restricted", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'in_review', 'returned', 'approved', 'approved_with_conditions', 'declined', 'withdrawn', 'suspended', 'lapsed', 'retired')",
            name=op.f("ck_use_case_status"),
        ),
        sa.CheckConstraint("tier IS NULL OR tier BETWEEN 1 AND 9", name=op.f("ck_use_case_tier")),
        sa.ForeignKeyConstraint(
            ["org_unit_id"], ["org_unit.id"], name=op.f("fk_use_case_org_unit_id_org_unit")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_use_case")),
        sa.UniqueConstraint("ref", name=op.f("uq_use_case_ref")),
    )
    with op.batch_alter_table("use_case", schema=None) as batch_op:
        batch_op.create_index("ix_use_case_org_unit_id", ["org_unit_id"], unique=False)
        batch_op.create_index("ix_use_case_status", ["status"], unique=False)


def downgrade() -> None:
    op.execute("DELETE FROM counter WHERE prefix IN ('UC', 'SYS', 'VND')")
    with op.batch_alter_table("use_case", schema=None) as batch_op:
        batch_op.drop_index("ix_use_case_status")
        batch_op.drop_index("ix_use_case_org_unit_id")

    op.drop_table("use_case")
    with op.batch_alter_table("record_owner", schema=None) as batch_op:
        batch_op.drop_index("ix_record_owner_account_id")

    op.drop_table("record_owner")
    with op.batch_alter_table("ai_system", schema=None) as batch_op:
        batch_op.drop_index("ix_ai_system_vendor_id")
        batch_op.drop_index("ix_ai_system_catalog_status")

    op.drop_table("ai_system")
    op.drop_table("vendor")
    with op.batch_alter_table("record_link", schema=None) as batch_op:
        batch_op.drop_index("ix_record_link_to")

    op.drop_table("record_link")
