"""Change declarations: an owner says an approved use has changed, and the rules say whether
the change is material.

A change that is not material is recorded and the approval stands. A material one opens a
review limited to what changed: reviewers see the answers that differ, before and after.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import Conflict, Invalid, PermissionDenied
from govwren.db.models import OrgUnit, Review, UseCase
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import USE_CASE
from govwren.program import vocab
from govwren.review import routing
from govwren.review import service as review

# Answers that change what was reviewed. A rule set may name its own under
# ``material_changes``; otherwise these are used.
DEFAULT_MATERIAL = (
    "purpose", "systems", "other_tool", "own_model", "affected_groups", "impact",
    "decision_role", "autonomy", "outputs_used_for", "data_class", "data_categories",
    "exposure", "reach", "model_source", "model_runs_on", "training_data_class",
    "model_sharing", "deidentified", "trains_on_inputs", "actions", "acts_as",
)  # fmt: skip


def material_keys(definition: Mapping[str, Any]) -> set[str]:
    named = definition.get("material_changes")
    return set(named) if isinstance(named, list) else set(DEFAULT_MATERIAL)


def declare(session: Session, principal: Principal, use_case: UseCase, summary: str) -> Review:
    """Begin a change to an approved use. The answers given last time are put back in front
    of the owner to correct; nothing about the approval changes until they submit them."""
    if not access.can_edit(session, principal, USE_CASE, use_case):
        raise PermissionDenied("You cannot declare a change to this use case.")
    if use_case.status not in review.APPROVED:
        raise Conflict("Only an approved use has changes to declare.")
    if review.open_review(session, use_case) is not None:
        raise Conflict("A review of this use is already open. Make the change there.")
    summary = summary.strip()
    if len(summary) < 10:
        raise Invalid("The change was not started.", {"summary": "Say what is changing."})
    rules = review.current_rules(session)
    answers = review.latest_answers(session, use_case)
    tier = use_case.tier or 1
    now = utc_now()
    with audit.operation(session, "review.change", summary=summary):
        found = Review(
            ref=next_ref(session, "RV"),
            subject_type="use_case",
            subject_id=use_case.id,
            kind="change",
            status="with_requester",
            tier_at_open=tier,
            rule_set_id=rules.id,
            authority="governance",
            routing={
                **routing.route(rules.definition, tier, answers, []),
                "change": {"summary": summary},
            },
            opened_by=principal.account_id,
            opened_at=now,
            paused_at=now,
            paused_seconds=0,
        )
        session.add(found)
        review.carry_forward(session, use_case, answers)
        use_case.version += 1
        session.flush()
    return found


def _shown(session: Session, question: Mapping[str, Any], value: Any) -> str | None:
    """An answer as a person would read it."""
    if value in (None, "", []):
        return None
    labels: dict[Any, str] = {}
    if question.get("options"):
        labels = {option["key"]: option["label"] for option in question["options"]}
    elif question.get("vocabulary"):
        labels = dict(vocab.labels(session, question["vocabulary"]))
    elif question["type"] == "yes_no":
        labels = {True: "Yes", False: "No", "yes": "Yes", "no": "No"}
    elif question["type"] == "unit":
        unit = session.get(OrgUnit, value) if isinstance(value, int) else None
        return unit.name if unit else str(value)
    if isinstance(value, list):
        return ", ".join(str(labels.get(item, item)) for item in value)
    return str(labels.get(value, value))


def differences(
    session: Session, schema: Mapping[str, Any], before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """The questions whose answers differ, in the form's order."""
    found = []
    for section in schema["sections"]:
        for question in section["questions"]:
            key = question["key"]
            old, new = before.get(key), after.get(key)
            if isinstance(old, list) and isinstance(new, list):
                same = sorted(map(str, old)) == sorted(map(str, new))
            else:
                same = old == new or (old in (None, "", []) and new in (None, "", []))
            if not same:
                found.append(
                    {
                        "key": key,
                        "label": question["label"],
                        "before": _shown(session, question, old),
                        "after": _shown(session, question, new),
                    }
                )
    return found


def judge(
    definition: Mapping[str, Any],
    changed: list[dict[str, Any]],
    *,
    tier_before: int,
    tier_after: int,
    required_before: set[str],
    required_after: set[str],
) -> dict[str, Any]:
    """Whether a change is material, and why. It is if the tier rises, if a review function
    is newly required, or if any answer that the rules name as material differs."""
    reasons = []
    if tier_after > tier_before:
        reasons.append("The risk tier is higher than the one approved.")
    added = sorted(required_after - required_before)
    if added:
        reasons.append("The rules now require a review that was not required before.")
    keys = material_keys(definition)
    touched = [item["label"] for item in changed if item["key"] in keys]
    if touched:
        reasons.append("Answers that the approval rested on have changed.")
    return {
        "material": bool(reasons),
        "reasons": reasons,
        "changed": changed,
        "tier_before": tier_before,
        "tier_after": tier_after,
        "new_functions": added,
    }


def previous_answers(session: Session, use_case: UseCase) -> dict[str, Any]:
    """The answers on record before the latest submission."""
    from govwren.db.models import FormResponse

    rows = session.scalars(
        select(FormResponse)
        .where(FormResponse.subject_type == "use_case", FormResponse.subject_id == use_case.id)
        .order_by(FormResponse.id.desc())
        .limit(2)
    ).all()
    return dict(rows[1].answers) if len(rows) > 1 else {}
