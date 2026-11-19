"""Checking answers against a form version: which questions are showing, and whether each
answer is one the question allows."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core import conditions
from govwren.core.errors import NotFound
from govwren.db.models import OrgUnit
from govwren.inventory import access
from govwren.inventory.registry import SYSTEM, find
from govwren.program import vocab

TEXT_LIMIT = 500
LONG_TEXT_LIMIT = 10_000
_MISSING = "Answer this question."


def visible(
    schema: Mapping[str, Any], answers: Mapping[str, Any]
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """The questions that are showing, given the answers, as (section, question).

    A question may depend only on questions before it, so ``answers`` is read as it stands:
    callers that are cleaning answers pass the ones they have cleaned so far.
    """
    for section in schema["sections"]:
        if not conditions.evaluate(section.get("show_when"), {"answers": answers}):
            continue
        for question in section["questions"]:
            if conditions.evaluate(question.get("show_when"), {"answers": answers}):
                yield section, question


def option_keys(session: Session, question: Mapping[str, Any]) -> list[str]:
    if question.get("vocabulary"):
        return vocab.keys(session, question["vocabulary"])
    return [option["key"] for option in question.get("options", [])]


def _clean_one(
    session: Session, principal: Principal, question: Mapping[str, Any], value: Any
) -> tuple[Any, str | None]:
    """An answer in its proper form, or what is wrong with it. None means not answered."""
    kind = question["type"]
    if value is None or value == "" or value == []:
        return None, None
    if kind in ("text", "long_text"):
        text = str(value).strip() if isinstance(value, str | int | float) else ""
        limit = TEXT_LIMIT if kind == "text" else LONG_TEXT_LIMIT
        if len(text) > limit:
            return None, f"Keep this to {limit} characters."
        return text or None, None
    if kind in ("choice", "data_class"):
        return (
            (value, None)
            if value in option_keys(session, question)
            else (None, "Choose one of the options.")
        )
    if kind == "choices":
        allowed = option_keys(session, question)
        if not isinstance(value, list) or any(item not in allowed for item in value):
            return None, "Choose from the options."
        return [key for key in allowed if key in value] or None, None  # in the form's own order
    if kind == "yes_no":
        return (value, None) if isinstance(value, bool) else (None, "Answer yes or no.")
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None, "Enter a number."
        return value, None
    if kind == "date":
        try:
            return date.fromisoformat(str(value)).isoformat(), None
        except ValueError:
            return None, "Enter a date."
    if kind == "unit":
        unit = (
            session.get(OrgUnit, value)
            if isinstance(value, int) and not isinstance(value, bool)
            else None
        )
        if unit is None or unit.status != "active":
            return None, "Choose a unit."
        return unit.id, None
    if kind == "systems":
        if not isinstance(value, list):
            return None, "Choose from the list."
        refs = []
        for ref in dict.fromkeys(str(item).strip().upper() for item in value):
            try:
                system = find(session, SYSTEM, ref)
            except NotFound:
                return None, f"There is no AI system {ref}."
            if access.sight(session, principal, SYSTEM, system) is None:
                return None, f"There is no AI system {ref}."
            refs.append(ref)
        return refs or None, None
    return None, "This question cannot be answered here."


def clean(
    session: Session,
    principal: Principal,
    schema: Mapping[str, Any],
    answers: Mapping[str, Any],
    *,
    complete: bool,
) -> tuple[dict[str, Any], dict[str, str]]:
    """The answers that count, and what is wrong with the rest.

    Answers to questions that are not showing are dropped, so that changing an earlier
    answer cannot leave a hidden one behind to affect the tier. With ``complete`` every
    required question that is showing must be answered.
    """
    cleaned: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for _section, question in visible(schema, cleaned):
        key = question["key"]
        value, problem = _clean_one(session, principal, question, answers.get(key))
        if problem:
            errors[key] = problem
        elif value is not None:
            cleaned[key] = value
        elif complete and question.get("required"):
            errors[key] = _MISSING
    return cleaned, errors


def mapped(schema: Mapping[str, Any], answers: Mapping[str, Any]) -> dict[str, Any]:
    """The record fields these answers fill."""
    values: dict[str, Any] = {}
    for section in schema["sections"]:
        for question in section["questions"]:
            target = question.get("maps_to")
            if target and question["key"] in answers:
                values[target] = answers[question["key"]]
    return values


def prefill(schema: Mapping[str, Any], record: Any, systems: list[str]) -> dict[str, Any]:
    """Answers taken from what a record already says, so that nothing is asked twice."""
    answers: dict[str, Any] = {}
    for section in schema["sections"]:
        for question in section["questions"]:
            target = question.get("maps_to")
            if not target:
                continue
            value = systems if target == "systems" else getattr(record, target, None)
            if value not in (None, "", []):
                answers[question["key"]] = value
    return answers


def progress(schema: Mapping[str, Any], answers: Mapping[str, Any]) -> dict[str, int]:
    showing = [question for _section, question in visible(schema, answers)]
    required = [question for question in showing if question.get("required")]
    return {
        "required": len(required),
        "answered": sum(1 for question in required if question["key"] in answers),
    }


def showing(
    schema: Mapping[str, Any], answers: Mapping[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    """Which questions are showing, and the answers that count: those to questions that show.

    This is the part of ``clean`` that the web app repeats to show and hide questions as
    someone types (``js/core/scoring.js``); the two must agree on ``tests/parity/scoring.json``.
    """
    kept: dict[str, Any] = {}
    keys: list[str] = []
    for _section, question in visible(schema, kept):
        key = question["key"]
        keys.append(key)
        if answers.get(key) not in (None, "", []):
            kept[key] = answers[key]
    return keys, kept
