"""Intake: forms and their versions, what people answered, and how a tier was worked out."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from govwren.db.base import Base
from govwren.db.types import JsonType, UtcDateTime

VERSION_STATUSES = ("draft", "published", "retired")


class Form(Base):
    """A form, such as the intake form for a use case. Its questions live in its versions."""

    __tablename__ = "form"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True)
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(200))


class FormVersion(Base):
    """One version of a form's questions. Once published it is never changed, so an old
    response always shows the questions that were actually asked."""

    __tablename__ = "form_version"
    __audit_parent__ = ("form", "form_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_id: Mapped[int] = mapped_column(ForeignKey("form.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    schema: Mapped[dict[str, Any]] = mapped_column(JsonType)
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    published_by: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("form_id", "version"),
        CheckConstraint(f"status IN {VERSION_STATUSES!r}", name="status"),
    )


class IntakeDraft(Base):
    """Answers saved while a request is still being written. Saving a draft is not history;
    what was submitted is (see ``FormResponse``)."""

    __tablename__ = "intake_draft"
    __audit__ = False

    use_case_id: Mapped[int] = mapped_column(ForeignKey("use_case.id"), primary_key=True)
    form_version_id: Mapped[int] = mapped_column(ForeignKey("form_version.id"))
    answers: Mapped[dict[str, Any]] = mapped_column(JsonType)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class FormResponse(Base):
    """What someone answered, against the exact version of the form they were shown."""

    __tablename__ = "form_response"
    __audit_parent__ = ("@subject_type", "subject_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_version_id: Mapped[int] = mapped_column(ForeignKey("form_version.id"))
    subject_type: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[int] = mapped_column(Integer)
    answers: Mapped[dict[str, Any]] = mapped_column(JsonType)
    submitted_by: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = mapped_column(UtcDateTime)

    __table_args__ = (Index("ix_form_response_subject", "subject_type", "subject_id"),)


class ScoringModel(Base):
    """One version of the rules that turn answers into a risk tier."""

    __tablename__ = "scoring_model"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    definition: Mapped[dict[str, Any]] = mapped_column(JsonType)
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    published_by: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (CheckConstraint(f"status IN {VERSION_STATUSES!r}", name="status"),)


class TierAssessment(Base):
    """How a tier was reached: each factor's level and the answer that set it, the floors
    that applied, and, if a person changed the result, who and why. Never edited: a new
    assessment supersedes an old one."""

    __tablename__ = "tier_assessment"
    __audit_parent__ = ("@subject_type", "subject_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[int] = mapped_column(Integer)
    scoring_model_id: Mapped[int] = mapped_column(ForeignKey("scoring_model.id"))
    form_response_id: Mapped[int | None] = mapped_column(ForeignKey("form_response.id"))
    factors: Mapped[dict[str, Any]] = mapped_column(JsonType)
    total: Mapped[int] = mapped_column(Integer)
    computed_tier: Mapped[int] = mapped_column(Integer)
    floors: Mapped[list[dict[str, Any]]] = mapped_column(JsonType)
    stops: Mapped[list[dict[str, Any]]] = mapped_column(JsonType)
    final_tier: Mapped[int] = mapped_column(Integer)
    override_reason: Mapped[str | None] = mapped_column(Text)
    overridden_by: Mapped[int | None] = mapped_column(Integer)
    assessed_by: Mapped[int | None] = mapped_column(Integer)
    assessed_at: Mapped[datetime] = mapped_column(UtcDateTime)

    __table_args__ = (Index("ix_tier_assessment_subject", "subject_type", "subject_id", "id"),)
