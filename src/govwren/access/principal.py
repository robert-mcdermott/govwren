"""The person, or the command, on whose behalf something is being done."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from govwren.access import roles
from govwren.events.actor import Actor


@dataclass(frozen=True)
class Grant:
    role: str
    org_unit_id: int | None = None
    review_function: str | None = None


@dataclass(frozen=True)
class Principal:
    account_id: int | None
    name: str
    email: str = ""
    grants: tuple[Grant, ...] = ()
    # Units a steward grant covers, with every unit beneath them, worked out at sign-in.
    steward_units: frozenset[int] = frozenset()
    # Units the person works in, with every unit beneath them (for what a member may see).
    member_units: frozenset[int] = frozenset()
    csrf_token: str = ""
    has_password: bool = True
    session_id: int | None = None
    command: bool = field(default=False)

    @classmethod
    def for_command(cls, label: str = "Command line") -> Principal:
        """Someone at the server's own command line: trusted with everything."""
        return cls(None, label, grants=(Grant(roles.ADMIN), Grant(roles.GOVERNANCE)), command=True)

    @property
    def actor(self) -> Actor:
        if self.command or self.account_id is None:
            return Actor.command(self.name)
        return Actor.account(self.account_id, self.name)

    def has(self, role: str) -> bool:
        return role == roles.MEMBER or any(grant.role == role for grant in self.grants)

    @property
    def role_names(self) -> list[str]:
        held = {grant.role for grant in self.grants}
        return [role for role in roles.ROLES if role in held or role == roles.MEMBER]

    @property
    def is_admin(self) -> bool:
        return self.has(roles.ADMIN)

    @property
    def governs(self) -> bool:
        """Runs the program: triage, decisions, campaigns."""
        return self.has(roles.GOVERNANCE)

    @property
    def configures(self) -> bool:
        """May edit the program: forms, scoring, rules, vocabularies."""
        return self.governs or self.is_admin

    @property
    def reads_all(self) -> bool:
        return self.governs or self.is_admin or self.has(roles.AUDITOR)

    @property
    def edits_all(self) -> bool:
        return self.governs or self.is_admin

    @property
    def reviews(self) -> bool:
        return self.governs or self.has(roles.REVIEWER)

    @property
    def stewards(self) -> bool:
        return bool(self.steward_units)

    def review_functions(self) -> frozenset[str] | None:
        """The functions this person reviews for; None means every function."""
        if self.governs:
            return None
        granted = [g.review_function for g in self.grants if g.role == roles.REVIEWER]
        if not granted:
            return frozenset()
        if any(function is None for function in granted):
            return None
        return frozenset(f for f in granted if f)

    def stewards_unit(self, org_unit_id: int | None) -> bool:
        return org_unit_id is not None and org_unit_id in self.steward_units

    def permissions(self) -> dict[str, bool]:
        """What the web app needs to decide which parts of itself to show."""
        return {
            "admin": self.is_admin,
            "govern": self.governs,
            "configure": self.configures,
            "read_all": self.reads_all,
            "edit_all": self.edits_all,
            "review": self.reviews,
            "steward": self.stewards,
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "account": {"id": self.account_id, "name": self.name, "email": self.email},
            "roles": self.role_names,
            "permissions": self.permissions(),
            "steward_units": sorted(self.steward_units),
            "has_password": self.has_password,
            "csrf_token": self.csrf_token,
        }
