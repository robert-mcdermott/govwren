"""Reviews: the queue, a review's packet, triage, findings, discussion, and decisions."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from govwren.access.policy import current
from govwren.api.common import database, envelope, reading, writing
from govwren.core.errors import NotFound
from govwren.inventory import access
from govwren.inventory.registry import USE_CASE, find
from govwren.review import service, sessions, spotchecks, views

router = APIRouter(prefix="/api/v1", tags=["review"])


class Triage(BaseModel):
    add: list[str] = Field(default=[], description="Review functions to require as well")
    remove: list[str] = Field(
        default=[], description="Review functions the rules required that are not needed"
    )
    reason: str = Field(default="", max_length=2000)


class Assignment(BaseModel):
    account_id: int | None = None


class Finding(BaseModel):
    finding: str = Field(description="no_concerns, conditions, or objection")
    notes: str = Field(default="", max_length=10000)
    conditions: list[dict[str, Any]] = []


class AcceptanceRequest(BaseModel):
    account_id: int | None = None


class AcceptanceAnswer(BaseModel):
    accept: bool
    statement: str = Field(default="", max_length=4000)


class NewSession(BaseModel):
    title: str
    held_on: date | None = None
    reviews: list[str] = []


class Agenda(BaseModel):
    reviews: list[str]


class SessionRecord(BaseModel):
    attendees: str | None = None
    minutes: str | None = None
    close: bool = False


class Draw(BaseModel):
    count: int = 5


class Check(BaseModel):
    agree: bool
    note: str = ""


class NewComment(BaseModel):
    body: str = Field(max_length=10000)
    visibility: str = Field(default="internal", description="requester or internal")
    question: bool = Field(
        default=False, description="Ask the requester, and pause the clock until they reply"
    )


class DecisionBody(BaseModel):
    outcome: str = Field(description="approved, declined, or returned")
    rationale: str = Field(max_length=10000)
    conditions: list[dict[str, Any]] = []
    session: str | None = Field(default=None, description="The committee session it is made in")


class Withdrawal(BaseModel):
    reason: str = Field(default="", max_length=2000)


class Closure(BaseModel):
    status: str = Field(description="met or waived")
    note: str = Field(max_length=4000)


class Read(BaseModel):
    ids: list[int] | None = None


@router.get("/me/work", summary="What is waiting on you")
def my_work(request: Request) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(views.my_work(session, principal))


@router.get("/notifications", summary="Your notices")
def notifications(request: Request) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(views.notifications(session, principal))


@router.post("/notifications/read", summary="Mark notices as read")
def read_notifications(request: Request, body: Read) -> dict[str, Any]:
    principal = current(request)
    with database(request).bookkeeping() as session:
        views.mark_read(session, principal, body.ids)
    return envelope({"read": True})


@router.get("/reviews", summary="Reviews you have a part in")
def queue(request: Request, scope: str = "open") -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(views.queue(session, principal, scope=scope))


@router.get("/reviews/{ref}", summary="One review: the decision packet")
def show(request: Request, ref: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(views.packet(session, principal, service.find(session, principal, ref)))


@router.get("/use-cases/{ref}/review", summary="The latest review of a use case")
def for_use_case(request: Request, ref: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        use_case = find(session, USE_CASE, ref)
        if access.sight(session, principal, USE_CASE, use_case) is None:
            raise NotFound(f"There is no use case {ref}.")
        return envelope(views.review_summary(session, principal, use_case))  # type: ignore[arg-type]


def _act(request: Request, ref: str, run: Any) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        review = service.find(session, principal, ref)
        run(session, principal, review)
        return envelope(views.packet(session, principal, review))


@router.post(
    "/reviews/{ref}/triage", summary="Confirm or adjust the reviews required, and start them"
)
def triage(request: Request, ref: str, body: Triage) -> dict[str, Any]:
    return _act(
        request,
        ref,
        lambda s, p, r: service.triage(
            s, p, r, add=body.add, remove=body.remove, reason=body.reason
        ),
    )


@router.post("/reviews/{ref}/tasks/{task_id}/claim", summary="Take a review task")
def claim(request: Request, ref: str, task_id: int) -> dict[str, Any]:
    return _act(request, ref, lambda s, p, r: service.claim(s, p, r, task_id))


@router.post("/reviews/{ref}/tasks/{task_id}/assign", summary="Give a review task to someone")
def assign(request: Request, ref: str, task_id: int, body: Assignment) -> dict[str, Any]:
    return _act(request, ref, lambda s, p, r: service.assign(s, p, r, task_id, body.account_id))


@router.post("/reviews/{ref}/tasks/{task_id}/complete", summary="Record a finding")
def complete(request: Request, ref: str, task_id: int, body: Finding) -> dict[str, Any]:
    return _act(
        request,
        ref,
        lambda s, p, r: service.complete_task(
            s, p, r, task_id, finding=body.finding, notes=body.notes, conditions=body.conditions
        ),
    )


@router.post("/reviews/{ref}/comments", summary="Add to the discussion")
def comment(request: Request, ref: str, body: NewComment) -> dict[str, Any]:
    """A question to the requester pauses the review's clock until they reply."""
    return _act(
        request,
        ref,
        lambda s, p, r: service.comment(
            s, p, r, body.body, visibility=body.visibility, question=body.question
        ),
    )


@router.post("/reviews/{ref}/decision", summary="Approve, decline, or return a request")
def decide(request: Request, ref: str, body: DecisionBody) -> dict[str, Any]:
    return _act(
        request,
        ref,
        lambda s, p, r: service.decide(
            s,
            p,
            r,
            outcome=body.outcome,
            rationale=body.rationale,
            conditions=body.conditions,
            at_session=body.session,
        ),
    )


@router.post("/reviews/{ref}/acceptance", summary="Ask a named person to accept the risk")
def ask_acceptance(request: Request, ref: str, body: AcceptanceRequest) -> dict[str, Any]:
    """Where the rules require it, a request cannot be approved until a named person has
    accepted its risk. Asking someone new replaces whoever was asked before."""
    return _act(request, ref, lambda s, p, r: service.request_acceptance(s, p, r, body.account_id))


@router.post("/reviews/{ref}/acceptance/answer", summary="Accept the risk, or decline to")
def answer_acceptance(request: Request, ref: str, body: AcceptanceAnswer) -> dict[str, Any]:
    """For the person who was asked, in their own words."""
    return _act(
        request,
        ref,
        lambda s, p, r: service.answer_acceptance(
            s, p, r, accept=body.accept, statement=body.statement
        ),
    )


@router.get("/sessions", summary="Committee sessions")
def list_sessions(request: Request) -> dict[str, Any]:
    with reading(request) as session:
        return envelope(sessions.listing(session), candidates=sessions.candidates(session))


@router.post("/sessions", status_code=201, summary="Plan a committee session")
def plan_session(request: Request, body: NewSession) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        meeting = sessions.plan(
            session, principal, title=body.title, held_on=body.held_on, reviews=body.reviews
        )
        return envelope(sessions.view(session, principal, meeting))


@router.get("/sessions/{ref}", summary="One session: its agenda, decisions, and minutes")
def show_session(request: Request, ref: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(sessions.view(session, principal, sessions.find(session, ref)))


@router.put("/sessions/{ref}/agenda", summary="Set a session's agenda")
def set_agenda(request: Request, ref: str, body: Agenda) -> dict[str, Any]:
    """The reviews to consider, in order. A decision made with ``session`` set to this
    session is recorded as made in it; the review must be on the agenda."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        meeting = sessions.find(session, ref)
        sessions.set_agenda(session, principal, meeting, body.reviews)
        return envelope(sessions.view(session, principal, meeting))


@router.put("/sessions/{ref}", summary="Record attendance and minutes, or close a session")
def record_session(request: Request, ref: str, body: SessionRecord) -> dict[str, Any]:
    """Closing needs attendance and minutes. A closed session cannot be changed."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        meeting = sessions.record(
            session,
            principal,
            sessions.find(session, ref),
            attendees=body.attendees,
            minutes=body.minutes,
            close=body.close,
        )
        return envelope(sessions.view(session, principal, meeting))


@router.get("/spot-checks", summary="Spot checks of automatic approvals")
def list_spot_checks(request: Request) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(spotchecks.listing(session, principal))


@router.post("/spot-checks", status_code=201, summary="Draw a sample to check")
def draw_spot_checks(request: Request, body: Draw) -> dict[str, Any]:
    """Draws at random from the approvals rules made in the last four months that have not
    been drawn before. The scheduler also draws about one in ten by itself."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        drawn = spotchecks.draw(session, principal, body.count)
        return envelope(spotchecks.listing(session, principal), drawn=drawn)


@router.post("/spot-checks/{check_id}", summary="Record a spot check")
def record_spot_check(request: Request, check_id: int, body: Check) -> dict[str, Any]:
    """Agree with the rule, or disagree and say why. Disagreeing opens a review of the use."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        spotchecks.check(session, principal, check_id, agree=body.agree, note=body.note)
        return envelope(spotchecks.listing(session, principal))


@router.post("/reviews/{ref}/withdraw", summary="Take a request back")
def withdraw(request: Request, ref: str, body: Withdrawal) -> dict[str, Any]:
    return _act(request, ref, lambda s, p, r: service.withdraw(s, p, r, body.reason))


@router.post("/conditions/{condition_id}/close", summary="Mark a condition as met, or waive it")
def close_condition(request: Request, condition_id: int, body: Closure) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        condition = service.close_condition(
            session, principal, condition_id, status=body.status, note=body.note
        )
        return envelope({"id": condition.id, "status": condition.status})
