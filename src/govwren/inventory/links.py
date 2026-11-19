"""Typed links between records, and pointers from records to things in other systems.

The links are the dependency graph: which use case uses which system, which system is built
on which model, which model was trained on which dataset. The set of relations is fixed, and
each is allowed only between the kinds of record it makes sense for, so that the graph can
be reasoned about.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import ExternalRef, Model, RecordLink
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import TYPES, USE_CASE, RecordType, find_any
from govwren.program import vocab

# relation -> the (from, to) pairs it may join
RELATIONS: dict[str, set[tuple[str, str]]] = {
    "uses": {("use_case", "system"), ("use_case", "model")},
    "processes": {("use_case", "dataset"), ("system", "dataset")},
    "built_on": {("system", "model")},
    "derived_from": {("model", "model")},
    "trained_on": {("model", "dataset")},
    "evaluated_on": {("model", "dataset")},
    "embedded_in": {("system", "system")},
    "depends_on": {("system", "system")},
    "replaces": {(key, key) for key in ("use_case", "system", "model", "dataset", "vendor")},
}
# How each relation reads from either end.
PHRASES = {
    "uses": ("Uses", "Used by"),
    "processes": ("Processes", "Processed by"),
    "built_on": ("Built on", "Built into"),
    "derived_from": ("Derived from", "Base of"),
    "trained_on": ("Trained on", "Used to train"),
    "evaluated_on": ("Evaluated on", "Used to evaluate"),
    "embedded_in": ("Embedded in", "Contains"),
    "depends_on": ("Depends on", "Depended on by"),
    "replaces": ("Replaces", "Replaced by"),
}
NO_LOOPS = {"derived_from", "embedded_in", "depends_on", "replaces"}
OPEN_TO_EDIT = ("draft", "returned")


def chip(record_type: RecordType, record: Any) -> dict[str, Any]:
    """A record in one line, for showing beside another record."""
    return {
        "type": record_type.key,
        "ref": record.ref,
        "name": record.name,
        "status": record.status,
        "catalog_status": getattr(record, "catalog_status", None),
        "data_class": getattr(record, "data_class", None),
        "tier": getattr(record, "tier", None),
        "kind": getattr(record, "kind", None),
    }


def _reaches(
    session: Session, relation: str, start: tuple[str, int], goal: tuple[str, int]
) -> bool:
    """Whether following ``relation`` from ``start`` arrives at ``goal``."""
    seen, frontier = set(), [start]
    while frontier:
        here = frontier.pop()
        if here == goal:
            return True
        if here in seen:
            continue
        seen.add(here)
        for link in session.scalars(
            select(RecordLink).where(
                RecordLink.relation == relation,
                RecordLink.from_type == here[0],
                RecordLink.from_id == here[1],
            )
        ):
            frontier.append((link.to_type, link.to_id))
    return False


def allowed(from_type: str) -> list[dict[str, Any]]:
    """The links a record of this kind may make: what the web app offers."""
    return [
        {"relation": relation, "label": PHRASES[relation][0], "to": to}
        for relation, pairs in RELATIONS.items()
        for source, to in sorted(pairs)
        if source == from_type
    ]


def add(
    session: Session, principal: Principal, from_ref: str, relation: str, to_ref: str,
    note: str | None = None,
) -> RecordLink:  # fmt: skip
    from_type, source = find_any(session, from_ref)
    to_type, target = find_any(session, to_ref)
    if access.sight(session, principal, from_type, source) is None:
        raise NotFound(f"There is no record {from_ref}.")
    if access.sight(session, principal, to_type, target) is None:
        raise NotFound(f"There is no record {to_ref}.")
    if relation not in RELATIONS or (from_type.key, to_type.key) not in RELATIONS[relation]:
        raise Invalid(
            "The link was not made.",
            {"relation": f"A {from_type.label} cannot be linked to a {to_type.label} that way."},
        )
    if not access.can_edit(session, principal, from_type, source):
        raise PermissionDenied(f"You cannot edit this {from_type.label}.")
    if from_type is USE_CASE and source.status not in OPEN_TO_EDIT and not principal.edits_all:  # type: ignore[attr-defined]
        raise Conflict(
            "Once a request has been submitted, what it uses is part of what was reviewed. "
            "Declare a change to alter it."
        )
    here, there = (from_type.key, source.id), (to_type.key, target.id)  # type: ignore[attr-defined]
    if here == there:
        raise Invalid("The link was not made.", {"to": "A record cannot be linked to itself."})
    if relation in NO_LOOPS and _reaches(session, relation, there, here):
        raise Invalid("The link was not made.", {"to": "That would make a loop."})
    existing = session.scalars(
        select(RecordLink).where(
            RecordLink.from_type == here[0],
            RecordLink.from_id == here[1],
            RecordLink.relation == relation,
            RecordLink.to_type == there[0],
            RecordLink.to_id == there[1],
        )
    ).first()
    if existing is not None:
        return existing
    with audit.operation(session, "link.add", relation=relation, to=target.ref):  # type: ignore[attr-defined]
        link = RecordLink(
            from_type=here[0], from_id=here[1], relation=relation, to_type=there[0],
            to_id=there[1], note=(note or "").strip()[:300] or None,
        )  # fmt: skip
        session.add(link)
        session.flush()
        if isinstance(source, Model) and relation in ("trained_on", "derived_from"):
            _inherit(session, source)
    return link


def _inherit(session: Session, model: Model) -> None:
    """A model is never less sensitive than what it was trained on."""
    from govwren.inventory.records import sensitivity_floor

    floor = sensitivity_floor(session, model)[0]
    if floor and vocab.rank(session, "data_classes", model.data_class) < vocab.rank(
        session, "data_classes", floor
    ):
        model.data_class = floor
        session.flush()


def remove(session: Session, principal: Principal, link_id: int) -> None:
    link = session.get(RecordLink, link_id)
    if link is None or link.from_type not in TYPES:
        raise NotFound("There is no such link.")
    from_type = TYPES[link.from_type]
    source = session.get(from_type.model, link.from_id)
    if source is None or access.sight(session, principal, from_type, source) is None:
        raise NotFound("There is no such link.")
    if not access.can_edit(session, principal, from_type, source):
        raise PermissionDenied(f"You cannot edit this {from_type.label}.")
    if from_type is USE_CASE and source.status not in OPEN_TO_EDIT and not principal.edits_all:  # type: ignore[attr-defined]
        raise Conflict("What a submitted request uses is part of what was reviewed.")
    with audit.operation(session, "link.remove", relation=link.relation):
        session.delete(link)
        session.flush()


def of(
    session: Session, principal: Principal, record_type: RecordType, record: Any
) -> dict[str, Any]:
    """What a record points to and what points to it, as far as the person may see."""
    here = (record_type.key, record.id)
    rows = session.scalars(
        select(RecordLink)
        .where(
            or_(
                (RecordLink.from_type == here[0]) & (RecordLink.from_id == here[1]),
                (RecordLink.to_type == here[0]) & (RecordLink.to_id == here[1]),
            )
        )
        .order_by(RecordLink.relation, RecordLink.id)
    ).all()
    setting = access.visibility(session)
    outgoing, incoming, hidden = [], [], 0
    for link in rows:
        forward = (link.from_type, link.from_id) == here
        other_type = TYPES.get(link.to_type if forward else link.from_type)
        other = (
            session.get(other_type.model, link.to_id if forward else link.from_id)
            if other_type
            else None
        )
        if other is None or other_type is None:
            continue
        if access.sight(session, principal, other_type, other, setting=setting) is None:
            hidden += 1
            continue
        entry = {
            "id": link.id,
            "relation": link.relation,
            "label": PHRASES.get(link.relation, (link.relation, link.relation))[
                0 if forward else 1
            ],
            "note": link.note,
            "record": chip(other_type, other),
        }
        (outgoing if forward else incoming).append(entry)
    return {"outgoing": outgoing, "incoming": incoming, "hidden": hidden}


# --- Pointers to other systems ------------------------------------------------------------


def references(session: Session, record_type: RecordType, record: Any) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(ExternalRef)
        .where(ExternalRef.record_type == record_type.key, ExternalRef.record_id == record.id)
        .order_by(ExternalRef.kind, ExternalRef.id)
    )
    return [
        {"id": r.id, "kind": r.kind, "identifier": r.identifier, "label": r.label, "url": r.url}
        for r in rows
    ]


def set_references(
    session: Session, principal: Principal, record_type: RecordType, record: Any,
    wanted: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:  # fmt: skip
    """Replace a record's pointers to other systems with the list given."""
    if not access.can_edit(session, principal, record_type, record):
        raise PermissionDenied(f"You cannot edit this {record_type.label}.")
    kinds = vocab.keys(session, "reference_kinds")
    cleaned: list[tuple[str, str, str | None, str | None]] = []
    errors: dict[str, str] = {}
    for index, item in enumerate(wanted):
        where = f"references[{index}]"
        kind = str(item.get("kind") or "")
        identifier = str(item.get("identifier") or "").strip()
        label = str(item.get("label") or "").strip() or None
        url = str(item.get("url") or "").strip() or None
        if kind not in kinds:
            errors[where] = "Choose what kind of thing it points to."
        elif not identifier or len(identifier) > 200:
            errors[where] = "Give its number or name in the other system."
        elif url and not url.lower().startswith(("https://", "http://")):
            errors[where] = "Start the address with https://"
        elif (url and len(url) > 300) or (label and len(label) > 200):
            errors[where] = "Keep the label to 200 characters and the address to 300."
        else:
            cleaned.append((kind, identifier, label, url))
    if len(cleaned) > 50:
        errors["references"] = "Keep at most 50."
    if errors:
        raise Invalid("The references were not saved.", errors)
    cleaned = list(dict.fromkeys(cleaned))
    have = {
        (r.kind, r.identifier, r.label, r.url): r
        for r in session.scalars(
            select(ExternalRef).where(
                ExternalRef.record_type == record_type.key, ExternalRef.record_id == record.id
            )
        )
    }
    with audit.operation(session, f"{record_type.key}.references"):
        for key, row in have.items():
            if key not in cleaned:
                session.delete(row)
        for key in cleaned:
            if key not in have:
                session.add(
                    ExternalRef(
                        record_type=record_type.key,
                        record_id=record.id,
                        kind=key[0],
                        identifier=key[1],
                        label=key[2],
                        url=key[3],
                    )
                )
        session.flush()
    return references(session, record_type, record)


# --- The graph around a record --------------------------------------------------------------

MAX_DEPTH = 6
MAX_NODES = 150


def _edges_of(
    session: Session, here: tuple[str, int]
) -> list[tuple[tuple[str, int], str, tuple[str, int]]]:
    """Every edge that touches a record, as (from, relation, to). A system's or model's
    vendor is a column, not a link, but it is a dependency all the same."""
    from govwren.db.models import AISystem, Vendor

    kind, identifier = here
    found = [
        ((link.from_type, link.from_id), link.relation, (link.to_type, link.to_id))
        for link in session.scalars(
            select(RecordLink).where(
                or_(
                    (RecordLink.from_type == kind) & (RecordLink.from_id == identifier),
                    (RecordLink.to_type == kind) & (RecordLink.to_id == identifier),
                )
            )
        )
    ]
    if kind in ("system", "model"):
        record = session.get(TYPES[kind].model, identifier)
        if record is not None and record.vendor_id:  # type: ignore[attr-defined]
            found.append((here, "supplied_by", ("vendor", record.vendor_id)))  # type: ignore[attr-defined]
    elif kind == "vendor":
        for other, model in (("system", AISystem), ("model", Model)):
            for (other_id,) in session.execute(
                select(model.id).where(model.vendor_id == identifier)
            ):
                found.append(((other, other_id), "supplied_by", here))
    _ = Vendor
    return found


def graph(
    session: Session, principal: Principal, record_type: RecordType, record: Any, *, depth: int = 3
) -> dict[str, Any]:
    """Everything this record relies on, and everything that relies on it, out to ``depth``
    steps. Records the person may not see are counted and not shown, and nothing beyond
    them is followed."""
    depth = max(1, min(depth, MAX_DEPTH))
    phrases = {**PHRASES, "supplied_by": ("Supplied by", "Supplies")}
    centre = (record_type.key, record.id)
    setting = access.visibility(session)
    nodes: dict[tuple[str, int], dict[str, Any]] = {
        centre: {**chip(record_type, record), "distance": 0, "side": "centre"}
    }
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    hidden: set[tuple[str, int]] = set()
    truncated = False

    def look(key: tuple[str, int]) -> Any:
        kind = TYPES.get(key[0])
        found = session.get(kind.model, key[1]) if kind else None
        if found is None or kind is None:
            return None
        return found if access.sight(session, principal, kind, found, setting=setting) else False

    for side in ("upstream", "downstream"):
        frontier = [centre]
        seen = {centre}
        for distance in range(1, depth + 1):
            following: list[tuple[str, int]] = []
            for here in frontier:
                for source, relation, target in _edges_of(session, here):
                    forward = source == here
                    # Upstream follows what a record points to; downstream what points to it.
                    if forward != (side == "upstream"):
                        continue
                    other = target if forward else source
                    found = look(other)
                    if found is None:
                        continue
                    if found is False:
                        hidden.add(other)
                        continue
                    if other not in nodes:
                        if len(nodes) >= MAX_NODES:
                            truncated = True
                            continue
                        nodes[other] = {
                            **chip(TYPES[other[0]], found),
                            "distance": distance,
                            "side": side,
                            "via": phrases.get(relation, (relation, relation))[0 if forward else 1],
                            "through": nodes[here]["ref"] if here != centre else None,
                        }
                    if other in nodes:
                        a, b = nodes[source]["ref"], nodes[target]["ref"]
                        edges[(a, relation, b)] = {
                            "from": a,
                            "to": b,
                            "relation": relation,
                            "label": phrases.get(relation, (relation, relation))[0],
                        }
                    if other not in seen:
                        seen.add(other)
                        following.append(other)
            frontier = following
    ordered = sorted(
        nodes.values(), key=lambda n: (n["side"] != "centre", n["side"], n["distance"], n["name"])
    )
    return {
        "centre": nodes[centre]["ref"],
        "nodes": ordered,
        "edges": list(edges.values()),
        "hidden": len(hidden),
        "truncated": truncated,
        "depth": depth,
    }
