"""A record's history, in words a person can read.

The events themselves are the record of what happened (``govwren.events``). This turns them
into a timeline: who did what, and for each changed field, what it was and what it became.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from govwren.db.models import Account, AISystem, Dataset, Event, Model, OrgUnit, UseCase, Vendor
from govwren.inventory import fields
from govwren.inventory.registry import RecordType
from govwren.program import vocab

LABELS = {
    "name": "Name",
    "summary": "Summary",
    "purpose": "Purpose",
    "org_unit_id": "Unit",
    "status": "Standing",
    "stage": "Stage",
    "domain": "Domain",
    "tier": "Tier",
    "tier_source": "How the tier was set",
    "decision_role": "Decision role",
    "human_oversight": "Human oversight",
    "affected_groups": "Who is affected",
    "data_class": "Data class",
    "data_categories": "Kinds of data",
    "outputs_used_for": "What outputs are used for",
    "approved_until": "Approved until",
    "next_review_on": "Next review",
    "tags": "Tags",
    "restricted": "Restricted",
    "kind": "Kind",
    "vendor_id": "Vendor",
    "embedded_in": "Inside",
    "hosting": "Hosting",
    "edition": "Edition",
    "access_path": "Reached through",
    "version_label": "Version",
    "url": "Address",
    "catalog_status": "Catalog standing",
    "permitted_data_class": "May be used with data up to",
    "excluded_data_categories": "Not to be used with",
    "terms": "Terms of use",
    "data_handling": "Data handling",
    "regulatory_status": "Regulatory status",
    "website": "Website",
    "contacts": "Contacts",
    "notes": "Notes",
    "due_diligence_status": "Due diligence",
}
LABELS.update(
    {field.key: field.label for spec in (fields.MODEL, fields.DATASET) for field in spec}
    | {"agent_profile": "Agent profile", "card": "Model card", "provider": "Made by"}
)
HIDDEN = {"id", "ref", "created_by", "created_at"}
VOCABULARIES = {
    "stage": "stages",
    "domain": "domains",
    "decision_role": "decision_roles",
    "affected_groups": "affected_groups",
    "data_class": "data_classes",
    "permitted_data_class": "data_classes",
    "data_categories": "data_categories",
    "excluded_data_categories": "data_categories",
    "outputs_used_for": "outputs_used_for",
    "kind": "system_kinds",
    "hosting": "hosting",
    "access_path": "access_paths",
    "origin": "model_origins",
    "modality": "modalities",
    "weights_format": "weights_formats",
    "tuning_method": "tuning_methods",
    "sharing": "sharing",
    "identifiability": "identifiability",
    "subjects": "affected_groups",
}
# The one field whose vocabulary depends on the kind of record.
KIND_VOCABULARY = {"model": "model_kinds"}
TIERS = {1: "Minimal", 2: "Moderate", 3: "High", 4: "Critical"}
REVIEW_STATUS = {
    "triage": "waiting for triage",
    "in_review": "with reviewers",
    "with_requester": "back with the requester",
    "ready": "ready for a decision",
    "decided": "decided",
    "cancelled": "cancelled",
}
FINDINGS = {
    "no_concerns": "no concerns",
    "conditions": "acceptable with conditions",
    "objection": "objection",
}
OUTCOMES = {
    "approved": "Approved",
    "approved_with_conditions": "Approved with conditions",
    "declined": "Declined",
    "returned": "Returned to the requester",
    "withdrawn": "Withdrawn",
}
OPERATIONS = {
    "create": "Added",
    "edit": "Edited",
    "owners": "Changed the owners",
    "systems": "Changed the systems it uses",
    "merge": "Merged into another record",
}


def _words(text: str) -> str:
    return text.replace("_", " ").capitalize()


class _Lookups:
    """Names for the keys and ids that events hold, loaded when first needed."""

    def __init__(
        self, session: Session, *, internal: bool = True, tasks: dict[int, str] | None = None
    ) -> None:
        self.session = session
        self.internal = internal
        self._tasks = tasks or {}
        self._vocab: dict[str, dict[str, str]] = {}
        self._names: dict[str, dict[int, str]] = {}
        self._tiers: dict[int, str] | None = None
        self.kind_vocabulary = "system_kinds"

    def vocab(self, name: str, key: Any) -> str:
        if name not in self._vocab:
            self._vocab[name] = vocab.labels(self.session, name)
        return self._vocab[name].get(str(key), _words(str(key)))

    def name(self, kind: str, identifier: Any) -> str:
        if kind not in self._names:
            model, column = {
                "unit": (OrgUnit, OrgUnit.name),
                "account": (Account, Account.display_name),
                "vendor": (Vendor, Vendor.name),
                "system": (AISystem, AISystem.name),
                "model": (Model, Model.name),
                "dataset": (Dataset, Dataset.name),
                "use_case": (UseCase, UseCase.name),
            }[kind]
            self._names[kind] = dict(self.session.execute(select(model.id, column)).all())  # type: ignore[arg-type]
        return self._names[kind].get(identifier, f"{kind} {identifier}")

    def task_function(self, task_id: int | None, given: Any) -> str:
        return str(given or self._tasks.get(task_id or 0, "review"))

    def tier(self, level: Any) -> str:
        """A tier's name, from the scoring model in force, or the usual names if there is none."""
        if self._tiers is None:
            from govwren.program import packs

            model = packs.published_scoring(self.session)
            self._tiers = (
                {tier["level"]: tier["label"] for tier in model.definition["tiers"]}
                if model
                else TIERS
            )
        return self._tiers.get(level, str(level))

    def value(self, field: str, value: Any) -> Any:
        if value is None or value == "" or value == []:
            return None
        if field in VOCABULARIES:
            name = self.kind_vocabulary if field == "kind" else VOCABULARIES[field]
            if isinstance(value, list):
                return ", ".join(self.vocab(name, item) for item in value)
            return self.vocab(name, value)
        if field == "org_unit_id":
            return self.name("unit", value)
        if field == "vendor_id":
            return self.name("vendor", value)
        if field == "tier":
            return self.tier(value)
        if field in ("status", "catalog_status", "due_diligence_status", "tier_source"):
            return _words(str(value))
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, list):
            return ", ".join(
                str(item.get("name") or item) if isinstance(item, dict) else str(item)
                for item in value
            )
        if isinstance(value, dict):
            return "; ".join(f"{_words(k)}: {v}" for k, v in value.items() if v not in (None, ""))
        return value


def _entry(event: Event, record_type: RecordType, lookups: _Lookups) -> dict[str, Any]:
    changes = event.changes or {}
    lines: list[dict[str, Any]] = []
    operation = str((event.context or {}).get("op", "")).rsplit(".", 1)[-1]

    def after(field: str) -> Any:
        return (changes.get(field) or [None, None])[1]

    def before(field: str) -> Any:
        return (changes.get(field) or [None, None])[0]

    if event.subject_type == "record_owner":
        person = lookups.name("account", after("account_id") or before("account_id"))
        kind = lookups.vocab("owner_kinds", after("kind") or before("kind")).lower()
        title = (
            f"Added {person} as {kind}"
            if event.action == "created"
            else f"Removed {person} as {kind}"
        )
    elif event.subject_type == "record_link":
        from govwren.inventory.links import PHRASES

        relation = after("relation") or before("relation") or "uses"
        target = lookups.name(
            after("to_type") or before("to_type") or "system", after("to_id") or before("to_id")
        )
        phrase = PHRASES.get(relation, (_words(relation), ""))[0]
        if relation == "uses":
            title = (
                f"Now uses {target}" if event.action == "created" else f"No longer uses {target}"
            )
        else:
            title = (
                f"{phrase}: {target}"
                if event.action == "created"
                else f"No longer {phrase.lower()}: {target}"
            )
    elif event.subject_type == "record_merge":
        title = f"Merged {after('from_ref')} into this record"
    elif event.subject_type == "evidence_link":
        from govwren.db.models import Evidence

        found = lookups.session.get(Evidence, after("evidence_id") or before("evidence_id"))
        name = f"{found.title} ({found.ref})" if found else "evidence"
        title = (
            f"Evidence attached: {name}"
            if event.action == "created"
            else f"Evidence removed: {name}"
        )
    elif event.subject_type == "external_ref":
        kind = lookups.vocab("reference_kinds", after("kind") or before("kind"))
        number = after("identifier") or before("identifier")
        title = (
            f"Added a reference: {kind} {number}"
            if event.action == "created"
            else f"Removed a reference: {kind} {number}"
        )
    elif event.subject_type == "agreement":
        name = after("title") or before("title") or ""
        title = {
            "created": f"Added an agreement: {name}",
            "deleted": f"Removed an agreement: {name}",
        }.get(event.action, "Changed an agreement")
        if event.action == "updated":
            for field, (old, new) in changes.items():
                lines.append({"field": field, "label": _words(field), "before": old, "after": new})
    elif event.subject_type == "review":
        if event.action == "created":
            kind = {"periodic": "Periodic review", "change": "Change review"}.get(
                after("kind"), "Review"
            )
            title = f"{kind} {event.subject_ref} opened"
        elif "status" in changes:
            title = "Review: " + REVIEW_STATUS.get(after("status"), _words(str(after("status"))))
        else:
            title = "Review updated"
    elif event.subject_type == "review_task":
        function = lookups.vocab(
            "review_functions", lookups.task_function(event.subject_id, after("review_function"))
        )
        if event.action == "created":
            title = f"{function} review required"
        elif after("status") == "waived":
            title = f"{function} review not required"
        elif after("status") == "completed":
            finding = FINDINGS.get(after("finding"), "completed")
            title = (
                f"{function} review: {finding}"
                if lookups.internal
                else f"{function} review completed"
            )
        elif "assignee_id" in changes and after("assignee_id") is not None:
            title = f"{function} review taken by {lookups.name('account', after('assignee_id'))}"
        else:
            title = f"{function} review updated"
    elif event.subject_type == "decision":
        title = OUTCOMES.get(after("outcome"), _words(str(after("outcome"))))
        if after("by_rule"):
            title += " by rule"
        if after("over_objection"):
            title += ", over an objection"
        lines.append(
            {"field": "rationale", "label": "Reason", "before": None, "after": after("rationale")}
        )
    elif event.subject_type == "condition":
        if event.action == "created":
            title = "Condition set"
            lines.append(
                {"field": "text", "label": "Condition", "before": None, "after": after("text")}
            )
        else:
            title = {"met": "Condition met", "waived": "Condition waived"}.get(
                after("status"), "Condition updated"
            )
            if after("note"):
                lines.append(
                    {"field": "note", "label": "Note", "before": None, "after": after("note")}
                )
    elif event.subject_type == "comment":
        if after("is_question"):
            title = "Asked the requester a question"
        elif after("visibility") == "requester":
            title = "Message between the requester and reviewers"
        else:
            title = "Note among reviewers"
    elif event.subject_type == "attestation":
        if event.action == "created":
            title = "Included in an attestation campaign"
        else:
            title = {
                "confirmed": "Confirmed as still accurate",
                "changed": "Reported as changed",
                "retired": "Reported as no longer in use",
                "attested": "List attested as complete",
            }.get(after("response"), "Attestation updated")
            if after("note"):
                lines.append(
                    {"field": "note", "label": "Note", "before": None, "after": after("note")}
                )
    elif event.subject_type == "form_response":
        title = (
            "Confirmed the answers for a periodic review"
            if operation == "confirm"
            else "Submitted the request"
        )
    elif event.subject_type == "tier_assessment":
        tier = lookups.tier(after("final_tier"))
        if after("override_reason"):
            title = f"Changed the tier to {tier}"
            lines.append(
                {
                    "field": "override_reason",
                    "label": "Reason",
                    "before": None,
                    "after": after("override_reason"),
                }
            )
        else:
            title = f"Tier worked out as {tier}"
    elif event.action == "created":
        title = f"Added this {record_type.label}"
    elif event.action == "updated" and operation == "retire":
        title = "Retired"
        reason = (event.context or {}).get("reason")
        lines.append({"field": "reason", "label": "Reason", "before": None, "after": reason})
    elif event.action == "updated" and operation == "lapse":
        title = "Approval lapsed"
        reason = (event.context or {}).get("reason")
        lines.append({"field": "reason", "label": "Reason", "before": None, "after": reason})
    elif event.action == "updated":
        for field, (old, new) in changes.items():
            if field in HIDDEN:
                continue
            lines.append(
                {
                    "field": field,
                    "label": LABELS.get(field, _words(field)),
                    "before": lookups.value(field, old),
                    "after": lookups.value(field, new),
                }
            )
        title = (
            lines[0]["label"] + " changed"
            if len(lines) == 1
            else OPERATIONS.get(operation, "Edited")
        )
    else:
        title = _words(event.action)
    return {
        "id": event.id,
        "at": event.at,
        "actor": event.actor_label,
        "actor_kind": event.actor_kind,
        "action": event.action,
        "title": title,
        "lines": lines,
    }


def for_record(
    session: Session,
    record_type: RecordType,
    record: Any,
    *,
    limit: int = 300,
    internal: bool = True,
) -> list[dict[str, Any]]:
    """The record's history, newest first. Permission to see it is the caller's to check.

    The reviews of a record are part of its story, so what happened in them is included.
    ``internal`` says whether the reader may know what reviewers found and said among
    themselves; without it those entries say only that something happened, or are left out.
    """
    from govwren.db.models import Review, ReviewTask

    own = or_(
        (Event.subject_type == record_type.key) & (Event.subject_id == record.id),
        (Event.parent_type == record_type.key) & (Event.parent_id == record.id),
    )
    review_ids = list(
        session.scalars(
            select(Review.id).where(
                Review.subject_type == record_type.key, Review.subject_id == record.id
            )
        )
    )
    tasks: dict[int, str] = {}
    if review_ids:
        own = or_(own, (Event.parent_type == "review") & Event.parent_id.in_(review_ids))
        tasks = dict(
            session.execute(
                select(ReviewTask.id, ReviewTask.review_function).where(
                    ReviewTask.review_id.in_(review_ids)
                )
            ).all()  # type: ignore[arg-type]
        )
    events = session.scalars(select(Event).where(own).order_by(Event.id.desc()).limit(limit)).all()
    lookups = _Lookups(session, internal=internal, tasks=tasks)
    lookups.kind_vocabulary = KIND_VOCABULARY.get(record_type.key, "system_kinds")
    entries = []
    for event in events:
        hidden = (
            event.subject_type == "comment"
            and (event.changes.get("visibility") or [None, None])[1] != "requester"
        )
        if hidden and not internal:
            continue
        entries.append(_entry(event, record_type, lookups))
    return entries
