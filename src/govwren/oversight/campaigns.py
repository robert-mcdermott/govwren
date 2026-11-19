"""Attestation campaigns: the people closest to the work say whether the record is still true.

There are two kinds. In an owner confirmation, each record's owners say it is unchanged, has
changed, or is no longer in use. In a unit completeness campaign, a unit's steward looks at
the unit's list, adds what is missing, and attests that it is complete.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from govwren.access import roles
from govwren.access.principal import Principal
from govwren.core.clock import today, utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import Account, Attestation, Campaign, OrgUnit, RecordOwner, Reminder
from govwren.db.models.oversight import CAMPAIGN_KINDS
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import DATASET, MODEL, SYSTEM, TYPES, USE_CASE, RecordType
from govwren.oversight import retirement
from govwren.people import units
from govwren.review import service as review

CONFIRMABLE = (USE_CASE, SYSTEM, MODEL, DATASET)
IN_USE = ("approved", "approved_with_conditions", "lapsed", "suspended")
OWNER_RESPONSES = ("confirmed", "changed", "retired")
SOON_DAYS = 7


def find(session: Session, ref: str) -> Campaign:
    campaign = session.scalars(select(Campaign).where(Campaign.ref == ref.strip().upper())).first()
    if campaign is None:
        raise NotFound(f"There is no campaign {ref}.")
    return campaign


def _scope(session: Session, unit_id: int | None) -> frozenset[int] | None:
    return units.with_descendants(session, [unit_id]) if unit_id is not None else None


def _records(session: Session, record_type: RecordType, scope: frozenset[int] | None) -> list[Any]:
    model = record_type.model
    statement = select(model).order_by(model.id)  # type: ignore[attr-defined]
    if record_type is USE_CASE:
        statement = statement.where(model.status.in_(IN_USE))  # type: ignore[attr-defined]
    else:
        statement = statement.where(model.status == "active")  # type: ignore[attr-defined]
    if scope is not None:
        statement = statement.where(model.org_unit_id.in_(scope))  # type: ignore[attr-defined]
    return list(session.scalars(statement))


def _owners(session: Session, type_key: str, record_ids: Iterable[int]) -> dict[int, set[int]]:
    owners: dict[int, set[int]] = defaultdict(set)
    ids = list(record_ids)
    if ids:
        for record_id, account_id in session.execute(
            select(RecordOwner.record_id, RecordOwner.account_id).where(
                RecordOwner.record_type == type_key,
                RecordOwner.record_id.in_(ids),
                RecordOwner.kind != "contact",
            )
        ):
            owners[record_id].add(account_id)
    return owners


def _direct_stewards(session: Session) -> dict[int, set[int]]:
    from govwren.db.models import RoleGrant

    found: dict[int, set[int]] = defaultdict(set)
    for unit_id, account_id in session.execute(
        select(RoleGrant.org_unit_id, RoleGrant.account_id)
        .join(Account, Account.id == RoleGrant.account_id)
        .where(RoleGrant.role == roles.STEWARD, Account.status == "active")
    ):
        if unit_id is not None:
            found[unit_id].add(account_id)
    return found


def answerers(session: Session, item: Attestation) -> set[int]:
    """The people an item is waiting on: a record's owners, or a unit's stewards."""
    if item.subject_type == "org_unit":
        return review.stewards_of(session, item.subject_id)
    people = _owners(session, item.subject_type, [item.subject_id]).get(item.subject_id, set())
    if not people:
        record = session.get(TYPES[item.subject_type].model, item.subject_id)
        created_by = getattr(record, "created_by", None)
        people = {created_by} if created_by is not None else set()
    active = set(
        session.scalars(
            select(Account.id).where(Account.id.in_(people or {0}), Account.status == "active")
        )
    )
    # With no owner left to ask, the question goes to the unit's steward.
    return active or review.stewards_of(session, item.org_unit_id)


def open_campaign(
    session: Session,
    principal: Principal,
    *,
    kind: str,
    title: str,
    due_on: date | None,
    scope_unit_id: int | None = None,
    record_types: Iterable[str] = ("use_case",),
    note: str = "",
) -> Campaign:
    """Start a campaign: work out what it asks about, and tell the people it asks."""
    if not principal.governs:
        raise PermissionDenied("Only governance can start a campaign.")
    title, kinds = title.strip(), list(dict.fromkeys(record_types))
    errors = {}
    if kind not in CAMPAIGN_KINDS:
        errors["kind"] = "Choose what the campaign asks."
    if not 3 <= len(title) <= 200:
        errors["title"] = "Give the campaign a name."
    if due_on is None or due_on <= today():
        errors["due_on"] = "Choose a date in the future."
    if scope_unit_id is not None and session.get(OrgUnit, scope_unit_id) is None:
        errors["scope_unit_id"] = "Choose a unit."
    allowed = {record_type.key for record_type in CONFIRMABLE}
    if kind == "owner_confirmation" and (not kinds or any(key not in allowed for key in kinds)):
        errors["record_types"] = "Choose at least one kind of record."
    if errors:
        raise Invalid("The campaign was not started.", errors)
    assert due_on is not None
    scope = _scope(session, scope_unit_id)
    with audit.operation(session, "campaign.open"):
        campaign = Campaign(
            ref=next_ref(session, "ATT"),
            kind=kind,
            title=title,
            note=note.strip() or None,
            scope_unit_id=scope_unit_id,
            record_types=kinds if kind == "owner_confirmation" else [],
            status="open",
            due_on=due_on,
            opened_by=principal.account_id,
            opened_at=utc_now(),
        )
        session.add(campaign)
        session.flush()
        items: list[Attestation] = []
        if kind == "owner_confirmation":
            for key in kinds:
                for record in _records(session, TYPES[key], scope):
                    items.append(
                        Attestation(campaign_id=campaign.id, subject_type=key,
                                    subject_id=record.id, org_unit_id=record.org_unit_id)
                    )  # fmt: skip
        else:
            stewarded = _direct_stewards(session)
            holding = set(session.scalars(select(USE_CASE.model.org_unit_id).distinct()))  # type: ignore[attr-defined]
            for unit in units.all_units(session):
                in_scope = scope is None or unit.id in scope
                if in_scope and (unit.id in stewarded or unit.id in holding):
                    items.append(
                        Attestation(campaign_id=campaign.id, subject_type="org_unit",
                                    subject_id=unit.id, org_unit_id=unit.id)
                    )  # fmt: skip
        if not items:
            raise Invalid(
                "The campaign was not started.",
                {"scope_unit_id": "There is nothing in that unit to ask about."},
            )
        session.add_all(items)
        session.flush()
    asked: dict[int, int] = defaultdict(int)
    for item in items:
        for account_id in answerers(session, item):
            asked[account_id] += 1
    what = "record" if kind == "owner_confirmation" else "unit"
    for account_id, count in asked.items():
        review.notify(
            session, [account_id], "attestation",
            f"{title}: {count} {what}{'' if count == 1 else 's'} to confirm by "
            f"{due_on:%b} {due_on.day}",
            f"/campaigns/{campaign.ref}",
        )  # fmt: skip
    return campaign


def can_answer(session: Session, principal: Principal, item: Attestation) -> bool:
    if item.subject_type == "org_unit":
        return principal.governs or principal.stewards_unit(item.subject_id)
    record_type = TYPES[item.subject_type]
    record = session.get(record_type.model, item.subject_id)
    return record is not None and access.can_edit(session, principal, record_type, record)


def _unit_snapshot(session: Session, unit_id: int) -> dict[str, Any]:
    scope = units.with_descendants(session, [unit_id])
    counts = {}
    for record_type in CONFIRMABLE:
        model = record_type.model
        counts[record_type.key] = session.execute(
            select(func.count()).select_from(model).where(
                model.org_unit_id.in_(scope), model.status != "retired"  # type: ignore[attr-defined]
            )
        ).scalar_one()  # fmt: skip
    return counts


def answer(
    session: Session,
    principal: Principal,
    campaign: Campaign,
    answers: Iterable[Mapping[str, Any]],
) -> int:
    """Record answers to some of a campaign's items. All of them are recorded, or none."""
    if campaign.status != "open":
        raise Conflict("This campaign has closed.")
    given = list(answers)
    if not given:
        raise Invalid("Nothing was recorded.", {"items": "Choose at least one."})
    items = {
        item.id: item
        for item in session.scalars(
            select(Attestation).where(
                Attestation.campaign_id == campaign.id,
                Attestation.id.in_([int(entry.get("id") or 0) for entry in given]),
            )
        )
    }
    now = utc_now()
    changed: list[Any] = []
    with audit.operation(session, "campaign.answer", campaign=campaign.ref):
        for entry in given:
            item = items.get(int(entry.get("id") or 0))
            if item is None:
                raise NotFound("That is not part of this campaign.")
            if not can_answer(session, principal, item):
                raise PermissionDenied("That is not yours to answer.")
            if item.response is not None:
                raise Conflict("That has already been answered.")
            response, note = str(entry.get("response") or ""), str(entry.get("note") or "").strip()
            if item.subject_type == "org_unit":
                if response != "attested":
                    raise Invalid("Nothing was recorded.", {"response": "Attest the list."})
                item.snapshot = _unit_snapshot(session, item.subject_id)
            else:
                if response not in OWNER_RESPONSES:
                    raise Invalid("Nothing was recorded.", {"response": "Choose an answer."})
                if response != "confirmed" and len(note) < 10:
                    words = "what has changed" if response == "changed" else "why it has ended"
                    raise Invalid("Nothing was recorded.", {"note": f"Say {words}."})
                record_type = TYPES[item.subject_type]
                record = session.get(record_type.model, item.subject_id)
                assert record is not None
                if response == "retired":
                    retirement.retire(session, principal, record_type, record, note)
                elif response == "changed":
                    changed.append((record_type, record))
            item.response, item.note = response, note or None
            item.answered_by, item.answered_at = principal.account_id, now
        session.flush()
    for record_type, record in changed:
        review.notify(
            session, review.holders(session, roles.GOVERNANCE), "change",
            f"Reported as changed in {campaign.ref}: {record.name}",
            f"/{record_type.path}/{record.ref}",
            skip=principal.account_id,
        )  # fmt: skip
    return len(given)


def close(session: Session, principal: Principal, campaign: Campaign) -> Campaign:
    if not principal.governs:
        raise PermissionDenied("Only governance can close a campaign.")
    if campaign.status != "open":
        raise Conflict("This campaign has already closed.")
    with audit.operation(session, "campaign.close"):
        campaign.status, campaign.closed_by, campaign.closed_at = (
            "closed", principal.account_id, utc_now(),
        )  # fmt: skip
        session.flush()
    return campaign


# --- Looking at campaigns -----------------------------------------------------------------


def _items(session: Session, campaign_ids: Iterable[int]) -> dict[int, list[Attestation]]:
    grouped: dict[int, list[Attestation]] = defaultdict(list)
    ids = list(campaign_ids)
    if ids:
        for item in session.scalars(
            select(Attestation).where(Attestation.campaign_id.in_(ids)).order_by(Attestation.id)
        ):
            grouped[item.campaign_id].append(item)
    return grouped


class _Mine:
    """Which items are a person's own to answer: records they own, units they steward."""

    def __init__(self, session: Session, principal: Principal) -> None:
        self.principal = principal
        self.owned: set[tuple[str, int]] = set()
        me = principal.account_id
        if me is None:
            return
        self.owned = {
            (kind, record_id)
            for kind, record_id in session.execute(
                select(RecordOwner.record_type, RecordOwner.record_id).where(
                    RecordOwner.account_id == me, RecordOwner.kind != "contact"
                )
            )
        }
        for record_type in CONFIRMABLE:
            model = record_type.model
            for record_id in session.scalars(select(model.id).where(model.created_by == me)):  # type: ignore[attr-defined]
                self.owned.add((record_type.key, record_id))

    def has(self, item: Attestation) -> bool:
        if item.subject_type == "org_unit":
            return self.principal.stewards_unit(item.subject_id)
        return (item.subject_type, item.subject_id) in self.owned


def _summary(campaign: Campaign, items: list[Attestation], mine: _Mine) -> dict[str, Any]:
    answered = sum(1 for item in items if item.response)
    return {
        "ref": campaign.ref,
        "kind": campaign.kind,
        "title": campaign.title,
        "note": campaign.note,
        "status": campaign.status,
        "scope_unit_id": campaign.scope_unit_id,
        "record_types": campaign.record_types,
        "due_on": campaign.due_on,
        "overdue": campaign.status == "open" and campaign.due_on < today(),
        "opened_at": campaign.opened_at,
        "closed_at": campaign.closed_at,
        "total": len(items),
        "answered": answered,
        "mine_waiting": sum(1 for item in items if not item.response and mine.has(item))
        if campaign.status == "open"
        else 0,
    }


def listing(session: Session, principal: Principal) -> list[dict[str, Any]]:
    """Every campaign, for those who see everything; for anyone else, those that ask them."""
    campaigns = session.scalars(select(Campaign).order_by(Campaign.id.desc())).all()
    items = _items(session, [campaign.id for campaign in campaigns])
    mine = _Mine(session, principal)
    out = []
    for campaign in campaigns:
        its = items.get(campaign.id, [])
        if principal.reads_all or any(mine.has(item) for item in its):
            out.append(_summary(campaign, its, mine))
    return out


def waiting_on(session: Session, principal: Principal) -> list[dict[str, Any]]:
    """Open campaigns with something this person has yet to answer, for their Home page."""
    return [c for c in listing(session, principal) if c["status"] == "open" and c["mine_waiting"]]


def view(session: Session, principal: Principal, campaign: Campaign) -> dict[str, Any]:
    items = _items(session, [campaign.id]).get(campaign.id, [])
    mine = _Mine(session, principal)
    if not principal.reads_all and not any(mine.has(item) for item in items):
        raise NotFound(f"There is no campaign {campaign.ref}.")
    unit_names = {unit.id: unit.name for unit in units.all_units(session)}
    records: dict[tuple[str, int], Any] = {}
    for key in {item.subject_type for item in items if item.subject_type != "org_unit"}:
        model = TYPES[key].model
        ids = [item.subject_id for item in items if item.subject_type == key]
        for record in session.scalars(select(model).where(model.id.in_(ids))):  # type: ignore[attr-defined]
            records[(key, record.id)] = record
    owners: dict[tuple[str, int], set[int]] = {}
    for key in {kind for kind, _ in records}:
        for record_id, people in _owners(session, key, [i for k, i in records if k == key]).items():
            owners[(key, record_id)] = people
    stewards = _direct_stewards(session)
    wanted = {i.answered_by for i in items if i.answered_by} | set().union(*owners.values(), set())
    wanted |= set().union(*stewards.values(), set())
    names = dict(
        session.execute(
            select(Account.id, Account.display_name).where(Account.id.in_(wanted or {0}))
        ).all()  # type: ignore[arg-type]
    )

    def shown(item: Attestation) -> dict[str, Any]:
        base = {
            "id": item.id,
            "type": item.subject_type,
            "org_unit_id": item.org_unit_id,
            "unit": unit_names.get(item.org_unit_id or 0),
            "response": item.response,
            "note": item.note,
            "answered_by": names.get(item.answered_by or 0),
            "answered_at": item.answered_at,
            "mine": mine.has(item),
            "can_answer": campaign.status == "open"
            and item.response is None
            and can_answer(session, principal, item),
        }
        if item.subject_type == "org_unit":
            people = stewards.get(item.subject_id, set())
            return {
                **base,
                "name": unit_names.get(item.subject_id, "A unit"),
                "ref": None,
                "path": None,
                "waiting_on": sorted(names[p] for p in people if p in names),
                "holds": item.snapshot
                if item.snapshot is not None
                else _unit_snapshot(session, item.subject_id),
            }
        record = records.get((item.subject_type, item.subject_id))
        people = owners.get((item.subject_type, item.subject_id), set())
        return {
            **base,
            "name": record.name if record else "A record that is gone",
            "ref": record.ref if record else None,
            "path": TYPES[item.subject_type].path,
            "status": getattr(record, "status", None),
            "tier": getattr(record, "tier", None),
            "waiting_on": sorted(names[p] for p in people if p in names),
        }

    visible = [item for item in items if principal.reads_all or mine.has(item)
               or can_answer(session, principal, item)]  # fmt: skip
    by_unit: dict[int | None, dict[str, int]] = defaultdict(lambda: {"total": 0, "answered": 0})
    by_response: dict[str, int] = defaultdict(int)
    for item in items:
        by_unit[item.org_unit_id]["total"] += 1
        if item.response:
            by_unit[item.org_unit_id]["answered"] += 1
            by_response[item.response] += 1
    return {
        **_summary(campaign, items, mine),
        "scope_unit": unit_names.get(campaign.scope_unit_id or 0),
        "can_close": principal.governs and campaign.status == "open",
        "sees_all": principal.reads_all,
        "by_response": dict(by_response),
        "by_unit": sorted(
            (
                {"org_unit_id": unit_id, "unit": unit_names.get(unit_id or 0, "No unit"), **counts}
                for unit_id, counts in by_unit.items()
            ),
            key=lambda row: (row["answered"] / row["total"], row["unit"]),
        )
        if principal.reads_all
        else [],
        "items": [shown(item) for item in visible],
    }


# --- Reminders ----------------------------------------------------------------------------


def remind(session: Session) -> int:
    """Remind people with answers outstanding when a campaign is nearly due, and again when
    it is late; then an owner's silence goes to their unit's steward as well."""
    sent = 0
    campaigns = session.scalars(select(Campaign).where(Campaign.status == "open")).all()
    for campaign in campaigns:
        left = (campaign.due_on - today()).days
        stage = "late" if left < 0 else "soon" if left <= SOON_DAYS else None
        if stage is None:
            continue
        done = set(
            session.scalars(
                select(Reminder.stage).where(
                    Reminder.subject_type == "campaign", Reminder.subject_id == campaign.id
                )
            )
        )
        waiting: dict[int, int] = defaultdict(int)
        for item in _items(session, [campaign.id]).get(campaign.id, []):
            if item.response is not None:
                continue
            people = answerers(session, item)
            if stage == "late" and item.subject_type != "org_unit":
                people = people | review.stewards_of(session, item.org_unit_id)
            for account_id in people:
                waiting[account_id] += 1
        for account_id, count in waiting.items():
            key = f"{stage}:{account_id}"
            if key in done:
                continue
            session.add(Reminder(subject_type="campaign", subject_id=campaign.id, stage=key,
                                 sent_on=today()))  # fmt: skip
            things = f"{count} answer{'' if count == 1 else 's'}"
            title = (
                f"Overdue: {things} still wanted for {campaign.title}"
                if stage == "late"
                else f"Due {campaign.due_on:%b} {campaign.due_on.day}: {things} wanted for "
                f"{campaign.title}"
            )
            review.notify(session, [account_id], "overdue" if stage == "late" else "reminder",
                          title, f"/campaigns/{campaign.ref}")  # fmt: skip
            sent += 1
    session.flush()
    return sent
