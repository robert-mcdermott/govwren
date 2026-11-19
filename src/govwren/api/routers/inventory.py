"""The inventory: use cases, AI systems, and vendors."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from govwren import reporting
from govwren.access.policy import current
from govwren.api.common import clamp_limit, decode_cursor, encode_cursor, envelope, reading, writing
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.inventory import access, agreements, catalog, fields, history, links, records
from govwren.inventory.registry import (
    DATASET,
    MODEL,
    SYSTEM,
    USE_CASE,
    VENDOR,
    RecordType,
    find,
    find_any,
)
from govwren.program import settings, vocab

router = APIRouter(prefix="/api/v1", tags=["inventory"])


class UseCaseBody(BaseModel):
    """A use case. On a change, send only what changes, with the ``version`` you were editing."""

    version: int | None = None
    name: str | None = Field(default=None, max_length=400)
    summary: str | None = None
    purpose: str | None = None
    org_unit_id: int | None = None
    domain: str | None = None
    stage: str | None = None
    decision_role: str | None = None
    human_oversight: str | None = None
    affected_groups: list[str] | None = None
    data_class: str | None = None
    data_categories: list[str] | None = None
    outputs_used_for: list[str] | None = None
    tags: list[str] | None = None
    restricted: bool | None = None


class SystemBody(BaseModel):
    """An AI system. The catalog fields can be set only by governance."""

    version: int | None = None
    name: str | None = Field(default=None, max_length=400)
    summary: str | None = None
    org_unit_id: int | None = None
    kind: str | None = None
    vendor: str | None = Field(default=None, description="The vendor's reference, such as VND-0003")
    embedded_in: str | None = None
    hosting: str | None = None
    edition: str | None = None
    access_path: str | None = None
    version_label: str | None = None
    url: str | None = None
    regulatory_status: str | None = None
    data_handling: dict[str, Any] | None = None
    agent_profile: dict[str, Any] | None = Field(
        default=None, description="For a system that acts: send only the fields that change"
    )
    tags: list[str] | None = None
    restricted: bool | None = None
    status: str | None = None
    catalog_status: str | None = None
    permitted_data_class: str | None = None
    excluded_data_categories: list[str] | None = None
    terms: str | None = None


class VendorBody(BaseModel):
    """A vendor. Its standing can be set only by governance."""

    version: int | None = None
    name: str | None = Field(default=None, max_length=400)
    summary: str | None = None
    website: str | None = None
    contacts: list[dict[str, Any]] | None = None
    notes: str | None = None
    tags: list[str] | None = None
    status: str | None = None
    due_diligence_status: str | None = None


class DescribedBody(BaseModel):
    """A model or a dataset. Its fields are listed by ``GET /record-types``. On a change, send
    only what changes, with the ``version`` you were editing."""

    model_config = ConfigDict(extra="allow")
    version: int | None = None
    name: str | None = Field(default=None, max_length=400)


class LinkBody(BaseModel):
    source: str = Field(description="The reference of the record the link starts from")
    relation: str
    target: str = Field(description="The reference of the record it points to")
    note: str | None = Field(default=None, max_length=300)


class ReferencesBody(BaseModel):
    references: list[dict[str, Any]] = Field(max_length=50)


class AgreementBody(BaseModel):
    kind: str | None = None
    title: str | None = Field(default=None, max_length=200)
    reference: str | None = None
    effective_on: str | None = None
    expires_on: str | None = None
    auto_renews: bool | None = None
    notice_days: int | None = None
    owner_id: int | None = None
    notes: str | None = None


class OwnersBody(BaseModel):
    owners: list[dict[str, Any]]


class SystemsBody(BaseModel):
    systems: list[str] = Field(description="References of the AI systems the use case uses")


class VisibilityBody(BaseModel):
    visibility: str


@router.get("/vocabularies", summary="The lists of values records choose from")
def vocabularies(request: Request) -> dict[str, Any]:
    with reading(request) as session:
        return envelope(vocab.all_(session))


@router.get("/admin/inventory", summary="How much of the inventory everyone can see")
def show_settings(request: Request) -> dict[str, Any]:
    with reading(request) as session:
        return envelope({"visibility": access.visibility(session), "choices": access.VISIBILITIES})


@router.put("/admin/inventory", summary="Change how much of the inventory everyone can see")
def save_settings(request: Request, body: VisibilityBody) -> dict[str, Any]:
    principal = current(request)
    if body.visibility not in access.VISIBILITIES:
        raise Invalid(
            "That is not one of the choices.",
            {"visibility": f"Use one of: {', '.join(access.VISIBILITIES)}."},
        )
    with writing(request, principal.actor) as session:
        settings.put(session, access.VISIBILITY_SETTING, body.visibility)
        return envelope({"visibility": body.visibility, "choices": access.VISIBILITIES})


def _values(body: BaseModel) -> dict[str, Any]:
    values = body.model_dump(exclude_unset=True)
    values.pop("version", None)
    return values


def _list(
    request: Request,
    record_type: RecordType,
    filters: dict[str, Any],
    sort: str,
    limit: int | None,
    cursor: str | None,
) -> dict[str, Any]:
    principal = current(request)
    size = clamp_limit(limit)
    offset = int((decode_cursor(cursor) or {}).get("offset", 0))
    with reading(request) as session:
        rows, total = records.search(
            session, principal, record_type, filters, sort=sort, limit=size, offset=offset
        )
        following = offset + len(rows)
        return envelope(
            records.cards(session, principal, record_type, rows),
            total=total,
            offset=offset,
            next_cursor=encode_cursor({"offset": following}) if following < total else None,
            prev_cursor=encode_cursor({"offset": max(0, offset - size)}) if offset > 0 else None,
            limit=size,
        )


def _show(request: Request, record_type: RecordType, ref: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(
            records.detail(session, principal, record_type, find(session, record_type, ref))
        )


def _create(request: Request, record_type: RecordType, body: BaseModel) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        record = records.create(session, principal, record_type, _values(body))
        return envelope(records.detail(session, principal, record_type, record))


def _update(request: Request, record_type: RecordType, ref: str, body: Any) -> dict[str, Any]:
    principal = current(request)
    if body.version is None:
        raise Invalid(
            "The change was not saved.", {"version": "Send the version you were editing."}
        )
    with writing(request, principal.actor) as session:
        record = find(session, record_type, ref)
        if access.sight(session, principal, record_type, record) is None:
            raise NotFound(f"There is no {record_type.label} {ref}.")
        records.update(session, principal, record_type, record, _values(body), version=body.version)
        return envelope(records.detail(session, principal, record_type, record))


def _history(request: Request, record_type: RecordType, ref: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        record = find(session, record_type, ref)
        seen = access.sight(session, principal, record_type, record)
        if seen is None:
            raise NotFound(f"There is no {record_type.label} {ref}.")
        if seen != access.FULL:
            raise PermissionDenied("The history is shown to those who can see the whole record.")
        internal = principal.reads_all
        if record_type is USE_CASE:
            from govwren.review import service as review

            latest = review.latest_review(session, record)
            if latest is not None:  # the review's own rule decides, requester or not
                internal = review.sees_internal(session, principal, latest)
        return envelope(history.for_record(session, record_type, record, internal=internal))


def _owners(
    request: Request, record_type: RecordType, ref: str, body: OwnersBody
) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        record = find(session, record_type, ref)
        if access.sight(session, principal, record_type, record) is None:
            raise NotFound(f"There is no {record_type.label} {ref}.")
        records.set_owners(session, principal, record_type, record, body.owners)
        return envelope(records.detail(session, principal, record_type, record))


Q = Query("", max_length=200, description="Words to look for in the name, reference, and summary")
SORT = Query("-updated_at", description="A field to sort by; put - in front for descending")
LIMIT = Query(None, ge=1, le=200)


# --- Use cases ---


@router.get("/use-cases", summary="Find use cases")
def list_use_cases(
    request: Request,
    q: str = Q,
    unit: int | None = None,
    status: str | None = None,
    tier: int | None = None,
    domain: str | None = None,
    stage: str | None = None,
    data_class: str | None = None,
    owner: int | None = None,
    mine: bool = False,
    sort: str = SORT,
    limit: int | None = LIMIT,
    cursor: str | None = None,
) -> dict[str, Any]:
    filters = {
        "q": q,
        "unit": unit,
        "status": status,
        "tier": tier,
        "domain": domain,
        "stage": stage,
        "data_class": data_class,
        "owner": owner,
        "mine": mine,
    }
    return _list(request, USE_CASE, filters, sort, limit, cursor)


@router.post("/use-cases", status_code=201, summary="Add a use case, as a draft")
def create_use_case(request: Request, body: UseCaseBody) -> dict[str, Any]:
    return _create(request, USE_CASE, body)


@router.get("/use-cases/{ref}", summary="One use case")
def show_use_case(request: Request, ref: str) -> dict[str, Any]:
    return _show(request, USE_CASE, ref)


@router.patch("/use-cases/{ref}", summary="Change a use case")
def update_use_case(request: Request, ref: str, body: UseCaseBody) -> dict[str, Any]:
    return _update(request, USE_CASE, ref, body)


@router.put("/use-cases/{ref}/owners", summary="Set a use case's owners")
def set_use_case_owners(request: Request, ref: str, body: OwnersBody) -> dict[str, Any]:
    return _owners(request, USE_CASE, ref, body)


@router.put("/use-cases/{ref}/systems", summary="Set the AI systems a use case uses")
def set_use_case_systems(request: Request, ref: str, body: SystemsBody) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        record = find(session, USE_CASE, ref)
        if access.sight(session, principal, USE_CASE, record) is None:
            raise NotFound(f"There is no use case {ref}.")
        records.set_systems(session, principal, record, body.systems)  # type: ignore[arg-type]
        return envelope(records.detail(session, principal, USE_CASE, record))


@router.get("/use-cases/{ref}/history", summary="Everything that has happened to a use case")
def use_case_history(request: Request, ref: str) -> dict[str, Any]:
    return _history(request, USE_CASE, ref)


# --- AI systems ---


@router.get("/systems", summary="Find AI systems")
def list_systems(
    request: Request,
    q: str = Q,
    unit: int | None = None,
    status: str | None = None,
    kind: str | None = None,
    catalog_status: str | None = None,
    vendor: str | None = None,
    owner: int | None = None,
    mine: bool = False,
    sort: str = SORT,
    limit: int | None = LIMIT,
    cursor: str | None = None,
) -> dict[str, Any]:
    filters = {
        "q": q,
        "unit": unit,
        "status": status,
        "kind": kind,
        "catalog_status": catalog_status,
        "vendor": vendor,
        "owner": owner,
        "mine": mine,
    }
    return _list(request, SYSTEM, filters, sort, limit, cursor)


@router.post("/systems", status_code=201, summary="Add an AI system")
def create_system(request: Request, body: SystemBody) -> dict[str, Any]:
    return _create(request, SYSTEM, body)


@router.get("/systems/{ref}", summary="One AI system")
def show_system(request: Request, ref: str) -> dict[str, Any]:
    return _show(request, SYSTEM, ref)


@router.patch("/systems/{ref}", summary="Change an AI system")
def update_system(request: Request, ref: str, body: SystemBody) -> dict[str, Any]:
    return _update(request, SYSTEM, ref, body)


@router.put("/systems/{ref}/owners", summary="Set an AI system's owners")
def set_system_owners(request: Request, ref: str, body: OwnersBody) -> dict[str, Any]:
    return _owners(request, SYSTEM, ref, body)


@router.get("/systems/{ref}/history", summary="Everything that has happened to an AI system")
def system_history(request: Request, ref: str) -> dict[str, Any]:
    return _history(request, SYSTEM, ref)


# --- Vendors ---


@router.get("/vendors", summary="Find vendors")
def list_vendors(
    request: Request,
    q: str = Q,
    status: str | None = None,
    sort: str = SORT,
    limit: int | None = LIMIT,
    cursor: str | None = None,
) -> dict[str, Any]:
    return _list(request, VENDOR, {"q": q, "status": status}, sort, limit, cursor)


@router.post("/vendors", status_code=201, summary="Add a vendor")
def create_vendor(request: Request, body: VendorBody) -> dict[str, Any]:
    return _create(request, VENDOR, body)


@router.get("/vendors/{ref}", summary="One vendor")
def show_vendor(request: Request, ref: str) -> dict[str, Any]:
    return _show(request, VENDOR, ref)


@router.patch("/vendors/{ref}", summary="Change a vendor")
def update_vendor(request: Request, ref: str, body: VendorBody) -> dict[str, Any]:
    return _update(request, VENDOR, ref, body)


@router.get("/vendors/{ref}/history", summary="Everything that has happened to a vendor")
def vendor_history(request: Request, ref: str) -> dict[str, Any]:
    return _history(request, VENDOR, ref)


# --- Models and datasets ---


@router.get("/record-types", summary="The fields of models, datasets, and agent profiles")
def record_types(request: Request) -> dict[str, Any]:
    """What the described record types are made of, for anything that draws or fills them."""
    with reading(request) as session:
        return envelope(
            {
                "model": fields.describe(session, fields.MODEL),
                "dataset": fields.describe(session, fields.DATASET),
                "agent_profile": fields.describe(session, fields.AGENT),
                "links": {
                    key: links.allowed(key)
                    for key in ("use_case", "system", "model", "dataset", "vendor")
                },
            }
        )


@router.get("/models", summary="Find models")
def list_models(
    request: Request,
    q: str = Q,
    unit: int | None = None,
    status: str | None = None,
    kind: str | None = None,
    origin: str | None = None,
    catalog_status: str | None = None,
    data_class: str | None = None,
    vendor: str | None = None,
    owner: int | None = None,
    mine: bool = False,
    sort: str = SORT,
    limit: int | None = LIMIT,
    cursor: str | None = None,
) -> dict[str, Any]:
    filters = {
        "q": q, "unit": unit, "status": status, "kind": kind, "origin": origin,
        "catalog_status": catalog_status, "data_class": data_class, "vendor": vendor,
        "owner": owner, "mine": mine,
    }  # fmt: skip
    return _list(request, MODEL, filters, sort, limit, cursor)


@router.post("/models", status_code=201, summary="Add a model")
def create_model(request: Request, body: DescribedBody) -> dict[str, Any]:
    return _create(request, MODEL, body)


@router.get("/models/{ref}", summary="One model")
def show_model(request: Request, ref: str) -> dict[str, Any]:
    return _show(request, MODEL, ref)


@router.patch("/models/{ref}", summary="Change a model")
def update_model(request: Request, ref: str, body: DescribedBody) -> dict[str, Any]:
    return _update(request, MODEL, ref, body)


@router.put("/models/{ref}/owners", summary="Set a model's owners")
def set_model_owners(request: Request, ref: str, body: OwnersBody) -> dict[str, Any]:
    return _owners(request, MODEL, ref, body)


@router.get("/models/{ref}/history", summary="Everything that has happened to a model")
def model_history(request: Request, ref: str) -> dict[str, Any]:
    return _history(request, MODEL, ref)


@router.get("/datasets", summary="Find datasets")
def list_datasets(
    request: Request,
    q: str = Q,
    unit: int | None = None,
    status: str | None = None,
    data_class: str | None = None,
    identifiability: str | None = None,
    owner: int | None = None,
    mine: bool = False,
    sort: str = SORT,
    limit: int | None = LIMIT,
    cursor: str | None = None,
) -> dict[str, Any]:
    filters = {
        "q": q, "unit": unit, "status": status, "data_class": data_class,
        "identifiability": identifiability, "owner": owner, "mine": mine,
    }  # fmt: skip
    return _list(request, DATASET, filters, sort, limit, cursor)


@router.post("/datasets", status_code=201, summary="Add a dataset")
def create_dataset(request: Request, body: DescribedBody) -> dict[str, Any]:
    return _create(request, DATASET, body)


@router.get("/datasets/{ref}", summary="One dataset")
def show_dataset(request: Request, ref: str) -> dict[str, Any]:
    return _show(request, DATASET, ref)


@router.patch("/datasets/{ref}", summary="Change a dataset")
def update_dataset(request: Request, ref: str, body: DescribedBody) -> dict[str, Any]:
    return _update(request, DATASET, ref, body)


@router.put("/datasets/{ref}/owners", summary="Set a dataset's owners")
def set_dataset_owners(request: Request, ref: str, body: OwnersBody) -> dict[str, Any]:
    return _owners(request, DATASET, ref, body)


@router.get("/datasets/{ref}/history", summary="Everything that has happened to a dataset")
def dataset_history(request: Request, ref: str) -> dict[str, Any]:
    return _history(request, DATASET, ref)


# --- Links, references, and agreements ---


@router.post("/links", status_code=201, summary="Link one record to another")
def add_link(request: Request, body: LinkBody) -> dict[str, Any]:
    """The relation must be one that makes sense between the two kinds of record:
    ``GET /record-types`` lists them."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        links.add(session, principal, body.source, body.relation, body.target, body.note)
        record_type, record = find_any(session, body.source)
        return envelope(links.of(session, principal, record_type, record))


@router.delete("/links/{link_id}", summary="Remove a link")
def remove_link(request: Request, link_id: int) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        links.remove(session, principal, link_id)
        return envelope({"removed": True})


@router.put("/records/{ref}/references", summary="Set a record's pointers to other systems")
def set_references(request: Request, ref: str, body: ReferencesBody) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        record_type, record = find_any(session, ref)
        if access.sight(session, principal, record_type, record) is None:
            raise NotFound(f"There is no record {ref}.")
        return envelope(
            links.set_references(session, principal, record_type, record, body.references)
        )


@router.post("/vendors/{ref}/agreements", status_code=201, summary="Add an agreement")
def add_agreement(request: Request, ref: str, body: AgreementBody) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        vendor = find(session, VENDOR, ref)
        made = agreements.create(session, principal, vendor, body.model_dump(exclude_unset=True))  # type: ignore[arg-type]
        return envelope(agreements.view(session, made))


@router.patch("/agreements/{agreement_id}", summary="Change an agreement")
def update_agreement(request: Request, agreement_id: int, body: AgreementBody) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        changed = agreements.update(
            session, principal, agreement_id, body.model_dump(exclude_unset=True)
        )
        return envelope(agreements.view(session, changed))


@router.delete("/agreements/{agreement_id}", summary="Remove an agreement")
def remove_agreement(request: Request, agreement_id: int) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        agreements.remove(session, principal, agreement_id)
        return envelope({"removed": True})


# --- The catalog and the dashboard ---


class Registration(BaseModel):
    name: str = Field(max_length=400, description="What you will use it for")
    org_unit_id: int | None = None
    purpose: str | None = None
    data_class: str | None = None
    data_categories: list[str] = []
    everyday: bool = Field(
        default=False,
        description="It only produces output for a person to check: no decisions about people, "
        "no actions of its own",
    )


@router.get("/catalog", summary="The AI systems the organization has evaluated")
def catalog_listing(request: Request, q: str = Q) -> dict[str, Any]:
    with reading(request) as session:
        return envelope(catalog.listing(session, query=q))


@router.post("/catalog/{ref}/register", summary="Register a use of a catalog system")
def catalog_register(request: Request, ref: str, body: Registration) -> dict[str, Any]:
    """Approved at once if the use fits what the system is permitted for. If not, a request
    is begun with what was entered carried forward."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        system = catalog.find_system(session, ref)
        return envelope(catalog.register(session, principal, system, body.model_dump()))


@router.get("/dashboard", summary="Where the program stands")
def dashboard(request: Request) -> dict[str, Any]:
    with reading(request) as session:
        return envelope(reporting.dashboard(session))
