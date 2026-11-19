"""Vocabularies: the lists of values an organization can rename, extend, and retire.

Records store a value's stable ``key``, never its label, so renaming a value never rewrites
history. Until an organization edits a vocabulary, the defaults below are what it has.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from govwren.core.errors import Invalid
from govwren.program import settings


def _items(*pairs: tuple[str, str] | tuple[str, str, str]) -> list[dict[str, Any]]:
    return [
        {"key": pair[0], "label": pair[1], **({"description": pair[2]} if len(pair) > 2 else {})}
        for pair in pairs
    ]


# Data classes are ordered from least to most sensitive: rules compare them.
DATA_CLASSES = [
    {
        "key": "public",
        "label": "Public",
        "description": "Poses little or no risk if disclosed, and may be shared with anyone.",
        "examples": {
            "Personal": ["Public staff directory entries"],
            "Research": ["Published papers and results", "Data already in a public repository"],
            "Health": ["Published population statistics"],
            "Financial": ["Figures in a published annual report"],
            "Administrative": ["Public web pages", "Job postings", "Press releases"],
        },
    },
    {
        "key": "internal",
        "label": "Internal",
        "description": "Meant for use inside the organization, by its own people, for its own "
        "work. Not to be shared outside without oversight.",
        "examples": {
            "Personal": ["Work contact details", "Event attendee lists and surveys"],
            "Research": [
                "Drafts, preliminary analysis, and plans for future work",
                "Laboratory procedures that involve no participants",
            ],
            "Health": ["Aggregate counts with no individuals identifiable"],
            "Financial": ["Award totals and cost breakdowns for grants received"],
            "Administrative": [
                "Internal policies and procedures",
                "Most correspondence and minutes",
                "Aggregate business figures",
            ],
        },
    },
    {
        "key": "protected",
        "label": "Protected",
        "description": "Could harm people or the organization if seen by the wrong person, "
        "inside or out. Access is limited to those who need it for their work.",
        "examples": {
            "Personal": [
                "Personnel records: applications, salary, evaluations",
                "Student and trainee records",
            ],
            "Research": [
                "Unpublished data, results, and manuscripts",
                "Study protocols and consent forms",
                "De-identified participant data",
                "Data held under a data use agreement",
                "Grant applications and invention disclosures",
            ],
            "Health": ["Staff immunization and fitness-for-work records"],
            "Financial": ["Budgets and financial records", "Purchasing and travel records"],
            "Administrative": [
                "Security plans and system logs",
                "Contracts that are not public",
                "Research compliance records",
            ],
        },
    },
    {
        "key": "restricted",
        "label": "Restricted",
        "description": "Governed by specific legal, regulatory, or contractual obligations. "
        "Loss or disclosure may require notifying people, partners, or authorities.",
        "examples": {
            "Personal": [
                "A name together with a government ID number, full date of birth, or biometric",
                "Payroll, bank, and disability details",
                "Donor records",
            ],
            "Research": [
                "Identifiable participant data, photographs, and recordings",
                "Participant contact details",
                "Genomic data that could identify a person",
                "Export-controlled information",
            ],
            "Health": [
                "Identifiable health information",
                "Records of sensitive conditions and treatment",
                "Health insurance numbers",
            ],
            "Financial": ["Payment card and bank account numbers"],
            "Administrative": ["Passwords, keys, and access codes", "Legally privileged material"],
        },
    },
]

DEFAULTS: dict[str, list[dict[str, Any]]] = {
    "data_classes": DATA_CLASSES,
    "data_categories": _items(
        ("personal", "Personal data", "Information about identifiable people"),
        ("health", "Health information", "Information about a person's health or care"),
        (
            "human_subjects",
            "Human-subjects research data",
            "Data collected under an ethics protocol",
        ),
        ("genetic", "Genetic data"),
        ("student", "Student records"),
        ("unpublished", "Unpublished research"),
        ("under_agreement", "Third-party data under an agreement"),
        ("source_code", "Proprietary source code"),
        ("credentials", "Credentials and secrets"),
        ("export_controlled", "Export-controlled information"),
    ),
    "domains": _items(
        ("research", "Research"),
        ("clinical", "Clinical care"),
        ("education", "Education"),
        ("operations", "Operations"),
        ("software", "Software development"),
    ),
    "stages": _items(
        ("proposed", "Proposed", "An idea, not yet started"),
        ("pilot", "Pilot", "Being tried on a small scale"),
        ("in_use", "In use", "In regular use"),
        ("paused", "Paused"),
        ("retired", "Retired", "No longer in use"),
    ),
    "decision_roles": _items(
        ("exploratory", "Exploratory", "Background or exploration; nothing relies on it"),
        ("informs", "Informs a person", "A person decides independently, with this as one input"),
        ("recommends", "Recommends", "A person usually accepts what it recommends"),
        ("decides", "Decides or acts", "It decides or acts without a person reviewing each case"),
    ),
    "affected_groups": _items(
        ("team", "Nobody outside the team"),
        ("staff", "Staff"),
        ("students", "Students and trainees"),
        ("participants", "Research participants"),
        ("patients", "Patients"),
        ("public", "The public"),
    ),
    "outputs_used_for": _items(
        ("publications", "Publications"),
        ("grant_applications", "Grant applications"),
        ("peer_review", "Peer review"),
        ("analysis", "Analysis of record"),
        ("production_software", "Software in production"),
        ("communications", "Communications"),
        ("decisions_about_people", "Decisions about people"),
    ),
    "owner_kinds": _items(
        ("accountable", "Accountable owner", "The person who answers for it"),
        ("technical", "Technical owner", "The person who runs or builds it"),
        ("contact", "Contact", "Someone to ask; cannot edit the record"),
    ),
    "system_kinds": _items(
        ("vendor_product", "Vendor product"),
        ("embedded_feature", "Feature inside another product"),
        ("model_service", "Model API or service"),
        ("open_source", "Open-source tool"),
        ("internal_app", "Built in-house"),
        ("agent", "Agent"),
    ),
    "hosting": _items(
        ("local", "On a person's own device"),
        ("on_premises", "On the organization's own equipment"),
        ("own_cloud", "The organization's cloud tenant"),
        ("vendor", "Hosted by the vendor"),
    ),
    "access_paths": _items(
        ("web", "Web app"),
        ("desktop", "Desktop or mobile app"),
        ("api", "API"),
        ("plugin", "Plug-in or extension"),
        ("embedded", "Inside another product"),
    ),
    "review_functions": _items(
        ("privacy", "Privacy"),
        ("security", "Information security"),
        ("legal", "Legal and contracts"),
        ("ethics", "Research ethics"),
        ("integrity", "Research integrity"),
        ("clinical_safety", "Clinical safety"),
        ("data_stewardship", "Data stewardship"),
        ("architecture", "Architecture"),
    ),
    "model_kinds": _items(
        ("language", "Language model"),
        ("embedding", "Embedding model"),
        ("vision", "Vision model"),
        ("speech", "Speech model"),
        ("multimodal", "Multimodal model"),
        ("classical", "Classical machine learning", "Regression, trees, and the like"),
        ("scientific", "Scientific model", "Built for sequences, structures, signals, or images"),
        ("other", "Other"),
    ),
    "model_origins": _items(
        (
            "commercial_api",
            "A supplier's service",
            "Reached through an API; the weights stay with them",
        ),
        ("open_weights", "Open weights", "Published weights the organization runs itself"),
        (
            "fine_tuned",
            "Fine-tuned in-house",
            "An existing model adapted with the organization's data",
        ),
        ("in_house", "Built in-house", "Trained from the organization's own data"),
    ),
    "modalities": _items(
        ("text", "Text"),
        ("code", "Code"),
        ("image", "Images"),
        ("audio", "Audio"),
        ("video", "Video"),
        ("tabular", "Tables"),
        ("sequence", "Biological sequences"),
        ("signal", "Signals and time series"),
    ),
    "weights_formats": _items(
        ("safetensors", "Safetensors", "Holds numbers only"),
        ("gguf", "GGUF", "Holds numbers only"),
        ("onnx", "ONNX"),
        (
            "pickle",
            "Pickle or a framework checkpoint",
            "Can run code when loaded: load only from a trusted source",
        ),
        ("other", "Other"),
    ),
    "tuning_methods": _items(
        ("full", "Full fine-tuning"),
        ("adapter", "Adapters", "Such as low-rank adapters, kept beside the base weights"),
        ("head", "A new head on a frozen model"),
        ("distillation", "Distillation"),
        ("other", "Other"),
    ),
    "sharing": _items(
        ("unit", "Stays within the unit"),
        ("organization", "May be shared within the organization"),
        ("collaborators", "May be shared with named collaborators"),
        ("published", "Published, or meant to be"),
    ),
    "identifiability": _items(
        ("identified", "Identified", "Names or other direct identifiers are present"),
        ("coded", "Coded", "Direct identifiers replaced by a code; a key exists"),
        ("deidentified", "De-identified", "Identifiers removed by a stated method"),
        ("anonymous", "Anonymous", "Cannot be linked to a person by anyone"),
        ("not_about_people", "Not about people"),
    ),
    "agreement_kinds": _items(
        ("master", "Master agreement"),
        ("data_processing", "Data processing agreement"),
        ("health_information", "Agreement covering health information"),
        ("data_use", "Data use agreement"),
        ("license", "License"),
        ("terms_accepted", "Terms of service accepted"),
        ("other", "Other"),
    ),
    "reference_kinds": _items(
        ("protocol", "Ethics protocol"),
        ("grant", "Grant or award"),
        ("agreement", "Agreement"),
        ("purchase", "Purchase or requisition"),
        ("ticket", "Ticket"),
        ("repository", "Code or data repository"),
        ("publication", "Publication"),
        ("other", "Other"),
    ),
    "evidence_kinds": _items(
        ("document", "Document"),
        ("approval", "Approval or sign-off"),
        ("agreement", "Signed agreement"),
        ("assessment", "Assessment or review"),
        ("test_result", "Test or evaluation result"),
        ("assurance", "Supplier's assurance report"),
        ("record", "Record or log"),
        ("other", "Other"),
    ),
    "autonomy_levels": _items(
        ("suggests", "Suggests only", "A person carries out anything it proposes"),
        ("with_approval", "Acts with approval", "A person approves each action"),
        ("within_limits", "Acts within limits", "Acts by itself inside stated limits"),
        ("autonomous", "Fully autonomous", "Acts by itself, including actions hard to undo"),
    ),
    "reversibility": _items(
        ("reversible", "Everything it does can be undone"),
        ("mostly", "Most of what it does can be undone"),
        ("irreversible", "Some of what it does cannot be undone"),
    ),
    "unit_kinds": _items(
        ("organization", "Organization"),
        ("division", "Division"),
        ("department", "Department"),
        ("center", "Center"),
        ("core", "Core facility"),
        ("lab", "Lab"),
        ("office", "Office"),
    ),
}

NAMES = tuple(DEFAULTS)


def _setting(name: str) -> str:
    return f"vocab.{name}"


def get(session: Session, name: str) -> list[dict[str, Any]]:
    """Every value of a vocabulary, in order, retired ones included."""
    if name not in DEFAULTS:
        raise KeyError(name)
    return settings.get(session, _setting(name), None) or [dict(item) for item in DEFAULTS[name]]


def all_(session: Session) -> dict[str, list[dict[str, Any]]]:
    return {name: get(session, name) for name in NAMES}


def keys(session: Session, name: str, *, active_only: bool = True) -> list[str]:
    return [item["key"] for item in get(session, name) if not (active_only and item.get("retired"))]


def labels(session: Session, name: str) -> dict[str, str]:
    return {item["key"]: item["label"] for item in get(session, name)}


def rank(session: Session, name: str, key: str | None) -> int:
    """Where a value sits in an ordered vocabulary (0 first); -1 if it is not in it."""
    order = keys(session, name, active_only=False)
    return order.index(key) if key in order else -1


def check(
    session: Session, name: str, key: str | None, field: str, *, required: bool = False
) -> None:
    """Raise ``Invalid`` unless ``key`` is a current value of the vocabulary."""
    if key in (None, ""):
        if required:
            raise Invalid("The record is not valid.", {field: "Choose a value."})
        return
    if key not in keys(session, name):
        raise Invalid("The record is not valid.", {field: f"{key!r} is not one of the choices."})


def check_many(session: Session, name: str, values: list[str] | None, field: str) -> list[str]:
    allowed = keys(session, name)
    chosen = list(dict.fromkeys(values or []))
    unknown = [value for value in chosen if value not in allowed]
    if unknown:
        raise Invalid(
            "The record is not valid.", {field: f"{unknown[0]!r} is not one of the choices."}
        )
    return chosen


def put(session: Session, name: str, items: list[dict[str, Any]]) -> None:
    """Replace a vocabulary. Keys already in use may be relabelled or retired, never removed:
    the caller is responsible for checking permission."""
    if name not in DEFAULTS:
        raise Invalid("There is no such vocabulary.", {"name": name})
    seen: set[str] = set()
    cleaned = []
    for item in items:
        key, label = str(item.get("key", "")).strip(), str(item.get("label", "")).strip()
        if not key or not label:
            raise Invalid(
                "The vocabulary is not valid.", {"items": "Every value needs a key and a label."}
            )
        if key in seen:
            raise Invalid(
                "The vocabulary is not valid.", {"items": f"The key {key!r} appears twice."}
            )
        seen.add(key)
        cleaned.append({**item, "key": key, "label": label})
    missing = [key for key in keys(session, name, active_only=False) if key not in seen]
    if missing:
        raise Invalid(
            "The vocabulary is not valid.",
            {"items": f"{missing[0]!r} is in use and cannot be removed. Retire it instead."},
        )
    settings.put(session, _setting(name), cleaned)
