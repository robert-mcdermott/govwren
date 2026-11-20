"""An optional tool server, so that an AI assistant can read GovWren and draft for a person.

It speaks the Model Context Protocol over standard input and output: an assistant's host
program starts ``govwren tools serve`` and asks it for tools. Each tool is one call to
GovWren's own API, made with an API token, so the assistant is the token's account and can
see and do exactly what that account can, cut down to the token's scope.

What it can do is deliberately short. It reads: search, a record, the catalog, the
checkpoint, what is waiting on the person. And it drafts: it can begin a request and fill
in its answers. It cannot submit a request, decide anything, or change a record. A draft
sits in GovWren until a person opens it, reads it, and submits it themselves.

Nothing here is needed to run GovWren, and nothing runs unless someone starts it.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import IO, Any

from govwren import __version__
from govwren.core import net

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
PATHS = {"UC": "use-cases", "SYS": "systems", "MDL": "models", "DS": "datasets", "VND": "vendors"}

# (method, path, query, body) -> (status, parsed JSON or None)
Call = Callable[[str, str, dict[str, Any] | None, Any], tuple[int, Any]]


def http_caller(base: str, token: str) -> Call:
    """Calls a GovWren server over HTTP with a token."""

    def call(method: str, path: str, query: dict[str, Any] | None, body: Any) -> tuple[int, Any]:
        address = base.rstrip("/") + path
        if query:
            address += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v})
        request = urllib.request.Request(  # noqa: S310
            address,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method=method,
        )
        try:
            # A redirect is not followed: it would carry the token to wherever it points.
            with net.opener().open(request, timeout=20) as answer:
                return int(answer.status), json.load(answer)
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.load(error)
            except ValueError:
                return error.code, None

    return call


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


_REF = {"type": "string", "description": "A GovWren reference, such as UC-0042 or SYS-0007"}
_ANSWERS = {
    "type": "object",
    "description": "Answers by question key, as request_form lists them. Give only what the "
    "person has told you. Leave out what you do not know: they will finish it themselves.",
}
TOOLS: list[dict[str, Any]] = [
    {
        "name": "search",
        "description": "Find records in GovWren by words or by reference: use cases, AI "
        "systems, models, datasets, and vendors. Returns only what this account may see.",
        "inputSchema": _schema({"query": {"type": "string"}}, ["query"]),
    },
    {
        "name": "get_record",
        "description": "Read one record by its reference: what it is, who owns it, how it "
        "stands, its tier, and what it relies on.",
        "inputSchema": _schema({"ref": _REF}, ["ref"]),
    },
    {
        "name": "check_reference",
        "description": "Ask whether a reference is approved, until when, and for what class "
        "of data. Give data_class to ask whether it covers data that sensitive.",
        "inputSchema": _schema(
            {"ref": _REF, "data_class": {"type": "string", "description": "A data class key"}},
            ["ref"],
        ),
    },
    {
        "name": "catalog",
        "description": "The AI tools the organization has evaluated, with whether each may be "
        "used and with what data. Use this to answer 'may I use X?'.",
        "inputSchema": _schema({"query": {"type": "string", "description": "A tool's name"}}),
    },
    {
        "name": "my_work",
        "description": "What is waiting on the person: reviews to do, questions to answer, "
        "conditions due, records to confirm.",
        "inputSchema": _schema({}),
    },
    {
        "name": "request_form",
        "description": "The questions on the request form, with their keys and choices, and "
        "the units a request can belong to. Read this before drafting a request.",
        "inputSchema": _schema({}),
    },
    {
        "name": "draft_request",
        "description": "Begin a request to use AI, as a draft. Needs at least what it is for "
        "(the 'name' question) and the unit. Nothing is submitted: the person must open the "
        "draft in GovWren, check it, and submit it themselves. Tell them so, with the link.",
        "inputSchema": _schema({"answers": _ANSWERS}, ["answers"]),
    },
    {
        "name": "update_draft",
        "description": "Add to or correct the answers of a request that is still a draft. "
        "Nothing is submitted.",
        "inputSchema": _schema({"ref": _REF, "answers": _ANSWERS}, ["ref", "answers"]),
    },
]


class ToolError(Exception):
    """Something to tell the assistant, in words it can pass on."""


def _data(answer: tuple[int, Any], missing: str = "There is no such record.") -> Any:
    status, body = answer
    if status == 404:
        raise ToolError(missing)
    if status in (401, 403):
        detail = (body or {}).get("detail") if isinstance(body, dict) else None
        raise ToolError(detail or "The token this server was started with may not do that.")
    if status == 422 and isinstance(body, dict):
        problems = "; ".join(
            f"{'.'.join(map(str, error.get('location', [])))}: {error.get('message')}"
            for error in body.get("errors", [])
        )
        raise ToolError(f"{body.get('detail') or 'That was not accepted.'} {problems}".strip())
    if status >= 400 or not isinstance(body, dict):
        raise ToolError(f"GovWren answered {status}.")
    return body.get("data")


def _path_of(ref: str) -> str:
    cleaned = ref.strip().upper()
    kind = PATHS.get(cleaned.split("-")[0])
    if kind is None:
        raise ToolError(
            "That is not the reference of a use case, system, model, dataset, or vendor."
        )
    return f"/api/v1/{kind}/{urllib.parse.quote(cleaned)}"


def run_tool(call: Call, name: str, arguments: dict[str, Any], base: str = "") -> Any:
    """Do one tool's work and return what the assistant is given."""
    link = (lambda ref: f"{base.rstrip('/')}/use-cases/{ref}/request") if base else (lambda ref: "")
    if name == "search":
        return _data(call("GET", "/api/v1/search", {"q": str(arguments.get("query", ""))}, None))
    if name == "get_record":
        return _data(call("GET", _path_of(str(arguments.get("ref", ""))), None, None))
    if name == "check_reference":
        ref = urllib.parse.quote(str(arguments.get("ref", "")).strip().upper())
        query = {"data_class": arguments.get("data_class")}
        return _data(call("GET", f"/api/v1/checkpoint/{ref}", query, None))
    if name == "catalog":
        return _data(call("GET", "/api/v1/catalog", {"q": arguments.get("query")}, None))
    if name == "my_work":
        return _data(call("GET", "/api/v1/me/work", None, None))
    if name == "request_form":
        program = _data(call("GET", "/api/v1/intake", None, None))
        units = _data(call("GET", "/api/v1/units", None, None))
        return {
            "sections": program["form"]["schema"]["sections"],
            "units": [{"id": unit["id"], "name": unit["name"]} for unit in units["units"]],
            "note": "Give a unit by its id. A draft needs only 'name' and 'unit' to begin.",
        }
    if name == "draft_request":
        made = _data(call("POST", "/api/v1/intake", None, {"answers": arguments.get("answers")}))
        return {
            "ref": made["ref"],
            "state": "draft",
            "progress": made.get("progress"),
            "open": link(made["ref"]),
            "note": "This is a draft. Nothing has been submitted. The person must open it in "
            "GovWren, check every answer, and submit it themselves.",
        }
    if name == "update_draft":
        ref = urllib.parse.quote(str(arguments.get("ref", "")).strip().upper())
        at = f"/api/v1/use-cases/{ref}/intake"
        now = _data(call("GET", at, None, None), "There is no such draft.")
        if now.get("state") != "draft" or not now.get("can_edit"):
            raise ToolError(f"{ref} is not a draft you can change. It may already be submitted.")
        merged = {**(now.get("answers") or {}), **(arguments.get("answers") or {})}
        saved = _data(call("PUT", at, None, {"answers": merged}), "There is no such draft.")
        return {
            "ref": ref,
            "saved": saved.get("saved"),
            "still_wrong": saved.get("errors"),
            "open": link(ref),
            "note": "Still a draft. The person submits it themselves.",
        }
    raise ToolError(f"There is no tool called {name}.")


def handle(call: Call, message: dict[str, Any], base: str = "") -> dict[str, Any] | None:
    """Answer one message of the protocol. A notification gets no answer."""
    method, identifier = message.get("method"), message.get("id")
    if identifier is None:
        return None

    def result(value: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": identifier, "result": value}

    if method == "initialize":
        asked = (message.get("params") or {}).get("protocolVersion")
        return result(
            {
                "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "govwren", "version": __version__},
                "instructions": "GovWren is this organization's record of how it uses AI. "
                "You may read it and you may draft a request for the person. You cannot "
                "submit, approve, or change anything: the person does that in GovWren.",
            }
        )
    if method == "ping":
        return result({})
    if method == "tools/list":
        return result({"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            value = run_tool(call, str(params.get("name")), params.get("arguments") or {}, base)
            text, failed = json.dumps(value, indent=1, ensure_ascii=False, default=str), False
        except ToolError as error:
            text, failed = str(error), True
        except (OSError, KeyError, TypeError, ValueError) as error:
            text, failed = f"GovWren could not be asked: {type(error).__name__}.", True
        return result({"content": [{"type": "text", "text": text}], "isError": failed})
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def serve(
    call: Call, base: str = "", source: IO[str] = sys.stdin, sink: IO[str] = sys.stdout
) -> None:
    """Read one JSON message a line and write one answer a line, until the input ends."""
    for line in source:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            answer: dict[str, Any] | None = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
        else:
            answer = handle(call, message, base) if isinstance(message, dict) else None
        if answer is not None:
            sink.write(json.dumps(answer, ensure_ascii=False) + "\n")
            sink.flush()
