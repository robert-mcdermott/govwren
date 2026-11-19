"""The tool server: an assistant reads GovWren and drafts, and a person submits."""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren import toolserver
from govwren.db.engine import Database
from govwren.db.models import UseCase
from tests.people import People
from tests.test_changes import linked

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")


def _caller(as_role: Clients, role: str, scope: str) -> toolserver.Call:
    """The server's way to GovWren, through the app under test, with a real token."""
    made = as_role(role).post("/api/v1/tokens", json={"name": "Assistant", "scope": scope})
    token = made.json()["data"]["token"]
    client = as_role(None)

    def call(method: str, path: str, query: dict[str, Any] | None, body: Any) -> tuple[int, Any]:
        client.cookies.clear()
        answer = client.request(
            method, path, params={k: v for k, v in (query or {}).items() if v},
            json=body, headers={"Authorization": f"Bearer {token}"},
        )  # fmt: skip
        try:
            return answer.status_code, answer.json()
        except ValueError:
            return answer.status_code, None

    return call


def _ask(call: toolserver.Call, name: str, **arguments: Any) -> tuple[Any, bool]:
    message = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}  # fmt: skip
    answer = toolserver.handle(call, message, "https://ai.example.org")
    assert answer is not None and answer["id"] == 7
    result = answer["result"]
    text = result["content"][0]["text"]
    return (text if result["isError"] else json.loads(text)), result["isError"]


def test_the_protocol(as_role: Clients) -> None:
    call = _caller(as_role, "member", "read")
    hello = toolserver.handle(
        call, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-03-26", "capabilities": {}}},
    )  # fmt: skip
    assert hello is not None and hello["result"]["protocolVersion"] == "2025-03-26"
    assert hello["result"]["capabilities"] == {"tools": {}}
    assert hello["result"]["serverInfo"]["name"] == "govwren"
    newer = toolserver.handle(
        call, {"jsonrpc": "2.0", "id": 2, "method": "initialize",
               "params": {"protocolVersion": "2099-01-01"}},
    )  # fmt: skip
    assert newer is not None and newer["result"]["protocolVersion"] == toolserver.PROTOCOLS[0]
    assert (
        toolserver.handle(call, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    )
    listed = toolserver.handle(call, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert listed is not None
    names = [tool["name"] for tool in listed["result"]["tools"]]
    assert names == ["search", "get_record", "check_reference", "catalog", "my_work",
                     "request_form", "draft_request", "update_draft"]  # fmt: skip
    assert all(tool["inputSchema"]["type"] == "object" for tool in listed["result"]["tools"])
    # Nothing an assistant could use to submit, decide, or change a record.
    assert not any(word in " ".join(names) for word in ("submit", "decide", "approve", "delete"))
    assert toolserver.handle(call, {"jsonrpc": "2.0", "id": 4, "method": "ping"})["result"] == {}  # type: ignore[index]
    unknown = toolserver.handle(call, {"jsonrpc": "2.0", "id": 5, "method": "resources/list"})
    assert unknown is not None and unknown["error"]["code"] == -32601

    source = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"ping"}\n\nnot json\n'
                         '{"jsonrpc":"2.0","method":"notifications/initialized"}\n')  # fmt: skip
    sink = io.StringIO()
    toolserver.serve(call, "", source, sink)
    lines = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert [line.get("result", line.get("error", {}).get("code")) for line in lines] == [{}, -32700]


def test_an_assistant_reads_what_its_account_may(
    as_role: Clients, db: Database, people: People
) -> None:
    use, system, _model = linked(db, people)
    call = _caller(as_role, "member", "read")
    found, failed = _ask(call, "search", query="Lumen")
    assert not failed and "Lumen" in json.dumps(found)
    record, _ = _ask(call, "get_record", ref=use.lower())
    assert record["ref"] == use and record["status"] == "approved_with_conditions"
    standing, _ = _ask(call, "check_reference", ref=system, data_class="restricted")
    assert standing["approved"] is True and standing["allowed"] is False
    tools, _ = _ask(call, "catalog", query="Lumen")
    assert "Lumen Assistant" in json.dumps(tools)
    waiting, failed = _ask(call, "my_work")
    assert not failed and isinstance(waiting, list)
    form, _ = _ask(call, "request_form")
    keys = [q["key"] for section in form["sections"] for q in section["questions"]]
    assert "name" in keys and "unit" in keys and {"id", "name"} <= set(form["units"][0])

    said, failed = _ask(call, "get_record", ref="UC-9999")
    assert failed and said == "There is no such record."
    said, failed = _ask(call, "get_record", ref="RV-0001")
    assert failed and "not the reference" in said
    said, failed = _ask(call, "draft_request", answers={"name": "x", "unit": 1})
    assert failed and "may not change anything" in said  # a read token cannot draft
    said, failed = _ask(call, "launch_rockets")
    assert failed and "no tool called" in said
    outsider = _caller(as_role, "reviewer", "read")  # the tools show no more than the account sees
    hidden, _ = _ask(outsider, "get_record", ref=use)
    assert hidden["sight"] == "summary" and "data_class" not in hidden


def test_an_assistant_drafts_and_a_person_submits(
    as_role: Clients, db: Database, people: People
) -> None:
    call = _caller(as_role, "member", "write")
    made, failed = _ask(
        call, "draft_request",
        answers={"name": "Summarizing seminar recordings", "unit": people.units["HALE"]},
    )  # fmt: skip
    assert not failed and made["state"] == "draft" and "must open it" in made["note"]
    ref = made["ref"]
    assert made["open"] == f"https://ai.example.org/use-cases/{ref}/request"
    more, failed = _ask(
        call, "update_draft", ref=ref,
        answers={"purpose": "Turn recorded seminars into short written summaries."},
    )  # fmt: skip
    assert not failed and more["saved"] is True
    with db.read() as session:
        draft = session.scalars(select(UseCase).where(UseCase.ref == ref)).one()
        assert draft.status == "draft" and draft.created_by == people.accounts["member"]
    kept = as_role("member").get(f"/api/v1/use-cases/{ref}/intake").json()["data"]
    assert kept["state"] == "draft" and kept["answers"]["name"] == "Summarizing seminar recordings"
    assert kept["answers"]["purpose"].startswith("Turn recorded")  # the first answers were kept

    said, failed = _ask(call, "draft_request", answers={"purpose": "No name or unit."})
    assert failed and "name" in said and "unit" in said
    approved, _system, _model = linked(db, people)
    said, failed = _ask(call, "update_draft", ref=approved, answers={"purpose": "Something else"})
    assert failed and "not a draft" in said
