"""Review: rule sets, reviews and tasks, decisions, conditions, comments, notices (REV-01 to REV-08).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import govwren.db.types

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    counter = sa.table("counter", sa.column("prefix", sa.String), sa.column("value", sa.Integer))
    op.bulk_insert(counter, [{"prefix": "RV", "value": 0}])
    op.create_table(
        "comment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("is_question", sa.Boolean(), nullable=False),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "visibility IN ('requester', 'internal')", name=op.f("ck_comment_visibility")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comment")),
    )
    with op.batch_alter_table("comment", schema=None) as batch_op:
        batch_op.create_index(
            "ix_comment_subject", ["subject_type", "subject_id", "id"], unique=False
        )

    op.create_table(
        "rule_set",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("definition", govwren.db.types.JsonType, nullable=False),
        sa.Column("published_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'retired')", name=op.f("ck_rule_set_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_set")),
        sa.UniqueConstraint("version", name=op.f("uq_rule_set_version")),
    )
    op.create_table(
        "notification",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("href", sa.String(length=300), nullable=True),
        sa.Column("created_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("read_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"], ["account.id"], name=op.f("fk_notification_account_id_account")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification")),
    )
    with op.batch_alter_table("notification", schema=None) as batch_op:
        batch_op.create_index(
            "ix_notification_account", ["account_id", "read_at", "id"], unique=False
        )

    op.create_table(
        "review",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=24), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("resume_status", sa.String(length=16), nullable=True),
        sa.Column("tier_at_open", sa.Integer(), nullable=True),
        sa.Column("rule_set_id", sa.Integer(), nullable=False),
        sa.Column("authority", sa.String(length=32), nullable=False),
        sa.Column("routing", govwren.db.types.JsonType, nullable=False),
        sa.Column("opened_by", sa.Integer(), nullable=True),
        sa.Column("opened_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("paused_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.Column("paused_seconds", sa.Integer(), nullable=False),
        sa.Column("closed_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('initial', 'periodic', 'change', 'incident', 'catalog', 'retirement')",
            name=op.f("ck_review_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('triage', 'in_review', 'with_requester', 'ready', 'decided', 'cancelled')",
            name=op.f("ck_review_status"),
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_id"], ["rule_set.id"], name=op.f("fk_review_rule_set_id_rule_set")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review")),
        sa.UniqueConstraint("ref", name=op.f("uq_review_ref")),
    )
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.create_index("ix_review_status", ["status"], unique=False)
        batch_op.create_index("ix_review_subject", ["subject_type", "subject_id"], unique=False)

    op.create_table(
        "decision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("authority", sa.String(length=32), nullable=False),
        sa.Column("by_rule", sa.String(length=120), nullable=True),
        sa.Column("over_objection", sa.Boolean(), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=True),
        sa.Column("approved_until", sa.Date(), nullable=True),
        sa.Column("decided_at", govwren.db.types.UtcDateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('approved', 'approved_with_conditions', 'declined', 'returned', 'withdrawn')",
            name=op.f("ck_decision_outcome"),
        ),
        sa.ForeignKeyConstraint(
            ["review_id"], ["review.id"], name=op.f("fk_decision_review_id_review")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision")),
    )
    with op.batch_alter_table("decision", schema=None) as batch_op:
        batch_op.create_index("ix_decision_review_id", ["review_id"], unique=False)

    op.create_table(
        "review_task",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("review_function", sa.String(length=40), nullable=False),
        sa.Column("assignee_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("required_by", sa.String(length=300), nullable=True),
        sa.Column("finding", sa.String(length=16), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recommended_conditions", govwren.db.types.JsonType, nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("completed_by", sa.Integer(), nullable=True),
        sa.Column("completed_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "finding IS NULL OR finding IN ('no_concerns', 'conditions', 'objection')",
            name=op.f("ck_review_task_finding"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'waived')", name=op.f("ck_review_task_status")
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"], ["account.id"], name=op.f("fk_review_task_assignee_id_account")
        ),
        sa.ForeignKeyConstraint(
            ["review_id"], ["review.id"], name=op.f("fk_review_task_review_id_review")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_task")),
    )
    with op.batch_alter_table("review_task", schema=None) as batch_op:
        batch_op.create_index("ix_review_task_assignee_id", ["assignee_id"], unique=False)
        batch_op.create_index("ix_review_task_review_id", ["review_id"], unique=False)

    op.create_table(
        "condition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("template_key", sa.String(length=60), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("closed_at", govwren.db.types.UtcDateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('before_use', 'by_date', 'ongoing')", name=op.f("ck_condition_kind")
        ),
        sa.CheckConstraint("status IN ('open', 'met', 'waived')", name=op.f("ck_condition_status")),
        sa.ForeignKeyConstraint(
            ["decision_id"], ["decision.id"], name=op.f("fk_condition_decision_id_decision")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["account.id"], name=op.f("fk_condition_owner_id_account")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_condition")),
    )
    with op.batch_alter_table("condition", schema=None) as batch_op:
        batch_op.create_index("ix_condition_owner_id", ["owner_id"], unique=False)
        batch_op.create_index("ix_condition_subject", ["subject_type", "subject_id"], unique=False)


def downgrade() -> None:
    op.execute("DELETE FROM counter WHERE prefix = 'RV'")
    with op.batch_alter_table("condition", schema=None) as batch_op:
        batch_op.drop_index("ix_condition_subject")
        batch_op.drop_index("ix_condition_owner_id")

    op.drop_table("condition")
    with op.batch_alter_table("review_task", schema=None) as batch_op:
        batch_op.drop_index("ix_review_task_review_id")
        batch_op.drop_index("ix_review_task_assignee_id")

    op.drop_table("review_task")
    with op.batch_alter_table("decision", schema=None) as batch_op:
        batch_op.drop_index("ix_decision_review_id")

    op.drop_table("decision")
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.drop_index("ix_review_subject")
        batch_op.drop_index("ix_review_status")

    op.drop_table("review")
    with op.batch_alter_table("notification", schema=None) as batch_op:
        batch_op.drop_index("ix_notification_account")

    op.drop_table("notification")
    op.drop_table("rule_set")
    with op.batch_alter_table("comment", schema=None) as batch_op:
        batch_op.drop_index("ix_comment_subject")

    op.drop_table("comment")
