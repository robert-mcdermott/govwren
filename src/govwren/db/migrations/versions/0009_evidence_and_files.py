"""Evidence: files stored by their content, evidence items, and what each supports (ASR-01).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    counter = sa.table("counter", sa.column("prefix", sa.String), sa.column("value", sa.Integer))
    op.bulk_insert(counter, [{"prefix": "EV", "value": 0}])
    op.create_table(
        "stored_file",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_file")),
        sa.UniqueConstraint("sha256", name=op.f("uq_stored_file_sha256")),
    )
    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column("file_name", sa.String(length=200), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.Column("url", sa.String(length=300), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("dated_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('current', 'withdrawn')", name=op.f("ck_evidence_status")),
        sa.ForeignKeyConstraint(
            ["file_id"], ["stored_file.id"], name=op.f("fk_evidence_file_id_stored_file")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["account.id"], name=op.f("fk_evidence_owner_id_account")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
        sa.UniqueConstraint("ref", name=op.f("uq_evidence_ref")),
    )
    op.create_index("ix_evidence_expires_on", "evidence", ["expires_on"], unique=False)
    op.create_index("ix_evidence_owner_id", "evidence", ["owner_id"], unique=False)

    op.create_table(
        "evidence_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["evidence.id"], name=op.f("fk_evidence_link_evidence_id_evidence")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_link")),
        sa.UniqueConstraint(
            "evidence_id",
            "subject_type",
            "subject_id",
            name=op.f("uq_evidence_link_evidence_id_subject_type_subject_id"),
        ),
    )
    op.create_index(
        "ix_evidence_link_subject", "evidence_link", ["subject_type", "subject_id"], unique=False
    )


def downgrade() -> None:
    op.execute("DELETE FROM counter WHERE prefix = 'EV'")
    op.drop_index("ix_evidence_link_subject", table_name="evidence_link")

    op.drop_table("evidence_link")
    op.drop_index("ix_evidence_owner_id", table_name="evidence")
    op.drop_index("ix_evidence_expires_on", table_name="evidence")

    op.drop_table("evidence")
    op.drop_table("stored_file")
