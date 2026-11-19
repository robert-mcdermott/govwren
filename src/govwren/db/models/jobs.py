"""Scheduled work: each job's next turn, the log of its runs, and which reminders have gone."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from govwren.db.base import Base
from govwren.db.types import JsonType, UtcDateTime


class Job(Base):
    """One piece of scheduled work and when it is next due. A process claims the row before
    it runs the job, so that no two run it at once."""

    __tablename__ = "job"
    __audit__ = False

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime] = mapped_column(UtcDateTime)
    claimed_until: Mapped[datetime | None] = mapped_column(UtcDateTime)
    last_started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    last_finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    last_status: Mapped[str | None] = mapped_column(String(16))
    last_summary: Mapped[str | None] = mapped_column(String(300))


class JobRun(Base):
    """A run that did something, or failed. Runs that found nothing to do are not kept."""

    __tablename__ = "job_run"
    __audit__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_key: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(UtcDateTime)
    finished_at: Mapped[datetime] = mapped_column(UtcDateTime)
    status: Mapped[str] = mapped_column(String(16))
    counts: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    error: Mapped[str | None] = mapped_column(String(600))

    __table_args__ = (
        CheckConstraint("status IN ('ok', 'failed')", name="status"),
        Index("ix_job_run_job_key", "job_key", "id"),
    )


class Reminder(Base):
    """That a reminder about something has been sent, so that it is sent once."""

    __tablename__ = "reminder"
    __audit__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(24))
    sent_on: Mapped[date] = mapped_column(Date)

    __table_args__ = (
        UniqueConstraint("subject_type", "subject_id", "stage", name="uq_reminder_subject_stage"),
    )


class MeasureSnapshot(Base):
    """What one measure stood at on one day. Trends are read from these, so that what a
    measure said in the past is what was stored then."""

    __tablename__ = "measure_snapshot"
    __audit__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    taken_on: Mapped[date] = mapped_column(Date)
    key: Mapped[str] = mapped_column(String(40))
    value: Mapped[float | None] = mapped_column(Float)
    numerator: Mapped[int | None] = mapped_column(Integer)
    denominator: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("taken_on", "key", name="uq_measure_snapshot"),)
