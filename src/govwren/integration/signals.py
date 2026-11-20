"""Signals: another tool pushes a result onto a record, and it is kept as evidence.

An evaluation harness, a monitoring service, or a scanner knows something GovWren does not:
that a model passed its tests last night, or that drift was seen this week. GovWren never
goes to fetch that. The other tool sends a short summary, with a token that can do nothing
else, and it becomes a piece of evidence on the record, dated and attributed, that people
see where they already look. A result that is not a pass is brought to the owners' notice.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import today, utc_now
from govwren.core.errors import Invalid, NotFound
from govwren.db.models import Evidence, EvidenceLink
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.inventory import access, records
from govwren.inventory.registry import VENDOR, find_any

RESULTS = {"pass": "Passed", "warn": "Needs a look", "fail": "Failed", "info": "For information"}
KINDS = {
    "evaluation": ("test_result", "Evaluation"),
    "monitoring": ("record", "Monitoring"),
    "scan": ("assessment", "Scan"),
    "other": ("other", "Signal"),
}


def push(
    session: Session, principal: Principal, values: dict[str, Any], *, anywhere: bool = False
) -> dict[str, Any]:
    """Keep a signal as evidence on the record it names. A sender who reads everything may
    push ``anywhere``. Anyone else may push only onto a record they see in full, and a record
    they may not push onto is answered exactly as one that does not exist."""
    errors: dict[str, str] = {}
    title = str(values.get("title") or "").strip()
    if not title or len(title) > 160:
        errors["title"] = "Give the result a title of up to 160 characters."
    source = str(values.get("source") or "").strip()
    if not source or len(source) > 80:
        errors["source"] = "Say which tool this comes from, in up to 80 characters."
    result = values.get("result") or "info"
    if result not in RESULTS:
        errors["result"] = f"Use one of: {', '.join(RESULTS)}."
    kind = values.get("kind") or "other"
    if kind not in KINDS:
        errors["kind"] = f"Use one of: {', '.join(KINDS)}."
    summary = str(values.get("summary") or "").strip()
    if len(summary) > 4000:
        errors["summary"] = "Keep the summary to 4,000 characters."
    url = str(values.get("url") or "").strip()
    if url and (not url.lower().startswith("https://") or len(url) > 300):
        errors["url"] = "Give an address of up to 300 characters that starts with https://."
    days: dict[str, date | None] = {"dated_on": today(), "good_until": None}
    for field in days:
        if values.get(field):
            try:
                days[field] = date.fromisoformat(str(values[field]))
            except ValueError:
                errors[field] = "Give a date as year-month-day."
    record_type = record = None
    try:
        record_type, record = find_any(session, str(values.get("ref") or ""))
        if not anywhere and access.sight(session, principal, record_type, record) != access.FULL:
            raise NotFound("not theirs to see")
    except NotFound:
        errors["ref"] = "There is no record with that reference."
    if errors:
        raise Invalid("The signal was not kept.", errors)
    assert record_type is not None and record is not None
    evidence_kind, word = KINDS[str(kind)]
    lines = [f"{word} from {source}: {RESULTS[str(result)].lower()}."]
    if summary:
        lines += ["", summary]
    with audit.operation(session, "signal.push", source=source, result=result):
        evidence = Evidence(
            ref=next_ref(session, "EV"),
            title=f"{title} ({RESULTS[str(result)].lower()})",
            kind=evidence_kind,
            description="\n".join(lines),
            url=url or None,
            dated_on=days["dated_on"],
            expires_on=days["good_until"],
            status="current",
            owner_id=None,
            created_by=principal.account_id,
            created_at=utc_now(),
        )
        session.add(evidence)
        session.flush()
        session.add(
            EvidenceLink(
                evidence_id=evidence.id, subject_type=record_type.key, subject_id=record.id
            )
        )
        session.flush()
        told = 0
        if result in ("warn", "fail") and record_type is not VENDOR:
            from govwren.review import service as review

            owners = records.owners_of(session, record_type, [record.id]).get(record.id, [])
            ids = {owner["account_id"] for owner in owners if owner["active"]}
            review.notify(
                session,
                ids,
                "signal",
                f"{source} reports on {record.name}: {RESULTS[str(result)].lower()}. {title}",
                f"/{record_type.path}/{record.ref}",
            )
            told = len(ids)
    return {"evidence": evidence.ref, "record": record.ref, "owners_told": told}
