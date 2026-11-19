"""What other systems use: API tokens, webhooks, and the deliveries waiting to be sent."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from govwren.db.base import Base
from govwren.db.types import JsonType, UtcDateTime


class ApiToken(Base):
    """A secret a script presents instead of signing in. Only its hash is kept. A token acts
    as the account it belongs to, cut down to its scope."""

    __tablename__ = "api_token"
    __audit_redact__ = frozenset({"token_hash"})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"))
    name: Mapped[str] = mapped_column(String(80))
    scope: Mapped[str] = mapped_column(String(16))
    prefix: Mapped[str] = mapped_column(String(12))  # the start of the token, to tell them apart
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Webhook(Base):
    """An address GovWren tells when something of a chosen kind happens."""

    __tablename__ = "webhook"
    __audit_redact__ = frozenset({"secret"})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    url: Mapped[str] = mapped_column(String(500))
    secret: Mapped[str] = mapped_column(String(80))  # signs each delivery
    topics: Mapped[list[str]] = mapped_column(JsonType, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class WebhookDelivery(Base):
    """One message for one webhook, until it is sent or given up on."""

    __tablename__ = "webhook_delivery"
    __audit__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    webhook_id: Mapped[int] = mapped_column(ForeignKey("webhook.id"))
    event_id: Mapped[int] = mapped_column(Integer)
    topic: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    send_after: Mapped[datetime] = mapped_column(UtcDateTime)
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (Index("ix_webhook_delivery_status", "status", "send_after"),)


class WebhookCursor(Base):
    """The last event the webhook job has looked at. One row."""

    __tablename__ = "webhook_cursor"
    __audit__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    event_id: Mapped[int] = mapped_column(Integer, default=0)


class ApiTokenUse(Base):
    """When a token was last used. Bookkeeping, kept apart from the token so that using a
    token is not an entry in the history."""

    __tablename__ = "api_token_use"
    __audit__ = False

    token_id: Mapped[int] = mapped_column(ForeignKey("api_token.id"), primary_key=True)
    last_used_at: Mapped[datetime] = mapped_column(UtcDateTime)


class WebhookState(Base):
    """How a webhook's deliveries are going. Bookkeeping, kept apart from the webhook."""

    __tablename__ = "webhook_state"
    __audit__ = False

    webhook_id: Mapped[int] = mapped_column(ForeignKey("webhook.id"), primary_key=True)
    last_status: Mapped[str | None] = mapped_column(String(200))
    last_delivered_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    failures: Mapped[int] = mapped_column(Integer, default=0)  # in a row
    # Set when deliveries have failed too many times in a row; cleared when it is switched on.
    paused: Mapped[bool] = mapped_column(Boolean, default=False)


class Suggestion(Base):
    """Something another system says about a record, waiting for a person to accept or
    dismiss. Nothing on the record changes until it is accepted, and accepting it is the
    person's own edit, in the history under their name."""

    __tablename__ = "suggestion"
    __audit__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[int] = mapped_column(Integer)
    field: Mapped[str] = mapped_column(String(60))
    proposed: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    decided_by: Mapped[int | None] = mapped_column(Integer)
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    __table_args__ = (Index("ix_suggestion_subject", "subject_type", "subject_id", "status"),)
