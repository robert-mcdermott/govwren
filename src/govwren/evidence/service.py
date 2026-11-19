"""Evidence items: what each is, who looks after it, how long it is good for, and what it
supports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import today, utc_now
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.db.models import (
    Account,
    Agreement,
    Condition,
    Evidence,
    EvidenceLink,
    Review,
    ReviewTask,
    StoredFile,
    UseCase,
    Vendor,
)
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import TYPES, USE_CASE, VENDOR, find_any
from govwren.program import vocab

SOON = 60  # days: evidence that expires within this is worth renewing
OTHER_SUBJECTS = {"condition": Condition, "review_task": ReviewTask, "agreement": Agreement}


def state(evidence: Evidence, on: date | None = None) -> str:
    on = on or today()
    if evidence.status == "withdrawn":
        return "withdrawn"
    if evidence.expires_on is None:
        return "current"
    if evidence.expires_on < on:
        return "expired"
    return "expiring" if evidence.expires_on <= on + timedelta(days=SOON) else "current"


def _date(value: Any, field: str, errors: dict[str, str]) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        errors[field] = "Give the date as year-month-day."
        return None


# --- What evidence supports ---------------------------------------------------------------


def _resolve(session: Session, subject: str) -> tuple[str, Any]:
    """A subject named as a reference (``UC-0012``) or as ``kind:id`` (``condition:7``)."""
    text = str(subject).strip()
    if ":" in text:
        kind, _, number = text.partition(":")
        model = OTHER_SUBJECTS.get(kind)
        found = session.get(model, int(number)) if model and number.isdigit() else None
        if found is None:
            raise NotFound(f"There is no {kind.replace('_', ' ')} {number}.")
        return kind, found
    record_type, record = find_any(session, text)
    return record_type.key, record


def _review_of(session: Session, task: ReviewTask) -> Review | None:
    return session.get(Review, task.review_id)


def _sees(session: Session, principal: Principal, kind: str, subject: Any) -> bool:
    """Whether the person may see evidence attached to this."""
    if principal.reads_all:
        return True
    if kind in TYPES:
        return access.sight(session, principal, TYPES[kind], subject) == access.FULL
    if kind == "condition":
        use_case = session.get(UseCase, subject.subject_id)
        return (
            use_case is not None
            and access.sight(session, principal, USE_CASE, use_case) == access.FULL
        )
    if kind == "review_task":
        from govwren.review import service as review

        found = _review_of(session, subject)
        return found is not None and review.sees_internal(session, principal, found)
    if kind == "agreement":
        vendor = session.get(Vendor, subject.vendor_id)
        return vendor is not None and bool(access.sight(session, principal, VENDOR, vendor))
    return False


def _may_attach(session: Session, principal: Principal, kind: str, subject: Any) -> bool:
    if principal.edits_all:
        return True
    if kind in TYPES:
        return access.can_edit(session, principal, TYPES[kind], subject)
    if kind == "condition":
        use_case = session.get(UseCase, subject.subject_id)
        return use_case is not None and access.can_edit(session, principal, USE_CASE, use_case)
    if kind == "review_task":
        return principal.reviews and _sees(session, principal, kind, subject)
    if kind == "agreement":
        vendor = session.get(Vendor, subject.vendor_id)
        return vendor is not None and access.can_edit(session, principal, VENDOR, vendor)
    return False


def _subject_view(session: Session, kind: str, subject: Any) -> dict[str, Any]:
    if kind in TYPES:
        return {"type": kind, "ref": subject.ref, "name": subject.name}
    if kind == "condition":
        use_case = session.get(UseCase, subject.subject_id)
        return {"type": kind, "id": subject.id, "name": subject.text[:120],
                "ref": use_case.ref if use_case else None}  # fmt: skip
    if kind == "review_task":
        found = _review_of(session, subject)
        label = vocab.labels(session, "review_functions").get(subject.review_function, "")
        return {"type": kind, "id": subject.id, "name": f"{label} review",
                "ref": found.ref if found else None}  # fmt: skip
    vendor = session.get(Vendor, subject.vendor_id)
    return {"type": kind, "id": subject.id, "name": subject.title,
            "ref": vendor.ref if vendor else None}  # fmt: skip


def _links(session: Session, evidence: Evidence) -> list[tuple[str, Any]]:
    out = []
    for link in session.scalars(
        select(EvidenceLink)
        .where(EvidenceLink.evidence_id == evidence.id)
        .order_by(EvidenceLink.id)
    ):
        model = (
            TYPES[link.subject_type].model
            if link.subject_type in TYPES
            else OTHER_SUBJECTS.get(link.subject_type)
        )
        found = session.get(model, link.subject_id) if model else None
        if found is not None:
            out.append((link.subject_type, found))
    return out


def can_see(session: Session, principal: Principal, evidence: Evidence) -> bool:
    if principal.reads_all or principal.account_id in (evidence.owner_id, evidence.created_by):
        return True
    return any(
        _sees(session, principal, kind, subject) for kind, subject in _links(session, evidence)
    )


def can_edit(principal: Principal, evidence: Evidence) -> bool:
    return principal.edits_all or (
        principal.account_id is not None
        and principal.account_id in (evidence.owner_id, evidence.created_by)
    )


# --- Showing ------------------------------------------------------------------------------


def view(session: Session, principal: Principal, evidence: Evidence) -> dict[str, Any]:
    owner = session.get(Account, evidence.owner_id) if evidence.owner_id else None
    stored = session.get(StoredFile, evidence.file_id) if evidence.file_id else None
    on = today()
    return {
        "ref": evidence.ref,
        "title": evidence.title,
        "kind": evidence.kind,
        "description": evidence.description,
        "url": evidence.url,
        "file": {
            "name": evidence.file_name,
            "size": stored.size,
            "media_type": stored.media_type,
            "sha256": stored.sha256,
            "href": f"/api/v1/evidence/{evidence.ref}/file",
        }
        if stored
        else None,
        "owner": {"id": owner.id, "name": owner.display_name} if owner else None,
        "dated_on": evidence.dated_on,
        "expires_on": evidence.expires_on,
        "days_left": (evidence.expires_on - on).days if evidence.expires_on else None,
        "state": state(evidence, on),
        "created_at": evidence.created_at,
        "supports": [
            _subject_view(session, kind, subject)
            for kind, subject in _links(session, evidence)
            if _sees(session, principal, kind, subject)
        ],
        "can": {"edit": can_edit(principal, evidence)},
    }


def find(session: Session, principal: Principal, ref: str) -> Evidence:
    evidence = session.scalars(select(Evidence).where(Evidence.ref == ref.strip().upper())).first()
    if evidence is None or not can_see(session, principal, evidence):
        raise NotFound(f"There is no evidence {ref}.")
    return evidence


def for_subject(
    session: Session, principal: Principal, kind: str, subject_id: int
) -> list[dict[str, Any]]:
    """The evidence attached to one thing. The caller has decided the person may see it."""
    rows = session.scalars(
        select(Evidence)
        .join(EvidenceLink, EvidenceLink.evidence_id == Evidence.id)
        .where(EvidenceLink.subject_type == kind, EvidenceLink.subject_id == subject_id)
        .order_by(Evidence.id.desc())
    )
    return [view(session, principal, row) for row in rows]


def search(
    session: Session, principal: Principal, filters: Mapping[str, Any], *, limit: int = 50,
    offset: int = 0,
) -> tuple[list[Evidence], int]:  # fmt: skip
    """Evidence the person may list: all of it for those who read everything, and otherwise
    what they own or added."""
    conditions = []
    if not principal.reads_all:
        me = principal.account_id
        conditions.append(or_(Evidence.owner_id == me, Evidence.created_by == me))
    text = str(filters.get("q") or "").strip().lower()
    if text:
        like = f"%{text}%"
        conditions.append(
            or_(
                func.lower(Evidence.title).like(like),
                func.lower(Evidence.ref).like(like),
                func.lower(func.coalesce(Evidence.file_name, "")).like(like),
            )
        )
    if filters.get("kind"):
        conditions.append(Evidence.kind == filters["kind"])
    on = today()
    wanted = filters.get("state")
    if wanted == "withdrawn":
        conditions.append(Evidence.status == "withdrawn")
    elif wanted in ("expired", "expiring", "current"):
        conditions.append(Evidence.status == "current")
        soon = on + timedelta(days=SOON)
        if wanted == "expired":
            conditions.append(Evidence.expires_on < on)
        elif wanted == "expiring":
            conditions += [Evidence.expires_on >= on, Evidence.expires_on <= soon]
        else:
            conditions.append(or_(Evidence.expires_on.is_(None), Evidence.expires_on > soon))
    total = session.execute(
        select(func.count()).select_from(Evidence).where(*conditions)
    ).scalar_one()
    rows = list(
        session.scalars(
            select(Evidence)
            .where(*conditions)
            .order_by(Evidence.expires_on.is_(None), Evidence.expires_on, Evidence.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return rows, total


def needing_attention(session: Session) -> int:
    """How many current evidence items have expired or expire soon."""
    soon = today() + timedelta(days=SOON)
    return session.execute(
        select(func.count())
        .select_from(Evidence)
        .where(Evidence.status == "current", Evidence.expires_on <= soon)
    ).scalar_one()


# --- Changing -----------------------------------------------------------------------------


def _apply(
    session: Session, evidence: Evidence, values: Mapping[str, Any], creating: bool
) -> dict[str, str]:
    errors: dict[str, str] = {}
    if "title" in values or creating:
        title = str(values.get("title") or "").strip()
        if not title or len(title) > 200:
            errors["title"] = "Give it a title of up to 200 characters."
        else:
            evidence.title = title
    if "kind" in values or creating:
        if values.get("kind") not in vocab.keys(session, "evidence_kinds"):
            errors["kind"] = "Choose what kind of evidence it is."
        else:
            evidence.kind = values["kind"]
    if "description" in values:
        evidence.description = str(values["description"] or "").strip() or None
    if "url" in values:
        url = str(values["url"] or "").strip()
        if url and (not url.lower().startswith(("https://", "http://")) or len(url) > 300):
            errors["url"] = "Give an address of up to 300 characters that starts with https://"
        else:
            evidence.url = url or None
    if "file_id" in values and values["file_id"] is not None:
        stored = session.get(StoredFile, int(values["file_id"]))
        if stored is None:
            errors["file"] = "Send the file again."
        else:
            from govwren.evidence.files import clean_name

            evidence.file_id, evidence.file_sha256 = stored.id, stored.sha256
            evidence.file_name = clean_name(str(values.get("file_name") or evidence.title))
    if "owner_id" in values:
        owner = values["owner_id"]
        if owner in (None, ""):
            evidence.owner_id = None
        elif session.get(Account, int(owner)) is None:
            errors["owner_id"] = "Choose a person."
        else:
            evidence.owner_id = int(owner)
    if "dated_on" in values:
        evidence.dated_on = _date(values["dated_on"], "dated_on", errors)
    if "expires_on" in values:
        evidence.expires_on = _date(values["expires_on"], "expires_on", errors)
    if "status" in values:
        if values["status"] not in ("current", "withdrawn"):
            errors["status"] = "Evidence is current or withdrawn."
        else:
            evidence.status = values["status"]
    if evidence.dated_on and evidence.expires_on and evidence.expires_on < evidence.dated_on:
        errors["expires_on"] = "It cannot stop being good before its own date."
    if not errors and not (evidence.file_id or evidence.url or evidence.description):
        errors["file"] = "Attach a file, give an address, or write a note."
    return errors


def _attach(
    session: Session, principal: Principal, evidence: Evidence, subjects: Sequence[str]
) -> None:
    have = {
        (link.subject_type, link.subject_id)
        for link in session.scalars(
            select(EvidenceLink).where(EvidenceLink.evidence_id == evidence.id)
        )
    }
    for subject in subjects:
        kind, found = _resolve(session, subject)
        if not _may_attach(session, principal, kind, found):
            raise PermissionDenied("You cannot attach evidence to that.")
        if (kind, found.id) not in have:
            session.add(
                EvidenceLink(evidence_id=evidence.id, subject_type=kind, subject_id=found.id)
            )
            have.add((kind, found.id))
    session.flush()


def create(session: Session, principal: Principal, values: Mapping[str, Any]) -> Evidence:
    subjects = list(values.get("supports") or [])
    if not subjects:
        raise Invalid("The evidence was not saved.", {"supports": "Say what it supports."})
    evidence = Evidence(status="current", created_by=principal.account_id, created_at=utc_now())
    evidence.owner_id = principal.account_id
    with session.no_autoflush:
        errors = _apply(session, evidence, values, True)
    if errors:
        raise Invalid("The evidence was not saved.", errors)
    with audit.operation(session, "evidence.add"):
        evidence.ref = next_ref(session, "EV")
        session.add(evidence)
        session.flush()
        _attach(session, principal, evidence, subjects)
    return evidence


def update(
    session: Session, principal: Principal, evidence: Evidence, values: Mapping[str, Any]
) -> Evidence:
    if not can_edit(principal, evidence):
        raise PermissionDenied("Only its owner or governance can change this evidence.")
    with audit.operation(session, "evidence.edit"):
        with session.no_autoflush:
            errors = _apply(session, evidence, values, False)
        if errors:
            session.expire(evidence)
            raise Invalid("The evidence was not saved.", errors)
        session.flush()
        if values.get("supports"):
            _attach(session, principal, evidence, list(values["supports"]))
    return evidence
