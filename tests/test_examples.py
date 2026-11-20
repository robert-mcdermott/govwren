"""The example programs for other systems do what the guide says they do."""

from __future__ import annotations

import importlib.util
import json
import threading
from datetime import timedelta
from pathlib import Path
from types import ModuleType

import pytest

from govwren.core.clock import frozen_at
from govwren.db.engine import Database
from govwren.integration import checkpoint as service
from govwren.integration import webhooks
from tests.people import People
from tests.test_changes import linked
from tests.test_review import MONDAY, who

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
pytestmark = pytest.mark.usefixtures("program")


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, EXAMPLES / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_checkpoint_example_reads_the_answer_as_the_guide_says(
    db: Database, people: People
) -> None:
    example = _load("checkpoint")
    use, system, _model = linked(db, people)
    asker = who(db, people, "governance")
    with frozen_at(MONDAY), db.read() as session:
        from govwren.events.chain import jsonable

        def answer(ref: str, data_class: str | None = None) -> dict:  # type: ignore[type-arg]
            return json.loads(json.dumps(jsonable(service.check(session, asker, ref, data_class))))

        assert example.decide(answer(use), use) == (True, f"{use} is approved until 2029-11-02.")
        go, why = example.decide(answer(use, "public"), use)
        assert go and "approved for public data" in why
        go, why = example.decide(answer(use, "restricted"), use)
        assert not go and "only for data up to Internal" in why
        go, why = example.decide(answer(system, "restricted"), system)
        assert not go and "up to Protected" in why
    assert example.decide(None, "UC-9999") == (
        False,
        "There is no record UC-9999. Check the reference.",
    )
    go, why = example.decide({"approved": False, "status": "in_review"}, "UC-0002")
    assert not go and why.endswith("Its standing is: in review.")


def test_the_receiver_takes_only_what_govwren_signed() -> None:
    example = _load("webhook_receiver")
    body = b'{"topic":"test"}'
    now = 1_800_000_000.0
    stamp = str(int(now))
    good = webhooks.sign("whsec_x", stamp, body)
    assert example.genuine("whsec_x", stamp, good, body, now)
    assert not example.genuine("whsec_other", stamp, good, body, now)
    assert not example.genuine("whsec_x", stamp, good, body + b" ", now)
    assert not example.genuine("whsec_x", stamp, good, body, now + 301)  # too old
    assert not example.genuine("whsec_x", "soon", good, body, now)
    said = example.sentence(
        {"topic": "decision.made", "data": {"ref": "UC-0042", "outcome": "approved_with_conditions",
                                            "approved_until": "2027-05-01", "by_rule": False}},
        "https://ai.example.org",
    )  # fmt: skip
    assert said == (
        "UC-0042 was decided: approved with conditions, until 2027-05-01. "
        "https://ai.example.org/use-cases/UC-0042"
    )
    assert example.sentence({"topic": "incident.reported", "data": {"ref": "INC-0003"}}) == (
        "An incident was reported: INC-0003."
    )


def test_a_delivery_reaches_the_receiver_end_to_end(db: Database, people: People) -> None:
    """GovWren's own sender, a real socket, and the example receiver."""
    example = _load("webhook_receiver")
    admin = who(db, people, "admin")
    server = example.serve(0, "placeholder")
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        wanted = {
            "name": "Chat",
            "url": f"http://127.0.0.1:{port}/hook",
            "topics": ["decision.made"],
        }
        with frozen_at(MONDAY - timedelta(hours=1)), db.write(admin.actor) as session:
            hook, secret = webhooks.create(session, admin, wanted)
            hook_id = hook.id
        server.RequestHandlerClass.secret = secret
        use, _system, _model = linked(db, people)
        ran = webhooks.run_once(db)
        assert ran["sent"] == 1 and ran["failed"] == 0
        assert server.RequestHandlerClass.passed_on == [
            f"{use} was decided by rule: approved with conditions, until 2029-11-02."
        ]
        server.RequestHandlerClass.secret = "whsec_someone_else"
        assert webhooks.send_test(db, admin, hook_id) == "The receiver answered 401."
    finally:
        server.shutdown()
        server.server_close()


def test_a_copied_message_is_not_passed_on_twice() -> None:
    """The delivery number is not signed, so repeats are told apart by what is."""
    import http.client
    import time

    example = _load("webhook_receiver")
    server = example.serve(0, "whsec_x")
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    body = b'{"data":{"ref":"INC-0003"},"event":41,"topic":"incident.reported"}'
    stamp = str(int(time.time()))
    signature = webhooks.sign("whsec_x", stamp, body)
    try:
        for delivery in ("7", "8", "9"):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("POST", "/hook", body, {
                "X-GovWren-Timestamp": stamp, "X-GovWren-Signature": signature,
                "X-GovWren-Delivery": delivery, "Content-Type": "application/json"})  # fmt: skip
            assert connection.getresponse().status == 204
            connection.close()
        assert server.RequestHandlerClass.passed_on == ["An incident was reported: INC-0003."]
    finally:
        server.shutdown()
        server.server_close()
