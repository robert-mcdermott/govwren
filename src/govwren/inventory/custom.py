"""Fields an organization adds to a kind of record.

The built-in fields are what every program needs. An organization's own, such as a cost
center on a use case or a contract number on a vendor, are defined here as a setting and
answered on each record. They are shown and edited with the record, kept in its history,
and included in its dossier. Rules and tiers do not read them.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.errors import Invalid, PermissionDenied
from govwren.events import audit
from govwren.inventory.registry import TYPES, RecordType
from govwren.program import settings

KEY = "custom_fields"
KINDS = {
    "text": "A line of text",
    "long": "A paragraph",
    "choice": "One of a list",
    "date": "A date",
    "yes_no": "Yes or no",
    "number": "A number",
}
MAX_FIELDS = 20
_KEY = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def definitions(session: Session) -> dict[str, list[dict[str, Any]]]:
    stored = settings.get(session, KEY, {}) or {}
    return {key: list(stored.get(key) or []) for key in TYPES}


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40]


def save(
    session: Session, principal: Principal, record_type: RecordType, fields: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """Set the fields added to one kind of record. A field taken away is no longer shown or
    asked for; what was answered stays on the records and in their history."""
    if not principal.configures:
        raise PermissionDenied("Only governance or an administrator can change the fields.")
    errors: dict[str, str] = {}
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    if len(fields) > MAX_FIELDS:
        errors["fields"] = f"Keep it to {MAX_FIELDS} added fields for a kind of record."
    for position, field in enumerate(fields[:MAX_FIELDS]):
        where = f"fields.{position}"
        label = str(field.get("label") or "").strip()
        key = str(field.get("key") or "").strip() or _slug(label)
        kind = field.get("kind") or "text"
        if not label or len(label) > 80:
            errors[where] = "Give each field a label of up to 80 characters."
            continue
        if not _KEY.match(key):
            errors[where] = f"“{label}” needs a key of lower-case letters, digits, and _."
            continue
        if key in seen:
            errors[where] = f"Two fields share the key {key}."
            continue
        if kind not in KINDS:
            errors[where] = f"“{label}” must be one of: {', '.join(KINDS)}."
            continue
        seen.add(key)
        entry: dict[str, Any] = {"key": key, "label": label, "kind": kind}
        help_text = str(field.get("help") or "").strip()
        if help_text:
            entry["help"] = help_text[:300]
        if kind == "choice":
            options = [
                str(option).strip() for option in field.get("options") or [] if str(option).strip()
            ]
            if len(options) < 2 or len(options) > 30 or len(set(options)) != len(options):
                errors[where] = f"“{label}” needs between 2 and 30 different choices."
                continue
            entry["options"] = [option[:80] for option in options]
        cleaned.append(entry)
    if errors:
        raise Invalid("The fields were not saved.", errors)
    stored = dict(settings.get(session, KEY, {}) or {})
    stored[record_type.key] = cleaned
    with audit.operation(session, "custom_fields.save", record_type=record_type.key):
        settings.put(session, KEY, stored)
    return definitions(session)


def clean(
    session: Session, record_type: RecordType, values: Any
) -> tuple[dict[str, Any], dict[str, str]]:
    """Answers to the added fields, checked. Returns what to store and what is wrong. An
    answer to a field that is not defined is dropped."""
    if not isinstance(values, dict):
        return {}, {"custom": "Send the added fields as an object of key and answer."}
    answers: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for field in definitions(session)[record_type.key]:
        key = field["key"]
        if key not in values:
            continue
        value, where = values[key], f"custom.{key}"
        if value in (None, "", []):
            answers[key] = None
        elif field["kind"] == "yes_no":
            if not isinstance(value, bool):
                errors[where] = "Answer yes or no."
            else:
                answers[key] = value
        elif field["kind"] == "number":
            if isinstance(value, bool) or not isinstance(value, int | float):
                errors[where] = "Give a number."
            else:
                answers[key] = value
        elif field["kind"] == "date":
            try:
                answers[key] = date.fromisoformat(str(value)).isoformat()
            except ValueError:
                errors[where] = "Give a date as year-month-day."
        elif field["kind"] == "choice":
            if value not in field["options"]:
                errors[where] = "Choose one of the listed answers."
            else:
                answers[key] = value
        else:
            text = str(value).strip()
            limit = 4000 if field["kind"] == "long" else 300
            if len(text) > limit:
                errors[where] = f"Keep it to {limit} characters."
            else:
                answers[key] = text or None
    return answers, errors


def apply(session: Session, record_type: RecordType, record: Any, values: Any) -> dict[str, str]:
    """Put checked answers on a record. Returns what is wrong, if anything."""
    answers, errors = clean(session, record_type, values)
    if errors:
        return errors
    merged = {**(record.custom or {}), **answers}
    merged = {key: value for key, value in merged.items() if value is not None}
    if merged != (record.custom or {}):
        record.custom = merged
    return {}
