"""The risk library: reusable risk statements, loaded from a pack."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.core.errors import Invalid
from govwren.db.models import RiskStatement


def builtin() -> dict[str, Any]:
    text = (
        resources.files("govwren.resources.packs").joinpath("risk-library.json").read_text("utf-8")
    )
    return json.loads(text)  # type: ignore[no-any-return]


def problems(pack: Any) -> list[str]:
    """Everything wrong with a risk library pack. An empty list means it can be loaded."""
    if not isinstance(pack, dict) or (pack.get("pack") or {}).get("kind") != "risk_library":
        return ["This is not a risk library pack."]
    found = []
    categories = {c.get("key") for c in pack.get("categories", []) if isinstance(c, dict)}
    seen: set[str] = set()
    for position, risk in enumerate(pack.get("risks") or [], start=1):
        key = risk.get("key") if isinstance(risk, dict) else None
        if not key or not risk.get("title") or not risk.get("description"):
            found.append(f"Risk {position} needs a key, a title, and a description.")
            continue
        if key in seen:
            found.append(f"The key {key} is used twice.")
        seen.add(key)
        if risk.get("category") not in categories:
            found.append(f"{key} names a category the pack does not define.")
    if not seen and not found:
        found.append("The pack holds no risks.")
    return found


def load(session: Session, pack: dict[str, Any]) -> int:
    """Add the pack's statements, and bring those already here up to date. Statements the
    pack no longer holds are retired, never removed: risks drawn from them keep their source."""
    wrong = problems(pack)
    if wrong:
        raise Invalid("The risk library was not loaded.", {"pack": " ".join(wrong)})
    labels = {c["key"]: c["label"] for c in pack["categories"]}
    version = pack["pack"].get("pack_version")
    existing = {row.key: row for row in session.scalars(select(RiskStatement))}
    for risk in pack["risks"]:
        values = {
            "category": risk["category"],
            "category_label": labels[risk["category"]],
            "title": risk["title"],
            "description": risk["description"],
            "treatment": risk.get("treatment"),
            "pack_version": version,
            "retired": False,
        }
        row = existing.pop(risk["key"], None)
        if row is None:
            session.add(RiskStatement(key=risk["key"], **values))
        else:
            for name, value in values.items():
                if getattr(row, name) != value:
                    setattr(row, name, value)
    if not pack["pack"].get("additions"):  # a content pack adds; it replaces nothing
        for row in existing.values():
            if not row.retired:
                row.retired = True
    session.flush()
    return len(pack["risks"])


def ensure(session: Session) -> bool:
    """Give an installation the built-in library if it has none."""
    if session.scalars(select(RiskStatement.id)).first() is not None:
        return False
    load(session, builtin())
    return True


def listing(session: Session) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(RiskStatement)
        .where(RiskStatement.retired.is_(False))
        .order_by(RiskStatement.category_label, RiskStatement.title)
    )
    return [
        {
            "key": r.key,
            "category": r.category,
            "category_label": r.category_label,
            "title": r.title,
            "description": r.description,
            "treatment": r.treatment,
        }
        for r in rows
    ]


def categories(session: Session) -> dict[str, str]:
    return dict(
        session.execute(
            select(RiskStatement.category, RiskStatement.category_label).distinct()
        ).all()  # type: ignore[arg-type]
    )
