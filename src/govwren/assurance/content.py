"""Content packs: more risks and controls for one kind of work, added to the libraries.

A content pack holds risk statements and controls, each under a category. Loading one adds
them, or brings them up to date if they are already here. Nothing is retired: the built-in
libraries and anything loaded before stay as they are.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.assurance import controls, library
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.events import audit

PREFIX = "content-"


def _packs() -> Any:
    return resources.files("govwren.resources.packs")


def builtin() -> list[dict[str, Any]]:
    """The content packs that come with GovWren, by key."""
    found = []
    for entry in sorted(_packs().iterdir(), key=lambda item: item.name):
        if entry.name.startswith(PREFIX) and entry.name.endswith(".json"):
            pack = json.loads(entry.read_text("utf-8"))
            found.append(
                {
                    "key": pack["pack"]["key"],
                    "title": pack["pack"]["title"],
                    "description": pack["pack"]["description"],
                    "risks": len(pack.get("risks") or []),
                    "controls": len(pack.get("controls") or []),
                }
            )
    return found


def read(key: str) -> dict[str, Any]:
    entry = _packs().joinpath(f"{key}.json")
    if not key.startswith(PREFIX) or not entry.is_file():
        raise NotFound(f"There is no content pack called {key}.")
    return json.loads(entry.read_text("utf-8"))  # type: ignore[no-any-return]


def _parts(pack: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    header = {**pack["pack"], "additions": True}
    risks = (
        {
            "pack": {**header, "kind": "risk_library"},
            "categories": pack.get("risk_categories") or [],
            "risks": pack["risks"],
        }
        if pack.get("risks")
        else None
    )
    safeguards = (
        {
            "pack": {**header, "kind": "control_library"},
            "categories": pack.get("control_categories") or [],
            "controls": pack["controls"],
        }
        if pack.get("controls")
        else None
    )
    return risks, safeguards


def problems(pack: Any) -> list[str]:
    if not isinstance(pack, dict) or (pack.get("pack") or {}).get("kind") != "content":
        return ["This is not a content pack."]
    if not pack["pack"].get("key") or not pack["pack"].get("title"):
        return ["The pack needs a key and a title."]
    risks, safeguards = _parts(pack)
    if risks is None and safeguards is None:
        return ["The pack holds no risks and no controls."]
    return (library.problems(risks) if risks else []) + (
        controls.problems(safeguards) if safeguards else []
    )


def load(session: Session, principal: Principal, pack: dict[str, Any]) -> dict[str, int]:
    """Add a content pack's risks and controls to the libraries."""
    if not principal.configures:
        raise PermissionDenied("Only governance or an administrator can load a content pack.")
    wrong = problems(pack)
    if wrong:
        raise Invalid("The content pack was not loaded.", {"pack": " ".join(wrong)})
    risks, safeguards = _parts(pack)
    with audit.operation(session, "content.load", pack=pack["pack"]["key"]):
        return {
            "risks": library.load(session, risks) if risks else 0,
            "controls": controls.load(session, safeguards) if safeguards else 0,
        }
