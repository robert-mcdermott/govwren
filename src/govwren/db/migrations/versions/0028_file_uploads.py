"""Who sent each file

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "file_upload",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["file_id"], ["stored_file.id"], name=op.f("fk_file_upload_file_id_stored_file")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_file_upload")),
        sa.UniqueConstraint("file_id", "account_id", name="uq_file_upload"),
    )


def downgrade() -> None:
    op.drop_table("file_upload")
