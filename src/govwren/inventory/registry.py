"""The kinds of record in the inventory."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.core.errors import NotFound
from govwren.db.base import Base
from govwren.db.models import AISystem, Dataset, Model, UseCase, Vendor
from govwren.db.refs import parse_ref


@dataclass(frozen=True)
class RecordType:
    key: str  # the name used in events, owners, and links
    model: type[Base]
    prefix: str
    path: str  # its place in the API and the web app
    label: str
    has_unit: bool = True


USE_CASE = RecordType("use_case", UseCase, "UC", "use-cases", "use case")
SYSTEM = RecordType("system", AISystem, "SYS", "systems", "AI system")
VENDOR = RecordType("vendor", Vendor, "VND", "vendors", "vendor", has_unit=False)

MODEL = RecordType("model", Model, "MDL", "models", "model")
DATASET = RecordType("dataset", Dataset, "DS", "datasets", "dataset")

TYPES = {record_type.key: record_type for record_type in (USE_CASE, SYSTEM, MODEL, DATASET, VENDOR)}
BY_PREFIX = {record_type.prefix: record_type for record_type in TYPES.values()}
BY_PATH = {record_type.path: record_type for record_type in TYPES.values()}


def find_any(session: Session, ref: str) -> tuple[RecordType, Base]:
    """The record with this reference, whatever kind it is."""
    parsed = parse_ref(ref)
    if parsed is None or parsed[0] not in BY_PREFIX:
        raise NotFound(f"There is no record {ref}.")
    record_type = BY_PREFIX[parsed[0]]
    return record_type, find(session, record_type, ref)


def find(session: Session, record_type: RecordType, ref: str) -> Base:
    """The record with this reference. What the asker may see of it is the caller's to check."""
    parsed = parse_ref(ref)
    if parsed is None or parsed[0] != record_type.prefix:
        raise NotFound(f"There is no {record_type.label} {ref}.")
    model = record_type.model
    record = session.scalars(select(model).where(model.ref == ref.strip().upper())).first()  # type: ignore[attr-defined]
    if record is None:
        raise NotFound(f"There is no {record_type.label} {ref}.")
    return record
