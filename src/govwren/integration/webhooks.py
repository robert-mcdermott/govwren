"""Webhooks: GovWren tells another system when something happens (PLT-18).

Deliveries are made from the history. A job reads the events added since it last looked,
turns the ones that matter into messages for the webhooks that asked for them, and sends
what is waiting. Each message is small and says what changed, never what a record holds;
the receiver asks the API for more if it needs it. Every message is signed with the
webhook's secret, so the receiver can tell it came from here and was not altered.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.config import Config
from govwren.core.clock import utc_now
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import (
    Event,
    Incident,
    Review,
    UseCase,
    Webhook,
    WebhookCursor,
    WebhookDelivery,
    WebhookState,
)
from govwren.events import audit
from govwren.events.chain import jsonable

TOPICS = {
    "use_case.status_changed": "A use case's standing changes: submitted, approved, lapsed, "
    "suspended, retired",
    "decision.made": "A review is decided",
    "catalog.changed": "An AI system's or a model's standing in the catalog changes",
    "incident.reported": "An incident is reported",
}
MAX_ATTEMPTS = 6
BATCH = 50
TIMEOUT = 10
GIVE_UP_AFTER = 20  # failures in a row before a webhook is switched off
LOCAL = ("localhost", "127.0.0.1", "::1")

Send = Callable[[str, bytes, dict[str, str]], int]


def sign(secret: str, stamp: str, body: bytes) -> str:
    """The signature a receiver recomputes: HMAC-SHA256 over the time, a dot, and the body."""
    mac = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def _post(url: str, body: bytes, headers: dict[str, str]) -> int:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")  # noqa: S310
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # noqa: S310
        return int(answer.status)


def _clean(values: dict[str, Any], current: Webhook | None) -> dict[str, Any]:
    errors: dict[str, str] = {}
    name = str(values.get("name", current.name if current else "") or "").strip()
    if not name or len(name) > 80:
        errors["name"] = "Give it a name of up to 80 characters."
    url = str(values.get("url", current.url if current else "") or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname or len(url) > 500:
        errors["url"] = "Give an address that starts with https://."
    elif parts.scheme == "http" and parts.hostname not in LOCAL:
        errors["url"] = "Use https, so that what is sent cannot be read on the way."
    elif parts.username or parts.password:
        errors["url"] = "Do not put a password in the address. Deliveries are signed instead."
    topics = values.get("topics", current.topics if current else [])
    if not isinstance(topics, list) or not topics or set(topics) - set(TOPICS):
        errors["topics"] = "Choose at least one kind of event."
    if errors:
        raise Invalid("The webhook was not saved.", errors)
    return {
        "name": name,
        "url": url,
        "topics": [topic for topic in TOPICS if topic in topics],
        "active": bool(values.get("active", current.active if current else True)),
    }


def _admin(principal: Principal) -> None:
    if not principal.is_admin:
        raise PermissionDenied("Only an administrator sets up webhooks.")


def create(session: Session, principal: Principal, values: dict[str, Any]) -> tuple[Webhook, str]:
    """Add a webhook. Returns it with its secret, which is shown this once."""
    _admin(principal)
    cleaned = _clean(values, None)
    secret = "whsec_" + secrets.token_urlsafe(32)
    with audit.operation(session, "webhook.create"):
        row = Webhook(
            **cleaned, secret=secret, created_by=principal.account_id, created_at=utc_now()
        )
        session.add(row)
        session.flush()
    return row, secret


def find(session: Session, webhook_id: int) -> Webhook:
    row = session.get(Webhook, webhook_id)
    if row is None:
        raise NotFound("There is no such webhook.")
    return row


def change(session: Session, principal: Principal, row: Webhook, values: dict[str, Any]) -> Webhook:
    _admin(principal)
    cleaned = _clean(values, row)
    with audit.operation(session, "webhook.change"):
        for key, value in cleaned.items():
            if getattr(row, key) != value:
                setattr(row, key, value)
        session.flush()
    if cleaned["active"]:  # switching it on again gives it a fresh start
        state = session.get(WebhookState, row.id)
        if state is not None:
            state.failures, state.paused = 0, False
    return row


def remove(session: Session, principal: Principal, row: Webhook) -> None:
    _admin(principal)
    with audit.operation(session, "webhook.remove"):
        session.execute(
            WebhookDelivery.__table__.delete().where(WebhookDelivery.webhook_id == row.id)
        )
        session.execute(WebhookState.__table__.delete().where(WebhookState.webhook_id == row.id))
        session.delete(row)
        session.flush()


def view(session: Session, row: Webhook) -> dict[str, Any]:
    recent = session.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == row.id)
        .order_by(WebhookDelivery.id.desc())
        .limit(10)
    ).all()
    state = session.get(WebhookState, row.id)
    return {
        "id": row.id,
        "name": row.name,
        "url": row.url,
        "topics": row.topics,
        "active": row.active,
        "paused": bool(state and state.paused),
        "created_at": row.created_at,
        "last_status": state.last_status if state else None,
        "last_delivered_at": state.last_delivered_at if state else None,
        "failures": state.failures if state else 0,
        "deliveries": [
            {
                "id": item.id,
                "topic": item.topic,
                "status": item.status,
                "attempts": item.attempts,
                "created_at": item.created_at,
                "sent_at": item.sent_at,
                "last_error": item.last_error,
            }
            for item in recent
        ],
    }


def listing(session: Session, principal: Principal) -> dict[str, Any]:
    _admin(principal)
    rows = session.scalars(select(Webhook).order_by(Webhook.id)).all()
    return {
        "webhooks": [view(session, row) for row in rows],
        "topics": [{"key": key, "label": label} for key, label in TOPICS.items()],
    }


# --- From the history to messages ---


def _changed(event: Event, field: str) -> tuple[Any, Any] | None:
    change_ = (event.changes or {}).get(field)
    if isinstance(change_, list) and len(change_) == 2 and change_[0] != change_[1]:
        return change_[0], change_[1]
    return None


def _message(session: Session, event: Event) -> tuple[str, dict[str, Any]] | None:
    """What an event means to the outside, if anything: a topic and a small payload."""
    if event.subject_type == "use_case" and event.action in ("created", "updated"):
        moved = _changed(event, "status")
        if moved is None or moved[1] == "draft":
            return None
        use_case = session.get(UseCase, event.subject_id)
        return "use_case.status_changed", {
            "ref": event.subject_ref,
            "name": use_case.name if use_case else None,
            "from": moved[0],
            "to": moved[1],
            "tier": use_case.tier if use_case else None,
            "approved_until": use_case.approved_until if use_case else None,
        }
    if event.subject_type == "decision" and event.action == "created":
        changes = event.changes or {}
        review = session.get(Review, event.parent_id) if event.parent_type == "review" else None
        use_case = session.get(UseCase, review.subject_id) if review else None
        return "decision.made", {
            "review": review.ref if review else None,
            "ref": use_case.ref if use_case else None,
            "outcome": (changes.get("outcome") or [None, None])[1],
            "approved_until": (changes.get("approved_until") or [None, None])[1],
            "by_rule": bool((changes.get("by_rule") or [None, None])[1]),
        }
    if event.subject_type in ("system", "model") and event.action in ("created", "updated"):
        moved = _changed(event, "catalog_status")
        if moved is None:
            return None
        return "catalog.changed", {
            "ref": event.subject_ref,
            "type": event.subject_type,
            "from": moved[0],
            "to": moved[1],
        }
    if event.subject_type == "incident" and event.action == "created":
        incident = session.get(Incident, event.subject_id)
        return "incident.reported", {
            "ref": event.subject_ref,
            "category": incident.category if incident else None,
        }
    return None


def queue(session: Session, since: datetime | None = None) -> int:
    """Turn the events added since last time into deliveries. Returns how many were queued.
    A webhook is told of what happened after it was added, or after ``since`` if given."""
    paused = set(
        session.scalars(select(WebhookState.webhook_id).where(WebhookState.paused.is_(True)))
    )
    hooks = [
        hook
        for hook in session.scalars(select(Webhook).where(Webhook.active.is_(True)))
        if hook.id not in paused
    ]
    cursor = session.get(WebhookCursor, 1)
    if cursor is None:
        cursor = WebhookCursor(id=1, event_id=0)
        session.add(cursor)
    last = cursor.event_id
    newest = session.scalars(select(Event.id).order_by(Event.id.desc()).limit(1)).first() or 0
    if newest <= last:
        return 0
    made = 0
    if hooks:
        now = utc_now()
        events = session.scalars(
            select(Event)
            .where(
                Event.id > last,
                Event.id <= newest,
                Event.subject_type.in_(("use_case", "decision", "system", "model", "incident")),
            )
            .order_by(Event.id)
        )
        for event in events:
            message = _message(session, event)
            if message is None:
                continue
            topic, payload = message
            body = {"topic": topic, "event": event.id, "at": event.at, "data": payload}
            for hook in hooks:
                if topic in hook.topics and event.at >= (since or hook.created_at):
                    session.add(
                        WebhookDelivery(
                            webhook_id=hook.id,
                            event_id=event.id,
                            topic=topic,
                            payload=jsonable(body),
                            created_at=now,
                            send_after=now,
                        )
                    )
                    made += 1
    cursor.event_id = newest
    return made


def _deliver(
    session: Session, item: WebhookDelivery, hook: Webhook, send: Send, *, counts: bool = True
) -> bool:
    """Send one message. ``counts`` is false for a test, which is not held against the webhook."""
    body = json.dumps(item.payload, separators=(",", ":"), sort_keys=True).encode()
    stamp = str(int(utc_now().timestamp()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "GovWren-Webhook",
        "X-GovWren-Topic": item.topic,
        "X-GovWren-Delivery": str(item.id),
        "X-GovWren-Timestamp": stamp,
        "X-GovWren-Signature": sign(hook.secret, stamp, body),
    }
    item.attempts += 1
    now = utc_now()
    try:
        status = send(hook.url, body, headers)
        problem = None if 200 <= status < 300 else f"The receiver answered {status}."
    except urllib.error.HTTPError as exc:
        problem = f"The receiver answered {exc.code}."
    except (OSError, ValueError) as exc:
        problem = f"It could not be reached: {type(exc).__name__}."
    state = session.get(WebhookState, hook.id)
    if state is None:
        state = WebhookState(webhook_id=hook.id, failures=0, paused=False)
        session.add(state)
    if problem is None:
        item.status, item.sent_at, item.last_error = "sent", now, None
        state.last_status, state.last_delivered_at = "Delivered", now
        if counts:
            state.failures = 0
        return True
    item.last_error = state.last_status = problem
    if item.attempts >= MAX_ATTEMPTS:
        item.status = "failed"
    else:
        item.send_after = now + timedelta(minutes=2**item.attempts)  # 2, 4, 8, 16, 32
    if counts:
        state.failures += 1
        if state.failures >= GIVE_UP_AFTER:
            state.paused = True
            state.last_status = f"Paused after {GIVE_UP_AFTER} failures in a row. {problem}"
    return False


def _claim(db: Database) -> list[int]:
    """Take a batch to send, so that no other process takes the same ones."""
    now = utc_now()
    with db.bookkeeping() as session:
        rows = session.scalars(
            select(WebhookDelivery)
            .where(WebhookDelivery.status == "queued", WebhookDelivery.send_after <= now)
            .order_by(WebhookDelivery.id)
            .limit(BATCH)
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            row.send_after = now + timedelta(minutes=10)  # taken up again if this process dies
        return [row.id for row in rows]


def send_queued(db: Database, send: Send = _post) -> tuple[int, int]:
    """Send what is due. Returns how many were delivered and how many were not."""
    sent = failed = 0
    for delivery_id in _claim(db):
        with db.bookkeeping() as session:
            item = session.get(WebhookDelivery, delivery_id)
            hook = session.get(Webhook, item.webhook_id) if item else None
            if item is None or hook is None or item.status != "queued":
                continue
            state = session.get(WebhookState, hook.id)
            if not hook.active or (state is not None and state.paused):
                item.status, item.last_error = "failed", "The webhook is switched off or paused."
                failed += 1
            elif _deliver(session, item, hook, send):
                sent += 1
            else:
                failed += 1
    return sent, failed


def run_once(db: Database, _config: Config | None = None, send: Send = _post) -> dict[str, int]:
    with db.bookkeeping() as session:
        queued = queue(session)
    sent, failed = send_queued(db, send)
    return {"queued": queued, "sent": sent, "failed": failed}


def send_test(db: Database, principal: Principal, webhook_id: int, send: Send = _post) -> str:
    """Send one made-up message now, and say how it went."""
    _admin(principal)
    with db.bookkeeping() as session:
        hook = find(session, webhook_id)
        now = utc_now()
        item = WebhookDelivery(
            webhook_id=hook.id,
            event_id=0,
            topic="test",
            payload={
                "topic": "test",
                "event": 0,
                "at": jsonable(now),
                "data": {"message": "A test from GovWren."},
            },
            created_at=now,
            send_after=now,
            attempts=MAX_ATTEMPTS - 1,
        )
        session.add(item)
        session.flush()
        ok = _deliver(session, item, hook, send, counts=False)
        return "Delivered" if ok else str(item.last_error)
