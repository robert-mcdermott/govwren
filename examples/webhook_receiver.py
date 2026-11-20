#!/usr/bin/env python3
"""Receive GovWren's webhook messages and pass them on to a chat channel or a ticket system.

    export GOVWREN_WEBHOOK_SECRET=whsec_...       # shown once when the webhook is added
    export FORWARD_URL=https://chat.example.org/hooks/abc   # an incoming-webhook address
    python3 webhook_receiver.py 8099

Each message's signature is checked before anything is done with it. A message that is not
from GovWren, or is more than five minutes old, is refused. A message that arrives twice is
passed on once.

What is passed on is JSON with one field, `text`, which is what most chat systems' incoming
webhooks accept. Change `sentence` and `forward` to suit a ticket system.

Standard library only. Put a reverse proxy with TLS in front of it: GovWren delivers only
to https addresses.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MAX_AGE = 300  # seconds
REMEMBER = 5000  # deliveries, to pass each on once
# Where each kind of reference is shown in GovWren.
PAGES = {"UC": "use-cases", "SYS": "systems", "MDL": "models", "INC": "incidents"}


def genuine(secret: str, stamp: str, signature: str, body: bytes, now: float | None = None) -> bool:
    """Whether a message was signed with the secret, recently."""
    if not stamp.isdigit() or abs((now or time.time()) - int(stamp)) > MAX_AGE:
        return False
    expected = hmac.new(secret.encode(), stamp.encode() + b"." + body, hashlib.sha256)
    return hmac.compare_digest(f"sha256={expected.hexdigest()}", signature)


def sentence(message: dict[str, Any], base: str = "") -> str:
    """One line a person can read, for a chat channel or a ticket's title."""
    topic, data = message.get("topic"), message.get("data") or {}
    ref = data.get("ref") or ""
    page = PAGES.get(ref.split("-")[0])
    link = f" {base.rstrip('/')}/{page}/{ref}" if base and page else ""
    words = lambda value: str(value or "").replace("_", " ")  # noqa: E731
    if topic == "use_case.status_changed":
        name = f" ({data['name']})" if data.get("name") else ""
        return f"{ref}{name} is now {words(data.get('to'))}.{link}"
    if topic == "decision.made":
        by = " by rule" if data.get("by_rule") else ""
        until = f", until {data['approved_until']}" if data.get("approved_until") else ""
        return f"{ref} was decided{by}: {words(data.get('outcome'))}{until}.{link}"
    if topic == "catalog.changed":
        return f"{ref} is now {words(data.get('to'))} in the catalog.{link}"
    if topic == "incident.reported":
        return f"An incident was reported: {ref}.{link}"
    if topic == "test":
        return "A test message from GovWren arrived."
    return f"GovWren: {topic}"


def forward(address: str, text: str) -> None:
    body = json.dumps({"text": text}).encode()
    request = urllib.request.Request(  # noqa: S310
        address, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=10):  # noqa: S310
        pass


class Receiver(BaseHTTPRequestHandler):
    secret = ""
    forward_to = ""
    base = ""
    seen: OrderedDict[str, bool]  # set for each server by `serve`
    passed_on: list[str]  # kept for whoever is testing this

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(min(length, 1_000_000))
        stamp = self.headers.get("X-GovWren-Timestamp", "")
        if not genuine(self.secret, stamp, self.headers.get("X-GovWren-Signature", ""), body):
            self.send_response(401)
            self.end_headers()
            return
        message = json.loads(body)
        # Repeats are told apart by what the signature covers: the event and its topic, which
        # a sender trying again repeats exactly. The delivery number in the headers is not
        # signed, so a copied message could be sent again under a new one.
        delivery = (
            f"{message.get('topic')}:{message.get('event')}"
            if message.get("event")
            else self.headers.get("X-GovWren-Signature", "")
        )
        # Answer first: GovWren waits ten seconds, and tries again if it hears nothing.
        self.send_response(204)
        self.end_headers()
        if delivery in self.seen:
            return
        self.seen[delivery] = True
        while len(self.seen) > REMEMBER:
            self.seen.popitem(last=False)
        text = sentence(message, self.base)
        self.passed_on.append(text)
        if self.forward_to:
            try:
                forward(self.forward_to, text)
            except OSError as error:
                print(f"Could not pass it on: {error}", file=sys.stderr)

    def log_message(self, *_args: Any) -> None:  # the default logs every request to stderr
        return


def serve(port: int, secret: str, forward_to: str = "", base: str = "") -> ThreadingHTTPServer:
    handler = type("Configured", (Receiver,), {
        "secret": secret, "forward_to": forward_to, "base": base,
        "seen": OrderedDict(), "passed_on": [],
    })  # fmt: skip
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main() -> int:
    secret = os.environ.get("GOVWREN_WEBHOOK_SECRET", "")
    if not secret:
        print(
            "Set GOVWREN_WEBHOOK_SECRET to the secret shown when the webhook was added.",
            file=sys.stderr,
        )
        return 2
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    server = serve(
        port, secret, os.environ.get("FORWARD_URL", ""), os.environ.get("GOVWREN_URL", "")
    )
    print(f"Listening on 127.0.0.1:{port}")
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
