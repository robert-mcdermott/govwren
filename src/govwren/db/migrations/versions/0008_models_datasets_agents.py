"""Models, datasets, agent profiles, vendor agreements, and external references (INV-05, INV-06, INV-09, INV-10, INV-18, INV-19).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    counter = sa.table("counter", sa.column("prefix", sa.String), sa.column("value", sa.Integer))
    op.bulk_insert(counter, [{"prefix": prefix, "value": 0} for prefix in ("MDL", "DS")])
    op.create_table(
        "external_ref",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("record_type", sa.String(length=24), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("identifier", sa.String(length=200), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("url", sa.String(length=300), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_ref")),
    )
    op.create_index(
        "ix_external_ref_record", "external_ref", ["record_type", "record_id"], unique=False
    )

    op.create_table(
        "agreement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("effective_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("auto_renews", sa.Boolean(), nullable=False),
        sa.Column("notice_days", sa.Integer(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["account.id"], name=op.f("fk_agreement_owner_id_account")
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"], ["vendor.id"], name=op.f("fk_agreement_vendor_id_vendor")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agreement")),
    )
    op.create_index("ix_agreement_expires_on", "agreement", ["expires_on"], unique=False)
    op.create_index("ix_agreement_vendor_id", "agreement", ["vendor_id"], unique=False)

    op.create_table(
        "dataset",
        sa.Column("org_unit_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("data_class", sa.String(length=40), nullable=True),
        sa.Column(
            "data_categories",
            govwren.db.types.JsonType,
            nullable=False,
        ),
        sa.Column(
            "subjects",
            govwren.db.types.JsonType,
            nullable=False,
        ),
        sa.Column("identifiability", sa.String(length=40), nullable=True),
        sa.Column("deidentification_method", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("permitted_uses", sa.Text(), nullable=True),
        sa.Column("restrictions", sa.Text(), nullable=True),
        sa.Column("retention", sa.String(length=200), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "tags",
            govwren.db.types.JsonType,
            nullable=False,
        ),
        sa.Column("restricted", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'retired')", name=op.f("ck_dataset_status")),
        sa.ForeignKeyConstraint(
            ["org_unit_id"], ["org_unit.id"], name=op.f("fk_dataset_org_unit_id_org_unit")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset")),
        sa.UniqueConstraint("ref", name=op.f("uq_dataset_ref")),
    )
    op.create_index("ix_dataset_data_class", "dataset", ["data_class"], unique=False)

    op.create_table(
        "model",
        sa.Column("org_unit_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("origin", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=200), nullable=True),
        sa.Column("vendor_id", sa.Integer(), nullable=True),
        sa.Column("family", sa.String(length=120), nullable=True),
        sa.Column("version_label", sa.String(length=80), nullable=True),
        sa.Column(
            "modality",
            govwren.db.types.JsonType,
            nullable=False,
        ),
        sa.Column("license", sa.String(length=200), nullable=True),
        sa.Column("license_restrictions", sa.Text(), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("deprecation_date", sa.Date(), nullable=True),
        sa.Column("weights_source", sa.String(length=300), nullable=True),
        sa.Column("weights_checksum", sa.String(length=200), nullable=True),
        sa.Column("weights_format", sa.String(length=40), nullable=True),
        sa.Column("parameters", sa.String(length=80), nullable=True),
        sa.Column("quantization", sa.String(length=80), nullable=True),
        sa.Column("runs_on", sa.Text(), nullable=True),
        sa.Column("tuning_method", sa.String(length=40), nullable=True),
        sa.Column("sharing", sa.String(length=40), nullable=True),
        sa.Column("data_class", sa.String(length=40), nullable=True),
        sa.Column(
            "card",
            govwren.db.types.JsonType,
            nullable=False,
        ),
        sa.Column("catalog_status", sa.String(length=32), nullable=False),
        sa.Column("permitted_data_class", sa.String(length=40), nullable=True),
        sa.Column(
            "excluded_data_categories",
            govwren.db.types.JsonType,
            nullable=False,
        ),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "tags",
            govwren.db.types.JsonType,
            nullable=False,
        ),
        sa.Column("restricted", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "catalog_status IN ('not_listed', 'under_evaluation', 'approved', 'approved_with_restrictions', 'not_approved', 'retired')",
            name=op.f("ck_model_catalog_status"),
        ),
        sa.CheckConstraint("status IN ('active', 'retired')", name=op.f("ck_model_status")),
        sa.ForeignKeyConstraint(
            ["org_unit_id"], ["org_unit.id"], name=op.f("fk_model_org_unit_id_org_unit")
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"], ["vendor.id"], name=op.f("fk_model_vendor_id_vendor")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model")),
        sa.UniqueConstraint("ref", name=op.f("uq_model_ref")),
    )
    op.create_index("ix_model_catalog_status", "model", ["catalog_status"], unique=False)
    op.create_index("ix_model_vendor_id", "model", ["vendor_id"], unique=False)

    with op.batch_alter_table("ai_system", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "agent_profile",
                govwren.db.types.JsonType,
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )


def downgrade() -> None:
    op.execute("DELETE FROM counter WHERE prefix IN ('MDL', 'DS')")
    with op.batch_alter_table("ai_system", schema=None) as batch_op:
        batch_op.drop_column("agent_profile")

    op.drop_index("ix_model_vendor_id", table_name="model")
    op.drop_index("ix_model_catalog_status", table_name="model")

    op.drop_table("model")
    op.drop_index("ix_dataset_data_class", table_name="dataset")

    op.drop_table("dataset")
    op.drop_index("ix_agreement_vendor_id", table_name="agreement")
    op.drop_index("ix_agreement_expires_on", table_name="agreement")

    op.drop_table("agreement")
    op.drop_index("ix_external_ref_record", table_name="external_ref")

    op.drop_table("external_ref")
