"""API tokens: how a script signs in (PLT-18).

A token is shown once, when it is made, and only its SHA-256 is kept. It acts as the
account it belongs to and can never do more than that account can; its scope cuts that
down further. A disabled account's tokens stop working with it.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import today, utc_now
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.db.models import Account, ApiToken, ApiTokenUse
from govwren.events import audit

PREFIX = "gw_"
SCOPES = {
    "checkpoint": "Ask whether a reference is approved, and nothing else",
    "read": "Read what the account can read",
    "write": "Read and change what the account can",
}
MAX_PER_ACCOUNT = 20
USED_EVERY = timedelta(minutes=5)  # how often a token's last use is written down


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(session: Session, principal: Principal, values: dict[str, Any]) -> tuple[ApiToken, str]:
    """Make a token for the person asking. Returns the row and the token itself, which is
    never available again."""
    if principal.account_id is None:
        raise PermissionDenied("A token belongs to an account. Sign in to make one.")
    errors: dict[str, str] = {}
    name = str(values.get("name") or "").strip()
    if not name or len(name) > 80:
        errors["name"] = "Say what the token is for, in up to 80 characters."
    scope = values.get("scope")
    if scope not in SCOPES:
        errors["scope"] = f"Choose one of: {', '.join(SCOPES)}."
    expires: date | None = None
    if values.get("expires_on"):
        try:
            expires = date.fromisoformat(str(values["expires_on"]))
        except ValueError:
            errors["expires_on"] = "Give a date as year-month-day."
        else:
            if expires <= today():
                errors["expires_on"] = "Choose a day after today."
    live = [row for row in mine(session, principal) if row["live"]]
    if len(live) >= MAX_PER_ACCOUNT:
        errors["name"] = f"You have {MAX_PER_ACCOUNT} tokens. Revoke one you no longer use."
    if errors:
        raise Invalid("The token was not made.", errors)
    token = PREFIX + secrets.token_urlsafe(32)
    with audit.operation(session, "token.create"):
        row = ApiToken(
            account_id=principal.account_id,
            name=name,
            scope=str(scope),
            prefix=token[:10],
            token_hash=digest(token),
            expires_on=expires,
            created_at=utc_now(),
        )
        session.add(row)
        session.flush()
    return row, token


def view(row: ApiToken, owner: str | None = None, used: datetime | None = None) -> dict[str, Any]:
    expired = row.expires_on is not None and row.expires_on < today()
    return {
        "id": row.id,
        "name": row.name,
        "scope": row.scope,
        "scope_label": SCOPES.get(row.scope, row.scope),
        "prefix": row.prefix,
        "expires_on": row.expires_on,
        "created_at": row.created_at,
        "last_used_at": used,
        "revoked_at": row.revoked_at,
        "live": row.revoked_at is None and not expired,
        "expired": expired,
        **({"owner": owner} if owner is not None else {}),
    }


def _used(session: Session) -> dict[int, datetime]:
    return dict(session.execute(select(ApiTokenUse.token_id, ApiTokenUse.last_used_at)).all())  # type: ignore[arg-type]


def mine(session: Session, principal: Principal) -> list[dict[str, Any]]:
    used = _used(session)
    rows = session.scalars(
        select(ApiToken)
        .where(ApiToken.account_id == (principal.account_id or 0))
        .order_by(ApiToken.id.desc())
    )
    return [view(row, used=used.get(row.id)) for row in rows]


def everyones(session: Session, principal: Principal) -> list[dict[str, Any]]:
    """Every token, for an administrator: who holds what, and when it was last used."""
    if not principal.is_admin:
        raise PermissionDenied("Only an administrator sees everyone's tokens.")
    used = _used(session)
    rows = session.execute(
        select(ApiToken, Account.display_name)
        .join(Account, Account.id == ApiToken.account_id)
        .order_by(ApiToken.id.desc())
    )
    return [view(row, name, used.get(row.id)) for row, name in rows]


def revoke(session: Session, principal: Principal, token_id: int) -> None:
    """Stop a token working. Its owner or an administrator may."""
    row = session.get(ApiToken, token_id)
    if row is None or not (principal.is_admin or row.account_id == principal.account_id):
        raise NotFound("There is no such token.")
    if row.revoked_at is None:
        with audit.operation(session, "token.revoke"):
            row.revoked_at = utc_now()
            session.flush()


def authenticate(session: Session, token: str) -> tuple[ApiToken, Account] | None:
    """The token's row and account if it may be used now. Notes the use, now and then."""
    if not token.startswith(PREFIX) or len(token) > 200:
        return None
    row = session.scalars(select(ApiToken).where(ApiToken.token_hash == digest(token))).first()
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_on is not None and row.expires_on < today():
        return None
    account = session.get(Account, row.account_id)
    if account is None or account.status == "disabled":
        return None
    now = utc_now()
    used = session.get(ApiTokenUse, row.id)
    if used is None:
        session.add(ApiTokenUse(token_id=row.id, last_used_at=now))
    elif now - used.last_used_at > USED_EVERY:
        used.last_used_at = now
    return row, account
