"""Findings: what a reader should know about a record before relying on it, and the same
for everything the record itself relies on.

A use case built on a system built on a model inherits what is known about both. Inherited
findings are marked as such, with the record they come from.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.inventory import links
from govwren.inventory.registry import RecordType

_STANDING = {
    "use_case": {
        "lapsed": ("danger", "Its approval has lapsed"),
        "suspended": ("danger", "Its approval is suspended"),
        "declined": ("danger", "It was declined"),
        "retired": ("warn", "It has been retired"),
    },
    "vendor": {
        "offboarding": ("warn", "This vendor is being offboarded"),
        "former": ("warn", "This vendor is no longer used"),
    },
}
_CATALOG = {
    "not_approved": ("danger", "It is not approved for use"),
    "retired": ("warn", "It has been retired from the catalog"),
}


def own(session: Session, chip: Mapping[str, Any]) -> list[dict[str, str]]:
    """The findings on one record, from its standing."""
    found = []
    kind, status = chip["type"], chip.get("status")
    if kind in _STANDING and status in _STANDING[kind]:
        tone, text = _STANDING[kind][status]
        found.append({"kind": "standing", "tone": tone, "text": text})
    elif kind not in _STANDING and status == "retired":
        found.append({"kind": "standing", "tone": "warn", "text": "It has been retired"})
    catalog = chip.get("catalog_status")
    if catalog in _CATALOG and not (catalog == "retired" and status == "retired"):
        tone, text = _CATALOG[catalog]
        found.append({"kind": "catalog", "tone": tone, "text": text})
    return found


def for_record(
    session: Session, principal: Principal, record_type: RecordType, record: Any
) -> dict[str, Any]:
    """A record's own findings, and those it inherits from what it relies on, nearest
    first. Records the reader may not see contribute nothing."""
    graph = links.graph(session, principal, record_type, record, depth=3)
    inherited = []
    for node in graph["nodes"]:
        if node["side"] != "upstream":
            continue
        for finding in own(session, node):
            inherited.append(
                {
                    **finding,
                    "inherited": True,
                    "from": {"type": node["type"], "ref": node["ref"], "name": node["name"]},
                    "via": node.get("via"),
                    "distance": node["distance"],
                }
            )
    inherited.sort(key=lambda f: (f["distance"], f["tone"] != "danger", f["from"]["name"]))
    return {"own": own(session, links.chip(record_type, record)), "inherited": inherited}
