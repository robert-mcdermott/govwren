"""Policies: the organization's own rules, kept with their versions, an owner, a review date,
the controls that carry them out, and a record of who has acknowledged them."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import today, utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import (
    Account,
    Control,
    Membership,
    OrgUnit,
    Policy,
    PolicyAcknowledgment,
    PolicyVersion,
    Reminder,
)
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.people import units
from govwren.review import service as review

SOON_DAYS = 7


def find(session: Session, ref: str) -> Policy:
    policy = session.scalars(select(Policy).where(Policy.ref == ref.strip().upper())).first()
    if policy is None:
        raise NotFound(f"There is no policy {ref}.")
    return policy


def _governs(principal: Principal) -> None:
    if not principal.governs:
        raise PermissionDenied("Only governance can change a policy.")


def versions_of(session: Session, policy: Policy) -> list[PolicyVersion]:
    return list(
        session.scalars(
            select(PolicyVersion)
            .where(PolicyVersion.policy_id == policy.id)
            .order_by(PolicyVersion.version.desc())
        )
    )


def in_force(session: Session, policy: Policy) -> PolicyVersion | None:
    return next((v for v in versions_of(session, policy) if v.status == "published"), None)


def _details(session: Session, values: Mapping[str, Any], *, creating: bool) -> dict[str, Any]:
    errors: dict[str, str] = {}
    out: dict[str, Any] = {}
    if creating or "title" in values:
        title = str(values.get("title") or "").strip()
        if not 3 <= len(title) <= 200:
            errors["title"] = "Give the policy a name."
        out["title"] = title
    if "summary" in values:
        out["summary"] = str(values.get("summary") or "").strip() or None
    if "owner_id" in values:
        owner = session.get(Account, values["owner_id"]) if values.get("owner_id") else None
        if values.get("owner_id") and (owner is None or owner.status != "active"):
            errors["owner_id"] = "Choose who owns the policy."
        out["owner_id"] = owner.id if owner else None
    if "review_on" in values:
        when = values.get("review_on")
        if isinstance(when, str) and when:
            try:
                when = date.fromisoformat(when)
            except ValueError:
                errors["review_on"] = "That is not a date."
        out["review_on"] = when or None
    if "control_keys" in values:
        keys = list(dict.fromkeys(values.get("control_keys") or []))
        known = set(session.scalars(select(Control.key).where(Control.key.in_(keys or [""]))))
        if set(keys) - known:
            errors["control_keys"] = "One of those is not a control in the library."
        out["control_keys"] = keys
    if errors:
        raise Invalid("The policy was not saved.", errors)
    return out


def create(session: Session, principal: Principal, values: Mapping[str, Any]) -> Policy:
    """Start a policy. It is a draft, with an empty first version, until it is published."""
    _governs(principal)
    cleaned = _details(session, values, creating=True)
    with audit.operation(session, "policy.create"):
        policy = Policy(
            ref=next_ref(session, "POL"),
            status="draft",
            created_by=principal.account_id,
            created_at=utc_now(),
            **{"control_keys": [], **cleaned},
        )
        if policy.owner_id is None:
            policy.owner_id = principal.account_id
        session.add(policy)
        session.flush()
        session.add(
            PolicyVersion(
                policy_id=policy.id,
                version=1,
                status="draft",
                body=str(values.get("body") or "").strip(),
            )
        )
        session.flush()
    return policy


def update(
    session: Session, principal: Principal, policy: Policy, values: Mapping[str, Any]
) -> Policy:
    _governs(principal)
    cleaned = _details(session, values, creating=False)
    with audit.operation(session, "policy.update"):
        for name, value in cleaned.items():
            setattr(policy, name, value)
        session.flush()
    return policy


def save_draft(
    session: Session, principal: Principal, policy: Policy, *, body: str, change_note: str = ""
) -> PolicyVersion:
    """Write the text of the next version. The version in force is not touched."""
    _governs(principal)
    if policy.status == "retired":
        raise Conflict("This policy has been retired.")
    existing = versions_of(session, policy)
    draft = next((v for v in existing if v.status == "draft"), None)
    with audit.operation(session, "policy.draft"):
        if draft is None:
            draft = PolicyVersion(
                policy_id=policy.id,
                status="draft",
                body="",
                version=max((v.version for v in existing), default=0) + 1,
            )
            session.add(draft)
        draft.body, draft.change_note = body.strip(), change_note.strip() or None
        session.flush()
    return draft


def publish(session: Session, principal: Principal, policy: Policy) -> PolicyVersion:
    """Put the draft in force. Earlier versions are kept as they were."""
    _governs(principal)
    draft = next((v for v in versions_of(session, policy) if v.status == "draft"), None)
    if draft is None:
        raise Conflict("There is no draft to publish.")
    errors = {}
    if len(draft.body) < 20:
        errors["body"] = "Write the policy before publishing it."
    if draft.version > 1 and len(draft.change_note or "") < 5:
        errors["change_note"] = "Say what changed in this version."
    if errors:
        raise Invalid("The policy was not published.", errors)
    with audit.operation(session, "policy.publish", version=draft.version):
        draft.status = "published"
        draft.published_by, draft.published_at = principal.account_id, utc_now()
        policy.status = "in_force"
        session.flush()
    return draft


def retire(session: Session, principal: Principal, policy: Policy) -> Policy:
    _governs(principal)
    if policy.status == "retired":
        raise Conflict("This policy has already been retired.")
    with audit.operation(session, "policy.retire"):
        policy.status, policy.review_on = "retired", None
        session.flush()
    return policy


# --- Acknowledgment -----------------------------------------------------------------------


def ask(
    session: Session,
    principal: Principal,
    policy: Policy,
    *,
    unit_id: int | None,
    due_on: date | None,
) -> int:
    """Ask everyone in a unit and the units beneath it, or everyone, to acknowledge the
    version in force. Someone already asked about this version is not asked twice."""
    _governs(principal)
    version = in_force(session, policy)
    if policy.status != "in_force" or version is None:
        raise Conflict("Publish the policy before asking anyone to acknowledge it.")
    errors = {}
    if due_on is None or due_on <= today():
        errors["due_on"] = "Choose a date in the future."
    if unit_id is not None and session.get(OrgUnit, unit_id) is None:
        errors["unit_id"] = "Choose a unit."
    if errors:
        raise Invalid("Nobody was asked.", errors)
    assert due_on is not None
    people: dict[int, int | None] = {}
    if unit_id is None:
        for account_id in session.scalars(select(Account.id).where(Account.status == "active")):
            people[account_id] = None
    else:
        scope = units.with_descendants(session, [unit_id])
        for account_id, unit in session.execute(
            select(Membership.account_id, Membership.org_unit_id)
            .join(Account, Account.id == Membership.account_id)
            .where(Membership.org_unit_id.in_(scope), Account.status == "active")
        ):
            people.setdefault(account_id, unit)
    asked = set(
        session.scalars(
            select(PolicyAcknowledgment.account_id).where(
                PolicyAcknowledgment.policy_version_id == version.id
            )
        )
    )
    fresh = [account_id for account_id in people if account_id not in asked]
    if not fresh:
        raise Conflict("Everyone there has already been asked about this version.")
    now = utc_now()
    with audit.operation(session, "policy.ask", version=version.version):
        for account_id in fresh:
            session.add(
                PolicyAcknowledgment(
                    policy_id=policy.id,
                    policy_version_id=version.id,
                    account_id=account_id,
                    org_unit_id=people[account_id],
                    due_on=due_on,
                    asked_at=now,
                )
            )
        session.flush()
    review.notify(
        session,
        fresh,
        "policy",
        f"Please read and acknowledge by {due_on:%b} {due_on.day}: {policy.title}",
        f"/policies/{policy.ref}",
        skip=principal.account_id,
    )
    return len(fresh)


def _mine(session: Session, principal: Principal, policy: Policy) -> PolicyAcknowledgment | None:
    version = in_force(session, policy)
    if version is None or principal.account_id is None:
        return None
    return session.scalars(
        select(PolicyAcknowledgment).where(
            PolicyAcknowledgment.policy_version_id == version.id,
            PolicyAcknowledgment.account_id == principal.account_id,
        )
    ).first()


def acknowledge(session: Session, principal: Principal, policy: Policy) -> PolicyAcknowledgment:
    """Say you have read the version in force."""
    mine = _mine(session, principal, policy)
    if mine is None:
        raise Conflict("You have not been asked to acknowledge this policy.")
    if mine.acknowledged_at is not None:
        raise Conflict("You have already acknowledged this version.")
    with audit.operation(session, "policy.acknowledge"):
        mine.acknowledged_at = utc_now()
        session.flush()
    return mine


def waiting_on(session: Session, principal: Principal) -> list[dict[str, Any]]:
    """The policies this person has been asked to acknowledge and has not."""
    rows = session.execute(
        select(PolicyAcknowledgment, Policy, PolicyVersion)
        .join(Policy, Policy.id == PolicyAcknowledgment.policy_id)
        .join(PolicyVersion, PolicyVersion.id == PolicyAcknowledgment.policy_version_id)
        .where(
            PolicyAcknowledgment.account_id == principal.account_id,
            PolicyAcknowledgment.acknowledged_at.is_(None),
            Policy.status == "in_force",
        )
    ).all()
    out = []
    for asked, policy, version in rows:
        current = in_force(session, policy)
        if current is not None and current.id == version.id:
            out.append({"ref": policy.ref, "title": policy.title, "due_on": asked.due_on})
    return out


# --- Looking at policies ------------------------------------------------------------------


def _coverage(session: Session, version: PolicyVersion | None) -> dict[str, Any]:
    if version is None:
        return {"asked": 0, "acknowledged": 0, "by_unit": []}
    rows = session.scalars(
        select(PolicyAcknowledgment).where(PolicyAcknowledgment.policy_version_id == version.id)
    ).all()
    names = dict(session.execute(select(OrgUnit.id, OrgUnit.name)).all())  # type: ignore[arg-type]
    by_unit: dict[int | None, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        by_unit[row.org_unit_id][0] += 1
        by_unit[row.org_unit_id][1] += row.acknowledged_at is not None
    return {
        "asked": len(rows),
        "acknowledged": sum(1 for row in rows if row.acknowledged_at is not None),
        "by_unit": sorted(
            (
                {"unit": names.get(unit or 0, "Everyone"), "asked": asked, "acknowledged": done}
                for unit, (asked, done) in by_unit.items()
            ),
            key=lambda r: (r["acknowledged"] / r["asked"], r["unit"]),
        ),
    }


def _summary(
    session: Session, principal: Principal, policy: Policy, names: Mapping[int, str]
) -> dict[str, Any]:
    current = in_force(session, policy)
    mine = _mine(session, principal, policy)
    return {
        "ref": policy.ref,
        "title": policy.title,
        "summary": policy.summary,
        "status": policy.status,
        "owner": names.get(policy.owner_id or 0),
        "owner_id": policy.owner_id,
        "review_on": policy.review_on,
        "review_due": policy.status == "in_force"
        and bool(policy.review_on and policy.review_on <= today()),
        "version": current.version if current else None,
        "published_at": current.published_at if current else None,
        "mine": None
        if mine is None
        else {
            "due_on": mine.due_on,
            "acknowledged_at": mine.acknowledged_at,
            "overdue": mine.acknowledged_at is None and mine.due_on < today(),
        },
    }


def _names(session: Session, policies: list[Policy]) -> dict[int, str]:
    ids = {p.owner_id for p in policies} - {None}
    return dict(
        session.execute(
            select(Account.id, Account.display_name).where(Account.id.in_(ids or {0}))
        ).all()  # type: ignore[arg-type]
    )


def listing(session: Session, principal: Principal) -> list[dict[str, Any]]:
    """Policies in force, for everyone. Governance and auditors also see drafts and retired ones."""
    statement = select(Policy).order_by(Policy.title)
    if not principal.reads_all:
        statement = statement.where(Policy.status == "in_force")
    policies = list(session.scalars(statement))
    names = _names(session, policies)
    return [_summary(session, principal, policy, names) for policy in policies]


def view(session: Session, principal: Principal, policy: Policy) -> dict[str, Any]:
    if policy.status != "in_force" and not principal.reads_all:
        raise NotFound(f"There is no policy {policy.ref}.")
    versions = versions_of(session, policy)
    current = next((v for v in versions if v.status == "published"), None)
    draft = next((v for v in versions if v.status == "draft"), None)
    controls = [
        {"key": c.key, "title": c.title}
        for c in session.scalars(
            select(Control).where(Control.key.in_(policy.control_keys or [""]))
        )
    ]
    return {
        **_summary(session, principal, policy, _names(session, [policy])),
        "body": current.body if current else None,
        "control_keys": policy.control_keys,
        "controls": controls,
        "versions": [
            {
                "version": v.version,
                "status": v.status,
                "change_note": v.change_note,
                "published_at": v.published_at,
            }
            for v in versions
            if v.status == "published" or principal.reads_all
        ],
        "draft": {"version": draft.version, "body": draft.body, "change_note": draft.change_note}
        if draft and principal.reads_all
        else None,
        "coverage": _coverage(session, current) if principal.reads_all else None,
        "can": {
            "edit": principal.governs and policy.status != "retired",
            "publish": principal.governs and draft is not None and policy.status != "retired",
            "ask": principal.governs and policy.status == "in_force",
            "retire": principal.governs and policy.status != "retired",
        },
    }


def remind(session: Session) -> int:
    """Remind people of an acknowledgment nearly due, and again when it is late; and remind
    a policy's owner when its review date comes."""
    done = {
        (kind, subject, stage)
        for kind, subject, stage in session.execute(
            select(Reminder.subject_type, Reminder.subject_id, Reminder.stage).where(
                Reminder.subject_type.in_(("policy", "policy_ack"))
            )
        )
    }
    sent = 0
    now = today()

    def once(kind: str, subject: int, stage: str) -> bool:
        if (kind, subject, stage) in done:
            return False
        done.add((kind, subject, stage))
        session.add(Reminder(subject_type=kind, subject_id=subject, stage=stage, sent_on=now))
        return True

    for asked, policy in session.execute(
        select(PolicyAcknowledgment, Policy)
        .join(Policy, Policy.id == PolicyAcknowledgment.policy_id)
        .where(PolicyAcknowledgment.acknowledged_at.is_(None), Policy.status == "in_force")
    ):
        left = (asked.due_on - now).days
        stage = "late" if left < 0 else "soon" if left <= SOON_DAYS else None
        if stage and once("policy_ack", asked.id, stage):
            words = "Overdue" if stage == "late" else f"Due {asked.due_on:%b} {asked.due_on.day}"
            review.notify(
                session,
                [asked.account_id],
                "overdue" if stage == "late" else "reminder",
                f"{words}: read and acknowledge {policy.title}",
                f"/policies/{policy.ref}",
            )
            sent += 1
    for policy in session.scalars(
        select(Policy).where(Policy.status == "in_force", Policy.review_on <= now)
    ):
        if policy.owner_id and once("policy", policy.id, f"due:{policy.review_on:%y%m%d}"):
            review.notify(
                session,
                [policy.owner_id],
                "reminder",
                f"This policy is due for review: {policy.title}",
                f"/policies/{policy.ref}",
            )
            sent += 1
    session.flush()
    return sent
