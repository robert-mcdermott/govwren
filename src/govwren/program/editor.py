"""Editing the program in the app: the form, the scoring model, the routing rules, and the
vocabularies.

An edit is a whole program, changed and sent back. It is checked as a pack is checked,
because it is one; what differs from what is published becomes a new version, and earlier
versions are kept. Before publishing, an editor can ask what the change would have done to
the requests already decided.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.errors import Invalid, PermissionDenied
from govwren.db.models import (
    Account,
    Form,
    FormResponse,
    FormVersion,
    RuleSet,
    ScoringModel,
    UseCase,
)
from govwren.intake import forms, scoring
from govwren.program import packs, vocab
from govwren.review import routing

INTAKE = "use_case_intake"
PARTS = ("forms", "scoring_model", "review", "vocabularies")
SAMPLE = 2000  # how many past requests an impact preview looks at, most recent first


def _may(principal: Principal) -> None:
    if not principal.configures:
        raise PermissionDenied("Only governance or an administrator can edit the program.")


def _names(session: Session, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict(
        session.execute(
            select(Account.id, Account.display_name).where(Account.id.in_(wanted))
        ).all()  # type: ignore[arg-type]
    )


def state(session: Session, principal: Principal) -> dict[str, Any]:
    """The program as it is published, and the versions each part has been through."""
    _may(principal)
    program = packs.export(session)
    form_versions = list(
        session.scalars(
            select(FormVersion)
            .join(Form, Form.id == FormVersion.form_id)
            .where(Form.key == INTAKE)
            .order_by(FormVersion.version.desc())
        )
    )
    models = list(session.scalars(select(ScoringModel).order_by(ScoringModel.version.desc())))
    rules = list(session.scalars(select(RuleSet).order_by(RuleSet.version.desc())))
    names = _names(session, {row.published_by for row in [*form_versions, *models, *rules]})

    def history(rows: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "version": row.version,
                "status": row.status,
                "published_at": row.published_at,
                "published_by": names.get(row.published_by or 0),
            }
            for row in rows[:20]
        ]

    return {
        "program": {key: program[key] for key in PARTS if key in program},
        "versions": {
            "form": history(form_versions),
            "scoring_model": history(models),
            "review": history(rules),
        },
        "question_types": list(packs.QUESTION_TYPES),
        "fields": {key: list(kinds) for key, kinds in packs.USE_CASE_FIELDS.items()},
        "field_vocabularies": dict(packs.FIELD_VOCABULARIES),
        "condition_kinds": list(routing.CONDITION_KINDS),
        "authorities": list(routing.AUTHORITIES),
        "responses": session.execute(
            select(func.count(func.distinct(FormResponse.subject_id))).where(
                FormResponse.subject_type == "use_case"
            )
        ).scalar_one(),
    }


def _candidate(session: Session, changes: Mapping[str, Any]) -> dict[str, Any]:
    """The program as it would be with these parts replaced."""
    unknown = [key for key in changes if key not in PARTS]
    if unknown:
        raise Invalid(
            "The program was not saved.", {unknown[0]: "This is not part of the program."}
        )
    current = packs.export(session)
    pack = {**current, **{key: changes[key] for key in PARTS if changes.get(key) is not None}}
    pack["pack"] = {"key": "edited-in-app", "kind": "program", "title": "Edited in the app"}
    return pack


def _retired_in_use(session: Session, pack: Mapping[str, Any]) -> list[str]:
    """A vocabulary value that records hold may be retired, never removed: the record would
    be left holding a word that means nothing."""
    found = []
    for name, items in (pack.get("vocabularies") or {}).items():
        if name not in vocab.NAMES:
            continue
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            found.append(f"vocabularies.{name}: must be a list of values")
            continue
        keys = [str(item.get("key") or "") for item in items]
        if any(not key.replace("_", "").isalnum() for key in keys) or len(set(keys)) != len(keys):
            found.append(
                f"vocabularies.{name}: every value needs its own key of letters and digits"
            )
        if any(not str(item.get("label") or "").strip() for item in items):
            found.append(f"vocabularies.{name}: every value needs a label")
        gone = [key for key in vocab.keys(session, name, active_only=False) if key not in keys]
        if gone:
            found.append(
                f"vocabularies.{name}: {gone[0]!r} cannot be removed, because records may hold "
                "it. Retire it instead."
            )
        if not [item for item in items if not item.get("retired")]:
            found.append(f"vocabularies.{name}: needs at least one value that is not retired")
    return found


def check(session: Session, principal: Principal, changes: Mapping[str, Any]) -> dict[str, Any]:
    """What is wrong with a proposed program, and what it would have done to past requests."""
    _may(principal)
    pack = _candidate(session, changes)
    problems = [*packs.problems(pack), *_retired_in_use(session, pack)]
    return {"problems": problems, "impact": None if problems else impact(session, pack)}


def publish(session: Session, principal: Principal, changes: Mapping[str, Any]) -> dict[str, Any]:
    """Publish the parts that changed. Each becomes a new version; the old ones are kept."""
    _may(principal)
    pack = _candidate(session, changes)
    problems = [*packs.problems(pack), *_retired_in_use(session, pack)]
    if problems:
        raise Invalid(
            "The program was not published.",
            {f"problem_{index + 1}": text for index, text in enumerate(problems)},
        )
    return packs.apply(session, principal, pack)


# --- What a change would have done --------------------------------------------------------


def _intake(pack: Mapping[str, Any]) -> Mapping[str, Any] | None:
    return next((f for f in pack.get("forms") or [] if f.get("key") == INTAKE), None)


def _outcome(pack: Mapping[str, Any], answers: Mapping[str, Any]) -> dict[str, Any] | None:
    form, model, review = _intake(pack), pack.get("scoring_model"), pack.get("review")
    if form is None or model is None:
        return None
    _keys, kept = forms.showing(form, answers)
    result = scoring.assess(model, kept)
    tier = result["final_tier"]
    route = routing.route(review, tier, kept) if review else {"require": [], "auto_approve": None}
    return {
        "tier": tier,
        "stopped": bool(result["stops"]),
        "reviews": sorted(entry["function"] for entry in route["require"]),
        "by_rule": bool(route.get("auto_approve")) and not result["stops"],
    }


def impact(session: Session, pack: Mapping[str, Any]) -> dict[str, Any]:
    """Run the requests already submitted through the proposed program and say what would
    have come out differently. Nothing that was decided is changed by this, or by publishing."""
    current = packs.export(session)
    latest = (
        select(func.max(FormResponse.id))
        .where(FormResponse.subject_type == "use_case")
        .group_by(FormResponse.subject_id)
    )
    rows = session.execute(
        select(FormResponse, UseCase)
        .join(UseCase, UseCase.id == FormResponse.subject_id)
        .where(FormResponse.id.in_(latest))
        .order_by(FormResponse.id.desc())
        .limit(SAMPLE)
    ).all()
    labels = {t["level"]: t["label"] for t in (pack.get("scoring_model") or {}).get("tiers", [])}
    moved: dict[tuple[int, int], int] = {}
    counts = {"tier_up": 0, "tier_down": 0, "reviews": 0, "by_rule": 0, "stopped": 0}
    examples: list[dict[str, Any]] = []
    changed = 0
    for response, use_case in rows:
        was, now = _outcome(current, response.answers), _outcome(pack, response.answers)
        if was is None or now is None or was == now:
            continue
        changed += 1
        what = []
        if now["tier"] != was["tier"]:
            counts["tier_up" if now["tier"] > was["tier"] else "tier_down"] += 1
            moved[(was["tier"], now["tier"])] = moved.get((was["tier"], now["tier"]), 0) + 1
            what.append(
                f"{labels.get(was['tier'], was['tier'])} → {labels.get(now['tier'], now['tier'])}"
            )
        if now["reviews"] != was["reviews"]:
            counts["reviews"] += 1
            added = sorted(set(now["reviews"]) - set(was["reviews"]))
            dropped = sorted(set(was["reviews"]) - set(now["reviews"]))
            if added:
                what.append("adds " + ", ".join(added).replace("_", " ") + " review")
            if dropped:
                what.append("drops " + ", ".join(dropped).replace("_", " ") + " review")
        if now["by_rule"] != was["by_rule"]:
            counts["by_rule"] += 1
            what.append("approved by rule" if now["by_rule"] else "no longer approved by rule")
        if now["stopped"] != was["stopped"]:
            counts["stopped"] += 1
            what.append("becomes a prohibited use" if now["stopped"] else "no longer prohibited")
        if len(examples) < 25:
            examples.append({"ref": use_case.ref, "name": use_case.name, "change": "; ".join(what)})
    return {
        "requests": len(rows),
        "changed": changed,
        "counts": counts,
        "tier_moves": [
            {"from": labels.get(a, a), "to": labels.get(b, b), "count": n}
            for (a, b), n in sorted(moved.items())
        ],
        "examples": examples,
    }
