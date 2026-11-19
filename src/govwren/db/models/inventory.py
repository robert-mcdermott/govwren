"""The inventory: use cases, AI systems, and vendors, with their owners and links."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from govwren.db.base import Base
from govwren.db.types import JsonType, UtcDateTime

USE_CASE_STATUSES = (
    "draft", "submitted", "in_review", "returned", "approved", "approved_with_conditions",
    "declined", "withdrawn", "suspended", "lapsed", "retired",
)  # fmt: skip
SYSTEM_STATUSES = ("active", "retired")
CATALOG_STATUSES = (
    "not_listed", "under_evaluation", "approved", "approved_with_restrictions", "not_approved",
    "retired",
)  # fmt: skip
VENDOR_STATUSES = ("prospective", "active", "offboarding", "former")
DUE_DILIGENCE = ("not_started", "in_progress", "complete")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class RecordMixin:
    """What every inventory record has."""

    __audit_skip__ = frozenset({"version", "updated_at"})

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JsonType, default=list)
    # Restricted records are known only to their owners, their unit's stewards, governance,
    # and auditors.
    restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    # Rises with every edit. An edit made against an older version is refused.
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Vendor(RecordMixin, Base):
    """An outside supplier of an AI system or model."""

    __tablename__ = "vendor"
    __subject__ = "vendor"

    website: Mapped[str | None] = mapped_column(String(300))
    contacts: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    status: Mapped[str] = mapped_column(String(24), default="prospective")
    due_diligence_status: Mapped[str] = mapped_column(String(24), default="not_started")
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_one_of("status", VENDOR_STATUSES), name="status"),
        CheckConstraint(
            _one_of("due_diligence_status", DUE_DILIGENCE), name="due_diligence_status"
        ),
    )


class AISystem(RecordMixin, Base):
    """A tool, product, service, or application that uses AI.

    A catalog standing applies to one edition reached one way: the enterprise plan under
    contract and the free consumer plan of the same product are different records.
    """

    __tablename__ = "ai_system"
    __subject__ = "system"

    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_unit.id"))
    status: Mapped[str] = mapped_column(String(24), default="active")
    kind: Mapped[str] = mapped_column(String(40))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendor.id"))
    embedded_in: Mapped[str | None] = mapped_column(String(200))
    hosting: Mapped[str | None] = mapped_column(String(40))
    edition: Mapped[str | None] = mapped_column(String(120))
    access_path: Mapped[str | None] = mapped_column(String(40))
    version_label: Mapped[str | None] = mapped_column(String(80))
    url: Mapped[str | None] = mapped_column(String(300))
    catalog_status: Mapped[str] = mapped_column(String(32), default="not_listed")
    permitted_data_class: Mapped[str | None] = mapped_column(String(40))
    excluded_data_categories: Mapped[list[str]] = mapped_column(JsonType, default=list)
    terms: Mapped[str | None] = mapped_column(Text)
    data_handling: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    regulatory_status: Mapped[str | None] = mapped_column(String(200))
    # For a system that acts: what it may do, as whom, and how a person stops it.
    agent_profile: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)

    __table_args__ = (
        CheckConstraint(_one_of("status", SYSTEM_STATUSES), name="status"),
        CheckConstraint(_one_of("catalog_status", CATALOG_STATUSES), name="catalog_status"),
        Index("ix_ai_system_vendor_id", "vendor_id"),
        Index("ix_ai_system_catalog_status", "catalog_status"),
    )


class Model(RecordMixin, Base):
    """A specific model, identified well enough to tell versions apart: one bought as a
    service, open weights the organization runs itself, or one it trained or tuned."""

    __tablename__ = "model"
    __subject__ = "model"

    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_unit.id"))
    status: Mapped[str] = mapped_column(String(24), default="active")
    kind: Mapped[str] = mapped_column(String(40))
    origin: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str | None] = mapped_column(String(200))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendor.id"))
    family: Mapped[str | None] = mapped_column(String(120))
    version_label: Mapped[str | None] = mapped_column(String(80))
    modality: Mapped[list[str]] = mapped_column(JsonType, default=list)
    license: Mapped[str | None] = mapped_column(String(200))
    license_restrictions: Mapped[str | None] = mapped_column(Text)
    release_date: Mapped[date | None] = mapped_column(Date)
    deprecation_date: Mapped[date | None] = mapped_column(Date)
    # For models the organization runs or trains itself.
    weights_source: Mapped[str | None] = mapped_column(String(300))
    weights_checksum: Mapped[str | None] = mapped_column(String(200))
    weights_format: Mapped[str | None] = mapped_column(String(40))
    parameters: Mapped[str | None] = mapped_column(String(80))
    quantization: Mapped[str | None] = mapped_column(String(80))
    runs_on: Mapped[str | None] = mapped_column(Text)
    tuning_method: Mapped[str | None] = mapped_column(String(40))
    sharing: Mapped[str | None] = mapped_column(String(40))
    # The sensitivity of the model itself: never below that of the data it was trained on.
    data_class: Mapped[str | None] = mapped_column(String(40))
    card: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    catalog_status: Mapped[str] = mapped_column(String(32), default="not_listed")
    permitted_data_class: Mapped[str | None] = mapped_column(String(40))
    excluded_data_categories: Mapped[list[str]] = mapped_column(JsonType, default=list)
    terms: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_one_of("status", SYSTEM_STATUSES), name="status"),
        CheckConstraint(_one_of("catalog_status", CATALOG_STATUSES), name="catalog_status"),
        Index("ix_model_vendor_id", "vendor_id"),
        Index("ix_model_catalog_status", "catalog_status"),
    )


class Dataset(RecordMixin, Base):
    """Data that AI is trained on, tuned with, or given. A description only: GovWren never
    holds the data."""

    __tablename__ = "dataset"
    __subject__ = "dataset"

    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_unit.id"))
    status: Mapped[str] = mapped_column(String(24), default="active")
    data_class: Mapped[str | None] = mapped_column(String(40))
    data_categories: Mapped[list[str]] = mapped_column(JsonType, default=list)
    subjects: Mapped[list[str]] = mapped_column(JsonType, default=list)
    identifiability: Mapped[str | None] = mapped_column(String(40))
    deidentification_method: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    permitted_uses: Mapped[str | None] = mapped_column(Text)
    restrictions: Mapped[str | None] = mapped_column(Text)
    retention: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_one_of("status", SYSTEM_STATUSES), name="status"),
        Index("ix_dataset_data_class", "data_class"),
    )


class Agreement(Base):
    """A contract or other legal instrument with a vendor."""

    __tablename__ = "agreement"
    __audit_parent__ = ("vendor", "vendor_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendor.id"))
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    reference: Mapped[str | None] = mapped_column(String(120))
    effective_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    auto_renews: Mapped[bool] = mapped_column(Boolean, default=False)
    notice_days: Mapped[int | None] = mapped_column(Integer)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_agreement_vendor_id", "vendor_id"),
        Index("ix_agreement_expires_on", "expires_on"),
    )


class ExternalRef(Base):
    """A pointer from a record to something in another system: a protocol, a grant, an
    agreement, a purchase, a ticket, a repository."""

    __tablename__ = "external_ref"
    __audit_parent__ = ("@record_type", "record_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_type: Mapped[str] = mapped_column(String(24))
    record_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    identifier: Mapped[str] = mapped_column(String(200))
    label: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (Index("ix_external_ref_record", "record_type", "record_id"),)


class UseCase(RecordMixin, Base):
    """What AI is being used for, by whom, on what. The unit of governance."""

    __tablename__ = "use_case"
    __subject__ = "use_case"

    org_unit_id: Mapped[int] = mapped_column(ForeignKey("org_unit.id"))
    status: Mapped[str] = mapped_column(String(32), default="draft")  # its standing with governance
    purpose: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(40))
    stage: Mapped[str] = mapped_column(String(40), default="proposed")
    tier: Mapped[int | None] = mapped_column(Integer)
    tier_source: Mapped[str | None] = mapped_column(String(16))
    decision_role: Mapped[str | None] = mapped_column(String(40))
    human_oversight: Mapped[str | None] = mapped_column(Text)
    affected_groups: Mapped[list[str]] = mapped_column(JsonType, default=list)
    data_class: Mapped[str | None] = mapped_column(String(40))  # the highest class involved
    data_categories: Mapped[list[str]] = mapped_column(JsonType, default=list)
    outputs_used_for: Mapped[list[str]] = mapped_column(JsonType, default=list)
    approved_until: Mapped[date | None] = mapped_column(Date)
    next_review_on: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (
        CheckConstraint(_one_of("status", USE_CASE_STATUSES), name="status"),
        CheckConstraint("tier IS NULL OR tier BETWEEN 1 AND 9", name="tier"),
        Index("ix_use_case_org_unit_id", "org_unit_id"),
        Index("ix_use_case_status", "status"),
    )


class RecordOwner(Base):
    """A person named on a record, and in what capacity."""

    __tablename__ = "record_owner"
    __audit_parent__ = ("@record_type", "record_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_type: Mapped[str] = mapped_column(String(24))
    record_id: Mapped[int] = mapped_column(Integer)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"))
    kind: Mapped[str] = mapped_column(String(24))

    __table_args__ = (
        UniqueConstraint("record_type", "record_id", "account_id", "kind"),
        Index("ix_record_owner_account_id", "account_id"),
    )


class RecordLink(Base):
    """A typed connection between two inventory records: the dependency graph."""

    __tablename__ = "record_link"
    __audit_parent__ = ("@from_type", "from_id")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_type: Mapped[str] = mapped_column(String(24))
    from_id: Mapped[int] = mapped_column(Integer)
    relation: Mapped[str] = mapped_column(String(24))
    to_type: Mapped[str] = mapped_column(String(24))
    to_id: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        UniqueConstraint("from_type", "from_id", "relation", "to_type", "to_id"),
        Index("ix_record_link_to", "to_type", "to_id"),
    )
