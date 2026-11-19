"""Finding things and keeping the inventory clean: one search across every kind of record,
lists saved under a name, what each record is missing, and records that are the same thing
entered twice."""

from __future__ import annotations

import re
from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import (
    Agreement,
    AISystem,
    EvidenceLink,
    ExternalRef,
    Model,
    RecordLink,
    RecordMerge,
    RecordOwner,
    SavedView,
)
from govwren.db.refs import parse_ref
from govwren.events import audit
from govwren.inventory import access, records
from govwren.inventory.registry import (
    BY_PREFIX,
    DATASET,
    MODEL,
    SYSTEM,
    USE_CASE,
    VENDOR,
    RecordType,
    find,
)

# --- One search ---------------------------------------------------------------------------


def everything(
    session: Session, principal: Principal, query: str, *, each: int = 6
) -> list[dict[str, Any]]:
    """Records of every kind that match, each cut to what the person may see. A reference
    typed whole comes first."""
    text = query.strip()
    if len(text) < 2:
        return []
    out: list[dict[str, Any]] = []
    parsed = parse_ref(text)
    exact: str | None = None
    if parsed and parsed[0] in BY_PREFIX:
        record_type = BY_PREFIX[parsed[0]]
        try:
            record = resolve(session, record_type, text)
        except NotFound:
            record = None
        if record is not None and access.sight(session, principal, record_type, record):
            exact = record.ref
            out.append(_hit(record_type, record, exact=True))
    for record_type in (USE_CASE, SYSTEM, MODEL, DATASET, VENDOR):
        rows, _total = records.search(
            session, principal, record_type, {"q": text}, sort="name", limit=each
        )
        out += [_hit(record_type, row) for row in rows if row.ref != exact]
    if (parsed and parsed[0] == "EV") or len(out) < each * 5:
        from govwren.evidence import service as evidence

        rows, _total = evidence.search(session, principal, {"q": text}, limit=each)
        out += [
            {
                "type": "evidence",
                "ref": e.ref,
                "name": e.title,
                "detail": e.file_name or "",
                "href": "/evidence?q=" + e.ref,
            }
            for e in rows
        ]
    return out


def _hit(record_type: RecordType, record: Any, *, exact: bool = False) -> dict[str, Any]:
    return {
        "type": record_type.key,
        "ref": record.ref,
        "name": record.name,
        "detail": (record.summary or "")[:140],
        "status": getattr(record, "catalog_status", None) or record.status,
        "href": f"/{record_type.path}/{record.ref}",
        "exact": exact,
    }


# --- Saved views --------------------------------------------------------------------------

LISTS = ("use_case", "system", "model", "dataset", "vendor", "evidence")
KEPT = re.compile(r"^[a-z_]{1,24}$")


def views(
    session: Session, principal: Principal, list_key: str | None = None
) -> list[dict[str, Any]]:
    statement = select(SavedView).where(SavedView.account_id == principal.account_id)
    if list_key:
        statement = statement.where(SavedView.list_key == list_key)
    rows = session.scalars(statement.order_by(SavedView.list_key, func.lower(SavedView.name)))
    return [{"id": v.id, "list": v.list_key, "name": v.name, "params": v.params} for v in rows]


def save_view(
    session: Session, principal: Principal, list_key: str, name: str, params: Mapping[str, Any]
) -> dict[str, Any]:
    """Keep a list's filters under a name. Saving under a name already used replaces it."""
    name = name.strip()
    errors = {}
    if list_key not in LISTS:
        errors["list"] = "That is not a list that can be saved."
    if not name or len(name) > 80:
        errors["name"] = "Give the view a name of up to 80 characters."
    cleaned = {
        str(key): str(value)[:200]
        for key, value in params.items()
        if KEPT.match(str(key)) and key != "cursor" and value not in (None, "")
    }
    if not cleaned:
        errors["params"] = "Choose a filter or a sort first: there is nothing to save."
    if errors or principal.account_id is None:
        raise Invalid("The view was not saved.", errors or {"name": "Sign in to save a view."})
    row = session.scalars(
        select(SavedView).where(
            SavedView.account_id == principal.account_id,
            SavedView.list_key == list_key,
            SavedView.name == name,
        )
    ).first()
    if row is None:
        row = SavedView(
            account_id=principal.account_id, list_key=list_key, name=name, created_at=utc_now()
        )
        session.add(row)
    row.params = cleaned
    session.flush()
    return {"id": row.id, "list": row.list_key, "name": row.name, "params": row.params}


def remove_view(session: Session, principal: Principal, view_id: int) -> None:
    row = session.get(SavedView, view_id)
    if row is None or row.account_id != principal.account_id:
        raise NotFound("There is no such view.")
    session.delete(row)
    session.flush()


# --- Completeness -------------------------------------------------------------------------


class Facts:
    """What completeness needs to know beyond a record's own fields, read once for every
    record instead of once for each: who has an accountable owner, and what is linked."""

    def __init__(self, session: Session) -> None:
        self.owned = {
            (kind, record_id)
            for kind, record_id in session.execute(
                select(RecordOwner.record_type, RecordOwner.record_id)
                .where(RecordOwner.kind == "accountable")
                .distinct()
            )
        }
        self.outgoing: set[tuple[str, int, str]] = set()
        self.incoming: set[tuple[str, int, str]] = set()
        for from_type, from_id, relation, to_type, to_id in session.execute(
            select(
                RecordLink.from_type, RecordLink.from_id, RecordLink.relation,
                RecordLink.to_type, RecordLink.to_id,
            )
        ):  # fmt: skip
            self.outgoing.add((from_type, from_id, relation))
            self.incoming.add((to_type, to_id, relation))
        self.agreed = set(session.scalars(select(Agreement.vendor_id).distinct()))


def _expected(
    session: Session, record_type: RecordType, record: Any, facts: Facts | None = None
) -> list[tuple[str, str, bool]]:
    """What a record of this kind should say, as (field, what is missing, whether it has it)."""

    def has(value: Any) -> bool:
        return value not in (None, "", [], {})

    owners = (
        1
        if record_type is VENDOR
        else int((record_type.key, record.id) in facts.owned)
        if facts is not None
        else session.execute(
            select(func.count())
            .select_from(RecordOwner)
            .where(
                RecordOwner.record_type == record_type.key,
                RecordOwner.record_id == record.id,
                RecordOwner.kind == "accountable",
            )
        ).scalar_one()
    )

    def linked(relation: str, *, incoming: bool = False) -> bool:
        if facts is not None:
            known = facts.incoming if incoming else facts.outgoing
            return (record_type.key, record.id, relation) in known
        column_type, column_id = (
            (RecordLink.to_type, RecordLink.to_id)
            if incoming
            else (RecordLink.from_type, RecordLink.from_id)
        )
        return bool(
            session.execute(
                select(func.count())
                .select_from(RecordLink)
                .where(
                    column_type == record_type.key,
                    column_id == record.id,
                    RecordLink.relation == relation,
                )
            ).scalar_one()
        )

    checks: list[tuple[str, str, bool]] = [("owners", "An accountable owner", bool(owners))]
    if record_type is USE_CASE:
        checks += [
            ("purpose", "What it is for", has(record.purpose)),
            ("domain", "The domain it belongs to", has(record.domain)),
            ("data_class", "The class of data involved", has(record.data_class)),
            ("human_oversight", "Who checks the outputs, and how", has(record.human_oversight)),
            ("systems", "The tool or model it uses", linked("uses")),
        ]
    elif record_type is SYSTEM:
        handling = record.data_handling or {}
        checks += [
            ("summary", "A summary of what it is", has(record.summary)),
            ("hosting", "Where it is hosted", has(record.hosting)),
            ("access_path", "How it is reached", has(record.access_path)),
            (
                "data_handling",
                "Whether the supplier trains on what is entered",
                handling.get("trains_on_inputs") in ("yes", "no"),
            ),
        ]
        if record.kind in ("vendor_product", "embedded_feature", "model_service"):
            checks.append(("vendor", "Its vendor", has(record.vendor_id)))
        if record.kind == "agent":
            profile = record.agent_profile or {}
            checks += [
                ("agent_profile.actions", "What the agent can change", has(profile.get("actions"))),
                (
                    "agent_profile.human_override",
                    "How a person stops the agent",
                    has(profile.get("human_override")),
                ),
                ("agent_profile.identity", "Who the agent acts as", has(profile.get("identity"))),
            ]
    elif record_type is MODEL:
        card = record.card or {}
        checks += [
            (
                "provider",
                "Who made it",
                has(record.provider) or record.origin in ("in_house", "fine_tuned"),
            ),
            ("version_label", "Its version", has(record.version_label)),
            ("intended_use", "Its intended use", has(card.get("intended_use"))),
        ]
        if record.origin != "commercial_api":
            checks += [
                ("license", "Its license", has(record.license) or record.origin == "in_house"),
                ("weights_source", "Where its weights came from", has(record.weights_source)),
                ("weights_checksum", "The checksum of its weights", has(record.weights_checksum)),
                ("weights_format", "The format of its weights", has(record.weights_format)),
                ("runs_on", "Where it runs", has(record.runs_on)),
            ]
        if record.origin in ("fine_tuned", "in_house"):
            checks.append(("trained_on", "The data it was trained on", linked("trained_on")))
        if record.origin == "fine_tuned":
            checks.append(("derived_from", "The model it was derived from", linked("derived_from")))
    elif record_type is DATASET:
        checks += [
            ("identifiability", "Whether people can be identified", has(record.identifiability)),
            ("source", "Where it came from", has(record.source)),
            ("location", "Where it is held", has(record.location)),
        ]
        if set(record.data_categories or []) & {"personal", "health", "human_subjects", "genetic"}:
            checks.append(("subjects", "Who the data is about", has(record.subjects)))
    else:
        agreed = (
            record.id in facts.agreed
            if facts is not None
            else session.execute(
                select(func.count()).select_from(Agreement).where(Agreement.vendor_id == record.id)
            ).scalar_one()
        )
        checks = [
            ("website", "Its website", has(record.website)),
            ("contacts", "A contact", has(record.contacts)),
            (
                "agreements",
                "An agreement, if you are a customer",
                bool(agreed) or record.status == "prospective",
            ),
        ]
    return checks


def completeness(
    session: Session, record_type: RecordType, record: Any, facts: Facts | None = None
) -> dict[str, Any]:
    """How complete one record is. Pass ``facts`` when scoring many records at once."""
    checks = _expected(session, record_type, record, facts)
    missing = [{"field": field, "label": label} for field, label, present in checks if not present]
    return {
        "score": round(100 * (len(checks) - len(missing)) / len(checks)) if checks else 100,
        "missing": missing,
    }


def completeness_by_type(session: Session) -> list[dict[str, Any]]:
    """How complete the records of each kind are, on average. Drafts and retired records
    are left out: one is not finished and the other no longer matters."""
    out = []
    facts = Facts(session)
    for record_type in (USE_CASE, SYSTEM, MODEL, DATASET, VENDOR):
        model: Any = record_type.model
        skip = ("draft", "retired", "withdrawn", "declined", "former")
        rows = list(session.scalars(select(model).where(model.status.notin_(skip))))
        scores = [completeness(session, record_type, row, facts)["score"] for row in rows]
        out.append(
            {
                "type": record_type.key,
                "records": len(rows),
                "average": round(sum(scores) / len(scores)) if scores else None,
                "complete": sum(1 for score in scores if score == 100),
                "href": f"/{record_type.path}",
            }
        )
    return out


# --- Duplicates and merging ---------------------------------------------------------------

MERGEABLE = (SYSTEM, MODEL, DATASET, VENDOR)
NOISE = re.compile(r"\b(inc|llc|ltd|corp|corporation|company|co|the|ai|labs?)\b|[^a-z0-9 ]")


def _key(name: str) -> str:
    return " ".join(NOISE.sub(" ", name.lower()).split())


def _same_thing(record_type: RecordType, a: Any, b: Any) -> float:
    """How alike two records are, from 0 to 1. Two editions of one product are not the same
    thing, and neither are two versions of one model."""
    if record_type is SYSTEM and (a.edition or "").lower() != (b.edition or "").lower():
        return 0.0
    if record_type is MODEL and (a.version_label or "") != (b.version_label or ""):
        return 0.0
    if record_type in (DATASET, MODEL) and a.org_unit_id != b.org_unit_id:
        return 0.0
    one, other = _key(a.name), _key(b.name)
    if not one or not other:
        return 0.0
    return 1.0 if one == other else SequenceMatcher(None, one, other).ratio()


def duplicates(
    session: Session, principal: Principal, record_type: RecordType, *, threshold: float = 0.88
) -> list[dict[str, Any]]:
    """Pairs of records that look like the same thing entered twice, likeliest first."""
    if not principal.reads_all:
        raise PermissionDenied("Only those who read the whole inventory can look for duplicates.")
    if record_type not in MERGEABLE:
        raise Invalid("Duplicates are not looked for there.", {"type": "Choose another kind."})
    model: Any = record_type.model
    gone = select(RecordMerge.from_id).where(RecordMerge.record_type == record_type.key)
    rows = list(session.scalars(select(model).where(model.id.notin_(gone)).order_by(model.id)))
    pairs = []
    for index, a in enumerate(rows):
        for b in rows[index + 1 :]:
            score = _same_thing(record_type, a, b)
            if score >= threshold:
                pairs.append(
                    {
                        "score": round(score, 2),
                        "records": [
                            {
                                "ref": r.ref,
                                "name": r.name,
                                "status": r.status,
                                "detail": getattr(r, "edition", None)
                                or getattr(r, "provider", None),
                            }
                            for r in (a, b)
                        ],
                    }
                )
    return sorted(pairs, key=lambda pair: -pair["score"])[:100]


def merged_into(session: Session, record_type: RecordType, record: Any) -> str | None:
    """The reference of the record this one was folded into, if it was."""
    return session.scalars(
        select(RecordMerge.into_ref).where(
            RecordMerge.record_type == record_type.key, RecordMerge.from_id == record.id
        )
    ).first()


def resolve(session: Session, record_type: RecordType, ref: str) -> Any:
    """The record with this reference, following it to whatever it was merged into."""
    record = find(session, record_type, ref)
    for _ in range(10):
        target = merged_into(session, record_type, record)
        if target is None:
            return record
        record = find(session, record_type, target)
    return record


def merge(
    session: Session, principal: Principal, record_type: RecordType, source: Any, target: Any
) -> Any:
    """Fold ``source`` into ``target``: everything that pointed to the one now points to the
    other, and the old reference leads to the new record."""
    if not principal.edits_all:
        raise PermissionDenied("Only governance can merge records.")
    if record_type not in MERGEABLE:
        raise Invalid("These cannot be merged.", {"type": "Use cases are not merged."})
    if source.id == target.id:
        raise Invalid("These cannot be merged.", {"into": "Choose a different record."})
    if merged_into(session, record_type, source) or merged_into(session, record_type, target):
        raise Conflict("One of these has already been merged into another record.")
    key = record_type.key
    with audit.operation(session, f"{key}.merge", source=source.ref, into=target.ref):
        session.flush()
        # Links, owners, references, and evidence are rows the history watches, so they are
        # moved one at a time and never rewritten in bulk.
        for link in session.scalars(
            select(RecordLink).where(
                ((RecordLink.from_type == key) & (RecordLink.from_id == source.id))
                | ((RecordLink.to_type == key) & (RecordLink.to_id == source.id))
            )
        ).all():
            start = (
                link.from_type,
                target.id if (link.from_type, link.from_id) == (key, source.id) else link.from_id,
            )
            end = (
                link.to_type,
                target.id if (link.to_type, link.to_id) == (key, source.id) else link.to_id,
            )
            session.delete(link)
            session.flush()
            exists = session.scalars(
                select(RecordLink.id).where(
                    RecordLink.from_type == start[0],
                    RecordLink.from_id == start[1],
                    RecordLink.relation == link.relation,
                    RecordLink.to_type == end[0],
                    RecordLink.to_id == end[1],
                )
            ).first()
            if exists is None and start != end:
                session.add(
                    RecordLink(
                        from_type=start[0],
                        from_id=start[1],
                        relation=link.relation,
                        to_type=end[0],
                        to_id=end[1],
                        note=link.note,
                    )
                )
        have_owners = {
            (o.account_id, o.kind)
            for o in session.scalars(
                select(RecordOwner).where(
                    RecordOwner.record_type == key, RecordOwner.record_id == target.id
                )
            )
        }
        for owner in session.scalars(
            select(RecordOwner).where(
                RecordOwner.record_type == key, RecordOwner.record_id == source.id
            )
        ).all():
            if (owner.account_id, owner.kind) not in have_owners and owner.kind != "accountable":
                session.add(
                    RecordOwner(
                        record_type=key,
                        record_id=target.id,
                        account_id=owner.account_id,
                        kind=owner.kind,
                    )
                )
        for model, type_column, id_column in (
            (ExternalRef, ExternalRef.record_type, ExternalRef.record_id),
            (EvidenceLink, EvidenceLink.subject_type, EvidenceLink.subject_id),
        ):
            for row in session.scalars(
                select(model).where(type_column == key, id_column == source.id)
            ).all():
                if model is ExternalRef:
                    session.add(
                        ExternalRef(
                            record_type=key,
                            record_id=target.id,
                            kind=row.kind,
                            identifier=row.identifier,
                            label=row.label,
                            url=row.url,
                        )
                    )
                else:
                    twin = session.scalars(
                        select(EvidenceLink.id).where(
                            EvidenceLink.evidence_id == row.evidence_id,
                            EvidenceLink.subject_type == key,
                            EvidenceLink.subject_id == target.id,
                        )
                    ).first()
                    if twin is None:
                        session.add(
                            EvidenceLink(
                                evidence_id=row.evidence_id, subject_type=key, subject_id=target.id
                            )
                        )
        if record_type is VENDOR:
            for dependent in (AISystem, Model):
                for row in session.scalars(
                    select(dependent).where(dependent.vendor_id == source.id)
                ).all():
                    row.vendor_id = target.id
            for agreement in session.scalars(
                select(Agreement).where(Agreement.vendor_id == source.id)
            ).all():
                agreement.vendor_id = target.id
        source.status = "former" if record_type is VENDOR else "retired"
        if hasattr(source, "catalog_status") and source.catalog_status != "not_listed":
            source.catalog_status = "retired"
        source.updated_at = target.updated_at = utc_now()
        source.version += 1
        session.add(
            RecordMerge(
                record_type=key,
                from_id=source.id,
                from_ref=source.ref,
                into_id=target.id,
                into_ref=target.ref,
                merged_by=principal.account_id,
                merged_at=utc_now(),
            )
        )
        session.flush()
    return target
