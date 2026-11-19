from __future__ import annotations

import pytest
from sqlalchemy import select

from govwren.access.principal import Grant
from govwren.auth import passwords, sessions
from govwren.core.errors import Conflict, Invalid, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Event, SessionToken
from govwren.people import accounts
from tests.people import ME, PASSWORD, People, email_of


def test_passwords_hash_and_verify() -> None:
    stored = passwords.hash_password(PASSWORD)
    assert stored.startswith("scrypt$") and PASSWORD not in stored
    assert passwords.verify_password(PASSWORD, stored)
    assert not passwords.verify_password(PASSWORD + "x", stored)
    assert not passwords.verify_password(PASSWORD, "not a hash")
    assert passwords.hash_password(PASSWORD) != stored  # salted


@pytest.mark.parametrize(
    ("password", "email"),
    [
        ("short", ""),
        ("aaaaaaaaaaaaaaaa", ""),
        ("x" * 2000, ""),
        ("my name is okafor ok", "okafor@x.example"),
    ],
)
def test_weak_passwords_are_refused(password: str, email: str) -> None:
    with pytest.raises(Invalid) as caught:
        passwords.check_rules(password, email=email)
    assert "password" in caught.value.errors


def test_an_account_with_a_password_is_active_and_without_one_is_invited(db: Database) -> None:
    with db.write(ME.actor) as session:
        active = accounts.create(
            session, ME, email=" Ana@Alderpoint.Example ", display_name="Ana", password=PASSWORD
        )
        invited = accounts.create(session, ME, email="bo@alderpoint.example", display_name="Bo")
        assert (active.email, active.status) == ("ana@alderpoint.example", "active")
        assert invited.status == "invited"
        with pytest.raises(Conflict, match="already an account"):
            accounts.create(session, ME, email="ANA@alderpoint.example", display_name="Again")
        with pytest.raises(Invalid) as caught:
            accounts.create(session, ME, email="not-an-address", display_name=" ")
        assert set(caught.value.errors) == {"email", "display_name"}
    with db.write(ME.actor) as session:
        bo = accounts.by_email(session, "bo@alderpoint.example")
        assert bo is not None
        assert accounts.authenticate(session, bo.email, PASSWORD) is None
        accounts.set_password(session, ME, bo, PASSWORD)
        assert bo.status == "active"
        assert accounts.authenticate(session, bo.email, PASSWORD) is bo


def test_signing_in_needs_the_right_password_for_an_active_account(
    db: Database, people: People
) -> None:
    with db.write(ME.actor) as session:
        assert accounts.authenticate(session, "MEMBER@alderpoint.example ", PASSWORD) is not None
        assert accounts.authenticate(session, email_of("member"), "wrong password!") is None
        assert accounts.authenticate(session, "nobody@alderpoint.example", PASSWORD) is None
        member = accounts.get(session, people.accounts["member"])
        accounts.set_status(session, ME, member, "disabled")
        assert accounts.authenticate(session, email_of("member"), PASSWORD) is None


def test_who_someone_is(db: Database, people: People) -> None:
    with db.read() as session:
        steward = accounts.principal_for(session, accounts.get(session, people.accounts["steward"]))
        member = accounts.principal_for(session, accounts.get(session, people.accounts["member"]))
        reviewer = accounts.principal_for(
            session, accounts.get(session, people.accounts["reviewer"])
        )
        governance = accounts.principal_for(
            session, accounts.get(session, people.accounts["governance"])
        )
    assert steward.steward_units == {people.units["NEURO"], people.units["HALE"]}
    assert steward.stewards_unit(people.units["HALE"]) and not steward.stewards_unit(
        people.units["CANCER"]
    )
    assert steward.role_names == ["steward", "member"] and not steward.edits_all
    assert member.member_units == {people.units["HALE"]} and member.role_names == ["member"]
    assert (
        reviewer.review_functions() == {"privacy"} and reviewer.reviews and not reviewer.reads_all
    )
    assert (
        governance.review_functions() is None and governance.reads_all and not governance.is_admin
    )
    assert member.review_functions() == frozenset()
    assert member.permissions() == dict.fromkeys(
        ["admin", "govern", "configure", "read_all", "edit_all", "review", "steward"], False
    )


def test_roles_must_make_sense(db: Database, people: People) -> None:
    with db.write(ME.actor) as session:
        member = accounts.get(session, people.accounts["member"])
        for grant, field in [
            (Grant("steward"), "org_unit_id"),
            (Grant("steward", org_unit_id=9999), "org_unit_id"),
            (Grant("admin", org_unit_id=people.units["HALE"]), "org_unit_id"),
            (Grant("auditor", review_function="privacy"), "review_function"),
            (Grant("member"), "role"),
            (Grant("wizard"), "role"),
        ]:
            with pytest.raises(Invalid) as caught:
                accounts.set_grants(session, ME, member, [grant])
            assert field in caught.value.errors, grant
        accounts.set_grants(
            session, ME, member, [Grant("reviewer", review_function="security"), Grant("reviewer")]
        )
        principal = accounts.principal_for(session, member)
        assert principal.review_functions() is None  # a grant with no function covers them all


def test_setting_roles_replaces_only_roles_from_the_same_source(
    db: Database, people: People
) -> None:
    with db.write(ME.actor) as session:
        member = accounts.get(session, people.accounts["member"])
        accounts.set_grants(session, ME, member, [Grant("auditor")], source="provider")
        accounts.set_grants(session, ME, member, [Grant("governance")])
        accounts.set_grants(session, ME, member, [])
        assert [(g.role, g.source) for g in accounts.grants_of(session, member.id)] == [
            ("auditor", "provider")
        ]


def test_the_last_administrator_is_protected(db: Database, people: People) -> None:
    with db.write(ME.actor) as session:
        admin = accounts.get(session, people.accounts["admin"])
        with pytest.raises(Conflict, match="last active administrator"):
            accounts.set_grants(session, ME, admin, [])
        with pytest.raises(Conflict, match="last active administrator"):
            accounts.set_status(session, ME, admin, "disabled")
        second = accounts.get(session, people.accounts["governance"])
        accounts.set_grants(session, ME, second, [Grant("governance"), Grant("admin")])
        accounts.set_grants(session, ME, admin, [])
        with pytest.raises(Conflict, match="last active administrator"):
            accounts.set_status(session, ME, second, "disabled")


def test_people_change_their_own_password_with_the_current_one(
    db: Database, people: People
) -> None:
    with db.write(ME.actor) as session:
        member = accounts.get(session, people.accounts["member"])
        me = accounts.principal_for(session, member)
        with pytest.raises(Invalid) as caught:
            accounts.set_password(
                session, me, member, "another long passphrase", current_password="wrong"
            )
        assert "current_password" in caught.value.errors
        accounts.set_password(
            session, me, member, "another long passphrase", current_password=PASSWORD
        )
        assert accounts.authenticate(session, member.email, "another long passphrase") is member
        other = accounts.get(session, people.accounts["auditor"])
        with pytest.raises(PermissionDenied):
            accounts.set_password(session, me, other, "another long passphrase")


def test_a_new_password_ends_other_sessions(db: Database, people: People) -> None:
    member_id = people.accounts["member"]
    with db.write(ME.actor) as session:
        _, mine = sessions.create(session, member_id, idle_hours=1, max_days=1, user_agent="here")
        sessions.create(session, member_id, idle_hours=1, max_days=1, user_agent="elsewhere")
        member = accounts.get(session, member_id)
        me = accounts.principal_for(session, member, mine)
        accounts.set_password(
            session, me, member, "another long passphrase", current_password=PASSWORD
        )
    with db.read() as session:
        live = session.scalars(
            select(SessionToken.user_agent).where(SessionToken.revoked_at.is_(None))
        ).all()
    assert live == ["here"]


def test_only_administrators_manage_accounts(db: Database, people: People) -> None:
    with db.write(ME.actor) as session:
        governance = accounts.principal_for(
            session, accounts.get(session, people.accounts["governance"])
        )
        member = accounts.get(session, people.accounts["member"])
        with pytest.raises(PermissionDenied):
            accounts.create(session, governance, email="x@alderpoint.example", display_name="X")
        with pytest.raises(PermissionDenied):
            accounts.set_grants(session, governance, member, [Grant("admin")])
        with pytest.raises(PermissionDenied):
            accounts.update(session, governance, member, {"display_name": "Renamed"})
        myself = accounts.get(session, people.accounts["governance"])
        accounts.update(
            session,
            governance,
            myself,
            {"display_name": "Sam Reyes", "time_zone": "America/Chicago"},
        )
        with pytest.raises(PermissionDenied):
            accounts.update(session, governance, myself, {"status": "disabled"})


def test_everything_about_accounts_is_in_the_history_except_secrets(
    db: Database, people: People
) -> None:
    with db.read() as session:
        events = session.scalars(select(Event).order_by(Event.id)).all()
    by_type = {event.subject_type for event in events}
    assert {"org_unit", "account", "credential", "role_grant", "membership"} <= by_type
    assert "session_token" not in by_type and "failed_sign_in" not in by_type
    grant = next(e for e in events if e.subject_type == "role_grant")
    assert (grant.parent_type, grant.parent_id) == ("account", people.accounts["admin"])
    assert grant.actor_kind == "command" and grant.actor_label == "Tester"
    text = " ".join(str(event.changes) for event in events)
    assert "scrypt$" not in text and PASSWORD not in text
    credential = next(e for e in events if e.subject_type == "credential")
    assert credential.changes["password_hash"] == [None, "[redacted]"]
