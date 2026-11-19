"""Assurance: the risk library and the risk register."""

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

TREATMENTS = ("mitigate", "accept", "transfer", "avoid")
RISK_STATUSES = ("open", "treated", "accepted", "closed")
IMPLEMENTATION_STATUSES = ("not_started", "in_progress", "implemented", "not_applicable")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class RiskStatement(Base):
    """A reusable statement of something that can go wrong, from a risk library pack."""

    __tablename__ = "risk_statement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    category: Mapped[str] = mapped_column(String(40))
    category_label: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    treatment: Mapped[str | None] = mapped_column(Text)  # what usually answers it
    pack_version: Mapped[str | None] = mapped_column(String(24))
    retired: Mapped[bool] = mapped_column(Boolean, default=False)


class Risk(Base):
    """Something that could go wrong, on one record or for the organization as a whole:
    how likely and how bad before anything is done, what is done, and what is left."""

    __tablename__ = "risk"
    __audit_parent__ = ("@subject_type", "subject_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(24), unique=True)
    subject_type: Mapped[str | None] = mapped_column(String(24))  # empty: the organization
    subject_id: Mapped[int | None] = mapped_column(Integer)
    org_unit_id: Mapped[int | None] = mapped_column(Integer)
    library_key: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    inherent_likelihood: Mapped[int] = mapped_column(Integer)
    inherent_impact: Mapped[int] = mapped_column(Integer)
    treatment: Mapped[str | None] = mapped_column(String(16))
    treatment_note: Mapped[str | None] = mapped_column(Text)
    residual_likelihood: Mapped[int | None] = mapped_column(Integer)
    residual_impact: Mapped[int | None] = mapped_column(Integer)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"))
    status: Mapped[str] = mapped_column(String(16), default="open")
    review_on: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(40))  # where it came from, such as a review
    created_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(_one_of("status", RISK_STATUSES), name="status"),
        CheckConstraint(
            f"treatment IS NULL OR {_one_of('treatment', TREATMENTS)}", name="treatment"
        ),
        CheckConstraint("inherent_likelihood BETWEEN 1 AND 5", name="inherent_likelihood"),
        CheckConstraint("inherent_impact BETWEEN 1 AND 5", name="inherent_impact"),
        CheckConstraint(
            "residual_likelihood IS NULL OR residual_likelihood BETWEEN 1 AND 5",
            name="residual_likelihood",
        ),
        CheckConstraint(
            "residual_impact IS NULL OR residual_impact BETWEEN 1 AND 5", name="residual_impact"
        ),
        Index("ix_risk_subject", "subject_type", "subject_id"),
        Index("ix_risk_status", "status"),
    )


class Control(Base):
    """A safeguard, defined once in a control library. It applies to the program as a whole,
    or to every record that its rule says it applies to; it is never copied per record."""

    __tablename__ = "control"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    category: Mapped[str] = mapped_column(String(40))
    category_label: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(300))
    statement: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(16))
    applies_to: Mapped[list[str]] = mapped_column(JsonType, default=list)
    applies_when: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    check_months: Mapped[int] = mapped_column(Integer, default=12)
    risk_keys: Mapped[list[str]] = mapped_column(JsonType, default=list)
    pack_version: Mapped[str | None] = mapped_column(String(24))
    retired: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (CheckConstraint("scope IN ('program', 'record')", name="scope"),)


class ControlImplementation(Base):
    """How one control stands for the program, or for one record it applies to. A row
    exists only once someone has said something about it."""

    __tablename__ = "control_implementation"
    __audit_parent__ = ("@subject_type", "subject_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("control.id"))
    subject_type: Mapped[str | None] = mapped_column(String(24))  # empty: the program
    subject_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="not_started")
    note: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"))
    next_check_on: Mapped[date | None] = mapped_column(Date)
    checked_by: Mapped[int | None] = mapped_column(Integer)
    checked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(_one_of("status", IMPLEMENTATION_STATUSES), name="status"),
        UniqueConstraint("control_id", "subject_type", "subject_id", name="uq_control_subject"),
        Index("ix_control_implementation_subject", "subject_type", "subject_id"),
    )


class Policy(Base):
    """A policy of the organization: what it is called, who owns it, when it is next
    reviewed, and the controls that carry it out. Its text lives in its versions."""

    __tablename__ = "policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(24), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"))
    review_on: Mapped[date | None] = mapped_column(Date)
    control_keys: Mapped[list[str]] = mapped_column(JsonType, default=list)
    created_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(_one_of("status", ("draft", "in_force", "retired")), name="status"),
    )


class PolicyVersion(Base):
    """One version of a policy's text. A published version is never edited."""

    __tablename__ = "policy_version"
    __audit_parent__ = ("policy", "policy_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policy.id"))
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    change_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    published_by: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(_one_of("status", ("draft", "published")), name="status"),
        UniqueConstraint("policy_id", "version", name="uq_policy_version"),
    )


class PolicyAcknowledgment(Base):
    """That one person was asked to read one version of a policy, and when they said they had."""

    __tablename__ = "policy_acknowledgment"
    __audit_parent__ = ("policy", "policy_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policy.id"))
    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_version.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"))
    org_unit_id: Mapped[int | None] = mapped_column(Integer)  # the unit they were asked through
    due_on: Mapped[date] = mapped_column(Date)
    asked_at: Mapped[datetime] = mapped_column(UtcDateTime)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (
        UniqueConstraint("policy_version_id", "account_id", name="uq_policy_acknowledgment"),
        Index("ix_policy_acknowledgment_account", "account_id", "acknowledged_at"),
    )


class Assessment(Base):
    """A structured set of answers about one record, on a template: an impact assessment
    of a use, or due diligence on a vendor. It is drafted, submitted, and then reviewed."""

    __tablename__ = "assessment"
    __audit_parent__ = ("@subject_type", "subject_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_key: Mapped[str] = mapped_column(String(60))
    template_version: Mapped[str | None] = mapped_column(String(24))
    subject_type: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[int] = mapped_column(Integer)
    review_id: Mapped[int | None] = mapped_column(ForeignKey("review.id"))
    answers: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    submitted_by: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    reviewed_by: Mapped[int | None] = mapped_column(Integer)
    reviewed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    review_note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(_one_of("status", ("draft", "submitted", "reviewed")), name="status"),
        Index("ix_assessment_subject", "subject_type", "subject_id", "template_key"),
    )


class Framework(Base):
    """An outside framework, loaded from a pack. GovWren works fully with none loaded."""

    __tablename__ = "framework"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    version: Mapped[str | None] = mapped_column(String(24))
    pack_version: Mapped[str | None] = mapped_column(String(24))
    details: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)  # publisher, license…
    loaded_by: Mapped[int | None] = mapped_column(Integer)
    loaded_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Requirement(Base):
    """One requirement of a framework. Its code is stable across versions of the pack."""

    __tablename__ = "requirement"
    __audit__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    framework_id: Mapped[int] = mapped_column(ForeignKey("framework.id"))
    code: Mapped[str] = mapped_column(String(60))
    parent_code: Mapped[str | None] = mapped_column(String(60))
    title: Mapped[str | None] = mapped_column(String(300))
    text: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    control_keys: Mapped[list[str]] = mapped_column(JsonType, default=list)  # the crosswalk

    __table_args__ = (UniqueConstraint("framework_id", "code", name="uq_requirement_code"),)


class RequirementExemption(Base):
    """That the organization has said a requirement does not apply to it, and why."""

    __tablename__ = "requirement_exemption"
    __audit_parent__ = ("framework", "framework_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    framework_id: Mapped[int] = mapped_column(ForeignKey("framework.id"))
    code: Mapped[str] = mapped_column(String(60))
    justification: Mapped[str] = mapped_column(Text)
    set_by: Mapped[int | None] = mapped_column(Integer)
    set_at: Mapped[datetime] = mapped_column(UtcDateTime)

    __table_args__ = (UniqueConstraint("framework_id", "code", name="uq_requirement_exemption"),)
