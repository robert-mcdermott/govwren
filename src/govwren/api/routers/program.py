"""The program: its form, scoring model, routing rules, and vocabularies, edited in the app."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from govwren.access.policy import current
from govwren.api.common import envelope, reading, writing
from govwren.program import editor

router = APIRouter(prefix="/api/v1", tags=["program"])


class ProgramBody(BaseModel):
    """The parts of the program to replace. Leave a part out to keep it as it is."""

    forms: list[dict[str, Any]] | None = None
    scoring_model: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    vocabularies: dict[str, list[dict[str, Any]]] | None = Field(default=None)


@router.get("/program", summary="The program as it is published")
def show(request: Request) -> dict[str, Any]:
    """The form, scoring model, routing rules, and vocabularies in force, with the versions
    each has been through."""
    principal = current(request)
    with reading(request) as session:
        return envelope(editor.state(session, principal))


@router.post("/program/check", summary="Check a change to the program before publishing it")
def check(request: Request, body: ProgramBody) -> dict[str, Any]:
    """Says what is wrong with the proposed program, if anything, and what it would have done
    to the requests already submitted: how many would have had a different tier, different
    reviews, or a different route to approval. Nothing is changed."""
    principal = current(request)
    with reading(request) as session:
        return envelope(editor.check(session, principal, body.model_dump(exclude_unset=True)))


@router.put("/program", summary="Publish a change to the program")
def publish(request: Request, body: ProgramBody) -> dict[str, Any]:
    """Each part that differs from what is published becomes a new version. Earlier versions
    are kept, and a request already decided keeps the version it was decided under."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        report = editor.publish(session, principal, body.model_dump(exclude_unset=True))
        return envelope({"published": report, **editor.state(session, principal)})
