"""Controls: safeguards defined once in a library, and how each one stands.

A control applies to the program as a whole, or to every record its rule picks out.
Applicability is worked out from the record each time it is asked; nothing is copied per
record. A row is kept only once someone has said how the control stands.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from importlib import resources
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core import conditions
from govwren.core.clock import today, utc_now
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.db.models import Account, Control, ControlImplementation, RiskStatement
from govwren.db.models.assurance import IMPLEMENTATION_STATUSES
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import DATASET, MODEL, SYSTEM, TYPES, USE_CASE, RecordType
from govwren.review import service as review

SCOPED = (USE_CASE, SYSTEM, MODEL, DATASET)
STATUS_WORDS = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "implemented": "In place",
    "not_applicable": "Does not apply",
}
LIVE_STANDINGS = ("approved", "approved_with_conditions", "suspended", "lapsed", "active")


def builtin() -> dict[str, Any]:
    text = (
        resources.files("govwren.resources.packs")
        .joinpath("control-library.json")
        .read_text("utf-8")
    )
    return json.loads(text)  # type: ignore[no-any-return]


def problems(pack: Any) -> list[str]:
    """Everything wrong with a control library pack. An empty list means it can be loaded."""
    if not isinstance(pack, dict) or (pack.get("pack") or {}).get("kind") != "control_library":
        return ["This is not a control library pack."]
    found: list[str] = []
    categories = {c.get("key") for c in pack.get("categories", []) if isinstance(c, dict)}
    kinds = {record_type.key for record_type in SCOPED}
    seen: set[str] = set()
    for position, control in enumerate(pack.get("controls") or [], start=1):
        key = control.get("key") if isinstance(control, dict) else None
        if not key or not control.get("title") or not control.get("statement"):
            found.append(f"Control {position} needs a key, a title, and a statement.")
            continue
        if key in seen:
            found.append(f"The key {key} is used twice.")
        seen.add(key)
        if control.get("category") not in categories:
            found.append(f"{key} names a category the pack does not define.")
        if control.get("scope") not in ("program", "record"):
            found.append(f"{key} must apply to the program or to records.")
        elif control["scope"] == "record":
            applies = control.get("applies_to") or []
            if not applies or any(kind not in kinds for kind in applies):
                found.append(f"{key} must name the kinds of record it applies to.")
            if control.get("when") is not None:
                found += [f"{key}: {p}" for p in conditions.problems(control["when"])]
    if not seen and not found:
        found.append("The pack holds no controls.")
    return found


def load(session: Session, pack: dict[str, Any]) -> int:
    """Add the pack's controls and bring those already here up to date. A control the pack
    no longer holds is retired, never removed, so what was recorded against it is kept."""
    wrong = problems(pack)
    if wrong:
        raise Invalid("The control library was not loaded.", {"pack": " ".join(wrong)})
    labels = {c["key"]: c["label"] for c in pack["categories"]}
    version = pack["pack"].get("pack_version")
    existing = {row.key: row for row in session.scalars(select(Control))}
    for control in pack["controls"]:
        values = {
            "category": control["category"],
            "category_label": labels[control["category"]],
            "title": control["title"],
            "statement": control["statement"],
            "scope": control["scope"],
            "applies_to": list(control.get("applies_to") or []),
            "applies_when": control.get("when"),
            "check_months": int(control.get("check_months") or 12),
            "risk_keys": list(control.get("risks") or []),
            "pack_version": version,
            "retired": False,
        }
        row = existing.pop(control["key"], None)
        if row is None:
            session.add(Control(key=control["key"], **values))
        else:
            for name, value in values.items():
                if getattr(row, name) != value:
                    setattr(row, name, value)
    for row in existing.values():
        if not row.retired:
            row.retired = True
    session.flush()
    return len(pack["controls"])


def ensure(session: Session) -> bool:
    if session.scalars(select(Control.id)).first() is not None:
        return False
    load(session, builtin())
    return True


def find(session: Session, key: str) -> Control:
    control = session.scalars(select(Control).where(Control.key == key)).first()
    if control is None:
        raise NotFound(f"There is no control {key}.")
    return control


def _facts(record: Any) -> dict[str, Any]:
    """What a control's rule may ask about a record."""
    names = (
        "tier",
        "data_class",
        "domain",
        "stage",
        "kind",
        "origin",
        "status",
        "catalog_status",
        "data_categories",
        "hosting",
    )
    return {"record": {name: getattr(record, name, None) for name in names}}


def applies(control: Control, record_type: RecordType, record: Any) -> bool:
    if control.retired or control.scope != "record" or record_type.key not in control.applies_to:
        return False
    return control.applies_when is None or conditions.evaluate(control.applies_when, _facts(record))


def _rows(session: Session, subject: tuple[str, int] | None) -> dict[int, ControlImplementation]:
    statement = select(ControlImplementation)
    if subject is None:
        statement = statement.where(ControlImplementation.subject_type.is_(None))
    else:
        statement = statement.where(
            ControlImplementation.subject_type == subject[0],
            ControlImplementation.subject_id == subject[1],
        )
    return {row.control_id: row for row in session.scalars(statement)}


def _evidence(session: Session, row: ControlImplementation | None) -> dict[str, Any]:
    """What supports a control's standing, and whether any of it is still good."""
    from govwren.db.models import Evidence, EvidenceLink
    from govwren.evidence import service as evidence

    if row is None:
        return {"implementation_id": None, "evidence": [], "evidence_gap": None}
    items = session.scalars(
        select(Evidence)
        .join(EvidenceLink, EvidenceLink.evidence_id == Evidence.id)
        .where(EvidenceLink.subject_type == "control", EvidenceLink.subject_id == row.id)
        .order_by(Evidence.id)
    ).all()
    states = [evidence.state(item) for item in items]
    live = [state for state in states if state != "withdrawn"]
    gap = None
    if row.status == "implemented":
        if not live:
            gap = "none"
        elif all(state == "expired" for state in live):
            gap = "expired"
    return {
        "implementation_id": row.id,
        "evidence": [
            {"ref": item.ref, "title": item.title, "state": state, "expires_on": item.expires_on}
            for item, state in zip(items, states, strict=True)
            if state != "withdrawn"
        ],
        "evidence_gap": gap,
    }


def _standing(row: ControlImplementation | None, names: Mapping[int, str]) -> dict[str, Any]:
    status = row.status if row else "not_started"
    due = row.next_check_on if row else None
    return {
        "status": status,
        "status_label": STATUS_WORDS[status],
        "note": row.note if row else None,
        "owner_id": row.owner_id if row else None,
        "owner": names.get(row.owner_id or 0) if row else None,
        "next_check_on": due,
        "check_due": status == "implemented" and bool(due and due <= today()),
        "checked_at": row.checked_at if row else None,
    }


def _names(session: Session, rows: Any) -> dict[int, str]:
    ids = {row.owner_id for row in rows if row is not None and row.owner_id}
    return dict(
        session.execute(
            select(Account.id, Account.display_name).where(Account.id.in_(ids or {0}))
        ).all()  # type: ignore[arg-type]
    )


def _card(control: Control) -> dict[str, Any]:
    return {
        "key": control.key,
        "category": control.category,
        "category_label": control.category_label,
        "title": control.title,
        "statement": control.statement,
        "scope": control.scope,
        "applies_to": control.applies_to,
        "check_months": control.check_months,
        "risk_keys": control.risk_keys,
    }


def for_record(
    session: Session, principal: Principal, record_type: RecordType, record: Any
) -> list[dict[str, Any]]:
    """The controls that apply to one record, each with how it stands there."""
    rows = _rows(session, (record_type.key, record.id))
    names = _names(session, rows.values())
    may = principal.governs or access.can_edit(session, principal, record_type, record)
    out = []
    for control in session.scalars(select(Control).order_by(Control.category_label, Control.id)):
        if applies(control, record_type, record):
            row = rows.get(control.id)
            out.append(
                {
                    **_card(control),
                    **_standing(row, names),
                    **_evidence(session, row),
                    "can_set": may,
                }
            )
    return out


def _live_records(
    session: Session, control: Control, loaded: dict[str, list[Any]] | None = None
) -> list[tuple[RecordType, Any]]:
    """The live records a control applies to. ``loaded`` keeps each kind's records between
    calls, so that going through every control reads each table once."""
    found = []
    loaded = {} if loaded is None else loaded
    for key in control.applies_to:
        record_type = TYPES[key]
        model = record_type.model
        if key not in loaded:
            loaded[key] = list(
                session.scalars(
                    select(model).where(model.status.in_(LIVE_STANDINGS)).order_by(model.id)  # type: ignore[attr-defined]
                )
            )
        for record in loaded[key]:
            if applies(control, record_type, record):
                found.append((record_type, record))
    return found


def library(session: Session, principal: Principal) -> list[dict[str, Any]]:
    """Every control, with how it stands for the program or across the records it applies to."""
    controls = session.scalars(
        select(Control)
        .where(Control.retired.is_(False))
        .order_by(Control.category_label, Control.id)
    ).all()
    program = _rows(session, None)
    names = _names(session, program.values())
    by_control: dict[int, dict[tuple[str, int], str]] = defaultdict(dict)
    for row in session.scalars(
        select(ControlImplementation).where(ControlImplementation.subject_type.is_not(None))
    ):
        by_control[row.control_id][(row.subject_type or "", row.subject_id or 0)] = row.status
    out = []
    loaded: dict[str, list[Any]] = {}
    for control in controls:
        card = _card(control)
        if control.scope == "program":
            out.append(
                {**card, **_standing(program.get(control.id), names), "can_set": principal.governs}
            )
            continue
        counts = dict.fromkeys(IMPLEMENTATION_STATUSES, 0)
        said = by_control.get(control.id, {})
        for record_type, record in _live_records(session, control, loaded):
            counts[said.get((record_type.key, record.id), "not_started")] += 1
        applicable = sum(counts.values()) - counts["not_applicable"]
        out.append(
            {**card, "counts": counts, "applicable": applicable, "in_place": counts["implemented"]}
        )
    return out


def detail(session: Session, principal: Principal, control: Control) -> dict[str, Any]:
    """One control: its wording, the risks it answers, and how it stands record by record."""
    risks = [
        {"key": row.key, "title": row.title}
        for row in session.scalars(
            select(RiskStatement).where(RiskStatement.key.in_(control.risk_keys or [""]))
        )
    ]
    out: dict[str, Any] = {**_card(control), "risks": risks, "records": []}
    if control.scope == "program":
        rows = _rows(session, None)
        row = rows.get(control.id)
        return {**out, **_standing(row, _names(session, [row])), "can_set": principal.governs}
    said = {
        (row.subject_type, row.subject_id): row
        for row in session.scalars(
            select(ControlImplementation).where(ControlImplementation.control_id == control.id)
        )
    }
    names = _names(session, said.values())
    for record_type, record in _live_records(session, control):
        if access.sight(session, principal, record_type, record) != access.FULL:
            continue
        out["records"].append(
            {
                "type": record_type.key,
                "ref": record.ref,
                "name": record.name,
                "href": f"/{record_type.path}/{record.ref}",
                **_standing(said.get((record_type.key, record.id)), names),
            }
        )
    order = {"not_started": 0, "in_progress": 1, "implemented": 2, "not_applicable": 3}
    out["records"].sort(key=lambda r: (order[r["status"]], r["name"]))
    return out


def add_months(start: date, months: int) -> date:
    return review.add_months(start, months)


def set_standing(
    session: Session,
    principal: Principal,
    control: Control,
    values: Mapping[str, Any],
    *,
    record: tuple[RecordType, Any] | None = None,
) -> ControlImplementation:
    """Say how a control stands, for the program or for one record it applies to. Marking it
    in place sets the date it is next checked. Saying it does not apply needs the reason."""
    if control.retired:
        raise Invalid("Nothing was saved.", {"control": "This control has been retired."})
    if control.scope == "program":
        if record is not None:
            raise Invalid("Nothing was saved.", {"record": "This control is for the program."})
        if not principal.governs:
            raise PermissionDenied("Only governance says how a program control stands.")
    else:
        if record is None:
            raise Invalid("Nothing was saved.", {"record": "Say which record this is about."})
        if not applies(control, record[0], record[1]):
            raise Invalid(
                "Nothing was saved.", {"record": "This control does not apply to that record."}
            )
        if not (principal.governs or access.can_edit(session, principal, record[0], record[1])):
            raise PermissionDenied(
                "Only those responsible for a record say how its controls stand."
            )
    status = str(values.get("status") or "")
    note = str(values.get("note") or "").strip()
    errors = {}
    if status not in IMPLEMENTATION_STATUSES:
        errors["status"] = "Choose how it stands."
    if status == "not_applicable" and len(note) < 10:
        errors["note"] = "Say why it does not apply here."
    if status == "not_applicable" and not principal.governs:
        errors["status"] = "Only governance can say a control does not apply."
    owner = session.get(Account, values["owner_id"]) if values.get("owner_id") else None
    if values.get("owner_id") and (owner is None or owner.status != "active"):
        errors["owner_id"] = "Choose who owns it."
    if errors:
        raise Invalid("Nothing was saved.", errors)
    subject = (record[0].key, record[1].id) if record else None
    row = _rows(session, subject).get(control.id)
    now = utc_now()
    with audit.operation(session, "control.set", control=control.key):
        if row is None:
            row = ControlImplementation(
                control_id=control.id,
                subject_type=subject[0] if subject else None,
                subject_id=subject[1] if subject else None,
                status="not_started",
                updated_at=now,
            )
            session.add(row)
        newly = status == "implemented" and row.status != "implemented"
        row.status, row.note, row.updated_at = status, note or None, now
        row.owner_id = owner.id if owner else (row.owner_id or principal.account_id)
        if newly or values.get("checked"):
            row.checked_by, row.checked_at = principal.account_id, now
            row.next_check_on = add_months(today(), control.check_months)
        if status != "implemented":
            row.next_check_on = None
        session.flush()
    return row


def for_risk(
    session: Session,
    principal: Principal,
    library_key: str | None,
    record: tuple[RecordType, Any] | None,
) -> list[dict[str, Any]]:
    """The controls that answer a risk drawn from the library, with how each stands for the
    record the risk is on, or for the program."""
    if not library_key:
        return []
    out = []
    rows = _rows(session, (record[0].key, record[1].id)) if record else {}
    program = _rows(session, None)
    for control in session.scalars(select(Control).where(Control.retired.is_(False))):
        if library_key not in (control.risk_keys or []):
            continue
        if control.scope == "program":
            row = program.get(control.id)
        elif record is not None and applies(control, record[0], record[1]):
            row = rows.get(control.id)
        else:
            continue
        out.append(
            {
                "key": control.key,
                "title": control.title,
                "scope": control.scope,
                **_standing(row, {}),
            }
        )
    return out


def remind(session: Session) -> int:
    """Tell the owner of a control that is in place when its check falls due, once per date."""
    from govwren.db.models import Reminder

    sent = 0
    done = {
        (subject, stage)
        for subject, stage in session.execute(
            select(Reminder.subject_id, Reminder.stage).where(Reminder.subject_type == "control")
        )
    }
    controls = {c.id: c for c in session.scalars(select(Control))}
    for row in session.scalars(
        select(ControlImplementation).where(
            ControlImplementation.status == "implemented",
            ControlImplementation.next_check_on.is_not(None),
            ControlImplementation.next_check_on <= today(),
        )
    ):
        stage = f"due:{row.next_check_on:%y%m%d}"
        if row.owner_id is None or (row.id, stage) in done:
            continue
        session.add(
            Reminder(subject_type="control", subject_id=row.id, stage=stage, sent_on=today())
        )
        record_type = TYPES.get(row.subject_type or "")
        record = session.get(record_type.model, row.subject_id) if record_type else None
        href = f"/controls/{controls[row.control_id].key}"
        if record is not None and record_type is not None:
            href = f"/controls?record={record.ref}"
        review.notify(
            session,
            [row.owner_id],
            "reminder",
            f"Check that this is still in place: {controls[row.control_id].title}",
            href,
        )
        sent += 1
    session.flush()
    return sent


def gaps(session: Session, principal: Principal, *, everything: bool) -> list[dict[str, Any]]:
    """What needs doing to keep controls true, as rows for the action list: a control in
    place whose check is due, or whose evidence has all expired."""
    statement = select(ControlImplementation).where(ControlImplementation.status == "implemented")
    if not everything:
        statement = statement.where(ControlImplementation.owner_id == principal.account_id)
    rows = session.scalars(statement).all()
    if not rows:
        return []
    names = _names(session, rows)
    controls = {c.id: c for c in session.scalars(select(Control))}
    out = []
    for row in rows:
        control = controls[row.control_id]
        record_type = TYPES.get(row.subject_type or "")
        record = session.get(record_type.model, row.subject_id) if record_type else None
        about = (
            {"ref": record.ref, "name": record.name, "href": f"/controls?record={record.ref}"}
            if record is not None
            else None
        )
        source = {"label": "A control", "href": f"/controls/{control.key}"}
        base = {
            "kind": "control",
            "id": row.id,
            "about": about,
            "source": source,
            "owner": names.get(row.owner_id or 0),
            "status": "open",
            "note": None,
            "can_close": False,
            "can_cancel": False,
        }
        if row.next_check_on and row.next_check_on <= today():
            out.append(
                {
                    **base,
                    "title": f"Check that this is still in place: {control.title}",
                    "detail": None,
                    "due_on": row.next_check_on,
                    "overdue": True,
                }
            )
        if _evidence(session, row)["evidence_gap"] == "expired":
            out.append(
                {
                    **base,
                    "title": f"Renew the evidence for: {control.title}",
                    "detail": "Everything attached has expired",
                    "due_on": None,
                    "overdue": True,
                }
            )
    return out
