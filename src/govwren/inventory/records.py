"""Creating, changing, finding, and showing inventory records."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import (
    Account,
    AISystem,
    Dataset,
    Model,
    OrgUnit,
    RecordLink,
    RecordOwner,
    UseCase,
    Vendor,
)
from govwren.db.models.inventory import (
    CATALOG_STATUSES,
    DUE_DILIGENCE,
    SYSTEM_STATUSES,
    VENDOR_STATUSES,
)
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.inventory import access, custom, fields
from govwren.inventory.registry import (
    DATASET,
    MODEL,
    SYSTEM,
    USE_CASE,
    VENDOR,
    RecordType,
    find,
)
from govwren.people import units
from govwren.program import vocab

USES = "uses"
SORTS = {
    "use_case": ("updated_at", "name", "ref", "tier", "status", "stage"),
    "system": ("updated_at", "name", "ref", "catalog_status", "kind"),
    "vendor": ("updated_at", "name", "ref", "status"),
    "model": ("updated_at", "name", "ref", "catalog_status", "kind", "origin"),
    "dataset": ("updated_at", "name", "ref", "data_class"),
}
TRAINS = ("yes", "no", "unknown")
OPEN_TO_EDIT = ("draft", "returned")
EDITABLE_AFTER_SUBMISSION = {"summary", "tags", "stage", "custom"}


class _Errors(dict[str, str]):
    def add(self, field: str, message: str) -> None:
        self.setdefault(field, message)


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _url(value: Any, field: str, errors: _Errors) -> str | None:
    text = _text(value)
    if text and not text.lower().startswith(("https://", "http://")):
        errors.add(field, "Start the address with https://")
        return None
    if text and len(text) > 300:
        errors.add(field, "Keep the address to 300 characters.")
        return None
    return text


def _choice(
    session: Session, name: str, value: Any, field: str, errors: _Errors, *, required: bool = False
) -> str | None:
    key = _text(value)
    if key is None:
        if required:
            errors.add(field, "Choose a value.")
        return None
    if key not in vocab.keys(session, name):
        errors.add(field, f"{key!r} is not one of the choices.")
        return None
    return key


def _choices(session: Session, name: str, values: Any, field: str, errors: _Errors) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list | tuple):
        errors.add(field, "Give a list of choices.")
        return []
    allowed = vocab.keys(session, name)
    chosen = list(dict.fromkeys(str(v) for v in values))
    unknown = [v for v in chosen if v not in allowed]
    if unknown:
        errors.add(field, f"{unknown[0]!r} is not one of the choices.")
    return chosen


def _tags(values: Any, errors: _Errors) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list | tuple):
        errors.add("tags", "Give a list of tags.")
        return []
    tags = list(dict.fromkeys(t for t in (str(v).strip().lower() for v in values) if t))
    if len(tags) > 20 or any(len(tag) > 40 for tag in tags):
        errors.add("tags", "Use at most 20 tags of up to 40 characters each.")
    return tags


def _unit(
    session: Session, principal: Principal, value: Any, errors: _Errors, *, required: bool
) -> int | None:
    if value in (None, ""):
        if required:
            errors.add("org_unit_id", "Say which unit this belongs to.")
        return None
    unit = session.get(OrgUnit, int(value)) if str(value).isdigit() else None
    if unit is None or unit.status != "active":
        errors.add("org_unit_id", "Choose a unit that is active.")
        return None
    own = principal.member_units | principal.steward_units
    if not principal.edits_all and own and unit.id not in own:
        errors.add("org_unit_id", "Choose one of your own units.")
        return None
    return unit.id


def _name(values: Mapping[str, Any], record: Any, errors: _Errors, creating: bool) -> None:
    if "name" in values or creating:
        name = _text(values.get("name"))
        if not name:
            errors.add("name", "Give it a name.")
        elif len(name) > 200:
            errors.add("name", "Keep the name to 200 characters.")
        else:
            record.name = name
    if "summary" in values:
        record.summary = _text(values["summary"])
    if "tags" in values:
        record.tags = _tags(values["tags"], errors)


def _apply_use_case(
    session: Session,
    principal: Principal,
    record: UseCase,
    values: Mapping[str, Any],
    creating: bool,
) -> _Errors:
    errors = _Errors()
    _name(values, record, errors, creating)
    if "org_unit_id" in values or creating:
        unit_id = _unit(session, principal, values.get("org_unit_id"), errors, required=True)
        if unit_id is not None:
            record.org_unit_id = unit_id
    for field in ("purpose", "human_oversight"):
        if field in values:
            setattr(record, field, _text(values[field]))
    for field, name in (
        ("domain", "domains"),
        ("decision_role", "decision_roles"),
        ("data_class", "data_classes"),
    ):
        if field in values:
            setattr(record, field, _choice(session, name, values[field], field, errors))
    if "stage" in values:
        stage = _choice(session, "stages", values["stage"], "stage", errors, required=True)
        if stage:
            record.stage = stage
    for field, name in (
        ("affected_groups", "affected_groups"),
        ("data_categories", "data_categories"),
        ("outputs_used_for", "outputs_used_for"),
    ):
        if field in values:
            setattr(record, field, _choices(session, name, values[field], field, errors))
    if "restricted" in values:
        record.restricted = bool(values["restricted"])
    return errors


def _apply_system(
    session: Session,
    principal: Principal,
    record: AISystem,
    values: Mapping[str, Any],
    creating: bool,
) -> _Errors:
    errors = _Errors()
    _name(values, record, errors, creating)
    if "org_unit_id" in values:
        record.org_unit_id = _unit(
            session, principal, values["org_unit_id"], errors, required=False
        )
    if "kind" in values or creating:
        kind = _choice(session, "system_kinds", values.get("kind"), "kind", errors, required=True)
        if kind:
            record.kind = kind
    for field, name in (("hosting", "hosting"), ("access_path", "access_paths")):
        if field in values:
            setattr(record, field, _choice(session, name, values[field], field, errors))
    for field in ("embedded_in", "edition", "version_label", "regulatory_status"):
        if field in values:
            setattr(record, field, _text(values[field]))
    if "url" in values:
        record.url = _url(values["url"], "url", errors)
    if "vendor" in values:
        ref = _text(values["vendor"])
        if ref is None:
            record.vendor_id = None
        else:
            try:
                record.vendor_id = find(session, VENDOR, ref).id  # type: ignore[attr-defined]
            except NotFound:
                errors.add("vendor", f"There is no vendor {ref}.")
    if "data_handling" in values:
        given = values["data_handling"] or {}
        trains = str(given.get("trains_on_inputs", "unknown"))
        if trains not in TRAINS:
            errors.add("data_handling", "Say yes, no, or unknown for training on inputs.")
        record.data_handling = {
            "trains_on_inputs": trains,
            "retention": _text(given.get("retention")),
            "regions": _text(given.get("regions")),
            "subprocessors": _text(given.get("subprocessors")),
        }
    if "restricted" in values:
        record.restricted = bool(values["restricted"])
    if "agent_profile" in values:
        given = values["agent_profile"] or {}
        if not isinstance(given, Mapping):
            errors.add("agent_profile", "Give the agent profile as named fields.")
        else:
            holder = type("Holder", (), {"agent_profile": dict(record.agent_profile or {})})()
            found = fields.apply(
                session, holder, given, fields.AGENT, creating=False, may_govern=True
            )
            for key, message in found.items():
                errors.add(f"agent_profile.{key}", message)
            # Fields are kept by name inside the profile.
            profile = dict(record.agent_profile or {})
            for field in fields.AGENT:
                if field.key in given:
                    value = getattr(holder, field.key, None)
                    if value in (None, [], ""):
                        profile.pop(field.key, None)
                    else:
                        profile[field.key] = value
            record.agent_profile = profile

    catalog = {
        "catalog_status",
        "permitted_data_class",
        "excluded_data_categories",
        "terms",
        "status",
    }
    touched = catalog & set(values)
    if touched and not access.can_edit_catalog(principal):
        raise PermissionDenied("Only governance can change a system's standing in the catalog.")
    if "catalog_status" in values:
        if values["catalog_status"] not in CATALOG_STATUSES:
            errors.add("catalog_status", "Choose one of the catalog standings.")
        else:
            record.catalog_status = values["catalog_status"]
    if "status" in values:
        if values["status"] not in SYSTEM_STATUSES:
            errors.add("status", "Use active or retired.")
        else:
            record.status = values["status"]
    if "permitted_data_class" in values:
        record.permitted_data_class = _choice(
            session, "data_classes", values["permitted_data_class"], "permitted_data_class", errors
        )
    if "excluded_data_categories" in values:
        record.excluded_data_categories = _choices(
            session,
            "data_categories",
            values["excluded_data_categories"],
            "excluded_data_categories",
            errors,
        )
    if "terms" in values:
        record.terms = _text(values["terms"])
    if (
        record.catalog_status in ("approved", "approved_with_restrictions")
        and not record.permitted_data_class
    ):
        errors.add(
            "permitted_data_class",
            "An approved system needs the highest data class it may be used with.",
        )
    return errors


def _apply_vendor(
    session: Session,
    principal: Principal,
    record: Vendor,
    values: Mapping[str, Any],
    creating: bool,
) -> _Errors:
    errors = _Errors()
    _name(values, record, errors, creating)
    if "website" in values:
        record.website = _url(values["website"], "website", errors)
    if "notes" in values:
        record.notes = _text(values["notes"])
    if "contacts" in values:
        contacts = []
        for contact in values["contacts"] or []:
            entry = {k: _text(contact.get(k)) for k in ("name", "email", "role")}
            if any(entry.values()):
                contacts.append(entry)
        if len(contacts) > 20:
            errors.add("contacts", "Keep at most 20 contacts.")
        record.contacts = contacts
    touched = {"status", "due_diligence_status", "signs_health_agreement"} & set(values)
    if touched and not access.can_edit_catalog(principal):
        raise PermissionDenied("Only governance can change a vendor's standing.")
    if "status" in values:
        if values["status"] not in VENDOR_STATUSES:
            errors.add("status", "Choose one of the vendor standings.")
        else:
            record.status = values["status"]
    if "due_diligence_status" in values:
        if values["due_diligence_status"] not in DUE_DILIGENCE:
            errors.add("due_diligence_status", "Choose one of the due-diligence states.")
        else:
            record.due_diligence_status = values["due_diligence_status"]
    if "signs_health_agreement" in values:
        if values["signs_health_agreement"] not in ("yes", "no", "unknown"):
            errors.add("signs_health_agreement", "Choose yes, no, or not known.")
        else:
            record.signs_health_agreement = values["signs_health_agreement"]
    return errors


def _apply_described(spec: Sequence[fields.Field]) -> Any:
    """The same for every record type whose fields are listed in ``fields``."""

    def apply(
        session: Session,
        principal: Principal,
        record: Any,
        values: Mapping[str, Any],
        creating: bool,
    ) -> _Errors:
        errors = _Errors()
        _name(values, record, errors, creating)
        if "org_unit_id" in values:
            record.org_unit_id = _unit(
                session, principal, values["org_unit_id"], errors, required=False
            )
        if "restricted" in values:
            record.restricted = bool(values["restricted"])
        if "vendor" in values and hasattr(record, "vendor_id"):
            ref = _text(values["vendor"])
            try:
                record.vendor_id = find(session, VENDOR, ref).id if ref else None  # type: ignore[attr-defined]
            except NotFound:
                errors.add("vendor", f"There is no vendor {ref}.")
        known = {"name", "summary", "tags", "org_unit_id", "restricted", "vendor", "custom"} | {
            field.key for field in spec
        }
        for key in values:
            if key not in known:
                errors.add(key, "This is not something this kind of record has.")
        found = fields.apply(
            session, record, values, spec, creating=creating,
            may_govern=access.can_edit_catalog(principal),
        )  # fmt: skip
        for key, message in found.items():
            errors.add(key, message)
        if isinstance(record, Model) and not errors:
            floor = sensitivity_floor(session, record)[0]
            if floor and vocab.rank(session, "data_classes", record.data_class) < vocab.rank(
                session, "data_classes", floor
            ):
                if values.get("data_class"):
                    wanted = vocab.labels(session, "data_classes").get(floor, floor)
                    errors.add(
                        "data_class",
                        f"It was trained on {wanted} data, so it is at least {wanted} itself.",
                    )
                else:
                    record.data_class = floor
        listed = getattr(record, "catalog_status", None) in (
            "approved",
            "approved_with_restrictions",
        )
        if listed and not errors and not record.permitted_data_class:
            errors.add("permitted_data_class", "Say what data an approved model may be used with.")
        return errors

    return apply


def sensitivity_floor(session: Session, model: Model) -> tuple[str | None, list[Dataset]]:
    """The least sensitive a model can be: as sensitive as the most sensitive data it, or any
    model it was derived from, was trained on. Returns that class and the datasets that set it."""
    if model.id is None:
        return None, []
    seen: set[int] = set()
    frontier = [model.id]
    datasets: dict[int, Dataset] = {}
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        for link in session.scalars(
            select(RecordLink).where(RecordLink.from_type == "model", RecordLink.from_id == current)
        ):
            if link.relation == "trained_on" and link.to_type == "dataset":
                found = session.get(Dataset, link.to_id)
                if found is not None:
                    datasets[found.id] = found
            elif link.relation == "derived_from" and link.to_type == "model":
                frontier.append(link.to_id)
    if not datasets:
        return None, []
    order = vocab.keys(session, "data_classes", active_only=False)
    rank = {key: index for index, key in enumerate(order)}
    top = max((rank.get(d.data_class or "", -1) for d in datasets.values()), default=-1)
    if top < 0:
        return None, []
    return order[top], [d for d in datasets.values() if rank.get(d.data_class or "", -1) == top]


_APPLY = {
    "use_case": _apply_use_case,
    "system": _apply_system,
    "vendor": _apply_vendor,
    "model": _apply_described(fields.MODEL),
    "dataset": _apply_described(fields.DATASET),
}


def create(
    session: Session, principal: Principal, record_type: RecordType, values: Mapping[str, Any]
) -> Any:
    """Add a record. Whoever adds a use case or system becomes its accountable owner."""
    now = utc_now()
    record = record_type.model(created_by=principal.account_id, created_at=now, updated_at=now)
    record.tags, record.restricted, record.version, record.custom = [], False, 1, {}
    if record_type is USE_CASE:
        record.status, record.stage = "draft", "proposed"
        record.affected_groups, record.data_categories, record.outputs_used_for = [], [], []
    elif record_type is SYSTEM:
        record.status, record.catalog_status = "active", "not_listed"
        record.excluded_data_categories, record.data_handling = [], {}
        record.agent_profile = {}
    elif record_type is MODEL:
        record.status, record.catalog_status = "active", "not_listed"
        record.modality, record.card, record.excluded_data_categories = [], {}, []
    elif record_type is DATASET:
        record.status, record.data_categories, record.subjects = "active", [], []
    else:
        record.status, record.due_diligence_status, record.contacts = (
            "prospective",
            "not_started",
            [],
        )
    errors = _APPLY[record_type.key](session, principal, record, values, True)
    if "custom" in values:
        errors = {**errors, **custom.apply(session, record_type, record, values["custom"])}
    if errors:
        raise Invalid(f"The {record_type.label} was not saved.", errors)
    with audit.operation(session, f"{record_type.key}.create"):
        record.ref = next_ref(session, record_type.prefix)
        session.add(record)
        session.flush()
        if record_type is not VENDOR and principal.account_id is not None:
            session.add(
                RecordOwner(
                    record_type=record_type.key,
                    record_id=record.id,
                    account_id=principal.account_id,
                    kind="accountable",
                )
            )
    return record


def update(
    session: Session,
    principal: Principal,
    record_type: RecordType,
    record: Any,
    values: Mapping[str, Any],
    *,
    version: int,
    reviewed: bool = False,
) -> Any:
    """Change a record. ``version`` is the one the editor was looking at: if someone else has
    saved since, the change is refused so that nothing is silently overwritten. ``reviewed``
    says the change is on its way to a review, which is what lets a decided record change."""
    if not access.can_edit(session, principal, record_type, record):
        raise PermissionDenied(f"You cannot edit this {record_type.label}.")
    if (
        record_type is USE_CASE
        and record.status not in OPEN_TO_EDIT
        and not principal.edits_all
        and not reviewed
    ):
        # What was reviewed is what was approved. Until changes can be declared and re-reviewed,
        # its owners may keep only the descriptive fields current.
        locked = sorted(set(values) - EDITABLE_AFTER_SUBMISSION)
        if locked:
            raise Conflict(
                "Once a request has been submitted, only its summary, tags, and stage can be "
                "edited here. Declare a change to alter anything else."
            )
    if version != record.version:
        raise Conflict(
            f"This {record_type.label} was changed by someone else while you were editing. "
            "Reload it, then make your change again."
        )
    with audit.operation(session, f"{record_type.key}.edit"):
        with session.no_autoflush:
            errors = _APPLY[record_type.key](session, principal, record, values, False)
            if "custom" in values:
                errors = {**errors, **custom.apply(session, record_type, record, values["custom"])}
        if errors:
            session.expire(record)  # put back what was there
            raise Invalid(f"The {record_type.label} was not saved.", errors)
        if session.is_modified(record):
            record.version += 1
            record.updated_at = utc_now()
            if record_type is SYSTEM and "catalog_status" in values:
                from govwren.inventory import catalog

                session.flush()
                catalog.answer_requests(session, record)
    return record


# --- Owners -------------------------------------------------------------------------------


def owners_of(
    session: Session, record_type: RecordType, ids: Iterable[int]
) -> dict[int, list[dict[str, Any]]]:
    """The people named on each record, accountable owners first."""
    ids = list(ids)
    found: dict[int, list[dict[str, Any]]] = defaultdict(list)
    if not ids:
        return found
    rows = session.execute(
        select(RecordOwner, Account)
        .join(Account, Account.id == RecordOwner.account_id)
        .where(RecordOwner.record_type == record_type.key, RecordOwner.record_id.in_(ids))
        .order_by(RecordOwner.kind, Account.display_name)
    )
    for owner, account in rows:
        found[owner.record_id].append(
            {
                "account_id": account.id,
                "name": account.display_name,
                "email": account.email,
                "kind": owner.kind,
                "active": account.status != "disabled",
            }
        )
    return found


def set_owners(
    session: Session,
    principal: Principal,
    record_type: RecordType,
    record: Any,
    owners: list[Mapping[str, Any]],
) -> None:
    if record_type is VENDOR:
        raise Invalid(
            "Vendors do not have owners.", {"owners": "Name contacts on the vendor instead."}
        )
    if not access.can_edit(session, principal, record_type, record):
        raise PermissionDenied(f"You cannot edit this {record_type.label}.")
    kinds = vocab.keys(session, "owner_kinds")
    wanted: set[tuple[int, str]] = set()
    for owner in owners:
        account = session.get(Account, int(owner.get("account_id") or 0))
        kind = str(owner.get("kind", ""))
        if account is None or account.status == "disabled":
            raise Invalid(
                "The owners were not saved.",
                {"owners": "Choose people whose accounts are not disabled."},
            )
        if kind not in kinds:
            raise Invalid(
                "The owners were not saved.", {"owners": f"{kind!r} is not a kind of owner."}
            )
        wanted.add((account.id, kind))
    if not any(kind == "accountable" for _, kind in wanted):
        raise Invalid(
            "The owners were not saved.", {"owners": "Every record needs an accountable owner."}
        )
    existing = session.scalars(
        select(RecordOwner).where(
            RecordOwner.record_type == record_type.key, RecordOwner.record_id == record.id
        )
    ).all()
    have = {(row.account_id, row.kind): row for row in existing}
    with audit.operation(session, f"{record_type.key}.owners"):
        for key, row in have.items():
            if key not in wanted:
                session.delete(row)
        for account_id, kind in sorted(wanted - set(have)):
            session.add(
                RecordOwner(
                    record_type=record_type.key,
                    record_id=record.id,
                    account_id=account_id,
                    kind=kind,
                )
            )


# --- Links --------------------------------------------------------------------------------


def systems_of(session: Session, use_case_ids: Iterable[int]) -> dict[int, list[AISystem]]:
    ids = list(use_case_ids)
    found: dict[int, list[AISystem]] = defaultdict(list)
    if not ids:
        return found
    rows = session.execute(
        select(RecordLink.from_id, AISystem)
        .join(AISystem, AISystem.id == RecordLink.to_id)
        .where(
            RecordLink.from_type == "use_case",
            RecordLink.relation == USES,
            RecordLink.to_type == "system",
            RecordLink.from_id.in_(ids),
        )
        .order_by(AISystem.name)
    )
    for use_case_id, system in rows:
        found[use_case_id].append(system)
    return found


def set_systems(session: Session, principal: Principal, use_case: UseCase, refs: list[str]) -> None:
    """Say which AI systems a use case uses."""
    if not access.can_edit(session, principal, USE_CASE, use_case):
        raise PermissionDenied("You cannot edit this use case.")
    wanted: dict[int, AISystem] = {}
    for ref in dict.fromkeys(refs):
        try:
            system = find(session, SYSTEM, ref)
        except NotFound as exc:
            raise Invalid("The systems were not saved.", {"systems": str(exc)}) from exc
        if access.sight(session, principal, SYSTEM, system) is None:
            raise Invalid(
                "The systems were not saved.", {"systems": f"There is no AI system {ref}."}
            )
        wanted[system.id] = system  # type: ignore[attr-defined]
    existing = session.scalars(
        select(RecordLink).where(
            RecordLink.from_type == "use_case",
            RecordLink.from_id == use_case.id,
            RecordLink.relation == USES,
            RecordLink.to_type == "system",
        )
    ).all()
    have = {row.to_id: row for row in existing}
    with audit.operation(session, "use_case.systems"):
        for system_id, row in have.items():
            if system_id not in wanted:
                session.delete(row)
        for system_id in wanted:
            if system_id not in have:
                session.add(
                    RecordLink(
                        from_type="use_case",
                        from_id=use_case.id,
                        relation=USES,
                        to_type="system",
                        to_id=system_id,
                    )
                )


def used_by(session: Session, principal: Principal, system: AISystem) -> tuple[list[UseCase], int]:
    """The use cases that use a system: those the person may see, and how many they may not."""
    rows = session.scalars(
        select(UseCase)
        .join(RecordLink, RecordLink.from_id == UseCase.id)
        .where(
            RecordLink.from_type == "use_case",
            RecordLink.relation == USES,
            RecordLink.to_type == "system",
            RecordLink.to_id == system.id,
        )
        .order_by(UseCase.name)
    ).all()
    setting = access.visibility(session)
    seen = [row for row in rows if access.sight(session, principal, USE_CASE, row, setting=setting)]
    return seen, len(rows) - len(seen)


# --- Finding ------------------------------------------------------------------------------


def search(
    session: Session,
    principal: Principal,
    record_type: RecordType,
    filters: Mapping[str, Any],
    *,
    sort: str = "-updated_at",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Any], int]:
    """Records the person may see that match the filters, and how many there are in all."""
    model: Any = record_type.model
    conditions = []
    seen = access.visible(session, principal, record_type)
    if seen is not None:
        conditions.append(seen)
    text = _text(filters.get("q"))
    if text:
        like = f"%{text.lower()}%"
        conditions.append(
            or_(
                func.lower(model.name).like(like),
                func.lower(model.ref).like(like),
                func.lower(func.coalesce(model.summary, "")).like(like),
            )
        )
    if filters.get("unit") and record_type.has_unit:
        conditions.append(
            model.org_unit_id.in_(units.with_descendants(session, [int(filters["unit"])]))
        )
    for field in (
        "status", "domain", "stage", "data_class", "kind", "catalog_status", "tier", "origin",
        "identifiability",
    ):  # fmt: skip
        value = filters.get(field)
        if field == "status" and value == "live" and record_type is USE_CASE:
            # Approved, with or without conditions: what the dashboard counts as in force.
            conditions.append(model.status.in_(("approved", "approved_with_conditions")))
        elif value not in (None, "") and hasattr(model, field):
            conditions.append(getattr(model, field) == (int(value) if field == "tier" else value))
    if filters.get("vendor") and record_type in (SYSTEM, MODEL):
        conditions.append(model.vendor_id == find(session, VENDOR, str(filters["vendor"])).id)  # type: ignore[attr-defined]
    owner = filters.get("owner")
    if filters.get("mine"):
        owner = principal.account_id
    if owner and record_type is not VENDOR:
        owned = select(RecordOwner.record_id).where(
            RecordOwner.record_type == record_type.key, RecordOwner.account_id == int(owner)
        )
        conditions.append(model.id.in_(owned))

    descending = sort.startswith("-")
    field = sort.lstrip("-")
    if field not in SORTS[record_type.key]:
        raise Invalid(
            "The list could not be sorted.",
            {"sort": f"Sort by one of: {', '.join(SORTS[record_type.key])}."},
        )
    column = getattr(model, field)
    order = [
        column.desc().nulls_last() if descending else column.asc().nulls_last(),
        model.id.desc(),
    ]
    total = session.execute(select(func.count()).select_from(model).where(*conditions)).scalar_one()
    rows = list(
        session.scalars(
            select(model).where(*conditions).order_by(*order).limit(limit).offset(offset)
        )
    )
    return rows, total


# --- Showing ------------------------------------------------------------------------------


def _owner_names(owners: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [o for o in owners if o["kind"] == "accountable"]


def _orphaned(owners: list[dict[str, Any]]) -> bool:
    accountable = _owner_names(owners)
    return bool(accountable) and not any(o["active"] for o in accountable)


def _health(session: Session, system: AISystem) -> dict[str, Any]:
    from govwren.inventory import agreements

    return agreements.health_view(session, system)


def _system_chip(system: AISystem) -> dict[str, Any]:
    return {
        "ref": system.ref,
        "name": system.name,
        "catalog_status": system.catalog_status,
        "kind": system.kind,
    }


def cards(
    session: Session, principal: Principal, record_type: RecordType, rows: list[Any]
) -> list[dict[str, Any]]:
    """Records as rows of a list, each cut to what the person may see of it."""
    ids = [row.id for row in rows]
    owners = owners_of(session, record_type, ids) if record_type is not VENDOR else {}
    systems = systems_of(session, ids) if record_type is USE_CASE else {}
    setting = access.visibility(session)
    vendors: dict[int, Vendor] = {}
    if record_type is SYSTEM:
        vendor_ids = {row.vendor_id for row in rows if row.vendor_id}
        if vendor_ids:
            vendors = {
                v.id: v for v in session.scalars(select(Vendor).where(Vendor.id.in_(vendor_ids)))
            }
    out = []
    for row in rows:
        mine = owners.get(row.id, [])
        owned = any(o["account_id"] == principal.account_id for o in mine)
        seen = access.sight(session, principal, record_type, row, owned=owned, setting=setting)
        card: dict[str, Any] = {
            "ref": row.ref,
            "name": row.name,
            "summary": row.summary,
            "status": row.status,
            "updated_at": row.updated_at,
            "sight": seen,
        }
        if record_type is USE_CASE:
            card.update(
                org_unit_id=row.org_unit_id,
                tier=row.tier,
                stage=row.stage,
                domain=row.domain,
                data_class=row.data_class if seen == access.FULL else None,
                owners=_owner_names(mine),
                orphaned=_orphaned(mine),
                systems=[_system_chip(s) for s in systems.get(row.id, [])],
            )
        elif record_type is SYSTEM:
            vendor = vendors.get(row.vendor_id)
            card.update(
                org_unit_id=row.org_unit_id,
                kind=row.kind,
                edition=row.edition,
                catalog_status=row.catalog_status,
                permitted_data_class=row.permitted_data_class,
                vendor={"ref": vendor.ref, "name": vendor.name} if vendor else None,
                owners=_owner_names(mine),
            )
        elif record_type is MODEL:
            card.update(
                org_unit_id=row.org_unit_id,
                kind=row.kind,
                origin=row.origin,
                provider=row.provider,
                version_label=row.version_label,
                catalog_status=row.catalog_status,
                permitted_data_class=row.permitted_data_class,
                data_class=row.data_class,
                owners=_owner_names(mine),
            )
        elif record_type is DATASET:
            card.update(
                org_unit_id=row.org_unit_id,
                data_class=row.data_class,
                data_categories=row.data_categories,
                identifiability=row.identifiability,
                owners=_owner_names(mine),
            )
        else:
            card.update(website=row.website, due_diligence_status=row.due_diligence_status)
        out.append(card)
    return out


def detail(
    session: Session,
    principal: Principal,
    record_type: RecordType,
    record: Any,
    *,
    sight: str | None = None,
) -> dict[str, Any]:
    """One record, cut to what the person may see of it. Raises NotFound if that is nothing.

    ``sight`` is given by a caller that has already decided what the person may see by
    another route: a reviewer reads the whole of a request they are asked to review.
    """
    seen = sight or access.sight(session, principal, record_type, record)
    if seen is None:
        raise NotFound(f"There is no {record_type.label} {record.ref}.")
    owners = (
        owners_of(session, record_type, [record.id]).get(record.id, [])
        if record_type is not VENDOR
        else []
    )
    base: dict[str, Any] = {
        "type": record_type.key,
        "ref": record.ref,
        "name": record.name,
        "summary": record.summary,
        "status": record.status,
        "sight": seen,
        "updated_at": record.updated_at,
    }
    if record_type is USE_CASE:
        base.update(
            org_unit_id=record.org_unit_id,
            purpose=record.purpose,
            tier=record.tier,
            stage=record.stage,
            domain=record.domain,
            owners=_owner_names(owners),
            systems=[_system_chip(s) for s in systems_of(session, [record.id]).get(record.id, [])],
        )
        if seen == access.SUMMARY:
            return base
        base.update(
            owners=owners,
            orphaned=_orphaned(owners),
            tier_source=record.tier_source,
            decision_role=record.decision_role,
            human_oversight=record.human_oversight,
            affected_groups=record.affected_groups,
            data_class=record.data_class,
            data_categories=record.data_categories,
            outputs_used_for=record.outputs_used_for,
            approved_until=record.approved_until,
            next_review_on=record.next_review_on,
        )
    elif record_type is SYSTEM:
        vendor = session.get(Vendor, record.vendor_id) if record.vendor_id else None
        seen_uses, hidden = used_by(session, principal, record)
        base.update(
            org_unit_id=record.org_unit_id,
            kind=record.kind,
            hosting=record.hosting,
            edition=record.edition,
            access_path=record.access_path,
            version_label=record.version_label,
            url=record.url,
            embedded_in=record.embedded_in,
            regulatory_status=record.regulatory_status,
            catalog_status=record.catalog_status,
            permitted_data_class=record.permitted_data_class,
            excluded_data_categories=record.excluded_data_categories,
            health_agreement=_health(session, record),
            terms=record.terms,
            data_handling=record.data_handling,
            agent_profile=record.agent_profile or {},
            owners=owners,
            orphaned=_orphaned(owners),
            vendor={"ref": vendor.ref, "name": vendor.name} if vendor else None,
            used_by=[
                {"ref": u.ref, "name": u.name, "status": u.status, "tier": u.tier}
                for u in seen_uses
            ],
            used_by_hidden=hidden,
        )
    elif record_type is MODEL:
        vendor = session.get(Vendor, record.vendor_id) if record.vendor_id else None
        floor, because = sensitivity_floor(session, record)
        base.update(
            fields.view(record, fields.MODEL),
            org_unit_id=record.org_unit_id,
            owners=owners,
            orphaned=_orphaned(owners),
            vendor={"ref": vendor.ref, "name": vendor.name} if vendor else None,
            data_class_floor=floor,
            data_class_from=[
                {"ref": d.ref, "name": d.name}
                for d in because
                if access.sight(session, principal, DATASET, d)
            ],
        )
    elif record_type is DATASET:
        base.update(
            fields.view(record, fields.DATASET),
            org_unit_id=record.org_unit_id,
            owners=owners,
            orphaned=_orphaned(owners),
        )
    else:
        from govwren.inventory import agreements

        systems = session.scalars(
            select(AISystem).where(AISystem.vendor_id == record.id).order_by(AISystem.name)
        )
        models = session.scalars(
            select(Model).where(Model.vendor_id == record.id).order_by(Model.name)
        )
        base.update(
            agreements=agreements.of(session, record),
            models=[
                {"ref": m.ref, "name": m.name, "catalog_status": m.catalog_status, "kind": m.kind}
                for m in models
                if access.sight(session, principal, MODEL, m)
            ],
            website=record.website,
            contacts=record.contacts,
            notes=record.notes,
            due_diligence_status=record.due_diligence_status,
            signs_health_agreement=record.signs_health_agreement,
            systems=[
                _system_chip(s) for s in systems if access.sight(session, principal, SYSTEM, s)
            ],
        )
    from govwren.evidence import service as evidence
    from govwren.inventory import links, tidy

    base.update(
        completeness=tidy.completeness(session, record_type, record),
        merged_into=tidy.merged_into(session, record_type, record),
        evidence=evidence.for_subject(session, principal, record_type.key, record.id),
        links=links.of(session, principal, record_type, record),
        references=links.references(session, record_type, record),
        tags=record.tags,
        custom=record.custom or {},
        restricted=record.restricted,
        version=record.version,
        created_at=record.created_at,
        can={
            "edit": access.can_edit(session, principal, record_type, record),
            "edit_catalog": access.can_edit_catalog(principal),
        },
    )
    return base
