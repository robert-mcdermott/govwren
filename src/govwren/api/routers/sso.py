"""Single sign-on: the round trip to the identity provider, and the mappings from its groups
to roles here."""

from __future__ import annotations

import html
import logging
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from govwren.access.policy import current
from govwren.api.common import database, envelope, reading, writing
from govwren.api.problems import problem
from govwren.auth import oidc, sessions
from govwren.core.errors import GovWrenError
from govwren.events.actor import Actor
from govwren.people import accounts, sso

router = APIRouter(prefix="/api/v1", tags=["single sign-on"])
log = logging.getLogger("govwren.sso")


class MappingIn(BaseModel):
    claim_value: str = Field(max_length=300)
    role: str = Field(max_length=24)
    org_unit_id: int | None = None
    review_function: str | None = Field(default=None, max_length=40)


class MappingsIn(BaseModel):
    mappings: list[MappingIn] = Field(max_length=500)


def client(request: Request) -> oidc.Client | None:
    """The one client this server process uses, made on first use."""
    state = request.app.state
    config = state.config.sso
    if not config.enabled:
        return None
    if getattr(state, "sso_client", None) is None:
        state.sso_client = oidc.Client(config, transport=getattr(state, "sso_transport", None))
    return state.sso_client


def _base(request: Request) -> str:
    configured = request.app.state.config.server.base_url
    if configured:
        return configured
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip() or request.url.scheme
    host = request.headers.get("x-forwarded-host", "").split(",")[0].strip() or request.headers.get(
        "host", request.url.netloc
    )
    return f"{proto}://{host}"


def _redirect_uri(request: Request) -> str:
    return f"{_base(request)}/api/v1/sso/callback"


def _safe(next_path: str | None) -> str:
    path = next_path or "/"
    return path if path.startswith("/") and not path.startswith("//") and "\\" not in path else "/"


def _failed(reason: str) -> RedirectResponse:
    return RedirectResponse(f"/sign-in?sso={quote(reason)}", status_code=303)


@router.get("/sso/start", summary="Begin single sign-on", response_class=RedirectResponse)
def start(request: Request, next: str | None = None) -> Any:
    """Sends the browser to the identity provider. It comes back to ``/sso/callback``."""
    provider = client(request)
    if provider is None:
        return problem(404, "Single sign-on is not set up here.", instance=request.url.path)
    challenge = oidc.new_challenge()
    try:
        address = provider.authorization_url(challenge, _redirect_uri(request))
    except GovWrenError as exc:
        log.error("single sign-on could not start: %s", exc)
        return _failed("unavailable")
    with database(request).bookkeeping() as session:
        sso.remember(session, challenge, _safe(next))
    return RedirectResponse(address, status_code=303)


@router.get("/sso/callback", summary="Finish single sign-on", response_class=HTMLResponse)
def callback(
    request: Request, code: str | None = None, state: str | None = None, error: str | None = None
) -> Any:
    provider = client(request)
    if provider is None:
        return problem(404, "Single sign-on is not set up here.", instance=request.url.path)
    if error or not code or not state:
        log.warning("single sign-on came back without a code: %s", error or "nothing sent")
        return _failed("cancelled" if error == "access_denied" else "failed")
    with database(request).bookkeeping() as session:
        begun = sso.recall(session, state)
        kept = (begun.nonce, begun.verifier, begun.next_path) if begun else None
    if kept is None:
        log.warning("single sign-on answer with an unknown or expired state")
        return _failed("expired")
    nonce, verifier, next_path = kept
    config = request.app.state.config
    try:
        claims = provider.redeem(
            code, verifier=verifier, nonce=nonce, redirect_uri=_redirect_uri(request)
        )
        with writing(request, Actor.system("Single sign-on")) as session:
            account = sso.sign_in(session, config.sso, claims)
            account_id, name = account.id, account.display_name
    except GovWrenError as exc:
        log.warning("single sign-on refused: %s", exc)
        return _failed("refused")
    with writing(request, Actor.account(account_id, name)) as session:
        account = accounts.get(session, account_id)
        token, _row = sessions.create(
            session, account.id, idle_hours=config.server.session_idle_hours,
            max_days=config.server.session_max_days, user_agent=request.headers.get("user-agent"),
        )  # fmt: skip
        accounts.note_sign_in(session, account, method="sso")
    # The session cookie is SameSite=Strict, and this request arrived by way of another site,
    # so a redirect from here would be followed without it. A page that sends the browser on
    # starts a navigation of GovWren's own, and the cookie goes with that.
    target = html.escape(_safe(next_path), quote=True)
    response = HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="0;url={target}"><title>Signing in…</title></head>'
        f'<body><p><a href="{target}">Continue</a></p></body></html>',
        headers={"cache-control": "no-store"},
    )
    response.set_cookie(
        sessions.COOKIE, token, httponly=True, samesite="strict",
        secure=_base(request).startswith("https://"), path="/",
        max_age=config.server.session_max_days * 86400,
    )  # fmt: skip
    return response


@router.get("/sso", summary="How single sign-on is set up")
def show(request: Request) -> dict[str, Any]:
    config = request.app.state.config.sso
    with reading(request) as session:
        rows = [sso.mapping_view(session, row) for row in sso.mappings(session)]
    return envelope(
        {
            "enabled": config.enabled,
            "issuer": config.issuer,
            "client_id": config.client_id,
            "groups_claim": config.groups_claim,
            "redirect_uri": _redirect_uri(request),
            "local_sign_in": config.local_sign_in,
            "trust_email": config.trust_email,
            "mappings": rows,
        }
    )


@router.put("/sso/mappings", summary="Say which groups give which roles")
def put_mappings(request: Request, body: MappingsIn) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        rows = sso.set_mappings(session, principal, [m.model_dump() for m in body.mappings])
        return envelope([sso.mapping_view(session, row) for row in rows])
