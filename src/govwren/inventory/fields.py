"""What the described record types are made of.

Use cases, AI systems, and vendors each have code of their own, because each has behavior of
its own. A model or a dataset is mostly a description, so its fields are listed here once,
and the same list checks what is saved, shapes what the API returns, and tells the web app
what to draw. A record type added later can be described the same way.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from govwren.program import vocab

KINDS = ("text", "long", "choice", "choices", "date", "url")


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str = "text"
    vocab: str | None = None
    group: str = "About"
    hint: str | None = None
    required: bool = False
    governed: bool = False  # only those who keep the catalog may set it
    inside: str | None = None  # the JSON column that holds it, if it has no column of its own
    limit: int = 300
    only_for: tuple[str, ...] = ()  # shown only when ``origin`` is one of these

    def to_json(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, False, (), "")}


OWN = ("open_weights", "fine_tuned", "in_house")
TUNED = ("fine_tuned", "in_house")

MODEL = (
    Field("kind", "Kind of model", "choice", "model_kinds", required=True),
    Field("origin", "Where it comes from", "choice", "model_origins", required=True),
    Field("provider", "Made by", hint="The company, lab, or group that produced it."),
    Field("family", "Family", limit=120, hint="The name its versions share."),
    Field("version_label", "Version", limit=80, hint="Exact enough to tell versions apart."),
    Field("modality", "Works with", "choices", "modalities"),
    Field("license", "License", limit=200),
    Field("license_restrictions", "What the license limits", "long",
          hint="Commercial use, redistribution, fields of use, acceptable-use terms."),
    Field("release_date", "Released", "date"),
    Field("deprecation_date", "Withdrawn or to be withdrawn", "date",
          hint="When the supplier stops offering it, or the organization stops running it."),
    Field("registry_name", "Name in the model registry", group="Running it", limit=200,
          hint="What your registry calls it, such as lumen/lumen-large. Only used if a "
          "registry is connected."),
    Field("weights_source", "Where the weights were obtained", group="Running it",
          only_for=OWN, hint="The repository or address they came from, or “trained here”."),
    Field("weights_checksum", "Checksum of the weights", group="Running it", only_for=OWN,
          limit=200, hint="A hash that says exactly which file is in use, such as its SHA-256."),
    Field("weights_format", "Format of the weights", "choice", "weights_formats",
          group="Running it", only_for=OWN),
    Field("parameters", "Size", group="Running it", only_for=OWN, limit=80,
          hint="Such as “7 billion parameters”."),
    Field("quantization", "Quantization", group="Running it", only_for=OWN, limit=80),
    Field("runs_on", "Where it runs", "long", group="Running it", only_for=OWN,
          hint="The machine, cluster, or service it is served from, and who can reach it."),
    Field("tuning_method", "How it was tuned", "choice", "tuning_methods", group="Running it",
          only_for=TUNED),
    Field("sharing", "Who the weights may go to", "choice", "sharing", group="Running it",
          only_for=OWN),
    Field("data_class", "Sensitivity of the model itself", "choice", "data_classes",
          group="Running it", only_for=OWN,
          hint="A model can reproduce what it was trained on, so it is never less sensitive "
          "than its training data."),
    Field("intended_use", "Intended use", "long", group="Model card", inside="card",
          limit=4000),
    Field("out_of_scope", "Out-of-scope use", "long", group="Model card", inside="card",
          limit=4000),
    Field("training_data", "Training data", "long", group="Model card", inside="card",
          limit=4000),
    Field("evaluation", "Evaluation", "long", group="Model card", inside="card", limit=4000,
          hint="What it was tested on, with which measures, and for which populations."),
    Field("limitations", "Known limitations", "long", group="Model card", inside="card",
          limit=4000),
    Field("card_url", "The published model card", "url", group="Model card", inside="card"),
    Field("catalog_status", "Catalog standing", "choice", "catalog_statuses", group="Catalog",
          governed=True),
    Field("permitted_data_class", "May be used with data up to", "choice", "data_classes",
          group="Catalog", governed=True),
    Field("excluded_data_categories", "Not to be used with", "choices", "data_categories",
          group="Catalog", governed=True),
    Field("terms", "Terms of use", "long", group="Catalog", governed=True, limit=4000),
    Field("status", "In use or retired", "choice", "record_statuses", group="Catalog",
          governed=True),
)  # fmt: skip

DATASET = (
    Field("data_class", "Data class", "choice", "data_classes", required=True),
    Field("data_categories", "Kinds of data", "choices", "data_categories"),
    Field("subjects", "Who the data is about", "choices", "affected_groups"),
    Field("identifiability", "Can people be identified?", "choice", "identifiability"),
    Field("deidentification_method", "How identifiers were removed", "long"),
    Field("source", "Where it came from", "long", group="Terms",
          hint="Who collected or supplied it, and under what study or agreement."),
    Field("permitted_uses", "What it may be used for", "long", group="Terms"),
    Field("restrictions", "What it may not be used for", "long", group="Terms",
          hint="Limits from consent, an agreement, or policy. A model trained on it carries them."),
    Field("retention", "How long it is kept", group="Terms", limit=200),
    Field("location", "Where it is held", "long", group="Terms",
          hint="The system or storage it lives in. GovWren never holds the data itself."),
    Field("status", "In use or retired", "choice", "record_statuses", group="Terms"),
)  # fmt: skip

AGENT = (
    Field("autonomy_level", "How much it does by itself", "choice", "autonomy_levels"),
    Field("actions", "What it can change, and where", "long", limit=4000),
    Field("tools", "Tools and services it is connected to", "long", limit=4000,
          hint="Each with what it is for and what access it has."),
    Field("identity", "Who it acts as", hint="The account or credentials it works under."),
    Field("reversibility", "Can what it does be undone?", "choice", "reversibility"),
    Field("human_override", "How a person stops or corrects it", "long", limit=4000),
    Field("memory", "What it remembers between runs", "long", limit=4000),
    Field("limits", "Limits on spending, rate, and scope", "long", limit=4000),
)  # fmt: skip

# Lists that are fixed by the product and not vocabularies an organization edits.
FIXED = {
    "catalog_statuses": [
        ("not_listed", "Not in the catalog"), ("under_evaluation", "Under evaluation"),
        ("approved", "Approved"), ("approved_with_restrictions", "Approved with restrictions"),
        ("not_approved", "Not approved"), ("retired", "Retired"),
    ],
    "record_statuses": [("active", "In use"), ("retired", "Retired")],
}  # fmt: skip


def choices(session: Session, name: str) -> list[str]:
    if name in FIXED:
        return [key for key, _ in FIXED[name]]
    return vocab.keys(session, name)


def labels(session: Session, name: str) -> dict[str, str]:
    return dict(FIXED[name]) if name in FIXED else vocab.labels(session, name)


def _clean(session: Session, field: Field, value: Any) -> tuple[Any, str | None]:
    """A value ready to store, or the reason it cannot be."""
    if field.kind == "choices":
        if value is None:
            return [], None
        if not isinstance(value, list | tuple):
            return None, "Give a list of choices."
        chosen = list(dict.fromkeys(str(v) for v in value))
        allowed = choices(session, field.vocab or "")
        unknown = [v for v in chosen if v not in allowed]
        return chosen, f"{unknown[0]!r} is not one of the choices." if unknown else None
    text = str(value).strip() if value is not None else ""
    if not text:
        return None, "Choose a value." if field.required and field.kind == "choice" else None
    if field.kind == "choice":
        if text not in choices(session, field.vocab or ""):
            return None, f"{text!r} is not one of the choices."
        return text, None
    if field.kind == "date":
        if isinstance(value, date):
            return value, None
        try:
            return date.fromisoformat(text), None
        except ValueError:
            return None, "Give the date as year-month-day."
    if field.kind == "url" and not text.lower().startswith(("https://", "http://")):
        return None, "Start the address with https://"
    limit = field.limit if field.kind != "long" or field.limit != 300 else 4000
    if len(text) > limit:
        return None, f"Keep it to {limit} characters."
    return text, None


def apply(
    session: Session,
    record: Any,
    values: Mapping[str, Any],
    spec: Sequence[Field],
    *,
    creating: bool,
    may_govern: bool,
) -> dict[str, str]:
    """Put the given values on the record. Returns what is wrong with any of them."""
    errors: dict[str, str] = {}
    for field in spec:
        if field.key not in values:
            if creating and field.required:
                errors[field.key] = (
                    "Choose a value." if field.kind == "choice" else "Say what it is."
                )
            continue
        if field.governed and not may_govern:
            errors[field.key] = "Only governance can change this."
            continue
        cleaned, problem = _clean(session, field, values[field.key])
        if problem:
            errors[field.key] = problem
            continue
        if field.required and cleaned in (None, [], ""):
            errors[field.key] = "Say what it is."
            continue
        if field.inside:
            holder = dict(getattr(record, field.inside) or {})
            if cleaned in (None, []):
                holder.pop(field.key, None)
            else:
                holder[field.key] = cleaned
            setattr(record, field.inside, holder)
        else:
            setattr(record, field.key, cleaned)
    return errors


def view(record: Any, spec: Sequence[Field]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in spec:
        if field.inside:
            out[field.key] = (getattr(record, field.inside) or {}).get(field.key)
        else:
            out[field.key] = getattr(record, field.key)
    return out


def describe(session: Session, spec: Sequence[Field]) -> list[dict[str, Any]]:
    """The fields as the web app needs them: with the choices each one offers."""
    out = []
    for field in spec:
        entry = field.to_json()
        if field.vocab in FIXED:
            entry["options"] = [{"key": k, "label": v} for k, v in FIXED[field.vocab]]
        out.append(entry)
    return out
