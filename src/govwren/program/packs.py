"""Program packs: an organization's forms and scoring model as one file (see
spec/content-packs.md). A pack is checked whole before any of it is loaded."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core import conditions
from govwren.core.clock import utc_now
from govwren.core.errors import Invalid, PermissionDenied
from govwren.db.models import Form, FormVersion, ScoringModel
from govwren.events import audit
from govwren.program import vocab

QUESTION_TYPES = (
    "text",
    "long_text",
    "choice",
    "choices",
    "data_class",
    "yes_no",
    "number",
    "date",
    "unit",
    "systems",
)
CHOICE_TYPES = ("choice", "choices", "data_class")
# Where a use case intake question may put its answer on the record.
USE_CASE_FIELDS = {
    "name": ("text",),
    "purpose": ("long_text", "text"),
    "org_unit_id": ("unit",),
    "domain": ("choice",),
    "stage": ("choice",),
    "decision_role": ("choice",),
    "human_oversight": ("long_text", "text"),
    "affected_groups": ("choices",),
    "data_class": ("data_class", "choice"),
    "data_categories": ("choices",),
    "outputs_used_for": ("choices",),
    "systems": ("systems",),
}
FIELD_VOCABULARIES = {
    "domain": "domains",
    "stage": "stages",
    "decision_role": "decision_roles",
    "affected_groups": "affected_groups",
    "data_class": "data_classes",
    "data_categories": "data_categories",
    "outputs_used_for": "outputs_used_for",
}


def default_pack() -> dict[str, Any]:
    text = (
        resources.files("govwren.resources")
        .joinpath("packs/default-program.json")
        .read_text("utf-8")
    )
    return json.loads(text)


def _answers_used(condition: Any) -> set[str]:
    return {
        field[len("answers.") :]
        for field in conditions.fields(condition)
        if field.startswith("answers.")
    }


def _check_condition(condition: Any, where: str, known: set[str], found: list[str]) -> None:
    shape = conditions.problems(condition, where=where)
    found += shape
    if shape:
        return
    for field in conditions.fields(condition):
        if not field.startswith("answers."):
            found.append(f"{where}: looks at {field}; conditions here may look only at answers")
    for key in sorted(_answers_used(condition) - known):
        found.append(f"{where}: looks at the answer to {key!r}, which is not an earlier question")


def form_problems(form: Any, where: str = "form") -> list[str]:
    found: list[str] = []
    if not isinstance(form, dict):
        return [f"{where}: must be an object"]
    for field in ("key", "kind", "title"):
        if not isinstance(form.get(field), str) or not form.get(field):
            found.append(f"{where}: needs a {field}")
    sections = form.get("sections")
    if not isinstance(sections, list) or not sections:
        return [*found, f"{where}: needs at least one section"]
    seen: set[str] = set()
    section_keys: set[str] = set()
    for s_index, section in enumerate(sections):
        at = f"{where}.sections[{s_index}]"
        if not isinstance(section, dict) or not section.get("key") or not section.get("title"):
            found.append(f"{at}: needs a key and a title")
            continue
        if section["key"] in section_keys:
            found.append(f"{at}: the key {section['key']!r} is used twice")
        section_keys.add(section["key"])
        _check_condition(section.get("show_when"), f"{at}.show_when", seen, found)
        questions = section.get("questions")
        if not isinstance(questions, list) or not questions:
            found.append(f"{at}: needs at least one question")
            continue
        for q_index, question in enumerate(questions):
            here = f"{at}.questions[{q_index}]"
            if not isinstance(question, dict):
                found.append(f"{here}: must be an object")
                continue
            key, kind = question.get("key"), question.get("type")
            if not isinstance(key, str) or not key.replace("_", "").isalnum():
                found.append(f"{here}: needs a key of letters, digits, and underscores")
                continue
            if key in seen:
                found.append(f"{here}: the key {key!r} is used twice")
            if not question.get("label"):
                found.append(f"{here}: needs a label")
            if kind not in QUESTION_TYPES:
                found.append(f"{here}: type must be one of {', '.join(QUESTION_TYPES)}")
                seen.add(key)
                continue
            _check_condition(question.get("show_when"), f"{here}.show_when", seen, found)
            if kind in CHOICE_TYPES:
                options, name = question.get("options"), question.get("vocabulary")
                if (options is None) == (name is None):
                    found.append(f"{here}: needs either options or a vocabulary")
                elif name is not None and name not in vocab.NAMES:
                    found.append(f"{here}: there is no vocabulary called {name!r}")
                elif options is not None:
                    keys = [o.get("key") for o in options if isinstance(o, dict)]
                    if len(keys) != len(options) or not all(keys) or len(set(keys)) != len(keys):
                        found.append(f"{here}: every option needs its own key")
                    if not all(isinstance(o, dict) and o.get("label") for o in options):
                        found.append(f"{here}: every option needs a label")
            target = question.get("maps_to")
            if target is not None:
                if form.get("kind") != "use_case" or target not in USE_CASE_FIELDS:
                    found.append(f"{here}: cannot fill the field {target!r}")
                elif kind not in USE_CASE_FIELDS[target]:
                    found.append(f"{here}: a {kind} question cannot fill {target}")
                elif (
                    target in FIELD_VOCABULARIES
                    and question.get("vocabulary") != FIELD_VOCABULARIES[target]
                ):
                    needed = FIELD_VOCABULARIES[target]
                    found.append(f"{here}: to fill {target} it must use the {needed} vocabulary")
            seen.add(key)
    if form.get("kind") == "use_case":
        mapped = {
            q.get("maps_to")
            for s in sections
            if isinstance(s, dict)
            for q in s.get("questions") or []
            if isinstance(q, dict)
        }
        for needed in ("name", "org_unit_id"):
            if needed not in mapped:
                found.append(
                    f"{where}: a use case form needs a required question that fills {needed}"
                )
    return found


def question_keys(form: Any) -> set[str]:
    """The keys of a form's questions, read carefully: the form may have faults of its own."""
    keys: set[str] = set()
    sections = form.get("sections") if isinstance(form, dict) else None
    for section in sections if isinstance(sections, list) else []:
        questions = section.get("questions") if isinstance(section, dict) else None
        for question in questions if isinstance(questions, list) else []:
            if isinstance(question, dict) and isinstance(question.get("key"), str):
                keys.add(question["key"])
    return keys


def scoring_problems(model: Any, known: set[str], where: str = "scoring_model") -> list[str]:
    found: list[str] = []
    if not isinstance(model, dict):
        return [f"{where}: must be an object"]
    factors = model.get("factors")
    if not isinstance(factors, list) or not factors:
        return [f"{where}: needs at least one factor"]
    levels: dict[str, int] = {}
    for index, factor in enumerate(factors):
        at = f"{where}.factors[{index}]"
        if not isinstance(factor, dict) or not factor.get("key") or not factor.get("label"):
            found.append(f"{at}: needs a key and a label")
            continue
        described = factor.get("levels")
        if not isinstance(described, list) or len(described) < 2:
            found.append(f"{at}: needs a description of each level, starting with level 0")
            continue
        if factor["key"] in levels:
            found.append(f"{at}: the key {factor['key']!r} is used twice")
        levels[factor["key"]] = len(described) - 1
    for index, contribution in enumerate(model.get("contributions") or []):
        at = f"{where}.contributions[{index}]"
        if not isinstance(contribution, dict) or contribution.get("factor") not in levels:
            found.append(f"{at}: names a factor that is not defined")
            continue
        level = contribution.get("level")
        if (
            isinstance(level, bool)
            or not isinstance(level, int)
            or not 1 <= level <= levels[contribution["factor"]]
        ):
            found.append(f"{at}: level must be between 1 and {levels[contribution['factor']]}")
        if not contribution.get("reason"):
            found.append(f"{at}: needs a reason to show")
        if not contribution.get("when"):
            found.append(f"{at}: needs a condition")
        _check_condition(contribution.get("when"), f"{at}.when", known, found)
    tiers = model.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        return [*found, f"{where}: needs at least one tier"]
    tier_levels = []
    for index, tier in enumerate(tiers):
        at = f"{where}.tiers[{index}]"
        if not isinstance(tier, dict) or not tier.get("label") or not tier.get("key"):
            found.append(f"{at}: needs a key and a label")
            continue
        if tier.get("level") != index + 1:
            found.append(f"{at}: levels count up from 1; this should be {index + 1}")
        if not isinstance(tier.get("min"), int) or (index == 0 and tier.get("min") != 0):
            found.append(f"{at}: needs the lowest total it covers, and the first tier starts at 0")
        elif (
            index
            and isinstance(tiers[index - 1].get("min"), int)
            and tier["min"] <= tiers[index - 1]["min"]
        ):
            found.append(f"{at}: must start above the tier before it")
        tier_levels.append(tier.get("level"))
    if len(tiers) > 9:
        found.append(f"{where}: at most nine tiers")
    for index, floor in enumerate(model.get("floors") or []):
        at = f"{where}.floors[{index}]"
        if not isinstance(floor, dict) or floor.get("tier") not in tier_levels:
            found.append(f"{at}: names a tier that is not defined")
            continue
        if not floor.get("reason") or not floor.get("when"):
            found.append(f"{at}: needs a condition and a reason to show")
        _check_condition(floor.get("when"), f"{at}.when", known, found)
    stop_keys: set[str] = set()
    for index, stop in enumerate(model.get("stops") or []):
        at = f"{where}.stops[{index}]"
        if (
            not isinstance(stop, dict)
            or not stop.get("key")
            or not stop.get("reason")
            or not stop.get("when")
        ):
            found.append(f"{at}: needs a key, a condition, and a reason to show")
            continue
        if stop["key"] in stop_keys:
            found.append(f"{at}: the key {stop['key']!r} is used twice")
        stop_keys.add(stop["key"])
        _check_condition(stop.get("when"), f"{at}.when", known, found)
    return found


def problems(pack: Any) -> list[str]:
    """Everything wrong with a pack. An empty list means it can be loaded."""
    if not isinstance(pack, dict) or not isinstance(pack.get("pack"), dict):
        return ["The file is not a pack: it needs a `pack` header."]
    if pack["pack"].get("kind") != "program":
        return ["This is not a program pack."]
    found: list[str] = []
    forms = pack.get("forms") or []
    keys: set[str] = set()
    intake: dict[str, Any] | None = None
    for index, form in enumerate(forms):
        issues = form_problems(form, f"forms[{index}]")
        found += issues
        if isinstance(form, dict) and form.get("key"):
            if form["key"] in keys:
                found.append(f"forms[{index}]: the key {form['key']!r} is used twice")
            keys.add(form["key"])
            if form.get("kind") == "use_case":
                intake = form  # the scoring model is checked against it even if it has faults
    if pack.get("scoring_model") is not None:
        if intake is None:
            found.append(
                "scoring_model: needs a use case form in the same pack, whose answers it scores"
            )
        else:
            found += scoring_problems(pack["scoring_model"], question_keys(intake))
    for name, items in (pack.get("vocabularies") or {}).items():
        if name not in vocab.NAMES:
            found.append(f"vocabularies: there is no vocabulary called {name!r}")
        elif not isinstance(items, list) or not all(
            isinstance(i, dict) and i.get("key") and i.get("label") for i in items
        ):
            found.append(f"vocabularies.{name}: every value needs a key and a label")
    return found


def published_form(session: Session, key: str) -> FormVersion | None:
    return session.scalars(
        select(FormVersion)
        .join(Form, Form.id == FormVersion.form_id)
        .where(Form.key == key, FormVersion.status == "published")
        .order_by(FormVersion.version.desc())
    ).first()


def published_scoring(session: Session) -> ScoringModel | None:
    return session.scalars(
        select(ScoringModel)
        .where(ScoringModel.status == "published")
        .order_by(ScoringModel.version.desc())
    ).first()


def apply(session: Session, principal: Principal, pack: dict[str, Any]) -> dict[str, Any]:
    """Load a pack. Anything that differs from what is published becomes a new version;
    anything the same is left alone. Earlier versions are kept, retired."""
    if not principal.configures:
        raise PermissionDenied("Only governance or an administrator can load a program pack.")
    found = problems(pack)
    if found:
        raise Invalid(
            "The pack was not loaded.", {f"problem_{i + 1}": text for i, text in enumerate(found)}
        )
    report: dict[str, Any] = {"forms": {}, "scoring_model": "unchanged", "vocabularies": []}
    now = utc_now()
    with audit.operation(session, "program.load", pack=pack["pack"].get("key")):
        for name, items in (pack.get("vocabularies") or {}).items():
            if vocab.get(session, name) != items:
                vocab.put(session, name, items)
                report["vocabularies"].append(name)
        for schema in pack.get("forms") or []:
            form = session.scalars(select(Form).where(Form.key == schema["key"])).first()
            if form is None:
                form = Form(key=schema["key"], kind=schema["kind"], title=schema["title"])
                session.add(form)
                session.flush()
            current = published_form(session, schema["key"])
            if current is not None and current.schema == schema:
                report["forms"][schema["key"]] = "unchanged"
                continue
            if current is not None:
                current.status = "retired"
            latest = session.execute(
                select(func.max(FormVersion.version)).where(FormVersion.form_id == form.id)
            ).scalar()
            form.title = schema["title"]
            session.add(
                FormVersion(
                    form_id=form.id,
                    version=(latest or 0) + 1,
                    status="published",
                    schema=schema,
                    published_at=now,
                    published_by=principal.account_id,
                )
            )
            report["forms"][schema["key"]] = f"version {(latest or 0) + 1}"
        definition = pack.get("scoring_model")
        if definition is not None:
            current_model = published_scoring(session)
            if current_model is None or current_model.definition != definition:
                if current_model is not None:
                    current_model.status = "retired"
                latest = session.execute(select(func.max(ScoringModel.version))).scalar()
                session.add(
                    ScoringModel(
                        version=(latest or 0) + 1,
                        status="published",
                        definition=definition,
                        published_at=now,
                        published_by=principal.account_id,
                    )
                )
                report["scoring_model"] = f"version {(latest or 0) + 1}"
        session.flush()
    return report


def ensure_defaults(session: Session, principal: Principal) -> bool:
    """Give a new installation the default program, so it can take requests on its first day."""
    if session.scalars(select(Form.id)).first() is not None:
        return False
    apply(session, principal, default_pack())
    return True


def export(session: Session) -> dict[str, Any]:
    """The program as it now stands, as one pack."""
    forms = session.scalars(
        select(FormVersion).where(FormVersion.status == "published").order_by(FormVersion.id)
    ).all()
    model = published_scoring(session)
    return {
        "pack": {
            "key": "exported-program",
            "kind": "program",
            "title": "Exported program",
            "exported_at": utc_now().isoformat(),
        },
        "vocabularies": vocab.all_(session),
        "forms": [version.schema for version in forms],
        **({"scoring_model": model.definition} if model else {}),
    }
