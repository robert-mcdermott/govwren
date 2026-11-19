"""Keeping watch: attestation campaigns and what people answered in them."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from govwren.db.base import Base
from govwren.db.types import JsonType, UtcDateTime

CAMPAIGN_KINDS = ("owner_confirmation", "unit_completeness")
CAMPAIGN_STATUSES = ("open", "closed")
RESPONSES = ("confirmed", "changed", "retired", "attested")
EXCEPTION_STATUSES = ("requested", "approved", "declined", "withdrawn", "expired", "revoked")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Campaign(Base):
    """One round of asking the people closest to the work whether the inventory is true:
    owners about their records, or stewards about their unit's list."""

    __tablename__ = "campaign"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(24), unique=True)
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    scope_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_unit.id"))
    record_types: Mapped[list[str]] = mapped_column(JsonType, default=list)
    status: Mapped[str] = mapped_column(String(16), default="open")
    due_on: Mapped[date] = mapped_column(Date)
    opened_by: Mapped[int | None] = mapped_column(Integer)
    opened_at: Mapped[datetime] = mapped_column(UtcDateTime)
    closed_by: Mapped[int | None] = mapped_column(Integer)
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(_one_of("kind", CAMPAIGN_KINDS), name="kind"),
        CheckConstraint(_one_of("status", CAMPAIGN_STATUSES), name="status"),
    )


class Attestation(Base):
    """One thing a campaign asks about, a record or a unit, and the answer once given."""

    __tablename__ = "attestation"
    __audit_parent__ = ("@subject_type", "subject_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaign.id"))
    subject_type: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[int] = mapped_column(Integer)
    org_unit_id: Mapped[int | None] = mapped_column(Integer)  # the unit it counts toward
    response: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    # For a unit: what its list held when the steward attested.
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    answered_by: Mapped[int | None] = mapped_column(Integer)
    answered_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(f"response IS NULL OR {_one_of('response', RESPONSES)}", name="response"),
        Index("ix_attestation_campaign_id", "campaign_id"),
        Index("ix_attestation_subject", "subject_type", "subject_id"),
    )


class ExceptionRecord(Base):
    """An approved, time-limited departure from a requirement, with why it is needed and
    what is done instead. It always has an end date."""

    __tablename__ = "exception"
    __audit_parent__ = ("@subject_type", "subject_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(24), unique=True)
    subject_type: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[int] = mapped_column(Integer)
    org_unit_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    requirement: Mapped[str] = mapped_column(Text)  # what is being departed from
    justification: Mapped[str] = mapped_column(Text)
    measures: Mapped[str] = mapped_column(Text)  # what is done instead, to keep the risk down
    status: Mapped[str] = mapped_column(String(16), default="requested")
    ends_on: Mapped[date] = mapped_column(Date)
    renews_id: Mapped[int | None] = mapped_column(ForeignKey("exception.id"))
    requested_by: Mapped[int | None] = mapped_column(Integer)
    requested_at: Mapped[datetime] = mapped_column(UtcDateTime)
    decided_by: Mapped[int | None] = mapped_column(Integer)
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    decision_note: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(_one_of("status", EXCEPTION_STATUSES), name="status"),
        Index("ix_exception_subject", "subject_type", "subject_id"),
        Index("ix_exception_status", "status", "ends_on"),
    )
