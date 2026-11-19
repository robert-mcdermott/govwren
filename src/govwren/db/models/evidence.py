"""Evidence: the documents and links that decisions rest on."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
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
from govwren.db.types import UtcDateTime

EVIDENCE_STATUSES = ("current", "withdrawn")


class StoredFile(Base):
    """A file in the data home, named by the SHA-256 of its content. The same content
    uploaded twice is one row and one file."""

    __tablename__ = "stored_file"
    __audit__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    size: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Evidence(Base):
    """Something that shows a thing is so: a file, a link, or a note, with an owner and,
    where it goes stale, a date it is good until."""

    __tablename__ = "evidence"
    __subject__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(24), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("stored_file.id"))
    file_name: Mapped[str | None] = mapped_column(String(200))
    # Kept on the evidence as well as the file, so that the history says exactly which
    # content was attached.
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(String(300))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"))
    dated_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="current")
    created_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)

    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(repr(v) for v in EVIDENCE_STATUSES) + ")", name="status"
        ),
        Index("ix_evidence_expires_on", "expires_on"),
        Index("ix_evidence_owner_id", "owner_id"),
    )


class EvidenceLink(Base):
    """What a piece of evidence supports: a record, a condition, a review task, or an
    agreement."""

    __tablename__ = "evidence_link"
    __audit_parent__ = ("@subject_type", "subject_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"))
    subject_type: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("evidence_id", "subject_type", "subject_id"),
        Index("ix_evidence_link_subject", "subject_type", "subject_id"),
    )
