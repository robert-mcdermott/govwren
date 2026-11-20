"""Open formats: the models as a bill of materials, and a model card for each (RPT-08).

The bill of materials is CycloneDX 1.6 JSON. Each model is a ``machine-learning-model``
component with its supplier, license, checksum, and model card; each dataset a model was
trained or evaluated on is a ``data`` component; and the dependencies say which model is
derived from which and which datasets it rests on. Records the person may not see are left
out, and so is the content of anything restricted to them.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren import __version__
from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import NotFound
from govwren.db.models import Dataset, Model, RecordLink, Vendor
from govwren.inventory import access, fields
from govwren.inventory.registry import DATASET, MODEL
from govwren.program import branding, vocab

SPEC_VERSION = "1.6"
_HEX = re.compile(r"^(?:sha-?256:)?([0-9a-fA-F]{64})$")


def _visible(session: Session, principal: Principal, record_type: Any, rows: Any) -> list[Any]:
    return [
        row for row in rows if access.sight(session, principal, record_type, row) == access.FULL
    ]


def _supplier(session: Session, model: Model) -> str | None:
    vendor = session.get(Vendor, model.vendor_id) if model.vendor_id else None
    return vendor.name if vendor else model.provider


def _model_component(
    session: Session, model: Model, datasets: list[Dataset], labels: dict[str, dict[str, str]]
) -> dict[str, Any]:
    view = fields.view(model, fields.MODEL)
    component: dict[str, Any] = {
        "type": "machine-learning-model",
        "bom-ref": model.ref,
        "name": model.name,
    }
    if model.version_label:
        component["version"] = model.version_label
    if model.summary:
        component["description"] = model.summary
    supplier = _supplier(session, model)
    if supplier:
        component["supplier"] = {"name": supplier}
    if view.get("license"):
        component["licenses"] = [{"license": {"name": view["license"]}}]
    checksum = _HEX.match(str(view.get("weights_checksum") or "").strip())
    if checksum:
        component["hashes"] = [{"alg": "SHA-256", "content": checksum.group(1).lower()}]
    parameters: dict[str, Any] = {}
    if model.kind:
        parameters["task"] = labels["model_kinds"].get(model.kind, model.kind)
    if model.family:
        parameters["architectureFamily"] = model.family
    if datasets:
        parameters["datasets"] = [{"ref": dataset.ref} for dataset in datasets]
    considerations: dict[str, Any] = {}
    if view.get("intended_use"):
        considerations["useCases"] = [view["intended_use"]]
    limits = [text for text in (view.get("limitations"), view.get("out_of_scope")) if text]
    if limits:
        considerations["technicalLimitations"] = limits
    card: dict[str, Any] = {}
    if parameters:
        card["modelParameters"] = parameters
    if considerations:
        card["considerations"] = considerations
    if card:
        component["modelCard"] = card
    if view.get("card_url"):
        component["externalReferences"] = [{"type": "model-card", "url": view["card_url"]}]
    properties = [
        {"name": f"govwren:{key}", "value": str(value)}
        for key, value in (
            ("origin", labels["model_origins"].get(model.origin, model.origin)),
            ("catalog_status", view.get("catalog_status")),
            ("data_class", view.get("data_class")),
            ("weights_source", view.get("weights_source")),
            ("weights_format", view.get("weights_format")),
            ("parameters", view.get("parameters")),
            ("quantization", view.get("quantization")),
        )
        if value
    ]
    if properties:
        component["properties"] = properties
    return component


def bill_of_materials(session: Session, principal: Principal) -> dict[str, Any]:
    """Every model the person may see in full, with the datasets and models it rests on."""
    models = _visible(
        session,
        principal,
        MODEL,
        session.scalars(select(Model).where(Model.status != "merged").order_by(Model.id)),
    )
    by_id = {model.id: model for model in models}
    links = session.scalars(
        select(RecordLink).where(
            RecordLink.from_type == "model",
            RecordLink.from_id.in_(by_id or {0}),
            RecordLink.relation.in_(("trained_on", "evaluated_on", "derived_from")),
        )
    ).all()
    wanted = {link.to_id for link in links if link.to_type == "dataset"}
    datasets = {
        dataset.id: dataset
        for dataset in _visible(
            session,
            principal,
            DATASET,
            session.scalars(select(Dataset).where(Dataset.id.in_(wanted or {0}))),
        )
    }
    labels = {name: vocab.labels(session, name) for name in ("model_kinds", "model_origins")}
    rests_on: dict[int, list[str]] = {model.id: [] for model in models}
    data_of: dict[int, list[Dataset]] = {model.id: [] for model in models}
    for link in links:
        if link.to_type == "dataset" and link.to_id in datasets:
            dataset = datasets[link.to_id]
            if dataset.ref not in rests_on[link.from_id]:
                rests_on[link.from_id].append(dataset.ref)
                data_of[link.from_id].append(dataset)
        elif link.to_type == "model" and link.to_id in by_id:
            rests_on[link.from_id].append(by_id[link.to_id].ref)
    components = [
        _model_component(session, model, data_of[model.id], labels) for model in models
    ] + [
        {
            "type": "data",
            "bom-ref": dataset.ref,
            "name": dataset.name,
            **({"description": dataset.summary} if dataset.summary else {}),
            "data": [
                {
                    "type": "dataset",
                    "name": dataset.name,
                    **(
                        {"classification": dataset.data_class}
                        if getattr(dataset, "data_class", None)
                        else {}
                    ),
                }
            ],
        }
        for dataset in sorted(datasets.values(), key=lambda d: d.id)
    ]
    brand = branding.load(session)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tools": {
                "components": [{"type": "application", "name": "GovWren", "version": __version__}]
            },
            "component": {
                "type": "application",
                "bom-ref": "inventory",
                "name": f"{brand.organization_name or brand.product_name} AI model inventory",
            },
        },
        "components": components,
        "dependencies": [
            {"ref": "inventory", "dependsOn": [model.ref for model in models]},
            *(
                {"ref": model.ref, "dependsOn": rests_on[model.id]}
                for model in models
                if rests_on[model.id]
            ),
        ],
    }


def _plain(text: str) -> str:
    """Text as text in Markdown: a renderer that lets HTML through finds none in it."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def model_card(session: Session, principal: Principal, model: Model) -> str:
    """A model card in Markdown, with the usual headings."""
    if access.sight(session, principal, MODEL, model) != access.FULL:
        raise NotFound(f"There is no model {model.ref}.")
    view = fields.view(model, fields.MODEL)
    labels = {
        field.key: vocab.labels(session, field.vocab)
        for field in fields.MODEL
        if field.vocab in vocab.DEFAULTS
    }

    def shown(key: str) -> str:
        value = view.get(key)
        if value in (None, "", []):
            return ""
        if isinstance(value, list):
            return ", ".join(labels.get(key, {}).get(item, str(item)) for item in value)
        text = str(value)
        if key in ("catalog_status", "status"):
            text = text.replace("_", " ").capitalize()
        return _plain(labels.get(key, {}).get(str(value), text))

    def rows(pairs: list[tuple[str, str]]) -> list[str]:
        kept = [(label, value) for label, value in pairs if value]
        if not kept:
            return []
        return ["| | |", "|---|---|", *(f"| {a} | {b.replace('|', '/')} |" for a, b in kept), ""]

    def section(title: str, key: str) -> list[str]:
        return [f"## {title}", "", shown(key), ""] if shown(key) else []

    links = session.execute(
        select(RecordLink.relation, Dataset)
        .join(Dataset, Dataset.id == RecordLink.to_id)
        .where(
            RecordLink.from_type == "model",
            RecordLink.from_id == model.id,
            RecordLink.to_type == "dataset",
        )
        .order_by(RecordLink.id)
    ).all()
    data = [
        f"- {'Trained on' if relation == 'trained_on' else 'Evaluated on'}: "
        + (
            f"{_plain(dataset.name)} ({dataset.ref})"
            if access.may_name(session, principal, DATASET, dataset)
            else access.HIDDEN_NAME
        )
        for relation, dataset in links
    ]
    lines = [f"# {_plain(model.name)}", ""]
    if model.summary:
        lines += [_plain(model.summary), ""]
    lines += ["## Model details", ""]
    lines += rows(
        [
            ("Reference", model.ref),
            ("Made by", _supplier(session, model) or ""),
            ("Kind", shown("kind")),
            ("Where it comes from", shown("origin")),
            ("Family", shown("family")),
            ("Version", shown("version_label")),
            ("Works with", shown("modality")),
            ("License", shown("license")),
            ("What the license limits", shown("license_restrictions")),
            ("Released", shown("release_date")),
            ("Size", shown("parameters")),
            ("Checksum of the weights", shown("weights_checksum")),
            ("Published model card", shown("card_url")),
        ]
    )
    lines += section("Intended use", "intended_use")
    lines += section("Out-of-scope use", "out_of_scope")
    if shown("training_data") or data:
        lines += [
            "## Training data",
            "",
            *([shown("training_data"), ""] if shown("training_data") else []),
        ]
        lines += [*data, ""] if data else []
    lines += section("Evaluation", "evaluation")
    lines += section("Known limitations", "limitations")
    governed = rows(
        [
            ("Catalog standing", shown("catalog_status")),
            ("May be used with data up to", shown("permitted_data_class")),
            ("Not to be used with", shown("excluded_data_categories")),
            ("Terms of use", shown("terms")),
        ]
    )
    if governed:
        lines += ["## How it may be used here", "", *governed]
    return "\n".join(lines).rstrip() + "\n"
