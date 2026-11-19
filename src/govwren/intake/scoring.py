"""Working out a risk tier from answers. A transparent calculation, never a hidden judgment.

Each factor takes the highest level that any of its contributions gives it. The total maps
to a tier. Floors set a minimum tier whatever the total; stops mark a prohibited use.

The web app has a twin of ``assess`` (``js/core/scoring.js``) for the live preview. Both
must agree on the cases in ``tests/parity/scoring.json``; the server's result is the one
that is recorded.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from govwren.core import conditions


def tier_for(definition: Mapping[str, Any], total: int) -> int:
    """The tier whose band the total falls in."""
    level = definition["tiers"][0]["level"]
    for tier in definition["tiers"]:
        if total >= tier["min"]:
            level = tier["level"]
    return level


def assess(definition: Mapping[str, Any], answers: Mapping[str, Any]) -> dict[str, Any]:
    """The tier for these answers, with the reason for every part of it."""
    context = {"answers": answers}
    factors: dict[str, dict[str, Any]] = {
        factor["key"]: {"level": 0, "reason": None} for factor in definition["factors"]
    }
    for contribution in definition["contributions"]:
        current = factors[contribution["factor"]]
        if contribution["level"] > current["level"] and conditions.evaluate(
            contribution["when"], context
        ):
            current["level"] = contribution["level"]
            current["reason"] = contribution["reason"]
    total = sum(factor["level"] for factor in factors.values())
    computed = tier_for(definition, total)
    floors = [
        {"tier": floor["tier"], "reason": floor["reason"]}
        for floor in definition.get("floors", [])
        if conditions.evaluate(floor["when"], context)
    ]
    raised = [floor for floor in floors if floor["tier"] > computed]
    stops = [
        {"key": stop["key"], "reason": stop["reason"]}
        for stop in definition.get("stops", [])
        if conditions.evaluate(stop["when"], context)
    ]
    return {
        "factors": factors,
        "total": total,
        "computed_tier": computed,
        "floors": raised,
        "final_tier": max([computed, *(floor["tier"] for floor in raised)]),
        "stops": stops,
    }


def tier_labels(definition: Mapping[str, Any]) -> dict[int, str]:
    return {tier["level"]: tier["label"] for tier in definition["tiers"]}
