"""Turning a tiered request into a review: which functions must look at it, who decides,
by when, and on what standard conditions.

Rules are evaluated in order and their effects add up. A request is approved by rule only
when a rule says so *and* no rule requires a review *and* nothing about it is a prohibited use.

The web app has a twin of ``route`` (``js/core/scoring.js``) so the request form can say what
will happen next. Both must agree on ``tests/parity/scoring.json``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from govwren.core import conditions

AUTHORITIES = ("governance", "committee", "committee_with_acceptance")
EFFECTS = ("require", "authority", "due_days", "conditions", "cadence_months", "auto_approve")
CONDITION_KINDS = ("before_use", "by_date", "ongoing")


def route(
    definition: Mapping[str, Any], tier: int, answers: Mapping[str, Any], stops: Sequence[Any] = ()
) -> dict[str, Any]:
    context = {"tier": tier, "answers": answers}
    require: list[dict[str, str]] = []
    templates: list[str] = []
    authority = AUTHORITIES[0]
    due_days: int | None = None
    cadence: int | None = None
    auto: str | None = None
    fired: list[dict[str, str]] = []
    for rule in definition.get("rules", []):
        if not conditions.evaluate(rule.get("when"), context):
            continue
        then = rule.get("then", {})
        fired.append({"key": rule["key"], "name": rule["name"]})
        for function in then.get("require", []):
            if all(entry["function"] != function for entry in require):
                require.append({"function": function, "rule": rule["name"]})
        if AUTHORITIES.index(then.get("authority", authority)) > AUTHORITIES.index(authority):
            authority = then["authority"]
        if "due_days" in then:
            due_days = then["due_days"]
        if "cadence_months" in then:
            cadence = then["cadence_months"]
        for key in then.get("conditions", []):
            if key not in templates:
                templates.append(key)
        if then.get("auto_approve") and auto is None:
            auto = rule["name"]
    if require or stops:
        auto = None
    return {
        "require": require,
        "authority": authority,
        "due_days": due_days,
        "cadence_months": cadence,
        "conditions": templates,
        "auto_approve": auto,
        "rules": fired,
    }


def templates_by_key(definition: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {template["key"]: template for template in definition.get("condition_templates", [])}
