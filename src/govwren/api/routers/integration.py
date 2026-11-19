"""What other systems use: tokens, the checkpoint, and webhooks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from govwren.access.policy import current
from govwren.api.common import database, envelope, reading, writing
from govwren.core.errors import PermissionDenied
from govwren.integration import checkpoint, tokens, webhooks

router = APIRouter(prefix="/api/v1", tags=["integration"])
DATA_CLASS = Query(
    None, description="A data class: is the record approved for data this sensitive?"
)


@router.get("/checkpoint/{ref}", summary="Is this reference approved, for what data, until when?")
def ask_checkpoint(
    request: Request, ref: str, data_class: str | None = DATA_CLASS
) -> dict[str, Any]:
    """For a system that is given a GovWren reference and must decide whether to proceed.
    The answer is the record's standing: ``approved``, ``status``, ``approved_until``, and
    the data class it covers. With ``data_class``, ``allowed`` says whether the record is
    approved and covers data that sensitive. Nothing about the record's content is given,
    so any signed-in person or token may ask about any reference."""
    with reading(request) as session:
        return envelope(checkpoint.check(session, ref, data_class))


class TokenBody(BaseModel):
    name: str = Field(default="", max_length=200)
    scope: str = Field(default="", max_length=40)
    expires_on: str | None = None


def _in_person(request: Request) -> Any:
    """Tokens are managed by a person who has signed in, never by another token."""
    principal = current(request)
    if getattr(request.state, "token_scope", None) is not None:
        raise PermissionDenied("Sign in to manage tokens. A token cannot make or revoke tokens.")
    return principal


@router.get("/tokens", summary="Your API tokens")
def list_tokens(request: Request) -> dict[str, Any]:
    principal = _in_person(request)
    with reading(request) as session:
        return envelope(
            {
                "tokens": tokens.mine(session, principal),
                "scopes": [{"key": key, "label": label} for key, label in tokens.SCOPES.items()],
            }
        )


@router.post("/tokens", status_code=201, summary="Make an API token")
def create_token(request: Request, body: TokenBody) -> dict[str, Any]:
    """The answer holds ``token``, the secret itself. It is shown this once and cannot be
    read again: only its hash is kept. Send it as ``Authorization: Bearer <token>``."""
    principal = _in_person(request)
    with writing(request, principal.actor) as session:
        row, secret = tokens.create(session, principal, body.model_dump())
        return envelope({**tokens.view(row), "token": secret})


@router.delete("/tokens/{token_id}", summary="Revoke an API token")
def revoke_token(request: Request, token_id: int) -> dict[str, Any]:
    principal = _in_person(request)
    with writing(request, principal.actor) as session:
        tokens.revoke(session, principal, token_id)
        return envelope({"tokens": tokens.mine(session, principal)})


@router.get("/admin/tokens", summary="Everyone's API tokens")
def all_tokens(request: Request) -> dict[str, Any]:
    principal = _in_person(request)
    with reading(request) as session:
        return envelope({"tokens": tokens.everyones(session, principal)})


class WebhookBody(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=1000)
    topics: list[str] | None = None
    active: bool | None = None


@router.get("/admin/webhooks", summary="The webhooks, and how their deliveries are going")
def list_webhooks(request: Request) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(webhooks.listing(session, principal))


@router.post("/admin/webhooks", status_code=201, summary="Add a webhook")
def create_webhook(request: Request, body: WebhookBody) -> dict[str, Any]:
    """The answer holds ``secret``, shown this once. Each delivery is signed with it: the
    ``X-GovWren-Signature`` header is ``sha256=`` and the HMAC-SHA256 of the
    ``X-GovWren-Timestamp`` header, a dot, and the body."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        row, secret = webhooks.create(session, principal, body.model_dump(exclude_none=True))
        return envelope({**webhooks.view(session, row), "secret": secret})


@router.patch("/admin/webhooks/{webhook_id}", summary="Change a webhook, or switch it off or on")
def change_webhook(request: Request, webhook_id: int, body: WebhookBody) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        row = webhooks.change(
            session,
            principal,
            webhooks.find(session, webhook_id),
            body.model_dump(exclude_none=True),
        )
        return envelope(webhooks.view(session, row))


@router.delete("/admin/webhooks/{webhook_id}", summary="Remove a webhook")
def remove_webhook(request: Request, webhook_id: int) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        webhooks.remove(session, principal, webhooks.find(session, webhook_id))
        return envelope(webhooks.listing(session, principal))


@router.post("/admin/webhooks/{webhook_id}/test", summary="Send a test delivery now")
def test_webhook(request: Request, webhook_id: int) -> dict[str, Any]:
    principal = current(request)
    send = getattr(request.app.state, "webhook_send", webhooks._post)
    return envelope({"result": webhooks.send_test(database(request), principal, webhook_id, send)})
