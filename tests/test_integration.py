"""What other systems use: tokens, the checkpoint, and webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren.core.clock import frozen_at, today
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import ApiToken, Event, WebhookDelivery
from govwren.integration import checkpoint, tokens, webhooks
from tests.conftest import Instance
from tests.people import People
from tests.test_changes import linked
from tests.test_review import HIGH, MONDAY, request, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
MONTH = timedelta(days=30)


def _bearer(app_client: TestClient, token: str) -> dict[str, str]:
    app_client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def test_the_checkpoint_says_what_stands(db: Database, people: People) -> None:
    use, system, model = linked(db, people)
    waiting = request(db, people, HIGH)
    with frozen_at(MONDAY + timedelta(days=1)), db.read() as session:
        from tests.test_changes import use_case_of

        asker = who(db, people, "governance")
        approved = checkpoint.check(session, asker, use)
        assert approved["approved"] is True and approved["type"] == "use_case"
        assert approved["status"] == "approved_with_conditions" and approved["tier"] == 1
        assert approved["data_class"] == "internal" and "allowed" not in approved
        assert checkpoint.check(session, asker, use, "public")["allowed"] is True
        assert checkpoint.check(session, asker, use, "restricted")["allowed"] is False
        pending = checkpoint.check(session, asker, use_case_of(session, waiting).ref, "public")
        assert pending["approved"] is False and pending["allowed"] is False
        tool = checkpoint.check(session, asker, system.lower(), "protected")
        assert tool["approved"] and tool["allowed"] and tool["data_class_label"] == "Protected"
        assert checkpoint.check(session, asker, system, "restricted")["allowed"] is False
        assert checkpoint.check(session, asker, model)["approved"] is False  # not in the catalog
        with pytest.raises(NotFound):
            checkpoint.check(session, asker, "UC-9999")
        with pytest.raises(Invalid):
            checkpoint.check(session, asker, use, "secret")
    with frozen_at(MONDAY + timedelta(days=366 * 4)), db.read() as session:
        asker = who(db, people, "governance")
        assert checkpoint.check(session, asker, use)["approved"] is False  # the approval has ended


def test_the_checkpoint_does_not_name_what_the_asker_may_not_see(
    as_role: Clients, db: Database, people: People
) -> None:
    governance, outsider = as_role("governance"), as_role("reviewer")
    made = governance.post(
        "/api/v1/datasets",
        json={"name": "Whistleblower interviews", "data_class": "restricted", "restricted": True},
    )
    hidden = made.json()["data"]["ref"]
    assert outsider.get(f"/api/v1/datasets/{hidden}").status_code == 404
    asked = outsider.get(f"/api/v1/checkpoint/{hidden}").json()["data"]
    assert asked["name"] is None and asked["data_class"] == "restricted"  # standing, not its title
    assert governance.get(f"/api/v1/checkpoint/{hidden}").json()["data"]["name"] == (
        "Whistleblower interviews"
    )
    from govwren.intake import service as intake
    from tests.test_intake import SIMPLE

    member = who(db, people, "member")
    with db.write(member.actor) as session:
        ref = intake.start(session, member, {**SIMPLE, "unit": people.units["HALE"]}).ref
    assert as_role("reviewer").get(f"/api/v1/checkpoint/{ref}").status_code == 404
    assert as_role("member").get(f"/api/v1/checkpoint/{ref}").json()["data"]["approved"] is False


def test_a_token_cannot_set_a_password(as_role: Clients) -> None:
    member = as_role("member")
    made = member.post("/api/v1/tokens", json={"name": "Writer", "scope": "write"})
    script = as_role(None)
    refused = script.post(
        "/api/v1/session/password",
        headers=_bearer(script, made.json()["data"]["token"]),
        json={"current_password": "", "new_password": "a brand new password 99"},
    )
    assert refused.status_code == 403


def test_a_webhook_goes_only_to_the_public_internet_and_follows_no_redirect() -> None:
    for inside in (
        "http://10.0.0.5/hook",
        "https://169.254.169.254/latest",
        "https://192.168.1.1/",
    ):
        with pytest.raises(ValueError, match="public internet"):
            webhooks._post(inside, b"{}", {})
    assert (
        webhooks._public("127.0.0.1") is False and webhooks._public("no.such.host.invalid") is False
    )
    assert (
        webhooks._NoRedirect().redirect_request(None, None, 302, "Found", {}, "http://x/") is None
    )


def test_a_token_is_its_account_cut_down_to_its_scope(
    as_role: Clients, db: Database, people: People
) -> None:
    use, _system, _model = linked(db, people)
    member = as_role("member")
    made = {
        scope: member.post("/api/v1/tokens", json={"name": f"A {scope} script", "scope": scope})
        for scope in ("checkpoint", "read", "write")
    }
    assert all(answer.status_code == 201 for answer in made.values())
    secret = {scope: answer.json()["data"]["token"] for scope, answer in made.items()}
    assert all(value.startswith("gw_") and len(value) > 40 for value in secret.values())
    listed = member.get("/api/v1/tokens").json()["data"]
    assert [t["scope"] for t in listed["tokens"]] == ["write", "read", "checkpoint"]
    assert (
        "token" not in listed["tokens"][0] and listed["tokens"][0]["prefix"] == secret["write"][:10]
    )
    with db.read() as session:
        stored = session.scalars(select(ApiToken.token_hash)).all()
        assert tokens.digest(secret["read"]) in stored and secret["read"] not in stored
        created = session.scalars(select(Event).where(Event.subject_type == "api_token")).first()
        assert created is not None and created.changes["token_hash"] != [
            None, tokens.digest(secret["checkpoint"]),
        ]  # fmt: skip

    script = as_role(None)
    ask = _bearer(script, secret["checkpoint"])
    assert script.get(f"/api/v1/checkpoint/{use}", headers=ask).json()["data"]["approved"] is True
    assert script.get(f"/api/v1/use-cases/{use}", headers=ask).status_code == 403
    read = _bearer(script, secret["read"])
    assert script.get(f"/api/v1/use-cases/{use}", headers=read).status_code == 200
    assert script.get("/api/v1/portfolio", headers=read).status_code == 403  # as the member is
    assert script.post("/api/v1/evidence", json={}, headers=read).status_code == 403
    write = _bearer(script, secret["write"])
    noted = script.post(
        "/api/v1/evidence", headers=write,
        json={"title": "Sent by a script", "kind": "document", "supports": [use],
              "description": "Section 4 of the lab manual."},
    )  # fmt: skip
    assert noted.status_code == 201  # no CSRF token is asked of a script
    assert script.get("/api/v1/tokens", headers=write).status_code == 403
    assert script.post("/api/v1/tokens", json={}, headers=write).status_code == 403
    assert (
        script.get("/api/v1/session", headers={"Authorization": "Bearer gw_nope"}).status_code
        == 401
    )

    token_id = made["read"].json()["data"]["id"]
    member = as_role("member")
    assert member.delete(f"/api/v1/tokens/{token_id}").status_code == 200
    script.cookies.clear()
    assert script.get(f"/api/v1/use-cases/{use}", headers=read).status_code == 401
    everyone = as_role("admin").get("/api/v1/admin/tokens").json()["data"]["tokens"]
    assert {t["owner"] for t in everyone} == {"Member Person"} or len(everyone) == 3


def test_tokens_expire_and_follow_their_account(db: Database, people: People) -> None:
    member = who(db, people, "member")
    with frozen_at(MONDAY), db.write(member.actor) as session:
        for bad, field in (
            ({"name": "", "scope": "read"}, "name"),
            ({"name": "x", "scope": "everything"}, "scope"),
            ({"name": "x", "scope": "read", "expires_on": str(MONDAY.date())}, "expires_on"),
            ({"name": "x", "scope": "read", "expires_on": "soon"}, "expires_on"),
        ):
            with pytest.raises(Invalid) as refused:
                tokens.create(session, member, bad)
            assert field in refused.value.errors
        _row, secret = tokens.create(
            session, member,
            {"name": "Nightly", "scope": "read", "expires_on": str(MONDAY.date() + MONTH)},
        )  # fmt: skip
        assert tokens.authenticate(session, secret) is not None
        assert tokens.authenticate(session, secret + "x") is None
        with pytest.raises(NotFound):  # someone else's token is not theirs to revoke
            tokens.revoke(session, who(db, people, "auditor"), _row.id)
        with pytest.raises(PermissionDenied):
            tokens.everyones(session, member)
    with frozen_at(MONDAY + timedelta(days=31)), db.bookkeeping() as session:
        assert tokens.authenticate(session, secret) is None
    assert today() > MONDAY.date()


class Receiver:
    """Stands in for the other system: remembers what it was sent, and answers as told."""

    def __init__(self) -> None:
        self.got: list[tuple[str, bytes, dict[str, str]]] = []
        self.answer = 204

    def __call__(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        self.got.append((url, body, headers))
        if self.answer == 0:
            raise OSError("no route")
        return self.answer


def test_webhooks_are_told_signed_and_tried_again(
    instance: Instance, db: Database, people: People
) -> None:
    admin = who(db, people, "admin")
    receiver = Receiver()
    with frozen_at(MONDAY - timedelta(hours=1)), db.write(admin.actor) as session:
        for bad, field in (
            ({"name": "x", "url": "ftp://example.org", "topics": ["decision.made"]}, "url"),
            ({"name": "x", "url": "http://example.org/hook", "topics": ["decision.made"]}, "url"),
            ({"name": "x", "url": "https://u:p@example.org/", "topics": ["decision.made"]}, "url"),
            ({"name": "x", "url": "https://example.org/hook", "topics": []}, "topics"),
            ({"name": "x", "url": "https://example.org/hook", "topics": ["weather"]}, "topics"),
            ({"name": "", "url": "https://example.org/hook", "topics": ["decision.made"]}, "name"),
        ):
            with pytest.raises(Invalid) as refused:
                webhooks.create(session, admin, bad)
            assert field in refused.value.errors
        with pytest.raises(PermissionDenied):
            webhooks.create(session, who(db, people, "governance"), {})
        hook, secret = webhooks.create(
            session, admin,
            {"name": "Purchasing", "url": "https://buy.example.org/hooks/govwren",
             "topics": ["use_case.status_changed", "decision.made"]},
        )  # fmt: skip
        hook_id = hook.id
        assert secret.startswith("whsec_")
        made = session.scalars(select(Event).where(Event.subject_type == "webhook")).one()
        assert secret not in json.dumps(made.changes)

    use, _system, _model = linked(db, people)  # approved by rule on Monday
    with frozen_at(MONDAY + timedelta(minutes=5)):
        ran = webhooks.run_once(db, None, receiver)
        assert ran["queued"] >= 2 and ran["sent"] == ran["queued"] and ran["failed"] == 0
        assert webhooks.run_once(db, None, receiver) == {"queued": 0, "sent": 0, "failed": 0}
    bodies = [json.loads(body) for _url, body, _headers in receiver.got]
    assert {body["topic"] for body in bodies} == {"use_case.status_changed", "decision.made"}
    decided = next(body for body in bodies if body["topic"] == "decision.made")
    assert decided["data"]["ref"] == use and decided["data"]["by_rule"] is True
    assert "purpose" not in json.dumps(bodies)  # what changed, never what the record holds
    url, body, headers = receiver.got[0]
    assert url == "https://buy.example.org/hooks/govwren"
    expected = hmac.new(
        secret.encode(), headers["X-GovWren-Timestamp"].encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    assert headers["X-GovWren-Signature"] == f"sha256={expected}"
    assert headers["X-GovWren-Topic"] == json.loads(body)["topic"]

    receiver.answer = 500
    receiver.got.clear()
    with frozen_at(MONDAY + timedelta(hours=1)):
        request(db, people, HIGH)
        assert webhooks.run_once(db, None, receiver)["failed"] >= 1
        assert webhooks.run_once(db, None, receiver)["failed"] == 0  # not yet due again
    receiver.answer = 204
    with frozen_at(MONDAY + timedelta(hours=1, minutes=3)):
        again = webhooks.run_once(db, None, receiver)
        assert again["sent"] >= 1 and again["failed"] == 0
    with db.read() as session:
        shown = webhooks.view(session, webhooks.find(session, hook_id))
        assert shown["last_status"] == "Delivered" and shown["failures"] == 0
        assert {d["status"] for d in shown["deliveries"]} == {"sent"} and "secret" not in shown
        assert (
            session.scalars(
                select(WebhookDelivery.attempts).order_by(WebhookDelivery.attempts.desc())
            ).first()
            == 2
        )

    receiver.answer = 0
    assert webhooks.send_test(db, admin, hook_id, receiver).startswith("It could not be reached")
    receiver.answer = 204
    assert webhooks.send_test(db, admin, hook_id, receiver) == "Delivered"
    assert json.loads(receiver.got[-1][1])["topic"] == "test"
    with db.write(admin.actor) as session:
        webhooks.change(session, admin, webhooks.find(session, hook_id), {"active": False})
    with frozen_at(MONDAY + timedelta(hours=3)):
        linked(db, people)
        assert webhooks.run_once(db, None, receiver)["queued"] == 0  # switched off: nothing queued
    with db.write(admin.actor) as session:
        webhooks.remove(session, admin, webhooks.find(session, hook_id))
        assert webhooks.listing(session, admin)["webhooks"] == []


def test_webhooks_over_the_api(as_role: Clients, instance: Instance) -> None:
    admin = as_role("admin")
    receiver = Receiver()
    admin.app.state.webhook_send = receiver  # type: ignore[attr-defined]
    body = {
        "name": "Tickets",
        "url": "https://tickets.example.org/in",
        "topics": ["incident.reported"],
    }
    made = admin.post("/api/v1/admin/webhooks", json=body)
    assert made.status_code == 201 and made.json()["data"]["secret"].startswith("whsec_")
    hook = made.json()["data"]["id"]
    listed = admin.get("/api/v1/admin/webhooks").json()["data"]
    assert listed["webhooks"][0]["name"] == "Tickets" and "secret" not in listed["webhooks"][0]
    assert len(listed["topics"]) == 4
    assert admin.post(f"/api/v1/admin/webhooks/{hook}/test").json()["data"]["result"] == "Delivered"
    off = admin.patch(f"/api/v1/admin/webhooks/{hook}", json={"active": False})
    assert off.status_code == 200 and off.json()["data"]["active"] is False
    assert as_role("governance").get("/api/v1/admin/webhooks").status_code == 403
    assert admin.delete(f"/api/v1/admin/webhooks/{hook}").json()["data"]["webhooks"] == []
    assert admin.delete(f"/api/v1/admin/webhooks/{hook}").status_code == 404
