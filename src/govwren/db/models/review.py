"""Review and decisions: the rules in force, a review and its tasks, what was decided and on
what conditions, the discussion, and notices to the people involved."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from govwren.db.base import Base
from govwren.db.types import JsonType, UtcDateTime

REVIEW_KINDS = ("initial", "periodic", "change", "incident", "catalog", "retirement")
REVIEW_STATUSES = ("triage", "in_review", "with_requester", "ready", "decided", "cancelled")
TASK_STATUSES = ("pending", "completed", "waived")
FINDINGS = ("no_concerns", "conditions", "objection")
OUTCOMES = ("approved", "approved_with_conditions", "declined", "returned", "withdrawn")
CONDITION_KINDS = ("before_use", "by_date", "ongoing")
CONDITION_STATUSES = ("open", "met", "waived")
VISIBILITIES = ("requester", "internal")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class RuleSet(Base):
    """One version of the routing rules and standard conditions."""

    __tablename__ = "rule_set"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    definition: Mapped[dict[str, Any]] = mapped_column(JsonType)
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    published_by: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint(_one_of("status", ("draft", "published", "retired")), name="status"),
    )


class Review(Base):
    """One pass of governance over a record."""

    __tablename__ = "review"
    __audit_parent__ = ("@subject_type", "subject_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(24), unique=True)
    subject_type: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16), default="initial")
    status: Mapped[str] = mapped_column(String(16), default="triage")
    resume_status: Mapped[str | None] = mapped_column(
        String(16)
    )  # where to return from the requester
    tier_at_open: Mapped[int | None] = mapped_column(Integer)
    rule_set_id: Mapped[int] = mapped_column(ForeignKey("rule_set.id"))
    authority: Mapped[str] = mapped_column(String(32), default="governance")
    routing: Mapped[dict[str, Any]] = mapped_column(
        JsonType
    )  # the rules that fired, and what they set
    opened_by: Mapped[int | None] = mapped_column(Integer)
    opened_at: Mapped[datetime] = mapped_column(UtcDateTime)
    due_on: Mapped[date | None] = mapped_column(Date)
    paused_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    paused_seconds: Mapped[int] = mapped_column(Integer, default=0)  # time spent with the requester
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(_one_of("kind", REVIEW_KINDS), name="kind"),
        CheckConstraint(_one_of("status", REVIEW_STATUSES), name="status"),
        Index("ix_review_subject", "subject_type", "subject_id"),
        Index("ix_review_status", "status"),
    )


class ReviewTask(Base):
    """One review function's part of a review."""

    __tablename__ = "review_task"
    __audit_parent__ = ("review", "review_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("review.id"))
    review_function: Mapped[str] = mapped_column(String(40))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    required_by: Mapped[str | None] = mapped_column(
        String(300)
    )  # the rule, or the reason given at triage
    finding: Mapped[str | None] = mapped_column(String(16))
    notes: Mapped[str | None] = mapped_column(Text)
    recommended_conditions: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    due_on: Mapped[date | None] = mapped_column(Date)
    completed_by: Mapped[int | None] = mapped_column(Integer)
    completed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(_one_of("status", TASK_STATUSES), name="status"),
        CheckConstraint(f"finding IS NULL OR {_one_of('finding', FINDINGS)}", name="finding"),
        Index("ix_review_task_review_id", "review_id"),
        Index("ix_review_task_assignee_id", "assignee_id"),
    )


class Decision(Base):
    """The recorded outcome of a review. Never edited: a later decision supersedes it."""

    __tablename__ = "decision"
    __audit_parent__ = ("review", "review_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("review.id"))
    outcome: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[int | None] = mapped_column(Integer)  # None when a rule decided
    authority: Mapped[str] = mapped_column(String(32))
    by_rule: Mapped[str | None] = mapped_column(String(120))  # the rule that approved automatically
    over_objection: Mapped[bool] = mapped_column(Boolean, default=False)
    tier: Mapped[int | None] = mapped_column(Integer)
    approved_until: Mapped[date | None] = mapped_column(Date)
    decided_at: Mapped[datetime] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(_one_of("outcome", OUTCOMES), name="outcome"),
        Index("ix_decision_review_id", "review_id"),
    )


class Condition(Base):
    """A requirement attached to a decision, tracked until it is met or waived."""

    __tablename__ = "condition"
    __audit_parent__ = ("@subject_type", "subject_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decision.id"))
    subject_type: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[int] = mapped_column(Integer)
    template_key: Mapped[str | None] = mapped_column(String(60))
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16), default="ongoing")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"))
    due_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="open")
    note: Mapped[str | None] = mapped_column(Text)
    closed_by: Mapped[int | None] = mapped_column(Integer)
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(_one_of("kind", CONDITION_KINDS), name="kind"),
        CheckConstraint(_one_of("status", CONDITION_STATUSES), name="status"),
        Index("ix_condition_subject", "subject_type", "subject_id"),
        Index("ix_condition_owner_id", "owner_id"),
    )


class Comment(Base):
    """Discussion on a review. Each comment is for the requester to see, or for reviewers only."""

    __tablename__ = "comment"
    __audit_parent__ = ("@subject_type", "subject_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[int | None] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(16), default="internal")
    is_question: Mapped[bool] = mapped_column(Boolean, default=False)  # it paused the clock
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(_one_of("visibility", VISIBILITIES), name="visibility"),
        Index("ix_comment_subject", "subject_type", "subject_id", "id"),
    )


class Notification(Base):
    """A notice to one person that something needs them, or has happened. Not history."""

    __tablename__ = "notification"
    __audit__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"))
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    href: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    read_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    # What became of it as email: queued, digest (in a daily summary), or skipped. Empty
    # until the mailer has looked at it.
    mail_state: Mapped[str | None] = mapped_column(String(16))

    __table_args__ = (
        Index("ix_notification_account", "account_id", "read_at", "id"),
        Index("ix_notification_mail_state", "mail_state"),
    )


class OutboxMessage(Base):
    """An email waiting to be sent, or sent. Kept in the database so that a restart loses
    nothing."""

    __tablename__ = "outbox_message"
    __audit__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"))
    to_address: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(300))
    body_text: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16), default="notice")
    digest_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    send_after: Mapped[datetime] = mapped_column(UtcDateTime)
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (
        UniqueConstraint("account_id", "digest_on", name="uq_outbox_message_digest"),
        CheckConstraint("status IN ('queued', 'sending', 'sent', 'failed')", name="status"),
        Index("ix_outbox_message_status", "status", "send_after"),
    )
