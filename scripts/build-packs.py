#!/usr/bin/env python3
"""Write the starter program packs from the default program.

Each starter is the default program with the changes one kind of organization would make
first: its own kinds of unit, areas of work, and a few rules and conditions. They are
written as whole packs, so that each can be read, edited, and loaded without the others.

    uv run python scripts/build-packs.py           write them
    uv run python scripts/build-packs.py --check   exit with 1 if any is out of date

A test runs the check, so edit this script, not the files it writes.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

PACKS = Path(__file__).resolve().parent.parent / "src" / "govwren" / "resources" / "packs"


def _items(*rows: tuple[str, str] | tuple[str, str, str]) -> list[dict[str, Any]]:
    return [
        {"key": row[0], "label": row[1], **({"description": row[2]} if len(row) > 2 else {})}
        for row in rows
    ]


def _vocabulary(name: str, *rows: tuple[str, str] | tuple[str, str, str]) -> list[dict[str, Any]]:
    """A vocabulary in the organization's words. A standard value it does not use is kept,
    retired: a value is never removed, so that a record that has it can still show it."""
    from govwren.program import vocab

    items = _items(*rows)
    kept = {item["key"] for item in items}
    return items + [
        {**item, "retired": True} for item in vocab.DEFAULTS[name] if item["key"] not in kept
    ]


def _rule(key: str, name: str, field: str, op: str, value: Any, **then: Any) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "when": {"field": field, "op": op, "value": value},
        "then": then,
    }


def _starter(default: dict[str, Any], key: str, title: str, description: str) -> dict[str, Any]:
    pack = copy.deepcopy(default)
    pack["pack"] = {
        **default["pack"],
        "key": key,
        "title": title,
        "description": description,
        "based_on": f"{default['pack']['key']} {default['pack']['pack_version']}",
    }
    pack["vocabularies"] = {}
    return pack


def research_institute(default: dict[str, Any]) -> dict[str, Any]:
    pack = _starter(
        default,
        "starter-research-institute",
        "Starter: research institute",
        "For an independent research institute: labs and cores under divisions, research "
        "first, with human-subjects work and publications given their own rules.",
    )
    pack["vocabularies"]["unit_kinds"] = _vocabulary(
        "unit_kinds",
        ("organization", "Institute"),
        ("division", "Division"),
        ("department", "Department"),
        ("center", "Center"),
        ("core", "Core facility"),
        ("lab", "Lab"),
        ("office", "Office"),
    )
    pack["review"]["condition_templates"].append(
        {
            "key": "data_use_terms",
            "text": "Use data received under an agreement only as that agreement allows, and "
            "check it before giving the data to any tool.",
            "kind": "ongoing",
        }
    )
    pack["review"]["rules"].append(
        _rule(
            "data-under-agreement",
            "Data received under an agreement",
            "answers.data_categories",
            "contains",
            "under_agreement",
            require=["data_stewardship"],
            conditions=["data_use_terms"],
        )
    )
    return pack


def university(default: dict[str, Any]) -> dict[str, Any]:
    pack = _starter(
        default,
        "starter-university",
        "Starter: university",
        "For a university: schools and departments, teaching beside research, and rules for "
        "student records and for decisions about students and applicants.",
    )
    vocab = pack["vocabularies"]
    vocab["unit_kinds"] = _vocabulary(
        "unit_kinds",
        ("organization", "University"),
        ("division", "School or college"),
        ("department", "Department"),
        ("center", "Center or institute"),
        ("core", "Core facility"),
        ("lab", "Lab or research group"),
        ("office", "Administrative office"),
    )
    vocab["domains"] = _vocabulary(
        "domains",
        ("research", "Research"),
        ("education", "Teaching and learning"),
        ("student_services", "Admissions and student services"),
        ("operations", "Administration"),
        ("software", "Software and IT"),
    )
    vocab["affected_groups"] = _vocabulary(
        "affected_groups",
        ("team", "Only the team using it"),
        ("staff", "Faculty and staff"),
        ("students", "Students"),
        ("applicants", "Applicants"),
        ("participants", "Research participants"),
        ("public", "The public"),
    )
    review = pack["review"]
    review["rules"] = [rule for rule in review["rules"] if rule["key"] != "patients"]
    review["condition_templates"] += [
        {
            "key": "student_records",
            "text": "Do not enter student education records unless the tool is approved for "
            "them in the catalog.",
            "kind": "ongoing",
        },
        {
            "key": "not_the_only_basis",
            "text": "Do not use it as the only basis for a grade, an admission, an award, or "
            "a finding of misconduct. A person decides, and can explain the decision.",
            "kind": "ongoing",
        },
    ]
    review["rules"] += [
        _rule(
            "student-data",
            "Student records",
            "answers.data_categories",
            "contains",
            "student",
            require=["privacy"],
            conditions=["student_records"],
        ),
        _rule(
            "students-and-applicants",
            "Students or applicants are affected",
            "answers.affected_groups",
            "contains_any",
            ["students", "applicants"],
            require=["privacy"],
        ),
        _rule(
            "decisions-about-people",
            "Decisions about people",
            "answers.outputs_used_for",
            "contains",
            "decisions_about_people",
            require=["legal", "integrity"],
            conditions=["not_the_only_basis", "human_reviews_each"],
        ),
    ]
    return pack


def academic_medical_center(default: dict[str, Any]) -> dict[str, Any]:
    pack = _starter(
        default,
        "starter-academic-medical-center",
        "Starter: academic medical center",
        "For an academic medical center: clinics beside labs, clinical safety review for "
        "anything near care, and conditions for work that touches the patient record.",
    )
    vocab = pack["vocabularies"]
    vocab["unit_kinds"] = _vocabulary(
        "unit_kinds",
        ("organization", "Medical center"),
        ("division", "Division"),
        ("department", "Department"),
        ("center", "Clinic or service line"),
        ("core", "Core facility"),
        ("lab", "Lab"),
        ("office", "Office"),
    )
    vocab["domains"] = _vocabulary(
        "domains",
        ("research", "Research"),
        ("clinical", "Clinical care"),
        ("quality", "Quality and patient safety"),
        ("education", "Education and training"),
        ("operations", "Operations"),
        ("software", "Software and IT"),
    )
    sections = {section["key"]: section for section in pack["forms"][0]["sections"]}
    sections["personal_data"]["questions"] += [
        {
            "key": "health_basis",
            "type": "choice",
            "label": "On what basis may this health information be used for this purpose?",
            "help": "Ask the privacy office if you are not sure. Choosing that is a fine answer.",
            "show_when": {"field": "answers.data_categories", "op": "contains", "value": "health"},
            "options": [
                {"key": "care", "label": "Treatment, or running the service that gives it"},
                {"key": "authorization", "label": "The patient's written authorization"},
                {"key": "waiver", "label": "A waiver from the ethics board"},
                {"key": "limited", "label": "A limited data set under a data use agreement"},
                {"key": "deidentified", "label": "It is de-identified first"},
                {"key": "unsure", "label": "Not sure"},
            ],
        },
    ]
    sections["people"]["questions"] += [
        {
            "key": "uses_characteristics",
            "type": "choice",
            "label": "Does it take a person's race, ethnicity, sex, age, or disability into "
            "account when it helps decide their care?",
            "help": "For example as an input to a score. Say yes even if it is one input "
            "among many.",
            "show_when": {
                "field": "answers.decision_role",
                "op": "in",
                "value": ["recommends", "decides"],
            },
            "options": [
                {"key": "yes", "label": "Yes"},
                {"key": "no", "label": "No"},
                {"key": "unsure", "label": "Not sure"},
            ],
        },
    ]
    review = pack["review"]
    review["condition_templates"] += [
        {
            "key": "checked_by_group",
            "text": "Show how it performs for each group of patients whose characteristics it "
            "uses, and say what is done where it performs worse.",
            "kind": "before_use",
        },
        {
            "key": "clinician_signs",
            "text": "Nothing it produces goes into a patient's record until a clinician has "
            "read it, corrected it, and signed it.",
            "kind": "ongoing",
        },
        {
            "key": "downtime_plan",
            "text": "Keep a way to do this work without it, and show that the way has been tried.",
            "kind": "before_use",
        },
    ]
    review["rules"] += [
        _rule(
            "clinical-work",
            "Clinical care or patient safety",
            "answers.domain",
            "in",
            ["clinical", "quality"],
            require=["clinical_safety", "privacy"],
            conditions=["clinician_signs"],
        ),
        _rule(
            "recommends-or-decides-for-patients",
            "It recommends or decides, and patients are affected",
            "answers.decision_role",
            "in",
            ["recommends", "decides"],
            conditions=["downtime_plan"],
        ),
        _rule(
            "health-basis-unsure",
            "The basis for using health information is not settled",
            "answers.health_basis",
            "eq",
            "unsure",
            require=["privacy"],
        ),
        _rule(
            "care-decisions-use-characteristics",
            "It helps decide care and takes a person's characteristics into account",
            "answers.uses_characteristics",
            "in",
            ["yes", "unsure"],
            require=["clinical_safety", "ethics"],
            conditions=["checked_by_group"],
        ),
    ]
    return pack


STARTERS = {
    "starter-research-institute": research_institute,
    "starter-university": university,
    "starter-academic-medical-center": academic_medical_center,
}


def main() -> int:
    default = json.loads((PACKS / "default-program.json").read_text("utf-8"))
    stale = []
    for key, make in STARTERS.items():
        text = json.dumps(make(default), indent=2, ensure_ascii=False) + "\n"
        path = PACKS / f"{key}.json"
        if "--check" in sys.argv:
            if not path.is_file() or path.read_text("utf-8") != text:
                stale.append(path.name)
        else:
            path.write_text(text, encoding="utf-8")
            print(f"Wrote {path.name}")
    if stale:
        print(f"Out of date: {', '.join(stale)}. Run scripts/build-packs.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
