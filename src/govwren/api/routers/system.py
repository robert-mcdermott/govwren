"""Health and what the web app needs before anyone signs in."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from govwren import TAGLINE, __version__, jobs, mail
from govwren.access.policy import current
from govwren.api.common import database, envelope, reading
from govwren.api.problems import problem
from govwren.db import migrate
from govwren.demo.build import marker as demo_marker
from govwren.people import accounts
from govwren.program import branding

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health/live", summary="Is the server process running?")
def live() -> dict[str, Any]:
    return envelope({"status": "ok"})


@router.get("/health/ready", summary="Can the server do its work?")
def ready(request: Request) -> JSONResponse:
    """The database answers and its schema is the one this version expects."""
    engine = database(request).engine
    state = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        if not migrate.is_current(engine):
            state = "outdated"
    except Exception:
        state = "unreachable"
    status = "ok" if state == "ok" else "degraded"
    body = envelope({"status": status, "database": state, "version": __version__})
    return JSONResponse(body, status_code=200 if status == "ok" else 503)


@router.get("/meta", summary="The product's name, version, and branding")
def meta(request: Request) -> dict[str, Any]:
    """What the web app needs before anyone signs in."""
    sso = request.app.state.config.sso
    with reading(request) as session:
        brand = branding.public_view(branding.load(session))
        demo = demo_marker(session)
    return envelope(
        {
            "product": {"name": brand["product_name"], "tagline": TAGLINE},
            "version": __version__,
            "branding": brand,
            "palettes": list(branding.PALETTES),
            "sso": {"label": sso.label, "local_sign_in": sso.local_sign_in}
            if sso.enabled
            else None,
            "mail": request.app.state.config.mail.enabled,
            # Absent unless one is configured, so that nothing in the app mentions it.
            "assistant": request.app.state.config.assistant.enabled,
            # A demo says so, and names the sample people its sign-in page offers.
            "demo": {"built_on": demo["built_on"], "accounts": demo["accounts"]} if demo else None,
        }
    )


@router.get("/jobs", summary="Scheduled work, and how its recent runs went")
def jobs_status(request: Request) -> dict[str, Any]:
    jobs.ensure(request.app.state.db)
    with reading(request) as session:
        return envelope(jobs.status(session))


@router.post("/jobs/{key}/run", summary="Run one job now")
def jobs_run(key: str, request: Request) -> Any:
    """Runs the job at once, whether or not it is due, and says what it did. If another
    process is running it at this moment, nothing is run and the answer says so."""
    if key not in jobs.JOBS:
        return problem(404, f"There is no job {key}.", instance=request.url.path)
    result = jobs.run_job(request.app.state.db, request.app.state.config, key, force=True)
    if result is None:
        return problem(409, "That job is running at the moment.", instance=request.url.path)
    return envelope(result)


@router.put("/jobs/{key}", summary="Pause or resume one job")
def jobs_set(key: str, body: dict[str, Any], request: Request) -> Any:
    if key not in jobs.JOBS:
        return problem(404, f"There is no job {key}.", instance=request.url.path)
    jobs.set_enabled(request.app.state.db, key, bool(body.get("enabled", True)))
    with reading(request) as session:
        return envelope(next(job for job in jobs.status(session) if job["key"] == key))


@router.get("/mail", summary="How email is set up, and how it is doing")
def mail_status(request: Request) -> dict[str, Any]:
    with reading(request) as session:
        return envelope(mail.status(session, request.app.state.config))


@router.post("/mail/test", summary="Send yourself a test message")
def mail_test(request: Request) -> Any:
    """Sends one message to your own address, now, and says whether the mail server took it."""
    principal = current(request)
    with reading(request) as session:
        account = accounts.get(session, principal.account_id or 0)
    try:
        mail.send_test(
            request.app.state.db,
            request.app.state.config,
            account,
            getattr(request.app.state, "mail_sender", None),
        )
    except mail.MailError as exc:
        return problem(502, str(exc), instance=request.url.path)
    return envelope({"sent_to": account.email})


@router.get("/operations", summary="How the installation is running")
def operations(request: Request) -> dict[str, Any]:
    """One page for whoever keeps the server: the checks `govwren doctor --production`
    makes, with scheduled work, email, webhooks, the last backup, and the size of things."""
    from sqlalchemy import func, select

    from govwren import backup
    from govwren.cli import doctor
    from govwren.db.models import (
        Account,
        Event,
        StoredFile,
        UseCase,
        Webhook,
        WebhookDelivery,
        WebhookState,
    )

    config, home = request.app.state.config, request.app.state.home
    checks = [doctor._disk(home), *doctor._database(config)]
    checks += [
        doctor.Check("Advice", doctor.WARN, text_) for text_ in doctor.config_warnings(config)
    ]
    checks += doctor.for_production(config, home)
    saved = backup.last(home)
    with reading(request) as session:

        def count(model: Any, *where: Any) -> int:
            return session.execute(
                select(func.count()).select_from(model).where(*where)
            ).scalar_one()

        return envelope(
            {
                "version": __version__,
                "database": "SQLite" if config.uses_sqlite else "PostgreSQL",
                "revision": migrate.current_revision(database(request).engine),
                "workers": config.server.workers,
                "checks": [
                    {"name": check.name, "status": check.status, "detail": check.detail}
                    for check in checks
                ],
                "jobs": [
                    {
                        key: job[key]
                        for key in (
                            "key",
                            "label",
                            "enabled",
                            "last_finished_at",
                            "last_status",
                            "last_summary",
                        )
                    }
                    for job in jobs.status(session, runs=0)
                ],
                "mail": {
                    key: value
                    for key, value in mail.status(session, config).items()
                    if key in ("enabled", "waiting", "sent", "failed", "last_error")
                },
                "webhooks": {
                    "set_up": count(Webhook),
                    "paused": count(WebhookState, WebhookState.paused.is_(True)),
                    "waiting": count(WebhookDelivery, WebhookDelivery.status == "queued"),
                    "given_up": count(WebhookDelivery, WebhookDelivery.status == "failed"),
                },
                "backup": {"at": saved["at"], "file": saved["file"]} if saved else None,
                "size": {
                    "accounts": count(Account),
                    "use_cases": count(UseCase),
                    "events": count(Event),
                    "files": count(StoredFile),
                    "file_bytes": session.execute(select(func.sum(StoredFile.size))).scalar() or 0,
                },
            }
        )
