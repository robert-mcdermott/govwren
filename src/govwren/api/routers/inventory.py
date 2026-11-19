"""The inventory: use cases, AI systems, and vendors."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from govwren.access.policy import current
from govwren.api.common import clamp_limit, decode_cursor, encode_cursor, envelope, reading, writing
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.inventory import access, history, records
from govwren.inventory.registry import SYSTEM, USE_CASE, VENDOR, RecordType, find
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
        return envelope(history.for_record(session, record_type, record))


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
