"""Frameworks, their requirements, and exemptions

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "framework",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=24), nullable=True),
        sa.Column("pack_version", sa.String(length=24), nullable=True),
        sa.Column("details", govwren.db.types.JsonType, nullable=False),
        sa.Column("loaded_by", sa.Integer(), nullable=True),
        sa.Column("loaded_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_framework")),
        sa.UniqueConstraint("key", name=op.f("uq_framework_key")),
    )
    op.create_table(
        "requirement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("framework_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("parent_code", sa.String(length=60), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("control_keys", govwren.db.types.JsonType, nullable=False),
        sa.ForeignKeyConstraint(
            ["framework_id"], ["framework.id"], name=op.f("fk_requirement_framework_id_framework")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement")),
        sa.UniqueConstraint("framework_id", "code", name="uq_requirement_code"),
    )
    op.create_table(
        "requirement_exemption",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("framework_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("set_by", sa.Integer(), nullable=True),
        sa.Column("set_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["framework_id"],
            ["framework.id"],
            name=op.f("fk_requirement_exemption_framework_id_framework"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement_exemption")),
        sa.UniqueConstraint("framework_id", "code", name="uq_requirement_exemption"),
    )


def downgrade() -> None:
    op.drop_table("requirement_exemption")
    op.drop_table("requirement")
    op.drop_table("framework")
