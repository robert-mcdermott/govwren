"""Build the fictional institute by using GovWren the way its people would.

Nothing here inserts a row. Every unit, account, tool, request, finding, and decision is made
by calling the same services the web app calls, as the person who would have done it, with
the clock set to when they would have done it. So everything in a demo is genuine output of
the product, and its history verifies like any other.

Time runs forward from thirty months ago to the day of the build. Each request is a small
script that says what happens next and when; the scripts are interleaved in time order, and
whatever would happen after today simply has not happened yet. That is why a fresh demo
always has work in progress.
"""

from __future__ import annotations

import heapq
import random
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from govwren.access.principal import Grant, Principal
from govwren.core.clock import clock_set_to
from govwren.core.errors import GovWrenError
from govwren.db.engine import Database
from govwren.demo import content as c
from govwren.intake import service as intake
from govwren.inventory import catalog, records
from govwren.inventory.registry import SYSTEM, USE_CASE, VENDOR, find
from govwren.people import accounts, units
from govwren.program import branding, packs, settings
from govwren.review import service as review

SETTING = "demo"
ORGANIZATION = c.ORGANIZATION
MONTHS = 30
ME = Principal.for_command("Demo build")

# Answers to the questions that only some requests are asked. The form drops the ones that do
# not apply, so every request can carry them all.
FOLLOW_UPS: dict[str, Any] = {
    "deidentified": True,
    "minimum_necessary": True,
    "actions": "It can set a ticket's category and priority, post a reply, and close "
    "tickets of the types on its allow-list.",
    "stop_mechanism": "A switch in the admin console stops it at once. Every action is "
    "logged and can be reversed from the same screen.",
    "acts_as": "A service account limited to its own queue",
    "disclosure": True,
    "verification": "Each author checks the passages they are responsible for, and every "
    "reference is opened and read before submission.",
}

RECOMMENDS = {
    "privacy": "deidentify_first",
    "security": "security_review_findings",
    "legal": "agreement_in_place",
    "ethics": "ethics_amendment",
    "integrity": "disclose_ai_use",
    "clinical_safety": "human_reviews_each",
    "data_stewardship": "stay_within_data",
    "architecture": "stop_mechanism_tested",
}


@dataclass
class Plan:
    """One request: who asks for what, when, and anything about its course that is fixed
    instead of left to chance."""

    start: datetime
    requester: int
    unit: int
    name: str
    purpose: str
    profile: str
    tools: list[str] = field(default_factory=list)
    answers: dict[str, Any] = field(default_factory=dict)
    # What is fixed: "halt" (draft, submitted, triaged, asked, ready), "question" (bool),
    # "asker" (account key), "outcome" (approved, declined, returned, withdrawn),
    # "findings" ({function: finding}), "pending" (functions left unfinished), "pace"
    # (a multiplier on every wait), "by" (who decides), "rationale".
    fixed: dict[str, Any] = field(default_factory=dict)
    then: Callable[[str], None] | None = None  # called with the use case's reference


@dataclass
class Summary:
    seed: int
    built_on: date
    counts: dict[str, int]
    sample_accounts: list[dict[str, str]]


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def email_for(name: str) -> str:
    words = _ascii(name.removeprefix("Dr. ")).lower().replace("'", "").split()
    return f"{words[0]}.{words[-1]}@{c.DOMAIN}"


class Builder:
    def __init__(self, db: Database, *, seed: int, today: date) -> None:
        self.db = db
        self.seed = seed
        self.rng = random.Random(seed)
        self.end = datetime(today.year, today.month, today.day, 16, 30, tzinfo=UTC)
        self.start = self._workday(self.end - timedelta(days=MONTHS * 30.4))
        self.now = self.start
        self.units: dict[str, int] = {}
        self.topics: dict[int, list[str]] = {}
        self.labs: list[int] = []
        self.human_labs: set[int] = set()
        self.cast: dict[str, int] = {}
        self.staff: dict[int, list[int]] = {}  # unit id -> the accounts that work in it
        self.heads: dict[int, int] = {}
        self.reviewers: dict[str, list[int]] = {}
        self.governance: list[int] = []
        self.names: dict[int, str] = {}
        self._principals: dict[int, Principal] = {}
        self.vendors: dict[str, str] = {}
        self.tools: dict[str, str] = {}  # tool name -> reference, once it is approved
        self.known: dict[str, str] = {}  # every evaluated tool, whatever its standing
        self._emails: set[str] = set()
        self.tool_class: dict[str, str] = {}
        self.unlisted = list(c.UNLISTED)
        self._queue: list[tuple[datetime, int, Iterator[datetime]]] = []
        self._count = 0
        self.counts: dict[str, int] = {}
        self._agreements = 200
        self._protocols = 300

    # --- Time ---------------------------------------------------------------------------

    def _workday(self, moment: datetime) -> datetime:
        """The same moment, moved into working hours on a weekday."""
        moment = moment.replace(second=self.rng.randrange(60), microsecond=0)
        if moment.hour < 8:
            moment = moment.replace(hour=8 + self.rng.randrange(3))
        elif moment.hour >= 18:
            moment = (moment + timedelta(days=1)).replace(hour=8 + self.rng.randrange(3))
        while moment.weekday() >= 5:
            moment += timedelta(days=1)
        return moment

    def later(self, low: float, high: float, pace: float = 1.0) -> datetime:
        """A working moment between ``low`` and ``high`` days from now."""
        days = self.rng.uniform(low, high) * pace
        return self._workday(self.now + timedelta(days=days))

    def pace(self, moment: datetime) -> float:
        """The program got faster as it found its feet: waits shrink over the thirty months."""
        done = (moment - self.start) / (self.end - self.start)
        return 1.9 - 1.2 * max(0.0, min(1.0, done))

    def ago(self, days: float, hour: int = 10) -> datetime:
        moment = (self.end - timedelta(days=days)).replace(hour=hour, minute=self.rng.randrange(60))
        while moment.weekday() >= 5:
            moment -= timedelta(days=1)
        return moment

    # --- Acting as someone --------------------------------------------------------------

    def principal(self, account_id: int) -> Principal:
        if account_id not in self._principals:
            with self.db.read() as session:
                self._principals[account_id] = accounts.principal_for(
                    session, accounts.get(session, account_id)
                )
        return self._principals[account_id]

    @contextmanager
    def act(self, account_id: int) -> Iterator[tuple[Session, Principal]]:
        who = self.principal(account_id)
        with self.db.write(who.actor) as session:
            yield session, who

    def tally(self, what: str, by: int = 1) -> None:
        self.counts[what] = self.counts.get(what, 0) + by

    # --- The schedule -------------------------------------------------------------------

    def schedule(self, script: Iterator[datetime]) -> None:
        try:
            first = next(script)
        except StopIteration:
            return
        self._count += 1
        heapq.heappush(self._queue, (first, self._count, script))

    def run(self) -> None:
        with clock_set_to(lambda: self.now):
            while self._queue:
                moment, order, script = heapq.heappop(self._queue)
                if moment > self.end:
                    continue  # it has not happened yet
                self.now = max(self.now, moment)
                try:
                    following = next(script)
                except StopIteration:
                    continue
                heapq.heappush(self._queue, (max(following, self.now), order, script))

    # --- The institute ------------------------------------------------------------------

    def _people_names(self, taken: set[str]) -> Iterator[str]:
        pairs = [(g, f) for g in c.GIVEN for f in c.FAMILY]
        self.rng.shuffle(pairs)
        self._emails |= {email_for(name) for name in taken}
        for given, family in pairs:
            name = f"{given} {family}"
            if email_for(name) not in self._emails:
                self._emails.add(email_for(name))
                yield name

    def found(self) -> None:
        """The day GovWren was installed: the organization, its people, and its program."""
        with clock_set_to(lambda: self.now):
            with self.db.write(ME.actor) as session:
                packs.ensure_defaults(session, ME)
                branding.save(session, ME, {"organization_name": c.ORGANIZATION})
                self._units(session)
            with self.db.write(ME.actor) as session:
                self._people(session)
            self.now += timedelta(minutes=20)

    def _unit(self, session: Session, name: str, kind: str, code: str, parent: str | None) -> int:
        unit = units.create(
            session, ME, name=name, kind=kind, code=code,
            parent_id=self.units[parent] if parent else None,
        )  # fmt: skip
        self.units[code] = unit.id
        self.staff[unit.id] = []
        self.tally("units")
        return unit.id

    def _units(self, session: Session) -> None:
        self._unit(session, c.ORGANIZATION, "organization", "ALD", None)
        surnames = list(c.FAMILY)
        self.rng.shuffle(surnames)
        self._lab_heads: dict[str, str | None] = {}
        for name, code, labs, topics in c.DIVISIONS:
            division = self._unit(session, name, "division", code, "ALD")
            self.topics[division] = topics
            parent = code
            fixed = list(c.FIXED_LABS.get(code, []))
            if code == "CLN":
                self._unit(session, "Clinical Research Unit", "center", "CRU", "CLN")
                self.topics[self.units["CRU"]] = topics
            for index in range(labs):
                if fixed:
                    surname, head = fixed.pop(0)
                else:
                    surname, head = surnames.pop(), None
                if code == "CLN":
                    parent = "CRU" if index < 3 else "CLN"
                lab_code = f"{code}-{_ascii(surname).upper()}"
                lab = self._unit(session, f"{surname} Lab", "lab", lab_code, parent)
                self._lab_heads[lab_code] = head or surname
                self.labs.append(lab)
                self.topics[lab] = self.rng.sample(topics, 2)
                if code in ("POP", "CLN"):
                    self.human_labs.add(lab)
        self._unit(session, "Shared Resources", "division", "SHR", "ALD")
        for name, code in c.CORES:
            self._unit(session, name, "core", code, "SHR")
        self._unit(session, "Administration", "division", "ADM", "ALD")
        for name, code in c.OFFICES:
            self._unit(session, name, "office", code, "ADM")
        for name, code in c.IT_TEAMS:
            self._unit(session, name, "office", code, "IT")

    def _person(
        self, session: Session, name: str, title: str, unit: str | int, *grants: Grant
    ) -> int:
        unit_id = self.units[unit] if isinstance(unit, str) else unit
        account = accounts.create(
            session, ME, email=email_for(name), display_name=name, title=title, grants=grants
        )
        # Nobody in the demo has a password: the sign-in page signs you in as a sample
        # person, and only from this machine.
        accounts.set_status(session, ME, account, "active")
        accounts.set_memberships(session, ME, account, [unit_id])
        self.staff[unit_id].append(account.id)
        self.names[account.id] = name
        self.tally("accounts")
        return account.id

    def _people(self, session: Session) -> None:
        fixed = {name for _, name, *_ in c.CAST} | {name for _, name, *_ in c.REVIEWERS}
        fixed |= {head for labs in c.FIXED_LABS.values() for _, head in labs}
        names = self._people_names(fixed)
        for key, name, title, unit, role, function, _ in c.CAST:
            grants = []
            if role == "steward":
                grants.append(Grant("steward", self.units[unit]))
            elif role == "reviewer":
                grants.append(Grant("reviewer", None, function))
            elif role != "member":
                grants.append(Grant(role))
            self.cast[key] = self._person(session, name, title, unit, *grants)
            if function:
                self.reviewers.setdefault(function, []).append(self.cast[key])
        self.governance = [self.cast["governance"], self.cast["deputy"]]
        for function, name, title, unit in c.REVIEWERS:
            person = self._person(session, name, title, unit, Grant("reviewer", None, function))
            self.reviewers.setdefault(function, []).append(person)
        self.heads[self.units["NEU"]] = self.cast["division"]
        for name, code, *_ in c.DIVISIONS:
            if code != "NEU":
                head = self._person(
                    session, next(names), f"Director, {name}", code,
                    Grant("steward", self.units[code]),
                )  # fmt: skip
                self.heads[self.units[code]] = head
        self._person(
            session, next(names), "Chief Research Officer", "ALD",
            Grant("steward", self.units["ALD"]),
        )  # fmt: skip
        titles = [title for title, weight in c.LAB_TITLES for _ in range(weight)]
        for lab_code, head in self._lab_heads.items():
            lab = self.units[lab_code]
            if lab_code == "NEU-NAIR":
                self.heads[lab] = self.cast["pi"]
            else:
                full = str(head)
                while " " not in full or (full != head and email_for(full) in self._emails):
                    full = f"{next(names).split()[0]} {head}"
                self._emails.add(email_for(full))
                self.heads[lab] = self._person(
                    session, full, "Principal Investigator", lab, Grant("steward", lab)
                )
            for _ in range(self.rng.randint(3, 5) - len(self.staff[lab]) + 1):
                self._person(session, next(names), self.rng.choice(titles), lab)
        for _name, code in c.CORES:
            for title in c.CORE_TITLES[: self.rng.randint(3, 4)]:
                grants = [Grant("steward", self.units[code])] if title == "Core Manager" else []
                person = self._person(session, next(names), title, code, *grants)
                if grants:
                    self.heads[self.units[code]] = person
        for code, titles_here in c.OFFICE_TITLES.items():
            for title in titles_here:
                self._person(session, next(names), title, code)
        cru = self.units["CRU"]
        for title in ("Clinical Research Coordinator", "Research Nurse", "Regulatory Specialist"):
            self._person(session, next(names), title, cru)
        sample = [
            {"key": key, "email": email_for(name), "name": name, "title": title, "about": about}
            for key, name, title, _unit, _role, _function, about in c.CAST
        ]
        settings.put(
            session, SETTING,
            {"seed": self.seed, "built_on": self.end.date().isoformat(), "accounts": sample},
        )  # fmt: skip
        self.sample = sample

    # --- Vendors and the catalog --------------------------------------------------------

    def _vendor(self, name: str, status: str, diligence: str, about: str) -> Iterator[datetime]:
        yield self.later(1, 55)
        slug = _ascii(name).lower().replace(" & ", "-").replace(" ", "-")
        with self.act(self.rng.choice(self.governance)) as (session, who):
            vendor = records.create(
                session, who, VENDOR,
                {"name": name, "website": f"https://{slug}.example",
                 "notes": about, "status": status, "due_diligence_status": diligence},
            )  # fmt: skip
            self.vendors[name] = vendor.ref
            self.tally("vendors")

    def _catalog_entry(self, entry: tuple[Any, ...]) -> Iterator[datetime]:
        (name, vendor, kind, edition, hosting, access, summary, standing, data_class,
         excluded, trains, terms) = entry  # fmt: skip
        evaluating = standing == "under_evaluation"
        yield self.ago(self.rng.uniform(5, 70)) if evaluating else self.later(62, 210)
        by = self.rng.choice(self.governance)
        with self.act(by) as (session, who):
            system = records.create(
                session, who, SYSTEM,
                {"name": name, "kind": kind, "vendor": self.vendors[vendor], "edition": edition,
                 "hosting": hosting, "access_path": access, "summary": summary,
                 "data_handling": {"trains_on_inputs": trains},
                 "catalog_status": "under_evaluation"},
            )  # fmt: skip
            ref = system.ref
            self.tally("systems")
        primary = next(e[3] for e in c.CATALOG if e[0] == name) == edition
        if primary:
            self.known[name] = ref
        if evaluating:
            return
        yield self.later(6, 40)
        with self.act(by) as (session, who):
            system = find(session, SYSTEM, ref)
            values: dict[str, Any] = {"catalog_status": standing}
            if data_class:
                values |= {"permitted_data_class": data_class, "excluded_data_categories": excluded}
            if terms:
                values["terms"] = terms
            records.update(session, who, SYSTEM, system, values, version=system.version)
        if standing != "not_approved" and primary:
            self.tools[name] = ref
            self.tool_class[name] = data_class

    # --- Requests -----------------------------------------------------------------------

    def _reference(self, kind: str) -> str:
        if kind == "agreement":
            self._agreements += self.rng.randint(1, 9)
            return f"ALD-AGR-{self._agreements:04d}"
        self._protocols += self.rng.randint(1, 9)
        return f"ALD-HS-{self._protocols:04d}"

    def _answers(self, plan: Plan, tools: list[str], other: str | None) -> dict[str, Any]:
        answers = {
            **c.BASE, **FOLLOW_UPS, **c.PROFILES[plan.profile], **plan.answers,
            "name": plan.name, "unit": plan.unit, "purpose": plan.purpose, "systems": tools,
            "ethics_protocol": self._reference("protocol"),
            "agreement_reference": self._reference("agreement"),
        }  # fmt: skip
        if other:
            answers["other_tool"] = other
        return answers

    def _own_tool(self, plan: Plan) -> str | None:
        """Someone who uses a tool nobody has evaluated adds it to the inventory first."""
        if not self.unlisted or self.rng.random() < 0.08:
            return None
        name, kind, hosting, access, summary = self.unlisted.pop(
            self.rng.randrange(len(self.unlisted))
        )
        with self.act(plan.requester) as (session, who):
            system = records.create(
                session, who, SYSTEM,
                {"name": name, "kind": kind, "hosting": hosting, "access_path": access,
                 "summary": summary, "org_unit_id": plan.unit},
            )  # fmt: skip
            self.tally("systems")
            return system.ref

    def _governor(self, plan: Plan) -> int:
        named = plan.fixed.get("by")
        if named:
            return self.cast[named]
        choice = self.governance[0] if self.rng.random() < 0.65 else self.governance[1]
        return choice if choice != plan.requester else self.governance[0]

    def _reviewer(self, function: str, plan: Plan) -> int:
        pool = [p for p in self.reviewers[function] if p != plan.requester]
        if not pool:  # the only reviewer for this function is the one asking
            return self._governor(plan)
        return pool[0] if self.rng.random() < 0.6 else self.rng.choice(pool)

    def request(self, plan: Plan) -> Iterator[datetime]:
        """The whole course of one request, a step at a time."""
        yield plan.start
        rng, fixed = self.rng, plan.fixed
        pace = fixed.get("pace") or self.pace(plan.start)
        halt = fixed.get("halt")
        ready = [name for name in plan.tools if name in self.tools]
        tools = [self.tools[name] for name in ready[:1]]
        if not tools:  # a tool still being evaluated, or one the catalog says not to use
            tools = [self.known[name] for name in plan.tools if name in self.known][:1]
        other = None if tools or not plan.tools else plan.tools[0]
        ref: str | None = None

        # The short way: an everyday use of an approved tool, registered from the catalog.
        if plan.profile == "everyday" and ready and not plan.answers:
            data_class = "public" if self.tool_class[ready[0]] == "public" else "internal"
            with self.act(plan.requester) as (session, who):
                result = catalog.register(
                    session, who, catalog.find_system(session, tools[0]),
                    {"name": plan.name, "org_unit_id": plan.unit, "purpose": plan.purpose,
                     "data_class": data_class, "data_categories": [], "everyday": True},
                )  # fmt: skip
            self.tally("use_cases")
            if result["registered"]:
                self.tally("registered")
                if plan.then:
                    plan.then(result["ref"])
                return
            ref = result["ref"]
        if not tools and not plan.tools:
            own = self._own_tool(plan)
            tools = [own] if own else []
            other = None if own else "An open-source tool run on the lab's own workstation"
        answers = self._answers(plan, tools, other)
        if plan.start > self.end - timedelta(days=120) and "stage" not in plan.answers:
            answers["stage"] = rng.choice(["proposed", "pilot", "pilot", "in_use"])

        with self.act(plan.requester) as (session, who):
            if ref is None:
                ref = intake.start(session, who, answers).ref
                self.tally("use_cases")
            else:
                intake.save(session, who, find(session, USE_CASE, ref), answers)  # type: ignore[arg-type]
        if plan.then:
            plan.then(ref)
        if halt == "draft":
            return

        yield self.later(0.02, 0.2 if fixed else 2.5)
        with self.act(plan.requester) as (session, who):
            use_case = find(session, USE_CASE, ref)
            assessment = intake.submit(session, who, use_case)  # type: ignore[arg-type]
            opened = review.latest_review(session, use_case)  # type: ignore[arg-type]
            assert opened is not None
            rref, status, tier = opened.ref, opened.status, assessment.final_tier
            stopped = bool(assessment.stops)
            standard = list(opened.routing.get("conditions", []))
        self.tally("reviews")
        self.tally(f"tier_{tier}")
        if status == "decided":
            yield from self._after_approval(plan, ref, pace)
            return
        if halt == "submitted":
            return

        if stopped:
            yield self.later(0.5, 3, pace)
            with self.act(self._governor(plan)) as (session, who):
                found = review.find(session, who, rref)
                reason = " ".join(stop["reason"] for stop in assessment.stops)
                review.decide(
                    session, who, found, outcome="declined",
                    rationale=fixed.get("rationale") or f"This is a prohibited use. {reason} "
                    "The catalog lists approved tools for this kind of work.",
                )  # fmt: skip
            self.tally("declined")
            return

        yield self.later(0.1, 2.2, pace)
        governor = self._governor(plan)
        with self.act(governor) as (session, who):
            found = review.triage(session, who, review.find(session, who, rref))
            tasks = [(task.id, task.review_function) for task in review.tasks_of(session, found)]
        if halt == "triaged":
            return

        outcome = fixed.get("outcome")
        if outcome is None and rng.random() < 0.03:
            outcome = "withdrawn"
        if outcome == "withdrawn":
            yield self.later(0.5, 6, pace)
            with self.act(plan.requester) as (session, who):
                review.withdraw(
                    session, who, review.find(session, who, rref),
                    "We have decided to use an approved tool from the catalog instead.",
                )  # fmt: skip
            self.tally("withdrawn")
            return

        # A question for the requester stops the clock until they answer.
        if fixed.get("question", rng.random() < (0.3 if tasks else 0.12)):
            question, answer = rng.choice(c.QUESTIONS)
            asker = (
                self.cast[fixed["asker"]]
                if fixed.get("asker")
                else self._reviewer(tasks[0][1], plan)
                if tasks
                else governor
            )
            yield self.later(0.3, 2.5, pace)
            with self.act(asker) as (session, who):
                review.comment(
                    session, who, review.find(session, who, rref),
                    fixed.get("ask") or question, question=True,
                )  # fmt: skip
            if halt == "asked":
                return
            yield self.later(0.2, 5, pace)
            with self.act(plan.requester) as (session, who):
                review.comment(session, who, review.find(session, who, rref), answer)

        # Reviewers work in parallel, each in their own time.
        pending = set(fixed.get("pending", ()))
        objected = False
        recommended: list[str] = []
        waits = sorted((rng.uniform(0.6, 4 + 2.5 * tier) * pace, task) for task in tasks)
        begun = self.now
        for wait, (task_id, function) in waits:
            if function in pending:
                continue
            yield self._workday(max(self.now, begun + timedelta(days=wait)))
            finding = (
                fixed.get("findings", {}).get(function)
                or rng.choices(["no_concerns", "conditions", "objection"], [66, 30, 4])[0]
            )
            notes = rng.choice(c.NOTES[function])
            given: list[dict[str, Any]] = []
            if finding == "conditions":
                recommended.append(RECOMMENDS[function])
                given = [{"template_key": RECOMMENDS[function]}]
            elif finding == "objection":
                objected = True
                notes = "The safeguards described are not enough for the data involved. " + notes
            with self.act(self._reviewer(function, plan)) as (session, who):
                found = review.find(session, who, rref)
                review.complete_task(
                    session, who, found, task_id, finding=finding, notes=notes, conditions=given
                )
            self.tally("findings")
        if pending or halt == "ready":
            return

        committee = tier >= 3
        yield self.later(1.5 if committee else 0.3, 9 if committee else 3.5, pace)
        if outcome is None:
            roll = rng.random()
            if objected:
                outcome = "declined" if roll < 0.7 else "approved"
            elif roll < (0.05 if tier >= 3 else 0.02):
                outcome = "declined"
            elif roll < 0.11:
                outcome = "returned"
            else:
                outcome = "approved"
        if outcome == "returned":
            with self.act(governor) as (session, who):
                review.decide(
                    session, who, review.find(session, who, rref), outcome="returned",
                    rationale=fixed.get("rationale") or rng.choice(c.RATIONALES["returned"]),
                )  # fmt: skip
            self.tally("returned")
            if halt == "returned":
                return
            yield self.later(0.5, 7, pace)
            with self.act(plan.requester) as (session, who):
                use_case = find(session, USE_CASE, ref)
                revised = {**answers, "human_oversight": answers["human_oversight"]
                           + " The check is recorded in the lab notebook, dated."}  # fmt: skip
                intake.save(session, who, use_case, revised)  # type: ignore[arg-type]
                intake.submit(session, who, use_case)  # type: ignore[arg-type]
            yield self.later(0.3, 3, pace)
            outcome = "approved"

        conditions = [{"template_key": key} for key in dict.fromkeys([*standard, *recommended])]
        if outcome == "approved" and rng.random() < 0.22:
            conditions.append(
                {"text": "Report to the governance office on accuracy and any problems after "
                 "three months of use.", "kind": "by_date",
                 "due_on": (self.now + timedelta(days=rng.randint(80, 130))).date().isoformat()}
            )  # fmt: skip
        conditions += fixed.get("conditions", [])
        with self.act(governor) as (session, who):
            found = review.find(session, who, rref)
            if found.status == "triage":
                found = review.triage(session, who, found)
            rationale = fixed.get("rationale") or rng.choice(
                c.RATIONALES["declined" if outcome == "declined" else
                             "conditions" if recommended else "approved"]
            )  # fmt: skip
            review.decide(
                session, who, found, outcome=outcome, rationale=rationale,
                conditions=conditions if outcome == "approved" else [],
            )  # fmt: skip
        self.tally(outcome)
        if outcome == "approved":
            yield from self._after_approval(plan, ref, pace)

    def _after_approval(self, plan: Plan, ref: str, pace: float) -> Iterator[datetime]:
        """Owners meet their conditions: most of them, and mostly on time."""
        with self.db.read() as session:
            use_case = find(session, USE_CASE, ref)
            waiting = [
                (cond.id, cond.kind, cond.due_on)
                for cond in review.conditions_of(session, use_case)  # type: ignore[arg-type]
                if cond.status == "open" and cond.kind != "ongoing"
            ]
        self.tally("conditions", len(waiting))
        keep_open = plan.fixed.get("leave_conditions", False)
        for condition_id, kind, due in waiting:
            if keep_open or self.rng.random() > (0.88 if kind == "before_use" else 0.7):
                continue
            if kind == "by_date" and due is not None:
                yield self._workday(
                    datetime(due.year, due.month, due.day, 11, tzinfo=UTC)
                    - timedelta(days=self.rng.uniform(1, 25))
                )
            else:
                yield self.later(1, 16, pace)
            with self.act(plan.requester) as (session, who):
                review.close_condition(
                    session, who, condition_id, status="met",
                    note=self.rng.choice(c.CONDITION_NOTES),
                )  # fmt: skip

    # --- Planning what gets asked -------------------------------------------------------

    def _when(self) -> datetime:
        """More requests arrive as the program becomes known."""
        span = (self.end - self.start).days - 40
        return self._workday(
            self.start + timedelta(days=36 + span * self.rng.random() ** 0.72,
                                   hours=self.rng.uniform(8, 17))
        )  # fmt: skip

    def _askers(self, unit: int) -> list[int]:
        """The people in a unit who ask for things: not those whose job is to review them."""
        busy = {p for pool in self.reviewers.values() for p in pool} | set(self.governance)
        return [p for p in self.staff[unit] if p not in busy] or self.staff[unit]

    def plans(self, total: int) -> list[Plan]:
        rng = self.rng
        made: list[Plan] = []
        for code, uses in c.UNIT_USES.items():
            unit = self.units[code]
            for name, purpose, profile, tools in uses:
                made.append(
                    Plan(self._when(), rng.choice(self._askers(unit)), unit, name, purpose,
                         profile, tools)
                )  # fmt: skip
        per_lab: dict[int, list[tuple[str, str, str, list[str]]]] = {}
        while len(made) < total:
            lab = rng.choice(self.labs)
            if lab not in per_lab:
                pool = list(c.RESEARCH_USES)
                if lab in self.human_labs:
                    pool += c.HUMAN_USES * 2
                rng.shuffle(pool)
                per_lab[lab] = pool
            if not per_lab[lab]:
                continue
            name, purpose, profile, tools = per_lab[lab].pop()
            topic = rng.choice(self.topics[lab])
            people = self.staff[lab]
            requester = people[0] if rng.random() < 0.22 else rng.choice(people[1:])
            made.append(
                Plan(self._when(), requester, lab, name.format(topic=topic),
                     purpose.format(topic=topic), profile, list(tools))
            )  # fmt: skip
        for plan in made:
            if plan.profile == "clinical" and rng.random() < 0.45:
                plan.answers = {"reach": "org_wide"}
        # A program in use always has a few weeks of work on its desks.
        busy = [p for p in made if not p.fixed and p.profile not in ("everyday", "minimal")]
        for plan in rng.sample(busy, min(26, len(busy))):
            plan.start = self.ago(rng.uniform(1, 30), 9 + rng.randrange(7))
            plan.fixed["pace"] = 1.7  # a busy month: things are taking longer than usual
        recent = [plan for plan in made if plan.start > self.end - timedelta(days=45)]
        for plan in rng.sample(recent, min(6, len(recent))):
            plan.fixed["halt"] = "draft"
        return made

    def storylines(self) -> list[Plan]:
        """The requests the guides talk about. They happen in every build, whatever the seed."""
        cast, unit = self.cast, self.units
        hale, nair = unit["NEU-HALE"], unit["NEU-NAIR"]
        coordinator = self.staff[unit["CRU"]][0]
        nurse = self.staff[unit["CRU"]][1]
        desk_lead = self.staff[unit["ITSD"]][0]
        pop_lab = next(lab for lab in self.labs if lab in self.human_labs)
        interviewer = self.staff[pop_lab][1]
        nair_postdoc = self.staff[nair][1]
        stories = [
            Plan(self.ago(420), cast["member"], hale,
                 "Drafting and summarizing internal documents",
                 "Draft emails, summarize long documents, and tidy meeting notes for the lab.",
                 "everyday", ["Brightfen Assistant"]),
            Plan(self.ago(170), coordinator, unit["CRU"],
                 "Summarizing study visit notes for coordinators",
                 "Draft a summary of each study visit from the coordinator's notes, for the "
                 "coordinator to check and sign before it goes into the study record.",
                 "clinical", ["Veridale Visit Summaries"],
                 answers={"reach": "org_wide", "stage": "pilot",
                          "human_oversight": "The coordinator reads every summary against the "
                          "visit notes and signs it. The medical director reviews a sample "
                          "of twenty each month."},
                 fixed={"question": True, "asker": "privacy", "outcome": "approved", "pace": 1.0,
                        "by": "governance",
                        "ask": "Do the visit notes ever contain genetic results? The tool is "
                        "not approved for those.",
                        "findings": {"privacy": "conditions", "security": "no_concerns",
                                     "legal": "no_concerns", "clinical_safety": "conditions",
                                     "ethics": "conditions"},
                        "rationale": "The committee approved this pilot in the clinical research "
                        "unit on the conditions below. Every summary is checked and signed by a "
                        "coordinator, and nothing reaches a participant from it directly."}),
            Plan(self.ago(250), desk_lead, unit["ITSD"],
                 "Service-desk agent that triages and closes tickets",
                 "An agent reads incoming tickets, sets the category and priority, and resolves "
                 "password resets and access requests on its allow-list.",
                 "agent", ["Deskhand Agent"],
                 fixed={"outcome": "approved", "by": "governance", "pace": 1.0,
                        "findings": {"security": "conditions", "architecture": "conditions"},
                        "conditions": [{"text": "The agent may close only the ticket types on "
                                        "its allow-list. Changes to the list need the service "
                                        "desk lead's approval.", "kind": "ongoing"}],
                        "rationale": "Approved with limits on what the agent may do by itself, "
                        "and a tested way to stop it."}),
            Plan(self.ago(96), interviewer, pop_lab,
                 "Transcribing participant interviews with a consumer chat app",
                 "Upload interview recordings to a consumer app to get transcripts quickly.",
                 "stop_consumer", ["Quillstream Transcribe"],
                 fixed={"by": "governance",
                        "rationale": "Recordings of participants may not be given to a supplier "
                        "that trains on them and has no agreement with the institute. Larkspur "
                        "Scribe is approved for this and is in the catalog."}),
            Plan(self.ago(84), interviewer, pop_lab,
                 "Transcribing participant interviews",
                 "Transcribe recorded interviews with study participants on the institute's "
                 "transcription service, for qualitative analysis.",
                 "people_data", ["Larkspur Scribe"],
                 fixed={"outcome": "approved", "question": False, "pace": 0.8}),
            Plan(self.ago(190), cast["division"], unit["NEU"],
                 "Grant-writing assistant for the Neuroscience division",
                 "Help investigators across the division draft and tighten funding "
                 "applications. Authors remain responsible for every statement.",
                 "grants", ["Brightfen Assistant"],
                 answers={"reach": "many_units", "data_class": "protected"},
                 fixed={"outcome": "approved", "findings": {"integrity": "conditions"},
                        "pace": 1.0}),
            Plan(self.ago(130), nair_postdoc, nair,
                 "Segmenting neurons in calcium imaging movies",
                 "Outline cell bodies in two-photon calcium imaging movies so that activity "
                 "can be extracted for each cell.",
                 "local", ["Segmentry Cell"], answers={"stage": "pilot"},
                 fixed={"outcome": "approved", "question": False, "pace": 0.9}),
            # What is on people's desks today.
            Plan(self.ago(9), cast["member"], hale,
                 "Classifying sleep stages from wearable recordings",
                 "Classify sleep stages from wrist-worn sensor recordings of study "
                 "participants, using a model trained in the lab.",
                 "people_data", [],
                 answers={"exposure": "own_cloud", "data_class": "restricted",
                          "data_categories": ["health", "human_subjects", "personal"]},
                 fixed={"halt": "asked", "question": True, "asker": "privacy", "pace": 0.6,
                        "ask": "Are the recordings linked to names or study IDs when the model "
                        "sees them? If study IDs, who holds the key?"}),
            Plan(self.ago(1.2), nair_postdoc, nair,
                 "Predicting seizure onset from electrophysiology recordings",
                 "Train a model on the lab's recordings to predict seizure onset in mice.",
                 "moderate", ["Junco AI Services"], fixed={"halt": "submitted"}),
            Plan(self.ago(16), nurse, unit["CRU"],
                 "Matching patients to open trials",
                 "Suggest open trials a patient may be eligible for, for the research nurse "
                 "to review with the treating clinician.",
                 "clinical", ["Trialwick Navigator"],
                 fixed={"halt": "ready", "question": False, "pace": 0.45,
                        "findings": {"privacy": "conditions", "clinical_safety": "conditions"}}),
            Plan(self.ago(38), self.staff[pop_lab][2], pop_lab,
                 "Linking registry records across hospitals",
                 "Match records about the same person across hospital registries using a "
                 "learned matcher, under the registry's data use agreement.",
                 "health", ["Junco AI Services"],
                 fixed={"pending": ["privacy"], "question": False, "pace": 0.7}),
            Plan(self.ago(3), cast["member"], hale,
                 "Summarizing reviewer feedback on our preprint",
                 "Summarize comments on the lab's preprint and draft replies.",
                 "writing", ["Brightfen Assistant"], fixed={"halt": "draft"}),
            Plan(self.ago(52), cast["member"], hale,
                 "Detecting sleep spindles in EEG recordings",
                 "Detect sleep spindles in EEG recordings from study participants with an "
                 "open-source detector run on the lab's server.",
                 "people_data", [],
                 answers={"exposure": "own_equipment",
                          "data_categories": ["health", "human_subjects", "personal"]},
                 fixed={"outcome": "approved", "question": False, "pace": 0.6,
                        "findings": {"privacy": "conditions"}, "leave_conditions": True}),
        ]  # fmt: skip
        return stories

    # --- Everything -----------------------------------------------------------------------

    def build(self, *, use_cases: int = 300) -> Summary:
        self.found()
        for vendor in c.VENDORS:
            self.schedule(self._vendor(*vendor))
        for entry in c.CATALOG:
            self.schedule(self._catalog_entry(entry))
        stories = self.storylines()
        for plan in [*self.plans(use_cases - len(stories)), *stories]:
            self.schedule(self.request(plan))
        self.run()
        return Summary(self.seed, self.end.date(), dict(sorted(self.counts.items())), self.sample)


def build(
    db: Database, *, seed: int = 1, today: date | None = None, use_cases: int = 300
) -> Summary:
    """Build the demo organization in an empty, migrated database."""
    with db.read() as session:
        if settings.get(session, SETTING) is not None or units.all_units(session):
            raise GovWrenError("This installation already has an organization in it.")
    from govwren.core.clock import today as real_today

    return Builder(db, seed=seed, today=today or real_today()).build(use_cases=use_cases)


def marker(session: Session) -> dict[str, Any] | None:
    """What says this installation is a demo, or None if it is not."""
    value = settings.get(session, SETTING)
    return value if isinstance(value, dict) else None
