"""The dossier: everything the record holds about one thing, as one package (RPT-05).

A dossier is read from the same services the pages use, so it shows a person exactly what
they may see and nothing else. The package is a zip: the dossier as data and as a page to
print, every evidence file, and a manifest that lists each file with its SHA-256 and names
the event the history ended at when the package was made. ``check`` recomputes the lot.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections.abc import Iterator, Mapping
from html import escape
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren import __version__
from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import NotFound
from govwren.db.models import (
    ChainHead,
    Decision,
    Event,
    Incident,
    IncidentRecord,
    Review,
    StoredFile,
)
from govwren.events.chain import jsonable
from govwren.evidence import files
from govwren.inventory import access, history, records
from govwren.inventory.registry import USE_CASE, VENDOR, RecordType
from govwren.program import branding

FORMAT = "govwren-dossier/1"
MANIFEST = "manifest.json"
HISTORY_LIMIT = 5000
_FIXED = (2000, 1, 1, 0, 0, 0)  # the same bytes for the same contents, whenever it is made


def _answers(session: Session, principal: Principal, use_case: Any) -> dict[str, Any] | None:
    """What was answered on the request form, in the words of the form."""
    from govwren.intake import forms
    from govwren.intake import service as intake
    from govwren.program import vocab

    try:
        view = intake.view(session, principal, use_case)
    except NotFound:
        return None
    if view["state"] == "none":
        return None
    schema, answers = view["form"]["schema"], view["answers"]
    sections: dict[str, dict[str, Any]] = {}
    for section, question in forms.visible(schema, answers):
        value = answers.get(question["key"])
        if value in (None, "", []):
            continue
        labels = {o["key"]: o["label"] for o in question.get("options", [])}
        if question.get("vocabulary"):
            labels = vocab.labels(session, question["vocabulary"])
        if question["type"] == "unit":
            from govwren.db.models import OrgUnit

            unit = session.get(OrgUnit, value) if isinstance(value, int) else None
            shown: Any = unit.name if unit else value
        elif isinstance(value, list):
            shown = [labels.get(item, item) if isinstance(item, str) else item for item in value]
        elif isinstance(value, bool):
            shown = "Yes" if value else "No"
        else:
            shown = labels.get(value, value) if isinstance(value, str) else value
        sections.setdefault(section["key"], {"title": section["title"], "questions": []})[
            "questions"
        ].append({"key": question["key"], "label": question["label"], "answer": shown})
    return {
        "state": view["state"],
        "form_version": view["form"]["version"],
        "submitted_at": view["submitted_at"],
        "sections": list(sections.values()),
    }


def _reviews(session: Session, principal: Principal, use_case: Any) -> list[dict[str, Any]]:
    from govwren.review import service as review
    from govwren.review import views

    out = []
    rows = session.scalars(
        select(Review)
        .where(Review.subject_type == USE_CASE.key, Review.subject_id == use_case.id)
        .order_by(Review.id)
    ).all()
    conditions = review.conditions_of(session, use_case)
    for row in rows:
        internal = review.sees_internal(session, principal, row)
        tasks = review.tasks_of(session, row)
        decisions = session.scalars(
            select(Decision).where(Decision.review_id == row.id).order_by(Decision.id)
        ).all()
        names = views._names(
            session,
            {d.decided_by for d in decisions}
            | {t.completed_by for t in tasks}
            | {c.owner_id for c in conditions},
        )
        ids = {d.id for d in decisions}
        out.append(
            {
                "ref": row.ref,
                "kind": row.kind,
                "status": row.status,
                "tier": row.tier_at_open,
                "authority": row.authority,
                "opened_at": row.opened_at,
                "closed_at": row.closed_at,
                "tasks": [
                    {
                        "function": task.review_function,
                        "status": task.status,
                        "finding": task.finding if internal else None,
                        "notes": task.notes if internal else None,
                        "completed_by": names.get(task.completed_by or 0),
                        "completed_at": task.completed_at,
                    }
                    for task in tasks
                ],
                "decisions": [views.decision_view(d, names) for d in decisions],
                "conditions": [
                    views.condition_view(c, names) for c in conditions if c.decision_id in ids
                ],
            }
        )
    return out


def _incidents(
    session: Session, principal: Principal, record_type: RecordType, record: Any
) -> list[dict[str, Any]]:
    from govwren.oversight import incidents

    rows = [
        incident
        for incident in session.scalars(
            select(Incident)
            .join(IncidentRecord, IncidentRecord.incident_id == Incident.id)
            .where(
                IncidentRecord.subject_type == record_type.key,
                IncidentRecord.subject_id == record.id,
            )
            .order_by(Incident.id)
        )
        if incidents.can_see(session, principal, incident)
    ]
    names = incidents._names(session, rows)
    return [incidents._summary(incident, names) for incident in rows]


def _assessments(
    session: Session, principal: Principal, record_type: RecordType, record: Any
) -> list[dict[str, Any]]:
    from govwren.assurance import assessments

    out = []
    for key, form in assessments.templates().items():
        if form["subject"] != record_type.key:
            continue
        try:
            view = assessments.view(session, principal, record_type, record, key)
        except NotFound:
            continue
        if view["status"] == "missing":
            continue
        answers = view["answers"]
        out.append(
            {
                "key": key,
                "title": view["template"]["title"],
                "status": view["status"],
                "submitted_by": view["submitted_by"],
                "submitted_at": view["submitted_at"],
                "reviewed_by": view["reviewed_by"],
                "reviewed_at": view["reviewed_at"],
                "review_note": view["review_note"],
                "sections": [
                    {
                        "title": section["title"],
                        "questions": [
                            {"label": q["label"], "answer": answers[q["key"]]}
                            for q in section["questions"]
                            if answers.get(q["key"]) not in (None, "", [])
                        ],
                    }
                    for section in view["template"]["sections"]
                ],
            }
        )
    return out


def _evidence_in(node: Any) -> Iterator[dict[str, Any]]:
    """Every piece of evidence mentioned anywhere in the dossier."""
    if isinstance(node, Mapping):
        if str(node.get("ref", "")).startswith("EV-") and "file" in node:
            yield dict(node)
        for value in node.values():
            yield from _evidence_in(value)
    elif isinstance(node, list):
        for value in node:
            yield from _evidence_in(value)


def build(
    session: Session, principal: Principal, record_type: RecordType, record: Any
) -> dict[str, Any]:
    """The dossier of one record, for someone who may see the whole of it."""
    from govwren.assurance import controls, risks
    from govwren.oversight import exceptions, findings

    if access.sight(session, principal, record_type, record) != access.FULL:
        raise NotFound(f"There is no {record_type.label} {record.ref}.")
    internal = principal.reads_all
    reviews: list[dict[str, Any]] = []
    answers = None
    conditions: list[dict[str, Any]] = []
    if record_type is USE_CASE:
        from govwren.evidence import service as evidence
        from govwren.review import service as review
        from govwren.review import views

        latest = review.latest_review(session, record)
        if latest is not None:
            internal = review.sees_internal(session, principal, latest)
        reviews = _reviews(session, principal, record)
        answers = _answers(session, principal, record)
        rows = review.conditions_of(session, record)
        names = views._names(session, {c.owner_id for c in rows})
        conditions = [
            {
                **views.condition_view(c, names),
                "evidence": evidence.for_subject(session, principal, "condition", c.id),
            }
            for c in rows
        ]
    head = session.execute(select(ChainHead.seq, ChainHead.hash)).one()
    brand = branding.load(session)
    past = history.for_record(
        session, record_type, record, limit=HISTORY_LIMIT, internal=internal, principal=principal
    )
    detail = records.detail(session, principal, record_type, record)
    detail.pop("can", None)
    document: dict[str, Any] = {
        "format": FORMAT,
        "generated_at": utc_now(),
        "generated_by": principal.name,
        "product": {"name": brand.product_name, "version": __version__},
        "organization": brand.organization_name,
        "history_head": {"events": head.seq, "hash": head.hash},
        "record": detail,
        "answers": answers,
        "reviews": reviews,
        "conditions": conditions,
        "findings": findings.for_record(session, principal, record_type, record),
        "risks": []
        if record_type is VENDOR
        else risks.register(session, principal, status="all", record=(record_type, record))[
            "risks"
        ],
        "controls": []
        if record_type is VENDOR
        else controls.for_record(session, principal, record_type, record),
        "exceptions": []
        if record_type is VENDOR
        else exceptions.register(session, principal, record=(record_type, record)),
        "incidents": _incidents(session, principal, record_type, record),
        "assessments": _assessments(session, principal, record_type, record),
        "history": list(reversed(past)),
    }
    document = jsonable(document)
    seen: dict[str, dict[str, Any]] = {}
    for item in _evidence_in(document):
        seen.setdefault(item["ref"], item)
    document["evidence"] = [
        {
            key: item.get(key)
            for key in (
                "ref",
                "title",
                "kind",
                "description",
                "url",
                "file",
                "dated_on",
                "expires_on",
                "state",
            )
        }
        for item in sorted(seen.values(), key=lambda e: e["ref"])
    ]
    return document


# --- The package ---


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _seal(entries: list[dict[str, Any]], head: Mapping[str, Any]) -> str:
    """One hash over the list of files and the place in the history."""
    lines = [f"{entry['sha256']}  {entry['path']}" for entry in entries]
    lines.append(f"{head['hash']}  history:{head['events']}")
    return _digest("\n".join(lines).encode())


def package(session: Session, files_dir: Path, document: Mapping[str, Any]) -> bytes:
    """The dossier as a zip with a manifest. The same dossier always gives the same bytes."""
    members: dict[str, bytes] = {
        "dossier.json": json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False).encode(),
        "dossier.html": page(document).encode(),
    }
    missing = []
    for item in document["evidence"]:
        if not item.get("file"):
            continue
        stored = session.scalars(
            select(StoredFile).where(StoredFile.sha256 == item["file"]["sha256"])
        ).first()
        name = f"evidence/{item['ref']}-{files.clean_name(item['file']['name'] or 'file')}"
        try:
            if stored is None:
                raise FileNotFoundError(name)
            members[name] = files.read(files_dir, stored)
        except OSError:
            missing.append({"path": name, "sha256": item["file"]["sha256"]})
    entries = [
        {"path": path, "sha256": _digest(data), "size": len(data)}
        for path, data in sorted(members.items())
    ]
    head = document["history_head"]
    manifest = {
        "format": FORMAT,
        "record": document["record"]["ref"],
        "generated_at": document["generated_at"],
        "generated_by": document["generated_by"],
        "history_head": head,
        "files": entries,
        "missing": missing,
        "seal": _seal(entries, head),
    }
    members[MANIFEST] = json.dumps(manifest, indent=2, sort_keys=True).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, data in sorted(members.items()):
            info = zipfile.ZipInfo(path, _FIXED)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return out.getvalue()


def check(data: bytes, session: Session | None = None) -> tuple[bool, list[str]]:
    """Whether a package is whole: every file matches the manifest, nothing is added or
    missing, and the seal holds. With a session, also whether the place in the history that
    the manifest names is in this installation's history."""
    lines: list[str] = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        manifest = json.loads(archive.read(MANIFEST))
        entries = manifest["files"]
        head = manifest["history_head"]
        listed = {entry["path"]: entry for entry in entries}
    except (zipfile.BadZipFile, KeyError, ValueError, TypeError):
        return False, ["This is not a dossier package: it has no manifest that can be read."]
    ok = True
    present = {name for name in archive.namelist() if name != MANIFEST}
    for path in sorted(present - set(listed)):
        ok = False
        lines.append(f"{path} is in the package but not in the manifest.")
    for path, entry in sorted(listed.items()):
        if path not in present:
            ok = False
            lines.append(f"{path} is in the manifest but not in the package.")
        elif _digest(archive.read(path)) != entry["sha256"]:
            ok = False
            lines.append(f"{path} has been altered.")
    if _seal(entries, head) != manifest.get("seal"):
        ok = False
        lines.append("The manifest has been altered: its seal does not hold.")
    if ok:
        lines.append(f"{len(entries)} files match the manifest, and its seal holds.")
    for gone in manifest.get("missing", []):
        lines.append(f"{gone['path']} was not in the file store when the package was made.")
    if session is not None and ok:
        found = session.scalars(select(Event.hash).where(Event.id == head["events"])).first()
        if found == head["hash"]:
            lines.append(f"Event {head['events']} of this installation's history matches.")
        else:
            ok = False
            lines.append(
                f"Event {head['events']} of this installation's history does not match the "
                "package: it was made elsewhere, or the history has changed."
            )
    return ok, lines


# --- The page to print ---

_STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z")
_KEY = re.compile(r"[a-z]+(_[a-z0-9]+)*")

_STYLE = """
body{font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:#1b1f23;margin:2rem auto;
max-width:52rem;padding:0 1.25rem}h1{font-size:1.7rem;margin:.2rem 0}h2{font-size:1.15rem;
margin:2rem 0 .5rem;border-bottom:1px solid #c9ced3;padding-bottom:.25rem}h3{font-size:1rem;
margin:1.2rem 0 .3rem}table{border-collapse:collapse;width:100%;margin:.4rem 0}
th,td{text-align:left;
vertical-align:top;padding:.3rem .6rem .3rem 0;border-bottom:1px solid #e3e6e9}th{font-weight:600;
width:14rem}.wide th{width:auto}.muted{color:#55606b}.eyebrow{text-transform:uppercase;
letter-spacing:.06em;font-size:.8rem;color:#55606b}code{font-size:.85em;word-break:break-all}
@media print{body{margin:0;max-width:none}h2{break-after:avoid}tr{break-inside:avoid}}
"""


def _text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(filter(None, (_text(item) for item in value)))
    if isinstance(value, Mapping):
        for key in ("name", "label", "title", "ref"):
            if value.get(key):
                return str(value[key])
        return "; ".join(f"{_words(k)}: {_text(v)}" for k, v in value.items() if _text(v))
    text = str(value)
    if _STAMP.fullmatch(text):
        return f"{text[:10]} {text[11:16]} UTC"
    return _words(text) if _KEY.fullmatch(text) else text


def _words(key: str) -> str:
    return key.replace("_", " ").capitalize()


def _pairs(pairs: list[tuple[str, Any]]) -> str:
    rows = [
        f"<tr><th scope='row'>{escape(label)}</th><td>{escape(_text(value))}</td></tr>"
        for label, value in pairs
        if _text(value)
    ]
    return f"<table>{''.join(rows)}</table>" if rows else ""


def _table(headings: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th scope='col'>{escape(h)}</th>" for h in headings)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(_text(cell))}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table class='wide'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _section(title: str, body: str) -> str:
    return f"<section><h2>{escape(title)}</h2>{body}</section>" if body else ""


_SKIP = {
    "type", "ref", "name", "sight", "evidence", "links", "references", "completeness", "version",
    "org_unit_id", "orphaned", "merged_into", "used_by_hidden", "agent_profile", "agreements",
    "systems",
}  # fmt: skip


def page(document: Mapping[str, Any]) -> str:
    """The dossier as one page that needs nothing else to be read or printed."""
    record = document["record"]
    parts = [
        _section(
            "The record",
            _pairs([(_words(k), v) for k, v in record.items() if k not in _SKIP])
            + (
                "<h3>Agent profile</h3>"
                + _pairs([(_words(k), v) for k, v in record["agent_profile"].items()])
                if record.get("agent_profile")
                else ""
            ),
        )
    ]
    answers = document.get("answers")
    if answers:
        parts.append(
            _section(
                f"Answers on the request form, version {answers['form_version']}",
                "".join(
                    f"<h3>{escape(s['title'])}</h3>"
                    + _pairs([(q["label"], q["answer"]) for q in s["questions"]])
                    for s in answers["sections"]
                ),
            )
        )
    reviews = ""
    for review in document["reviews"]:
        reviews += f"<h3>{escape(review['ref'])}: {escape(_words(review['kind']))} review</h3>"
        reviews += _pairs(
            [
                ("Status", _words(review["status"])),
                ("Opened", review["opened_at"]),
                ("Closed", review["closed_at"]),
                ("Decided by", _words(review["authority"])),
            ]
        )
        if review["tasks"]:
            reviews += _table(
                ["Review function", "Status", "Finding", "By", "Notes"],
                [
                    [
                        _words(t["function"]),
                        _words(t["status"]),
                        _words(t["finding"] or ""),
                        t["completed_by"],
                        t["notes"],
                    ]
                    for t in review["tasks"]
                ],
            )
        for decision in review["decisions"]:
            reviews += _pairs(
                [
                    ("Decision", _words(decision["outcome"])),
                    ("Reason", decision["rationale"]),
                    ("By", decision["by_rule"] or decision["decided_by"]),
                    ("On", decision["decided_at"]),
                    ("Approved until", decision["approved_until"]),
                ]
            )
    parts.append(_section("Reviews and decisions", reviews))
    if document["conditions"]:
        parts.append(
            _section(
                "Conditions",
                _table(
                    ["Condition", "Owner", "Due", "Status", "Evidence"],
                    [
                        [
                            c["text"],
                            c["owner"],
                            c["due_on"],
                            _words(c["status"]),
                            [e["ref"] for e in c["evidence"]],
                        ]
                        for c in document["conditions"]
                    ],
                ),
            )
        )
    found = document["findings"]
    listed = [*found.get("own", []), *found.get("inherited", [])]
    if listed:
        parts.append(
            _section(
                "Findings, its own and inherited",
                _table(
                    ["Finding", "From"],
                    [[f.get("text") or f.get("title"), f.get("from") or ""] for f in listed],
                ),
            )
        )
    if document["risks"]:
        parts.append(
            _section(
                "Risks",
                _table(
                    ["Risk", "Statement", "Level", "Status", "Owner"],
                    [
                        [
                            r["ref"],
                            r.get("title") or r.get("statement"),
                            _words(r["level"]),
                            _words(r["status"]),
                            r.get("owner"),
                        ]
                        for r in document["risks"]
                    ],
                ),
            )
        )
    if document["controls"]:
        parts.append(
            _section(
                "Controls that apply",
                _table(
                    ["Control", "Standing", "Owner", "Next check"],
                    [
                        [c["title"], c["status_label"], c.get("owner"), c.get("next_check_on")]
                        for c in document["controls"]
                    ],
                ),
            )
        )
    if document["exceptions"]:
        parts.append(
            _section(
                "Exceptions",
                _table(
                    ["Exception", "Title", "Status", "Ends"],
                    [
                        [e["ref"], e["title"], _words(e["status"]), e.get("ends_on")]
                        for e in document["exceptions"]
                    ],
                ),
            )
        )
    if document["incidents"]:
        parts.append(
            _section(
                "Incidents",
                _table(
                    ["Incident", "Title", "Severity", "Status", "Reported"],
                    [
                        [
                            i["ref"],
                            i["title"],
                            _words(i["severity"] or ""),
                            _words(i["status"]),
                            i["reported_at"],
                        ]
                        for i in document["incidents"]
                    ],
                ),
            )
        )
    for assessment in document["assessments"]:
        parts.append(
            _section(
                f"{assessment['title']} ({_words(assessment['status']).lower()})",
                _pairs(
                    [
                        ("Submitted by", assessment["submitted_by"]),
                        ("Reviewed by", assessment["reviewed_by"]),
                        ("Note", assessment["review_note"]),
                    ]
                )
                + "".join(
                    f"<h3>{escape(s['title'])}</h3>"
                    + _pairs([(q["label"], q["answer"]) for q in s["questions"]])
                    for s in assessment["sections"]
                    if s["questions"]
                ),
            )
        )
    links = record.get("links") or {}
    rows = [
        [link["label"], link["record"]["ref"], link["record"]["name"]]
        for link in links.get("outgoing", [])
    ] + [
        [f"{link['label']} (from)", link["record"]["ref"], link["record"]["name"]]
        for link in links.get("incoming", [])
    ]
    for system in record.get("systems") or []:
        rows.append(["Uses", system["ref"], system["name"]])
    if rows:
        parts.append(_section("Connections", _table(["Relation", "Record", "Name"], rows)))
    if document["evidence"]:
        parts.append(
            _section(
                "Evidence",
                _table(
                    ["Evidence", "Title", "Dated", "Good until", "File and SHA-256"],
                    [
                        [
                            e["ref"],
                            e["title"],
                            e["dated_on"],
                            e["expires_on"],
                            f"{e['file']['name']} {e['file']['sha256']}"
                            if e.get("file")
                            else e.get("url"),
                        ]
                        for e in document["evidence"]
                    ],
                ),
            )
        )
    parts.append(
        _section(
            "History, oldest first",
            _table(
                ["When", "Who", "What"],
                [
                    [
                        e["at"],
                        e["actor"],
                        ". ".join(
                            [
                                e["title"],
                                *(
                                    f"{line['label']}: {_text(line['after'])}"
                                    for line in e["lines"]
                                ),
                            ]
                        ),
                    ]
                    for e in document["history"]
                ],
            ),
        )
    )
    head = document["history_head"]
    title = f"{record['name']} · {record['ref']}"
    organization = document.get("organization") or document["product"]["name"]
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{escape(title)}</title><style>{_STYLE}</style></head><body><main>"
        f"<p class='eyebrow'>{escape(organization)} · Dossier</p><h1>{escape(record['name'])}</h1>"
        f"<p class='muted'>{escape(record['ref'])}. Made {escape(document['generated_at'])} by "
        f"{escape(document['generated_by'])} with {escape(document['product']['name'])} "
        f"{escape(document['product']['version'])}. The history stood at event {head['events']}, "
        f"<code>{escape(head['hash'])}</code>.</p>{''.join(parts)}</main></body></html>"
    )
