"""Frameworks: an outside set of requirements, loaded as a pack, with a crosswalk from the
control library. Readiness against a framework is worked out from how the controls stand;
it is never typed in. GovWren works fully with no framework loaded."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping
from importlib import resources
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.assurance import controls
from govwren.core.clock import utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import (
    Control,
    ControlImplementation,
    Framework,
    Requirement,
    RequirementExemption,
)
from govwren.events import audit

BUILT_IN = ("nist-ai-rmf", "iso-iec-42001", "hipaa", "owasp-agentic-top-10")
STATES = ("covered", "partly", "gap", "not_mapped", "not_applicable")


def builtin(key: str) -> dict[str, Any]:
    if key not in BUILT_IN:
        raise NotFound(f"There is no built-in framework called {key}.")
    file = resources.files("govwren.resources.packs").joinpath(f"{key}.json")
    return json.loads(file.read_text("utf-8"))  # type: ignore[no-any-return]


def _flatten(nodes: Any, parent: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in nodes or []:
        if not isinstance(node, dict):
            out.append({"code": None})
            continue
        out.append(
            {
                "code": node.get("code"),
                "title": node.get("title"),
                "text": node.get("text"),
                "parent": parent,
            }
        )
        out += _flatten(node.get("children"), node.get("code"))
    return out


def problems(session: Session, pack: Any) -> list[str]:
    """Everything wrong with a framework pack. An empty list means it can be loaded."""
    head = pack.get("pack") if isinstance(pack, dict) else None
    if not isinstance(head, dict) or head.get("kind") != "framework":
        return ["This is not a framework pack."]
    found = []
    if not head.get("key") or not head.get("title"):
        found.append("The pack needs a key and a title.")
    flat = _flatten(pack.get("requirements"))
    codes: set[str] = set()
    for position, item in enumerate(flat, start=1):
        code = item.get("code")
        if not code or not (item.get("title") or item.get("text")):
            found.append(f"Requirement {position} needs a code and a title or some text.")
        elif code in codes:
            found.append(f"The code {code} is used twice.")
        else:
            codes.add(code)
    if not flat:
        found.append("The pack holds no requirements.")
    known = set(session.scalars(select(Control.key)))
    crosswalk = pack.get("crosswalk") or {}
    if not isinstance(crosswalk, dict):
        found.append("The crosswalk must map requirement codes to lists of control keys.")
        crosswalk = {}
    for code, keys in crosswalk.items():
        if code not in codes:
            found.append(f"The crosswalk names a requirement that is not in the pack: {code}.")
        for key in keys if isinstance(keys, list) else []:
            if key not in known:
                found.append(f"{code} is mapped to a control that is not in the library: {key}.")
    return found


def find(session: Session, key: str) -> Framework:
    framework = session.scalars(select(Framework).where(Framework.key == key)).first()
    if framework is None:
        raise NotFound(f"No framework called {key} is loaded.")
    return framework


def load(session: Session, principal: Principal, pack: dict[str, Any]) -> Framework:
    """Load a framework, or bring a loaded one up to date. A pack that fails its checks is
    refused whole. Requirements keep their codes, so what was said about them stays attached."""
    if not principal.governs:
        raise PermissionDenied("Only governance can load a framework.")
    wrong = problems(session, pack)
    if wrong:
        raise Invalid("The framework was not loaded.", {"pack": " ".join(wrong[:8])})
    head = pack["pack"]
    details = {
        name: head.get(name)
        for name in ("publisher", "source_url", "license", "text_policy", "attribution")
    }
    crosswalk = pack.get("crosswalk") or {}
    with audit.operation(session, "framework.load", framework=head["key"]):
        framework = session.scalars(select(Framework).where(Framework.key == head["key"])).first()
        if framework is None:
            framework = Framework(key=head["key"], title=head["title"], loaded_at=utc_now())
            session.add(framework)
        framework.title, framework.version = head["title"], head.get("version")
        framework.pack_version, framework.details = head.get("pack_version"), details
        framework.loaded_by, framework.loaded_at = principal.account_id, utc_now()
        session.flush()
        session.execute(delete(Requirement).where(Requirement.framework_id == framework.id))
        for position, item in enumerate(_flatten(pack["requirements"])):
            session.add(
                Requirement(
                    framework_id=framework.id,
                    code=item["code"],
                    parent_code=item["parent"],
                    title=item.get("title"),
                    text=item.get("text"),
                    position=position,
                    control_keys=list(crosswalk.get(item["code"], [])),
                )
            )
        session.flush()
    return framework


def unload(session: Session, principal: Principal, framework: Framework) -> None:
    """Remove a framework. Controls, their standing, and their evidence are not touched."""
    if not principal.governs:
        raise PermissionDenied("Only governance can remove a framework.")
    with audit.operation(session, "framework.unload", framework=framework.key):
        session.execute(delete(Requirement).where(Requirement.framework_id == framework.id))
        for row in session.scalars(
            select(RequirementExemption).where(RequirementExemption.framework_id == framework.id)
        ):
            session.delete(row)
        session.delete(framework)
        session.flush()


def set_applicability(
    session: Session,
    principal: Principal,
    framework: Framework,
    code: str,
    *,
    applies: bool,
    justification: str = "",
) -> None:
    """Say that a requirement does not apply to the organization, with why, or that it does."""
    if not principal.governs:
        raise PermissionDenied("Only governance can say a requirement does not apply.")
    known = session.scalars(
        select(Requirement.id).where(
            Requirement.framework_id == framework.id, Requirement.code == code
        )
    ).first()
    if known is None:
        raise NotFound(f"{framework.title} has no requirement {code}.")
    existing = session.scalars(
        select(RequirementExemption).where(
            RequirementExemption.framework_id == framework.id, RequirementExemption.code == code
        )
    ).first()
    justification = justification.strip()
    if not applies and len(justification) < 10:
        raise Invalid("Nothing was saved.", {"justification": "Say why it does not apply."})
    with audit.operation(session, "framework.applicability", code=code):
        if applies:
            if existing is None:
                raise Conflict("That requirement already applies.")
            session.delete(existing)
        elif existing is None:
            session.add(
                RequirementExemption(
                    framework_id=framework.id,
                    code=code,
                    justification=justification,
                    set_by=principal.account_id,
                    set_at=utc_now(),
                )
            )
        else:
            existing.justification = justification
        session.flush()


# --- Readiness ----------------------------------------------------------------------------


def _control_states(session: Session, principal: Principal) -> dict[str, dict[str, Any]]:
    """Each control as full, partial, or none: a program control by its standing and whether
    it has evidence that is still good; a record control by the share of records in place."""
    program = {
        row.control_id: row
        for row in session.scalars(
            select(ControlImplementation).where(ControlImplementation.subject_type.is_(None))
        )
    }
    ids = dict(session.execute(select(Control.key, Control.id)).all())  # type: ignore[arg-type]
    out: dict[str, dict[str, Any]] = {}
    for card in controls.library(session, principal):
        if card["scope"] == "program":
            row = program.get(ids[card["key"]])
            evidence = controls._evidence(session, row)
            good = card["status"] == "implemented" and evidence["evidence_gap"] is None
            level = (
                "full"
                if good
                else "partial"
                if card["status"] in ("implemented", "in_progress")
                else "none"
            )
            detail = card["status_label"] + (
                ""
                if card["status"] != "implemented"
                else ", with evidence"
                if good
                else ", evidence expired"
                if evidence["evidence_gap"] == "expired"
                else ", no evidence"
            )
        else:
            total, done = card["applicable"], card["in_place"]
            level = "full" if total and done == total else "partial" if done else "none"
            detail = (
                f"In place on {done} of {total} records" if total else "No record it applies to"
            )
        out[card["key"]] = {
            "key": card["key"],
            "title": card["title"],
            "scope": card["scope"],
            "level": level,
            "detail": detail,
        }
    return out


def _state(levels: list[str]) -> str:
    if not levels:
        return "not_mapped"
    if all(level == "full" for level in levels):
        return "covered"
    return "gap" if all(level == "none" for level in levels) else "partly"


def readiness(session: Session, principal: Principal, framework: Framework) -> dict[str, Any]:
    """Each requirement as covered, partly covered, a gap, not mapped, or not applicable,
    with the controls behind it. A group takes its state from the requirements beneath it."""
    rows = session.scalars(
        select(Requirement)
        .where(Requirement.framework_id == framework.id)
        .order_by(Requirement.position)
    ).all()
    exempt = {
        row.code: row.justification
        for row in session.scalars(
            select(RequirementExemption).where(RequirementExemption.framework_id == framework.id)
        )
    }
    states = _control_states(session, principal)
    parents = {row.parent_code for row in rows if row.parent_code}
    counts = dict.fromkeys(STATES, 0)
    by_code: dict[str, dict[str, Any]] = {}
    for row in rows:
        behind = [states[key] for key in row.control_keys if key in states]
        leaf = row.code not in parents
        state = "not_applicable" if row.code in exempt else _state([c["level"] for c in behind])
        if leaf:
            counts[state] += 1
        by_code[row.code] = {
            "code": row.code,
            "title": row.title,
            "text": row.text,
            "parent": row.parent_code,
            "leaf": leaf,
            "state": state if leaf else None,
            "justification": exempt.get(row.code),
            "controls": behind,
            "children": [],
        }
    tree = []
    for item in by_code.values():
        if item["parent"] and item["parent"] in by_code:
            by_code[item["parent"]]["children"].append(item)
        else:
            tree.append(item)
    return {
        "key": framework.key,
        "title": framework.title,
        "version": framework.version,
        "pack_version": framework.pack_version,
        **framework.details,
        "loaded_at": framework.loaded_at,
        "counts": counts,
        "total": sum(counts.values()),
        "requirements": tree,
        "can_change": principal.governs,
    }


def listing(session: Session, principal: Principal) -> dict[str, Any]:
    loaded = session.scalars(select(Framework).order_by(Framework.title)).all()
    keys = {framework.key for framework in loaded}
    available = []
    for key in BUILT_IN:
        if key not in keys:
            head = builtin(key)["pack"]
            available.append(
                {
                    "key": key,
                    "title": head["title"],
                    "version": head.get("version"),
                    "attribution": head.get("attribution"),
                }
            )
    return {
        "loaded": [
            {
                "key": f.key,
                "title": f.title,
                "version": f.version,
                "counts": readiness(session, principal, f)["counts"],
            }
            for f in loaded
        ],
        "available": available,
        "can_load": principal.governs,
    }


# --- The statement of applicability ---------------------------------------------------------


def statement_of_applicability(session: Session, principal: Principal) -> list[dict[str, Any]]:
    """Every control in the library with whether it applies, why, how it stands, who owns
    it, and what evidence there is."""
    states = _control_states(session, principal)
    out = []
    program = {
        row.control_id: row
        for row in session.scalars(
            select(ControlImplementation).where(ControlImplementation.subject_type.is_(None))
        )
    }
    ids = dict(session.execute(select(Control.key, Control.id)).all())  # type: ignore[arg-type]
    for card in controls.library(session, principal):
        row = program.get(ids[card["key"]]) if card["scope"] == "program" else None
        evidence = controls._evidence(session, row)["evidence"] if row else []
        if card["scope"] == "program":
            applies = card["status"] != "not_applicable"
            why = card["note"] if not applies else "Applies to the program as a whole"
            status, owner = card["status_label"], card["owner"]
        else:
            applies = card["applicable"] > 0
            kinds = " and ".join(kind.replace("_", " ") + "s" for kind in card["applies_to"])
            exempt = card["counts"]["not_applicable"]
            why = f"Applies to {card['applicable']} {kinds} by rule" + (
                f"; {exempt} marked as not applicable" if exempt else ""
            )
            status, owner = states[card["key"]]["detail"], None
        out.append(
            {
                "key": card["key"],
                "group": card["category_label"],
                "control": card["title"],
                "statement": card["statement"],
                "scope": "Program" if card["scope"] == "program" else "Records",
                "applies": "Yes" if applies else "No",
                "justification": why or "",
                "status": status,
                "owner": owner or "",
                "evidence": "; ".join(f"{e['ref']} {e['title']}" for e in evidence),
            }
        )
    return out


STATE_WORDS = {
    "covered": "Covered",
    "partly": "Partly covered",
    "gap": "Gap",
    "not_mapped": "No control answers it",
    "not_applicable": "Does not apply",
}
FRAMEWORK_HEADINGS = ["Code", "Requirement", "Applies", "Justification", "State", "Controls"]


def framework_statement(
    session: Session, principal: Principal, framework: Framework
) -> list[dict[str, Any]]:
    """The statement of applicability against one framework: each of its requirements with
    whether it applies, the reason given if it does not, how it stands, and the controls
    that answer it with where each of those stands."""
    out: list[dict[str, Any]] = []

    def walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            if item["leaf"]:
                exempt = item["state"] == "not_applicable"
                out.append(
                    {
                        "code": item["code"],
                        "requirement": item["title"] or "",
                        "applies": "No" if exempt else "Yes",
                        "justification": item["justification"] or "",
                        "state": STATE_WORDS[item["state"]],
                        "controls": "; ".join(
                            f"{c['title']} ({c['detail']})" for c in item["controls"]
                        ),
                    }
                )
            walk(item["children"])

    walk(readiness(session, principal, framework)["requirements"])
    return out


def statement_csv(rows: list[Mapping[str, Any]], headings: list[str] | None = None) -> str:
    out = io.StringIO()
    headings = headings or [
        "Key",
        "Group",
        "Control",
        "Statement",
        "Scope",
        "Applies",
        "Justification",
        "Status",
        "Owner",
        "Evidence",
    ]
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(headings)
    for row in rows:
        writer.writerow([row[name.lower()] for name in headings])
    return out.getvalue()
