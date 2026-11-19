"""Bring existing records in from a spreadsheet saved as CSV, and take any list out again.

An import maps the file's columns onto a record's fields, then runs dry: every row is tried,
every problem is reported with its row, and nothing is kept unless every row is good. Each
row goes through the same service as a record typed in by hand, so an imported record is
checked the same way and has the same history.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import GovWrenError, Invalid, PermissionDenied
from govwren.db.models import AISystem, Model, RecordOwner, Vendor
from govwren.inventory import access, fields, records
from govwren.inventory.registry import DATASET, MODEL, SYSTEM, USE_CASE, VENDOR, RecordType
from govwren.people import accounts, units
from govwren.program import vocab

MAX_ROWS = 5000
IMPORTABLE = (SYSTEM, MODEL, DATASET, VENDOR)
SKIP = ""  # a column mapped to this is left out


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    kind: str = "text"  # text, choice, choices, unit, vendor, owner, yes_no
    vocab: str | None = None
    required: bool = False


COMMON = (
    Column("ref", "Reference (to change an existing record)"),
    Column("name", "Name", required=True),
    Column("summary", "Summary"),
)
PLACED = (Column("unit", "Unit (code or name)", "unit"), Column("owner", "Owner (email)", "owner"))
SYSTEM_COLUMNS = (
    *COMMON,
    Column("kind", "Kind", "choice", "system_kinds", required=True),
    Column("vendor", "Vendor (name or reference)", "vendor"),
    Column("edition", "Edition"),
    Column("hosting", "Hosting", "choice", "hosting"),
    Column("access_path", "Reached through", "choice", "access_paths"),
    Column("version_label", "Version"),
    Column("url", "Address"),
    Column("embedded_in", "Inside which product"),
    Column("trains_on_inputs", "Supplier trains on inputs (yes, no, unknown)"),
    Column("catalog_status", "Catalog standing", "choice", "catalog_statuses"),
    Column("permitted_data_class", "May be used with data up to", "choice", "data_classes"),
    Column("excluded_data_categories", "Not to be used with", "choices", "data_categories"),
    Column("terms", "Terms of use"),
    *PLACED,
)
VENDOR_COLUMNS = (
    *COMMON,
    Column("website", "Website"),
    Column("status", "Standing", "choice", "vendor_statuses"),
    Column("due_diligence_status", "Due diligence", "choice", "due_diligence"),
    Column("notes", "Notes"),
    Column("contact_name", "Contact name"),
    Column("contact_email", "Contact email"),
)
FIXED = {
    **fields.FIXED,
    "vendor_statuses": [("prospective", "Prospective"), ("active", "Active"),
                        ("offboarding", "Offboarding"), ("former", "Former")],
    "due_diligence": [("not_started", "Not started"), ("in_progress", "In progress"),
                      ("complete", "Complete")],
}  # fmt: skip


def _described(spec: Sequence[fields.Field], *, vendor: bool) -> tuple[Column, ...]:
    out = list(COMMON)
    if vendor:
        out.append(Column("vendor", "Vendor (name or reference)", "vendor"))
    for item in spec:
        kind = item.kind if item.kind in ("choice", "choices") else "text"
        out.append(Column(item.key, item.label, kind, item.vocab, item.required))
    return (*out, *PLACED)


def columns(record_type: RecordType) -> tuple[Column, ...]:
    if record_type is SYSTEM:
        return SYSTEM_COLUMNS
    if record_type is VENDOR:
        return VENDOR_COLUMNS
    if record_type is MODEL:
        return _described(fields.MODEL, vendor=True)
    if record_type is DATASET:
        return _described(fields.DATASET, vendor=False)
    raise Invalid(
        "That cannot be imported.", {"type": "Import systems, models, datasets, or vendors."}
    )


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def suggest(headers: Sequence[str], offered: Sequence[Column]) -> dict[str, str]:
    """A first guess at which column is which field, by name."""
    by_name: dict[str, str] = {}
    for column in offered:
        by_name[_plain(column.key)] = column.key
        by_name[_plain(column.label.split("(")[0])] = column.key
    extra = {"owner email": "owner", "email": "owner", "unit code": "unit", "department": "unit",
             "supplier": "vendor", "description": "summary", "reference": "ref", "id": "ref",
             "title": "name", "data classification": "data_class", "classification": "data_class",
             "type": "kind", "plan": "edition", "tier": "edition", "link": "url",
             "website": "website"}  # fmt: skip
    keys = {column.key for column in offered}
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    for header in headers:
        plain = _plain(header)
        guess = by_name.get(plain) or (extra.get(plain) if extra.get(plain) in keys else None)
        if guess and guess not in taken:
            mapping[header] = guess
            taken.add(guess)
        else:
            mapping[header] = SKIP
    return mapping


@dataclass
class Report:
    kind: str
    dry_run: bool
    headers: list[str] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)
    rows: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    problems: list[dict[str, Any]] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)

    def problem(self, row: int, message: str) -> None:
        self.problems.append({"row": row, "message": message})

    @property
    def applied(self) -> bool:
        return not self.dry_run and not self.problems

    def to_json(self, offered: Sequence[Column]) -> dict[str, Any]:
        return {
            "kind": self.kind, "dry_run": self.dry_run, "applied": self.applied,
            "headers": self.headers, "mapping": self.mapping, "rows": self.rows,
            "created": self.created, "updated": self.updated, "unchanged": self.unchanged,
            "problems": self.problems[:500], "problem_count": len(self.problems),
            "fields": [{"key": c.key, "label": c.label, "required": c.required} for c in offered],
        }  # fmt: skip


def _labels(session: Session, name: str) -> dict[str, str]:
    """Every way a choice may be written: its key or its label, in any case."""
    pairs = FIXED[name] if name in FIXED else [
        (item["key"], item["label"]) for item in vocab.get(session, name) if not item.get("retired")
    ]  # fmt: skip
    found: dict[str, str] = {}
    for key, label in pairs:
        found[_plain(key)] = key
        found[_plain(label)] = key
    return found


def _existing(session: Session, record_type: RecordType, values: Mapping[str, Any]) -> Any:
    """The record a row is about, if it is already here: by name, and by edition or version
    where two records may share a name."""
    model: Any = record_type.model
    statement = select(model).where(func.lower(model.name) == str(values["name"]).lower())
    if record_type is SYSTEM:
        statement = statement.where(
            func.lower(func.coalesce(AISystem.edition, ""))
            == str(values.get("edition") or "").lower()
        )
    elif record_type is MODEL:
        statement = statement.where(
            func.coalesce(Model.version_label, "") == str(values.get("version_label") or "")
        )
    return session.scalars(statement.order_by(model.id)).first()


def run(
    session: Session, principal: Principal, record_type: RecordType, text: str, *,
    mapping: Mapping[str, str] | None = None, dry_run: bool = True,
) -> Report:  # fmt: skip
    """Import a CSV. With no mapping, the columns are matched to fields by name and the
    guess is returned for the person to correct."""
    if not principal.edits_all:
        raise PermissionDenied("Only governance can import records.")
    offered = columns(record_type)
    by_key = {column.key: column for column in offered}
    lines = [line for line in text.lstrip("﻿").splitlines() if not line.startswith("#")]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    headers = [h for h in (reader.fieldnames or []) if h and h.strip()]
    report = Report(record_type.key, dry_run, headers=headers)
    if not headers:
        raise Invalid("The file cannot be read.", {"file": "It needs a header row."})
    report.mapping = dict(mapping) if mapping else suggest(headers, offered)
    unknown = [target for target in report.mapping.values() if target and target not in by_key]
    if unknown:
        raise Invalid(
            "The mapping is not valid.", {"mapping": f"There is no field {unknown[0]!r}."}
        )
    targets = [target for target in report.mapping.values() if target]
    doubled = {target for target in targets if targets.count(target) > 1}
    if doubled:
        label = by_key[sorted(doubled)[0]].label
        raise Invalid(
            "The mapping is not valid.", {"mapping": f"Two columns are mapped to {label}."}
        )
    if "name" not in targets:
        report.problem(1, "No column is mapped to Name. Every record needs a name.")
        return report
    choices = {c.vocab: _labels(session, c.vocab) for c in offered if c.vocab}
    seen: dict[str, int] = {}
    for number, raw in enumerate(reader, start=2):
        if not any((value or "").strip() for value in raw.values() if isinstance(value, str)):
            continue
        report.rows += 1
        if report.rows > MAX_ROWS:
            raise Invalid("The file is too large.", {"file": f"Import at most {MAX_ROWS} rows."})
        values: dict[str, Any] = {}
        owner_id: int | None = None
        ref = ""
        bad = False
        for header, target in report.mapping.items():
            cell = (raw.get(header) or "").strip()
            if not target or not cell:
                continue
            column = by_key[target]
            if target == "ref":
                ref = cell.upper()
            elif column.kind == "choice":
                key = choices[column.vocab or ""].get(_plain(cell))
                if key is None:
                    report.problem(number, f"{column.label}: {cell!r} is not one of the choices.")
                    bad = True
                else:
                    values[target] = key
            elif column.kind == "choices":
                found = []
                for part in filter(None, (p.strip() for p in re.split(r"[;|]", cell))):
                    key = choices[column.vocab or ""].get(_plain(part))
                    if key is None:
                        report.problem(
                            number, f"{column.label}: {part!r} is not one of the choices."
                        )
                        bad = True
                    else:
                        found.append(key)
                values[target] = found
            elif column.kind == "unit":
                unit = units.by_code(session, cell) or next(
                    (u for u in units.all_units(session) if u.name.lower() == cell.lower()), None
                )
                if unit is None:
                    report.problem(number, f"There is no unit called {cell}.")
                    bad = True
                else:
                    values["org_unit_id"] = unit.id
            elif column.kind == "vendor":
                vendor = session.scalars(
                    select(Vendor).where(
                        (Vendor.ref == cell.upper()) | (func.lower(Vendor.name) == cell.lower())
                    )
                ).first()
                if vendor is None:
                    report.problem(
                        number, f"There is no vendor called {cell}. Import vendors first."
                    )
                    bad = True
                else:
                    values["vendor"] = vendor.ref
            elif column.kind == "owner":
                account = accounts.by_email(session, accounts.normalize_email(cell))
                if account is None:
                    report.problem(number, f"There is no account for {cell}.")
                    bad = True
                else:
                    owner_id = account.id
            elif target == "trains_on_inputs":
                answer = {"y": "yes", "true": "yes", "n": "no", "false": "no"}.get(
                    cell.lower(), cell.lower()
                )
                if answer not in ("yes", "no", "unknown"):
                    report.problem(
                        number, f"Trains on inputs: write yes, no, or unknown, not {cell!r}."
                    )
                    bad = True
                else:
                    values["data_handling"] = {"trains_on_inputs": answer}
            elif target in ("contact_name", "contact_email"):
                values.setdefault("contacts", [{}])[0][target.removeprefix("contact_")] = cell
            else:
                values[target] = cell
        if not values.get("name") and not ref:
            report.problem(number, "This row has no name.")
            continue
        identity = ref or "|".join(
            str(values.get(key, "")).lower() for key in ("name", "edition", "version_label")
        )
        if identity in seen:
            report.problem(number, f"This is the same record as row {seen[identity]}.")
            continue
        seen[identity] = number
        if bad:
            continue
        try:
            with session.begin_nested():
                if ref:
                    from govwren.inventory.registry import find

                    record = find(session, record_type, ref)
                elif values.get("name"):
                    record = _existing(session, record_type, values)
                else:
                    record = None
                if record is None:
                    record = records.create(session, principal, record_type, values)
                    report.created += 1
                else:
                    before = record.version
                    records.update(
                        session, principal, record_type, record, values, version=record.version
                    )
                    if record.version == before:
                        report.unchanged += 1
                    else:
                        report.updated += 1
                if owner_id is not None and record_type is not VENDOR:
                    _own(session, principal, record_type, record, owner_id)
                report.refs.append(record.ref)
        except Invalid as exc:
            for key, message in (exc.errors or {"": str(exc)}).items():
                label = by_key[key].label if key in by_key else key
                report.problem(number, f"{label}: {message}" if label else message)
        except GovWrenError as exc:
            report.problem(number, str(exc))
    if not report.rows:
        report.problem(1, "The file has a header and no rows.")
    return report


def _own(
    session: Session, principal: Principal, record_type: RecordType, record: Any, owner_id: int
) -> None:
    """Make the named person the accountable owner, in place of whoever ran the import."""
    have = session.scalars(
        select(RecordOwner).where(
            RecordOwner.record_type == record_type.key, RecordOwner.record_id == record.id
        )
    ).all()
    if any(o.account_id == owner_id and o.kind == "accountable" for o in have):
        return
    keep = [
        {"account_id": o.account_id, "kind": o.kind}
        for o in have
        if o.kind != "accountable" and o.account_id != owner_id
    ]
    records.set_owners(
        session, principal, record_type, record,
        [{"account_id": owner_id, "kind": "accountable"}, *keep],
    )  # fmt: skip


# --- Export -------------------------------------------------------------------------------

EXPORT_LIMIT = 20_000


def _flat(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return "; ".join(str(_flat(item)) for item in value)
    if isinstance(value, dict):
        if "ref" in value and "name" in value:
            return f"{value['name']} ({value['ref']})"
        return "; ".join(f"{k}: {v}" for k, v in value.items() if v not in (None, ""))
    return value


def export_rows(
    session: Session, principal: Principal, record_type: RecordType, filters: Mapping[str, Any],
    *, sort: str = "name",
) -> list[dict[str, Any]]:  # fmt: skip
    """Every record that matches, each as flat fields, cut to what the person may see."""
    found, _total = records.search(
        session, principal, record_type, filters, sort=sort, limit=EXPORT_LIMIT
    )
    unit_names = {unit.id: unit.name for unit in units.all_units(session)}
    setting = access.visibility(session)
    out = []
    for record in found:
        seen = access.sight(session, principal, record_type, record, setting=setting)
        detail = records.detail(session, principal, record_type, record, sight=seen)
        row: dict[str, Any] = {"ref": detail["ref"], "name": detail["name"]}
        skip = {"type", "ref", "name", "sight", "can", "links", "references", "evidence",
                "completeness", "used_by", "used_by_hidden", "systems", "models", "agreements",
                "owners", "org_unit_id", "version", "card", "data_class_from",
                "contacts"}  # fmt: skip
        if "org_unit_id" in detail:
            row["unit"] = unit_names.get(detail["org_unit_id"], "")
        row["owners"] = "; ".join(
            f"{o['name']} <{o['email']}>" if o.get("email") else o["name"]
            for o in detail.get("owners", [])
            if o.get("kind", "accountable") == "accountable"
        )
        for key, value in detail.items():
            if key not in skip:
                row[key] = _flat(value)
        if record_type is USE_CASE:
            row["systems"] = "; ".join(s["ref"] for s in detail.get("systems", []))
        if "completeness" in detail:
            row["completeness"] = detail["completeness"]["score"]
        for entry in (detail.get("links") or {}).get("outgoing", []):
            key = entry["relation"]
            row[key] = "; ".join(filter(None, [row.get(key, ""), entry["record"]["ref"]]))
        out.append(row)
    return out


def note(what: str, filters: Mapping[str, Any], count: int) -> str:
    """One line that says what an export is and which filters produced it."""
    used = "; ".join(
        f"{key}={value}" for key, value in filters.items() if value not in (None, "", False)
    )
    return (
        f"GovWren export: {count} {what}, {utc_now():%Y-%m-%d %H:%M} UTC, filters: {used or 'none'}"
    )


def to_csv(rows: Sequence[Mapping[str, Any]], heading: str) -> str:
    """CSV with a first line, beginning ``#``, that records what the file is. GovWren's own
    import skips that line."""
    names: list[str] = []
    for row in rows:
        names += [key for key in row if key not in names]
    out = io.StringIO()
    out.write(f"# {heading}\r\n")
    writer = csv.DictWriter(out, fieldnames=names or ["ref", "name"], extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _safe(row.get(key, "")) for key in names})
    return out.getvalue()


def _safe(value: Any) -> Any:
    """A cell that a spreadsheet will not run as a formula."""
    text = str(value) if not isinstance(value, int | float) else value
    if isinstance(text, str) and text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text
