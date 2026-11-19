"""Generated documentation must match the code. Regenerate with ``UPDATE_DOCS=1 uv run pytest
tests/test_docs.py``."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from govwren.cli import reference

DOCS = Path(__file__).resolve().parent.parent / "docs"
UPDATE = os.environ.get("UPDATE_DOCS") == "1"


def _check(path: Path, fresh: str) -> None:
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fresh, encoding="utf-8")
    assert path.is_file(), f"{path.name} is missing; run with UPDATE_DOCS=1"
    assert path.read_text(encoding="utf-8") == fresh, (
        f"{path.name} is out of date; run UPDATE_DOCS=1 uv run pytest tests/test_docs.py"
    )


def test_the_command_reference_is_current() -> None:
    _check(DOCS / "cli.md", reference.render())


def test_the_openapi_document_is_current(client: TestClient) -> None:
    document = client.get("/api/openapi.json").json()
    document["info"]["version"] = "current"  # the version changes every release
    _check(DOCS / "openapi.json", json.dumps(document, indent=2, sort_keys=True) + "\n")


CONTRACT = DOCS / "api-contract.json"


def _surface(document: dict) -> dict[str, list[str]]:  # type: ignore[type-arg]
    """What a caller depends on: each route, and the names it may send in the address."""
    surface = {}
    for path, methods in sorted(document["paths"].items()):
        for method, operation in sorted(methods.items()):
            names = sorted(
                parameter["name"]
                for parameter in operation.get("parameters", [])
                if parameter.get("in") == "query"
            )
            surface[f"{method.upper()} {path}"] = names
    return surface


def test_the_api_keeps_its_promises(client: TestClient) -> None:
    """The recorded contract is every route released so far and its query parameters. A
    route or a parameter may be added. Taking one away, or renaming it, breaks whoever
    calls it, and fails here until the contract is changed on purpose and the changelog
    says so under Breaking. ``UPDATE_DOCS=1`` records additions and never removes."""
    now = _surface(client.get("/api/openapi.json").json())
    recorded: dict[str, list[str]] = (
        json.loads(CONTRACT.read_text(encoding="utf-8"))["routes"] if CONTRACT.is_file() else {}
    )
    gone = sorted(set(recorded) - set(now))
    assert not gone, f"Routes were removed or renamed: {gone}"
    lost = {
        route: sorted(set(names) - set(now[route]))
        for route, names in recorded.items()
        if set(names) - set(now[route])
    }
    assert not lost, f"Query parameters were removed or renamed: {lost}"
    merged = {
        route: sorted(set(names) | set(recorded.get(route, []))) for route, names in now.items()
    }
    fresh = json.dumps({"contract": "govwren-api/v1", "routes": merged}, indent=2) + "\n"
    _check(CONTRACT, fresh)
