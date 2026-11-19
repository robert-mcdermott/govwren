"""Assurance: the risk library and the risk register."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from govwren.db.base import Base
from govwren.db.types import UtcDateTime

TREATMENTS = ("mitigate", "accept", "transfer", "avoid")
RISK_STATUSES = ("open", "treated", "accepted", "closed")


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
