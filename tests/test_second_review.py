"""Findings of the second security review (wave 9), each with a test that fails without its fix.
The bypasses of the rule on agreements covering health information are tested in
test_health_agreements.py."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from dataclasses import replace
from email.message import EmailMessage
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from govwren.assurance import assessments, controls, frameworks
from govwren.core.errors import NotFound
from govwren.db.engine import Database
from govwren.db.models import Control, OutboxMessage
from govwren.insight import formats
from govwren.inventory import access, agreements, history, links, records
from govwren.inventory.registry import DATASET, MODEL, SYSTEM, VENDOR, find
from govwren.program import branding
from govwren.review import service as review
from tests.conftest import Instance
from tests.people import ME, People
from tests.test_review import who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")


def _bearer(client: TestClient, token: str) -> dict[str, str]:
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def test_a_signal_token_pushes_only_where_its_account_may(
    as_role: Clients, db: Database, people: People
) -> None:
    governance = who(db, people, "governance")
    with db.write(ME.actor) as session:
        sealed = records.create(
            session, governance, SYSTEM,
            {"name": "Sealed tool", "kind": "internal_app", "restricted": True},
        )  # fmt: skip
        sealed_ref = sealed.ref
    member = as_role("member")
    made = member.post("/api/v1/tokens", json={"name": "My script", "scope": "signal"})
    script = as_role(None)
    token = _bearer(script, made.json()["data"]["token"])
    body = {"title": "Check", "source": "Script", "result": "warn"}
    hidden = script.post("/api/v1/signals", headers=token, json={**body, "ref": sealed_ref})
    missing = script.post("/api/v1/signals", headers=token, json={**body, "ref": "SYS-9999"})
    # A record it may not push onto is answered exactly as one that does not exist.
    assert hidden.status_code == missing.status_code == 422
    assert hidden.json()["errors"] == missing.json()["errors"]


def test_a_record_you_cannot_see_is_not_named_through_its_links(
    as_role: Clients, db: Database, people: People
) -> None:
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with db.write(ME.actor) as session:
        model = records.create(
            session, governance, MODEL,
            {"name": "Open model", "kind": "language", "origin": "open_weights"},
        )  # fmt: skip
        sealed = records.create(
            session, governance, DATASET,
            {"name": "Sealed cohort", "data_class": "restricted", "restricted": True},
        )  # fmt: skip
        links.add(session, governance, model.ref, "trained_on", sealed.ref)
        vendor = records.create(session, governance, VENDOR, {"name": "Cobaltine"})
        hidden_tool = records.create(
            session, governance, SYSTEM,
            {"name": "Hidden tool", "kind": "vendor_product", "vendor": vendor.ref,
             "restricted": True},
        )  # fmt: skip
        agreements.create(
            session,
            governance,
            vendor,
            {"kind": "health_information", "title": "Agreement", "covers": [hidden_tool.ref]},
        )
        model_ref, vendor_ref = model.ref, vendor.ref
    with db.read() as session:
        model = find(session, MODEL, model_ref)
        with pytest.raises(NotFound):
            records.detail(session, member, DATASET, find(session, DATASET, "DS-0001"))
        card = formats.model_card(session, member, model)
        assert "Sealed cohort" not in card and access.HIDDEN_NAME in card
        assert "Sealed cohort" in formats.model_card(session, governance, model)
        past = history.for_record(session, MODEL, model, principal=member)
        assert not any("Sealed cohort" in entry["title"] for entry in past)
        assert any(
            "Sealed cohort" in entry["title"]
            for entry in history.for_record(session, MODEL, model, principal=governance)
        )
        shown = records.detail(session, member, VENDOR, find(session, VENDOR, vendor_ref))
        assert shown["agreements"][0]["covers"] == []
    seen = as_role("member").get(f"/api/v1/models/{model_ref}/history").json()["data"]
    assert not any("Sealed cohort" in entry["title"] for entry in seen)


def test_security_assessments_are_for_those_responsible_and_reviewers(
    db: Database, people: People
) -> None:
    governance, member, reviewer = (
        who(db, people, r) for r in ("governance", "member", "reviewer")
    )
    with db.write(governance.actor) as session:
        agent = records.create(session, governance, SYSTEM, {"name": "Desk agent", "kind": "agent"})
        assessments.save(
            session, governance, SYSTEM, agent, "agent_assessment",
            {"credentials": "One token, kept in the vault."},
        )  # fmt: skip
        vendor = records.create(session, governance, VENDOR, {"name": "Cobaltine"})
        agent_ref, vendor_ref = agent.ref, vendor.ref
    with db.read() as session:
        agent, vendor = find(session, SYSTEM, agent_ref), find(session, VENDOR, vendor_ref)
        with pytest.raises(NotFound):
            assessments.view(session, member, SYSTEM, agent, "agent_assessment")
        with pytest.raises(NotFound):
            assessments.view(session, member, VENDOR, vendor, "vendor_due_diligence")
        seen = assessments.view(session, reviewer, SYSTEM, agent, "agent_assessment")
        assert seen["answers"]["credentials"].startswith("One token")
        assert assessments.view(session, governance, VENDOR, vendor, "vendor_due_diligence")


def test_the_statement_of_applicability_cannot_carry_a_formula(
    db: Database, people: People
) -> None:
    governance = who(db, people, "governance")
    with db.write(ME.actor) as session:
        controls.ensure(session)
        control = session.scalars(select(Control).where(Control.key == "roles-assigned")).one()
        from govwren.people import accounts

        account = accounts.get(session, people.accounts["member"])
        account.display_name = '=HYPERLINK("https://elsewhere.example","x")'
        controls.set_standing(
            session, governance, control, {"owner_id": account.id, "status": "in_progress"}
        )
        loaded = frameworks.load(session, governance, frameworks.builtin("nist-ai-rmf"))
        sheets = [
            frameworks.statement_csv(frameworks.statement_of_applicability(session, governance)),
            frameworks.statement_csv(
                frameworks.framework_statement(session, governance, loaded),
                frameworks.FRAMEWORK_HEADINGS,
            ),
        ]
    for sheet in sheets:
        for row in csv.reader(io.StringIO(sheet)):
            assert not any(cell[:1] in ("=", "+", "-", "@") for cell in row), row


def test_a_line_break_in_a_notice_does_not_stop_email(
    db: Database, people: People, instance: Instance
) -> None:
    from govwren import mail

    with db.bookkeeping() as session:
        review.notify(session, [people.accounts["member"]], "decision", "Tool\r\nBcc: x@y", "/")
        review.notify(session, [people.accounts["member"]], "decision", "The next notice", "/")
    sent: list[EmailMessage] = []

    class Sender:
        def send(self, message: EmailMessage) -> None:
            sent.append(message)

    config = replace(
        instance.config,
        mail=replace(instance.config.mail, host="127.0.0.1", from_address="g@alderpoint.example"),
    )
    assert mail.run_once(db, config, Sender())["sent"] == 2
    assert [m["Subject"] for m in sent] == ["Tool Bcc: x@y", "The next notice"]
    with db.read() as session:
        assert set(session.scalars(select(OutboxMessage.status))) == {"sent"}


def test_a_model_card_carries_no_markup(db: Database, people: People) -> None:
    governance = who(db, people, "governance")
    with db.write(ME.actor) as session:
        model = records.create(
            session, governance, MODEL,
            {"name": "Model <b>", "kind": "language", "origin": "open_weights",
             "summary": '<img src=x onerror="alert(1)">'},
        )  # fmt: skip
        card = formats.model_card(session, governance, model)
    assert "<img" not in card and "&lt;img" in card and "Model &lt;b&gt;" in card


def test_an_svg_named_in_the_configuration_file_is_cleaned(
    instance: Instance, tmp_path: Path
) -> None:
    from govwren.api.app import create_app

    (tmp_path / "logo.svg").write_bytes(
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script>'
        b'<rect width="2" height="2" onclick="alert(2)"/></svg>'
    )
    file, found = branding.from_file({"logo_light": "logo.svg"}, tmp_path)
    assert found == [] and file is not None
    try:
        app = create_app(replace(instance.config, branding=file))
        with TestClient(app, base_url="http://localhost") as client:
            served = client.get("/branding/logo-light")
        assert served.status_code == 200 and b"<rect" in served.content
        assert b"script" not in served.content and b"onclick" not in served.content
    finally:
        branding.pin(None)
    (tmp_path / "bad.svg").write_bytes(b'<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"/>')
    assert branding.from_file({"logo_light": "bad.svg"}, tmp_path)[1]


# --- Integrations and outbound calls -----------------------------------------------------


def test_the_assistant_is_never_shown_a_class_a_draft_has_raised(
    db: Database, people: People
) -> None:
    from govwren import assistant
    from govwren.core.errors import Invalid
    from govwren.db.models import IntakeDraft, Review
    from tests.test_assistant import ON, Model
    from tests.test_review import HIGH, request

    ref = request(db, people, HIGH)  # internal data, which the assistant may be shown
    governance = who(db, people, "governance")
    model = Model("- A summary.")
    with db.write(governance.actor) as session:
        found = session.scalars(select(Review).where(Review.ref == ref)).one()
        use_case = review.subject_of(session, found)
        response = review.latest_answers(session, use_case)
        version = session.scalars(select(IntakeDraft.form_version_id)).first()
        from govwren.intake import service as intake

        session.add(
            IntakeDraft(
                use_case_id=use_case.id,
                form_version_id=version or intake.current_form(session).id,
                answers={**response, "data_class": "restricted", "purpose": "Restricted detail."},
                updated_at=use_case.updated_at,
            )
        )
        session.flush()
        with pytest.raises(Invalid):
            assistant.summarize_review(session, governance, ON, found, model)
    assert model.saw == []


def test_no_redirect_is_followed_and_a_slow_server_is_given_up_on() -> None:
    import http.server
    import threading
    import time

    from govwren import assistant
    from govwren.config import AssistantConfig
    from govwren.core import net

    class Redirect(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/elsewhere")
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        config = AssistantConfig(url=f"http://127.0.0.1:{server.server_port}/v1", model="m")
        with pytest.raises(assistant.AssistantError):
            assistant.ask_server(config, [{"role": "user", "content": "hello"}])
    finally:
        server.shutdown()
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        net.within(0.3, lambda: time.sleep(5))
    assert time.monotonic() - started < 2

    class Trickle:
        def read(self, size: int) -> bytes:
            time.sleep(0.05)
            return b"x"

    with pytest.raises(TimeoutError):
        net.read_within(Trickle(), 1_000_000, 0.2)


def test_a_registry_name_cannot_leave_the_model_s_place(db: Database, people: People) -> None:
    from govwren.core.errors import Invalid
    from govwren.integration import registry

    assert registry.name_ok("lumen/lumen-large") and registry.name_ok("org/model:v1.2")
    for bad in ("../../admin", "lumen/../secrets", "/abs", "a//b", "a/./b", "a b", "a?x=1"):
        assert not registry.name_ok(bad), bad
    governance = who(db, people, "governance")
    with db.write(ME.actor) as session, pytest.raises(Invalid) as refused:
        records.create(
            session, governance, MODEL,
            {"name": "M", "kind": "language", "origin": "open_weights",
             "registry_name": "../../../admin/secrets"},
        )  # fmt: skip
    assert "registry_name" in refused.value.errors


def test_the_demo_sign_in_needs_a_name_for_this_machine(as_role: Clients) -> None:
    from types import SimpleNamespace

    from govwren.api.routers import session as sessions

    def asked(host: str) -> object:
        server = SimpleNamespace(base_url="")
        app = SimpleNamespace(state=SimpleNamespace(config=SimpleNamespace(server=server)))
        return SimpleNamespace(headers={"host": host}, app=app)

    assert not sessions._named_locally(asked("rebind.attacker.example:8010"))  # type: ignore[arg-type]
    assert sessions._named_locally(asked("127.0.0.1:8010"))  # type: ignore[arg-type]
    assert sessions._named_locally(asked("localhost"))  # type: ignore[arg-type]


def test_a_change_being_written_does_not_rename_the_approved_use(
    db: Database, people: People
) -> None:
    from govwren.intake import service as intake
    from tests.test_changes import LATER, declared
    from tests.test_schedule import use_case_of

    first = declared(db, people)
    member = who(db, people, "member")
    from govwren.core.clock import frozen_at

    with frozen_at(LATER), db.write(member.actor) as session:
        use_case = use_case_of(session, first)
        name = use_case.name
        answers = review.latest_answers(session, use_case)
        intake.save(session, member, use_case, {**answers, "name": "Something else entirely"})
        assert use_case.name == name and use_case.status != "draft"


def test_every_token_ends_within_a_year(as_role: Clients) -> None:
    from datetime import date, timedelta

    from govwren.core.clock import today

    member = as_role("member")
    made = member.post("/api/v1/tokens", json={"name": "Script", "scope": "read"}).json()["data"]
    ends = date.fromisoformat(made["expires_on"])
    assert today() < ends <= today() + timedelta(days=366)
    too_long = (today() + timedelta(days=400)).isoformat()
    refused = member.post(
        "/api/v1/tokens", json={"name": "Long", "scope": "read", "expires_on": too_long}
    )
    assert refused.status_code == 422


def test_addresses_are_judged_by_their_host() -> None:
    from govwren.config import _secure_or_local

    assert _secure_or_local("https://models.example.org/v1")
    assert _secure_or_local("http://localhost:11434/v1") and _secure_or_local("http://127.0.0.1/x")
    for bad in ("http://localhost.attacker.example/v1", "http://host/x//localhost",
                "http://models.example.org", "ftp://localhost/"):  # fmt: skip
        assert not _secure_or_local(bad), bad


def test_nothing_holds_the_database_while_another_server_is_asked(
    db: Database, people: People
) -> None:
    from govwren.integration import webhooks

    admin = who(db, people, "admin")
    with db.write(admin.actor) as session:
        hook, _secret = webhooks.create(
            session, admin, {"name": "Chat", "url": "https://chat.example.org/hook",
                             "topics": ["decision.made"]},
        )  # fmt: skip
        hook_id = hook.id
    others: list[int] = []

    def receiver(url: str, body: bytes, headers: dict[str, str]) -> int:
        # Another person's work, done while the receiver is being asked. A write session
        # takes the database's write lock at once; it would wait, and then fail, if the
        # delivery were holding it.
        with db.bookkeeping() as session:
            others.append(session.execute(text("SELECT 1")).scalar_one())
        return 204

    assert webhooks.send_test(db, admin, hook_id, receiver) == "Delivered" and others == [1]


def test_a_restricted_use_is_not_named_to_a_webhook(db: Database, people: People) -> None:
    from govwren.db.models import Event, UseCase
    from govwren.integration import webhooks
    from tests.test_review import SIMPLE, request

    request(db, people, SIMPLE)
    with db.write(ME.actor) as session:
        use_case = session.scalars(select(UseCase)).one()
        use_case.restricted = True
        session.flush()
        event = session.scalars(
            select(Event).where(Event.subject_type == "use_case", Event.action == "updated")
            .order_by(Event.id)
        ).all()  # fmt: skip
        told = [webhooks._message(session, row) for row in event]
        sent = [message for message in told if message is not None]
    assert sent and all(payload["name"] is None for _topic, payload in sent)
