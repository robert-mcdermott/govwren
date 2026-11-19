"""Single sign-on, against a provider that speaks real OpenID Connect inside the test run.
Nothing here reaches a real identity provider."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from govwren.access.principal import Grant
from govwren.api.app import create_app
from govwren.auth import tokens
from govwren.config import ConfigError, load_config
from govwren.db import migrate
from govwren.db.engine import Database
from govwren.db.models import Account, Identity, SessionToken, SignInRequest
from govwren.home import DataHome
from govwren.people import accounts
from tests.people import ME, PASSWORD, People, seed

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "dev_identity_provider.py"
spec = importlib.util.spec_from_file_location("dev_identity_provider", SCRIPT)
assert spec and spec.loader
idp = importlib.util.module_from_spec(spec)
sys.modules["dev_identity_provider"] = idp
spec.loader.exec_module(idp)

ISSUER = "https://id.alderpoint.example/tenant-1"
NEW = idp.Person("s-noor", "Noor Valdivia", "noor.valdivia@alderpoint.example", ["hale-lab"])
MEMBER = idp.Person("s-member", "Member Person", "member@alderpoint.example", ["hale-lab"])
ADMIN = idp.Person("s-admin", "Admin Person", "admin@alderpoint.example", ["gw-admins"])


@dataclass
class World:
    app: Any
    db: Database
    provider: Any
    people: People

    def client(self) -> TestClient:
        return TestClient(self.app, base_url="http://localhost")

    def round_trip(self, client: TestClient, subject: str, next_path: str = "/") -> httpx.Response:
        """Everything a browser does between pressing the button and landing back in GovWren."""
        sent = client.get("/api/v1/sso/start", params={"next": next_path}, follow_redirects=False)
        assert sent.status_code == 303, sent.text
        there = sent.headers["location"]
        assert there.startswith(f"{ISSUER}/authorize?")
        back = self.provider.handle("GET", f"{there}&as={subject}")
        assert back.status == 302, back.body
        home = urlsplit(back.headers["location"])
        assert f"{home.scheme}://{home.netloc}{home.path}" == "http://localhost/api/v1/sso/callback"
        return client.get(f"{home.path}?{home.query}", follow_redirects=False)

    def who(self, client: TestClient) -> dict[str, Any]:
        return client.get("/api/v1/session").json().get("data", {})


@pytest.fixture
def world(
    config_file: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[World]:
    settings = {"ISSUER": ISSUER, "CLIENT_ID": idp.CLIENT_ID, **getattr(request, "param", {})}
    for key, value in settings.items():
        monkeypatch.setenv(f"GOVWREN_SSO_{key}", value)
    monkeypatch.setenv("GOVWREN_SSO_CLIENT_SECRET", idp.CLIENT_SECRET)
    config = load_config(config_file)
    DataHome(config.data.home).create()
    db = Database(config.database_url)
    migrate.upgrade(db.engine)
    provider = idp.Provider(
        ISSUER, n=idp.DEV_N, d=idp.DEV_D, client_id=idp.CLIENT_ID,
        client_secret=idp.CLIENT_SECRET, people=[NEW, MEMBER, ADMIN],
    )  # fmt: skip

    def over_http(sent: httpx.Request) -> httpx.Response:
        answer = provider.handle(sent.method, str(sent.url), sent.content, dict(sent.headers))
        return httpx.Response(answer.status, headers=answer.headers, content=answer.body)

    app = create_app(config)
    app.state.sso_transport = httpx.MockTransport(over_http)
    try:
        with TestClient(app, base_url="http://localhost"):  # starts the app
            yield World(app, db, provider, seed(db))
    finally:
        db.dispose()


def admin_client(world: World) -> TestClient:
    client = world.client()
    done = client.post(
        "/api/v1/session", json={"email": "admin@alderpoint.example", "password": PASSWORD}
    )
    client.headers["X-CSRF-Token"] = done.json()["data"]["csrf_token"]
    return client


def test_a_new_person_signs_in_and_gets_an_account(world: World) -> None:
    assert world.client().get("/api/v1/meta").json()["data"]["sso"] == {
        "label": "Sign in with your organization account", "local_sign_in": True,
    }  # fmt: skip
    client = world.client()
    landed = world.round_trip(client, NEW.subject, "/catalog")
    assert landed.status_code == 200 and 'content="0;url=/catalog"' in landed.text
    assert "samesite=strict" in landed.headers["set-cookie"].lower()
    me = world.who(client)
    assert me["account"]["email"] == NEW.email and me["account"]["name"] == NEW.name
    assert me["has_password"] is False

    again = world.client()
    world.round_trip(again, NEW.subject)
    assert world.who(again)["account"]["id"] == me["account"]["id"]
    with world.db.read() as session:
        assert session.execute(select(func.count()).select_from(Identity)).scalar_one() == 1
        assert session.execute(select(func.count()).select_from(SignInRequest)).scalar_one() == 0


def test_an_existing_account_is_joined_by_a_verified_address(world: World) -> None:
    client = world.client()
    world.round_trip(client, MEMBER.subject)
    assert world.who(client)["account"]["id"] == world.people.accounts["member"]
    with world.db.read() as session:  # and from then on by the provider's own name for them
        identity = session.scalars(select(Identity)).one()
        assert (identity.issuer, identity.subject) == (ISSUER, MEMBER.subject)


def test_an_unverified_address_matches_nobody(world: World) -> None:
    world.provider.email_verified = False
    for person in (MEMBER, NEW):
        client = world.client()
        landed = world.round_trip(client, person.subject)
        assert landed.status_code == 303 and landed.headers["location"] == "/sign-in?sso=refused"
        assert world.who(client) == {}
    with world.db.read() as session:
        assert session.scalars(select(Account).where(Account.email == NEW.email)).first() is None


@pytest.mark.parametrize("world", [{"TRUST_EMAIL": "true"}], indirect=True)
def test_a_trusted_provider_may_match_without_the_verified_mark(world: World) -> None:
    world.provider.email_verified = False
    client = world.client()
    world.round_trip(client, MEMBER.subject)
    assert world.who(client)["account"]["id"] == world.people.accounts["member"]


@pytest.mark.parametrize(
    "wrong", ["expired", "audience", "issuer", "nonce", "signature", "unsigned"]
)
def test_a_token_that_does_not_check_out_is_refused(world: World, wrong: str) -> None:
    world.provider.tamper = wrong
    client = world.client()
    landed = world.round_trip(client, NEW.subject)
    assert landed.status_code == 303 and landed.headers["location"] == "/sign-in?sso=refused"
    assert "set-cookie" not in landed.headers and world.who(client) == {}
    with world.db.read() as session:
        assert session.execute(select(func.count()).select_from(SessionToken)).scalar_one() == 0
        assert session.execute(select(func.count()).select_from(Identity)).scalar_one() == 0


def test_an_answer_works_once_and_only_for_a_sign_in_that_was_started(world: World) -> None:
    client = world.client()
    made_up = client.get("/api/v1/sso/callback?code=x&state=never-issued", follow_redirects=False)
    assert made_up.headers["location"] == "/sign-in?sso=expired"

    sent = client.get("/api/v1/sso/start", follow_redirects=False)
    back = world.provider.handle("GET", f"{sent.headers['location']}&as={NEW.subject}")
    home = urlsplit(back.headers["location"])
    first = client.get(f"{home.path}?{home.query}", follow_redirects=False)
    assert first.status_code == 200
    replay = world.client().get(f"{home.path}?{home.query}", follow_redirects=False)
    assert replay.headers["location"] == "/sign-in?sso=expired"

    cancelled = client.get(
        "/api/v1/sso/callback?error=access_denied&state=x", follow_redirects=False
    )
    assert cancelled.headers["location"] == "/sign-in?sso=cancelled"


def test_the_request_to_the_provider_is_well_formed(world: World) -> None:
    sent = world.client().get(
        "/api/v1/sso/start", params={"next": "//evil.example"}, follow_redirects=False
    )
    query = {k: v[0] for k, v in parse_qs(urlsplit(sent.headers["location"]).query).items()}
    assert query["response_type"] == "code" and query["client_id"] == idp.CLIENT_ID
    assert query["redirect_uri"] == "http://localhost/api/v1/sso/callback"
    assert query["code_challenge_method"] == "S256" and len(query["code_challenge"]) == 43
    assert "openid" in query["scope"].split() and len(query["state"]) >= 32 and query["nonce"]
    with world.db.read() as session:
        kept = session.scalars(select(SignInRequest)).one()
        assert kept.next_path == "/"  # somewhere outside GovWren is never remembered
        assert query["state"] not in (kept.state_hash, kept.nonce)  # only its hash is stored


def test_groups_give_roles_and_losing_a_group_takes_them_away(world: World) -> None:
    admin = admin_client(world)
    hale, neuro = world.people.units["HALE"], world.people.units["NEURO"]
    saved = admin.put("/api/v1/sso/mappings", json={"mappings": [
        {"claim_value": "ai-governance", "role": "governance"},
        {"claim_value": "privacy-office", "role": "reviewer", "review_function": "privacy"},
        {"claim_value": "neuro-leads", "role": "steward", "org_unit_id": neuro},
        {"claim_value": "hale-lab", "role": "member", "org_unit_id": hale},
    ]})  # fmt: skip
    assert saved.status_code == 200 and len(saved.json()["data"]) == 4
    shown = admin.get("/api/v1/sso").json()["data"]
    assert shown["enabled"] and shown["redirect_uri"].endswith("/api/v1/sso/callback")
    assert [m["claim_value"] for m in shown["mappings"]] == [
        "ai-governance", "hale-lab", "neuro-leads", "privacy-office",
    ]  # fmt: skip

    NEW.groups[:] = ["hale-lab", "ai-governance", "privacy-office", "neuro-leads", "unmapped"]
    client = world.client()
    world.round_trip(client, NEW.subject)
    me = world.who(client)
    assert set(me["roles"]) == {"governance", "reviewer", "steward", "member"}
    assert hale in me["member_units"] and neuro in me["steward_units"]

    with world.db.write(ME.actor) as session:  # a role given by hand, here
        account = accounts.by_email(session, NEW.email)
        assert account is not None
        accounts.set_grants(session, ME, account, [Grant("auditor")])
    NEW.groups[:] = ["hale-lab"]
    later = world.client()
    world.round_trip(later, NEW.subject)
    assert set(world.who(later)["roles"]) == {"auditor", "member"}  # the hand-given role stays
    NEW.groups[:] = ["hale-lab"]


def test_mappings_are_checked_and_only_an_administrator_sets_them(world: World) -> None:
    admin = admin_client(world)
    bad = admin.put("/api/v1/sso/mappings", json={"mappings": [
        {"claim_value": "", "role": "governance"},
        {"claim_value": "x", "role": "emperor"},
        {"claim_value": "x", "role": "steward"},
        {"claim_value": "x", "role": "reviewer", "review_function": "astrology"},
    ]})  # fmt: skip
    assert bad.status_code == 422 and len(bad.json()["errors"]) == 4
    member = world.client()
    member.post(
        "/api/v1/session", json={"email": "member@alderpoint.example", "password": PASSWORD}
    )
    assert member.get("/api/v1/sso").status_code == 403


def test_a_token_without_the_groups_claim_changes_no_roles(world: World) -> None:
    admin = admin_client(world)
    admin.put("/api/v1/sso/mappings", json={"mappings": [
        {"claim_value": "hale-lab", "role": "governance"}]})  # fmt: skip
    client = world.client()
    world.round_trip(client, NEW.subject)
    assert "governance" in world.who(client)["roles"]
    world.provider.send_groups = False
    again = world.client()
    world.round_trip(again, NEW.subject)
    assert "governance" in world.who(again)["roles"]


def test_a_mapping_never_removes_the_last_administrator(world: World) -> None:
    admin = admin_client(world)
    admin.put("/api/v1/sso/mappings", json={"mappings": [
        {"claim_value": "gw-admins", "role": "admin"}]})  # fmt: skip
    client = world.client()
    world.round_trip(client, ADMIN.subject)  # the administrator now also holds it by mapping
    with world.db.write(ME.actor) as session:  # and no longer by hand
        account = accounts.get(session, world.people.accounts["admin"])
        accounts.set_grants(session, ME, account, [])
        assert accounts.active_admins(session) == 1
    ADMIN.groups[:] = []
    try:
        again = world.client()
        world.round_trip(again, ADMIN.subject)
        assert "admin" in world.who(again)["roles"]
    finally:
        ADMIN.groups[:] = ["gw-admins"]


def test_a_disabled_account_cannot_come_in_through_the_provider(world: World) -> None:
    with world.db.write(ME.actor) as session:
        account = accounts.get(session, world.people.accounts["member"])
        accounts.set_status(session, ME, account, "disabled")
    client = world.client()
    landed = world.round_trip(client, MEMBER.subject)
    assert landed.headers["location"] == "/sign-in?sso=refused" and world.who(client) == {}


@pytest.mark.parametrize("world", [{"LOCAL_SIGN_IN": "false"}], indirect=True)
def test_passwords_can_be_kept_for_administrators_only(world: World) -> None:
    client = world.client()
    refused = client.post(
        "/api/v1/session", json={"email": "member@alderpoint.example", "password": PASSWORD}
    )
    assert refused.status_code == 403 and "organization account" in refused.json()["detail"]
    allowed = client.post(
        "/api/v1/session", json={"email": "admin@alderpoint.example", "password": PASSWORD}
    )
    assert allowed.status_code == 200
    assert world.client().get("/api/v1/meta").json()["data"]["sso"]["local_sign_in"] is False


def test_new_keys_at_the_provider_are_picked_up(world: World) -> None:
    from govwren.api.routers import sso as routes

    class Asked:
        app = world.app

    provider_client = routes.client(Asked)  # type: ignore[arg-type]
    assert provider_client is not None
    stale = tokens.Key("dev-key-1", idp.DEV_N + 2, 65537)
    provider_client._keys = (float("inf"), [stale])  # remembered, and wrong
    client = world.client()
    assert world.round_trip(client, NEW.subject).status_code == 200


def test_without_single_sign_on_there_is_nothing_to_start(client: TestClient) -> None:
    assert client.get("/api/v1/meta").json()["data"]["sso"] is None
    assert client.get("/api/v1/sso/start", follow_redirects=False).status_code == 404
    assert client.get("/api/v1/sso/callback?code=a&state=b").status_code == 404


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ('issuer = "https://id.example/t"', "issuer and client_id go together"),
        ('issuer = "http://id.example/t"\nclient_id = "x"', "must be an https address"),
        ('issuer = "https://id.example/t"\nclient_id = "x"\nscopes = "profile"', "openid"),
        ('issuer = "https://id.example/t"\nclient_id = "x"\nclient_secret = "s3cret"', "never"),
    ],
)
def test_settings_are_checked(tmp_path: Path, section: str, message: str) -> None:
    path = tmp_path / "govwren.toml"
    path.write_text(f"[sso]\n{section}\n", encoding="utf-8")
    with pytest.raises(ConfigError) as caught:
        load_config(path, env={})
    assert message in " ".join(caught.value.problems)


def test_the_token_reader_refuses_what_it_does_not_understand() -> None:
    keys = [tokens.Key("k", idp.DEV_N, 65537)]
    for junk in ("", "a.b", "a.b.c.d", "!!!.###.$$$"):
        with pytest.raises(tokens.TokenError):
            tokens.verify(junk, keys, issuer=ISSUER, audience="x", now=0)
    weak = {"keys": [{"kty": "RSA", "n": "AQAB", "e": "AQAB"}, {"kty": "EC"}, {"kty": "RSA"}]}
    assert tokens.keys_from_jwks(weak) == []  # too short, the wrong kind, and incomplete


def test_an_answer_is_taken_only_in_the_browser_that_asked(world: World) -> None:
    """Someone who starts a sign-in and hands the finished address to another person does
    not sign that person in as themselves."""
    attacker = world.client()
    sent = attacker.get("/api/v1/sso/start", follow_redirects=False)
    assert "govwren_sso" in sent.headers["set-cookie"].lower()
    assert "httponly" in sent.headers["set-cookie"].lower()
    back = world.provider.handle("GET", f"{sent.headers['location']}&as={NEW.subject}")
    home = urlsplit(back.headers["location"])
    victim = world.client()
    handed = victim.get(f"{home.path}?{home.query}", follow_redirects=False)
    assert handed.headers["location"] == "/sign-in?sso=expired"
    assert victim.get("/api/v1/session").status_code == 401
    own = attacker.get(f"{home.path}?{home.query}", follow_redirects=False)
    assert own.status_code == 200  # in the browser that began it, it still works


@pytest.mark.parametrize(
    "path",
    [
        "//evil.example",
        "/\\evil.example",
        "/\t/evil.example",
        "/\n/evil.example",
        "https://evil.example",
        "",
    ],
)
def test_where_to_go_next_is_always_inside_govwren(path: str) -> None:
    from govwren.api.routers.sso import _safe

    assert _safe(path) == "/"
    assert _safe("/use-cases/UC-0001?tab=history") == "/use-cases/UC-0001?tab=history"
