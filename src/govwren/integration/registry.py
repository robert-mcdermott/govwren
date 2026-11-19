"""Reading model details from a registry the organization names.

This is the one place GovWren asks another system for something by itself, and it is off
unless an address is configured. Once a day it sends a GET for each model that has a
registry name and compares the answer with the record. Where they differ it leaves a
suggestion on the model's page. It never writes to the registry, and nothing on a record
changes until a person who may edit the record accepts a suggestion; accepting is that
person's own edit, in the history under their name. A suggestion that was dismissed is not
made again.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.config import Config
from govwren.core.clock import utc_now
from govwren.core.errors import NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Model, Suggestion
from govwren.inventory import access, fields, records
from govwren.inventory.registry import MODEL, RecordType

MAX_BYTES = 1_000_000
TIMEOUT = 10
# The record's field, and the names a registry may give it.
READS: dict[str, tuple[str, ...]] = {
    "version_label": ("version", "version_label", "revision"),
    "license": ("license",),
    "release_date": ("released", "release_date", "released_on"),
    "deprecation_date": ("deprecated", "deprecation_date", "deprecated_on"),
    "parameters": ("parameters", "size"),
    "card_url": ("card_url", "model_card", "card"),
    "summary": ("summary", "description"),
}
LABELS = {field.key: field.label for field in fields.MODEL} | {"summary": "Summary"}
_DATES = ("release_date", "deprecation_date")

Get = Callable[[str, dict[str, str]], Any]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _get(address: str, headers: dict[str, str]) -> Any:
    """One GET, read-only, with no redirect followed and a limit on what is read."""
    request = urllib.request.Request(address, headers=headers, method="GET")  # noqa: S310
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT) as answer:
            return json.loads(answer.read(MAX_BYTES + 1)[:MAX_BYTES])
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def _proposals(found: Any, model: Model) -> dict[str, str]:
    """What the registry says that differs from the record, as field and proposed value."""
    if not isinstance(found, dict):
        return {}
    now = {**fields.view(model, fields.MODEL), "summary": model.summary}
    out: dict[str, str] = {}
    for field, names in READS.items():
        value = next((found[name] for name in names if found.get(name) not in (None, "")), None)
        if isinstance(value, dict | list | bool) or value is None:
            continue
        text = str(value).strip()
        if field in _DATES:
            text = text[:10]
            if len(text) != 10 or text[4] != "-" or text[7] != "-":
                continue
        if field == "card_url" and not text.lower().startswith("https://"):
            continue
        if not text or len(text) > 2000:
            continue
        if text != str(now.get(field) if now.get(field) is not None else ""):
            out[field] = text
    return out


def sync(db: Database, config: Config, get: Get = _get) -> dict[str, int]:
    """Ask the registry about every model that has a name there, and leave suggestions."""
    if not config.registry.enabled:
        return {"asked": 0, "suggested": 0}
    token = os.environ.get(config.registry.token_env, "")
    headers = {"Accept": "application/json", "User-Agent": "GovWren"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    base = config.registry.url.rstrip("/")
    with db.read() as session:
        wanted = [
            (model.id, model.registry_name)
            for model in session.scalars(
                select(Model).where(Model.registry_name.is_not(None), Model.status == "active")
            )
            if model.registry_name
        ]
    asked = suggested = failed = 0
    for model_id, name in wanted:
        address = f"{base}/{urllib.parse.quote(name, safe='/')}"
        try:
            found = get(address, headers)
        except (OSError, ValueError):
            failed += 1
            continue
        asked += 1
        with db.bookkeeping() as session:
            model = session.get(Model, model_id)
            if model is None:
                continue
            proposals = _proposals(found, model)
            earlier = session.scalars(
                select(Suggestion).where(
                    Suggestion.subject_type == MODEL.key, Suggestion.subject_id == model_id
                )
            ).all()
            made = {(row.field, row.proposed) for row in earlier}
            for row in earlier:  # the registry has moved on, or the record has caught up
                if row.status == "pending" and proposals.get(row.field) != row.proposed:
                    row.status, row.decided_at = "withdrawn", utc_now()
            for field, text in proposals.items():
                if (field, text) not in made:
                    session.add(
                        Suggestion(
                            subject_type=MODEL.key,
                            subject_id=model_id,
                            field=field,
                            proposed=text,
                            source=address,
                            status="pending",
                            created_at=utc_now(),
                        )
                    )
                    suggested += 1
    return {"asked": asked, "suggested": suggested, "failed": failed}


def for_record(
    session: Session, principal: Principal, record_type: RecordType, record: Any
) -> list[dict[str, Any]]:
    """The suggestions waiting on a record, for someone who sees the whole of it."""
    if access.sight(session, principal, record_type, record) != access.FULL:
        raise NotFound(f"There is no record {record.ref}.")
    may = access.can_edit(session, principal, record_type, record)
    now = (
        {**fields.view(record, fields.MODEL), "summary": record.summary}
        if record_type is MODEL
        else {}
    )
    rows = session.scalars(
        select(Suggestion)
        .where(
            Suggestion.subject_type == record_type.key,
            Suggestion.subject_id == record.id,
            Suggestion.status == "pending",
        )
        .order_by(Suggestion.id)
    )
    return [
        {
            "id": row.id,
            "field": row.field,
            "label": LABELS.get(row.field, row.field),
            "current": now.get(row.field),
            "proposed": row.proposed,
            "source": row.source,
            "created_at": row.created_at,
            "can_decide": may,
        }
        for row in rows
    ]


def _pending(
    session: Session, principal: Principal, suggestion_id: int
) -> tuple[Suggestion, Model]:
    row = session.get(Suggestion, suggestion_id)
    model = session.get(Model, row.subject_id) if row and row.subject_type == MODEL.key else None
    if row is None or model is None or row.status != "pending":
        raise NotFound("There is no such suggestion waiting.")
    if access.sight(session, principal, MODEL, model) != access.FULL:
        raise NotFound("There is no such suggestion waiting.")
    if not access.can_edit(session, principal, MODEL, model):
        raise PermissionDenied("Only someone who can edit the record decides its suggestions.")
    return row, model


def accept(session: Session, principal: Principal, suggestion_id: int) -> Model:
    """Make the change the suggestion proposes, as the person accepting it."""
    row, model = _pending(session, principal, suggestion_id)
    records.update(
        session, principal, MODEL, model, {row.field: row.proposed}, version=model.version
    )
    row.status, row.decided_by, row.decided_at = "accepted", principal.account_id, utc_now()
    return model


def dismiss(session: Session, principal: Principal, suggestion_id: int) -> Model:
    """Leave the record as it is. The same suggestion is not made again."""
    row, model = _pending(session, principal, suggestion_id)
    row.status, row.decided_by, row.decided_at = "dismissed", principal.account_id, utc_now()
    return model
