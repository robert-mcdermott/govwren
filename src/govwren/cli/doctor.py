"""``govwren doctor``: is this installation healthy?"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass

from sqlalchemy import text

from govwren.config import Config, config_warnings, load_config
from govwren.core.errors import GovWrenError
from govwren.db import migrate
from govwren.db.engine import Database
from govwren.events import chain
from govwren.home import DataHome

OK, WARN, FAIL = "ok", "warn", "fail"
MARKS = {OK: "✓", WARN: "!", FAIL: "✗"}

SQLITE_TRIGGERS = "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'event'"
POSTGRES_TRIGGERS = (
    "SELECT tgname FROM pg_trigger WHERE tgrelid = 'event'::regclass AND NOT tgisinternal"
)
EXPECTED_TRIGGERS = {
    "sqlite": {"event_no_update", "event_no_delete"},
    "postgresql": {"event_no_change", "event_no_truncate"},
}


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def run(config_path: str | None = None, *, production: bool = False) -> list[Check]:
    """Every check. ``production`` adds what matters once people depend on the installation."""
    checks = [_python()]
    try:
        config = load_config(config_path)
    except GovWrenError as exc:
        return [*checks, Check("Configuration", FAIL, str(exc).splitlines()[0])]
    checks.append(Check("Configuration", OK, str(config.path)))
    checks += [Check("Advice", WARN, warning) for warning in config_warnings(config)]

    home = DataHome(config.data.home)
    if not home.is_initialized():
        return [*checks, Check("Data home", FAIL, f"{home.root} is not set up; run `govwren init`")]
    checks.append(_disk(home))
    checks += _database(config)
    if config.sso.enabled:
        checks.append(_sso(config))
    if config.mail.enabled:
        checks.append(_mail(config))
    if production and not any(check.status == FAIL for check in checks):
        checks += for_production(config, home)
    return checks


def for_production(config: Config, home: DataHome) -> list[Check]:
    """What to look at before, and while, people depend on this installation."""
    import stat
    from datetime import timedelta

    from sqlalchemy import select

    from govwren import backup
    from govwren.core.clock import utc_now
    from govwren.db.models import Job
    from govwren.demo import build as demo
    from govwren.people import accounts

    checks = []
    base = config.server.base_url
    if base.startswith("https://"):
        checks.append(Check("Address", OK, base))
    else:
        checks.append(
            Check(
                "Address",
                FAIL,
                "set [server] base_url to the https address people use, and serve it over TLS",
            )
        )
    if config.uses_sqlite:
        checks.append(
            Check(
                "Database for production",
                WARN,
                "SQLite suits a small team on one server. For many people at once, or more "
                "than one server process, move to PostgreSQL",
            )
        )
    else:
        checks.append(Check("Database for production", OK, "PostgreSQL"))
    db = Database(config.database_url)
    try:
        with db.read() as session:
            is_demo = demo.marker(session) is not None
            admins = accounts.active_admins(session)
            ran = session.scalars(
                select(Job.last_finished_at).where(Job.last_finished_at.is_not(None))
            ).all()
    finally:
        db.dispose()
    if is_demo:
        checks.append(
            Check("Demo", FAIL, "this is a demo organization: anyone can sign in as its people")
        )
    if admins >= 2:
        checks.append(Check("Administrators", OK, f"{admins} active"))
    else:
        checks.append(
            Check(
                "Administrators",
                WARN,
                "there is one administrator. Give a second person the role, so that the "
                "installation can be managed if the first is away",
            )
        )
    if config.sso.enabled:
        checks.append(Check("Sign-in", OK, "single sign-on"))
    else:
        checks.append(
            Check(
                "Sign-in",
                WARN,
                "people sign in with passwords kept here. Connect single sign-on so that "
                "leavers lose access with their organization account",
            )
        )
    if not config.mail.enabled:
        checks.append(
            Check(
                "Email for production",
                WARN,
                "not set up: nobody is told by email of work that waits for them",
            )
        )
    now = utc_now()
    newest = max(ran) if ran else None
    if not config.server.scheduler:
        checks.append(
            Check(
                "Scheduled work",
                WARN,
                "[server] scheduler is off. Run `govwren jobs run` on a schedule, or reviews "
                "will not be opened and approvals will not lapse",
            )
        )
    elif newest is None or now - newest > timedelta(minutes=15):
        since = (
            "has not run yet"
            if newest is None
            else f"has not run since {newest:%Y-%m-%d %H:%M} UTC"
        )
        checks.append(Check("Scheduled work", WARN, f"{since}. It runs while the server is up"))
    else:
        checks.append(Check("Scheduled work", OK, "ran within the last fifteen minutes"))
    saved = backup.last(home)
    if saved is None:
        checks.append(
            Check(
                "Backup",
                WARN,
                "`govwren backup` has never been run here. Ignore this if you back up the "
                "database and the data home another way",
            )
        )
    else:
        days = (now - saved["at"]).days
        checks.append(
            Check(
                "Backup",
                OK if days <= 2 else WARN,
                f"last made {saved['at']:%Y-%m-%d %H:%M} UTC"
                + ("" if days <= 2 else f", {days} days ago"),
            )
        )
    try:
        open_to_others = bool(stat.S_IMODE(home.root.stat().st_mode) & 0o077)
    except OSError:
        open_to_others = False
    if open_to_others:
        checks.append(
            Check(
                "Data home access",
                WARN,
                f"other accounts on this machine can read {home.root}. Run: chmod 700 {home.root}",
            )
        )
    else:
        checks.append(Check("Data home access", OK, "only the account that runs GovWren"))
    return checks


def _sso(config: Config) -> Check:
    """Can the identity provider be read, and is the client secret where it should be?"""
    import os

    from govwren.auth import oidc

    client = oidc.Client(config.sso)
    try:
        client.metadata()
        client.keys()
    except GovWrenError as exc:
        return Check("Single sign-on", FAIL, str(exc))
    if not os.environ.get(config.sso.client_secret_env):
        return Check(
            "Single sign-on",
            FAIL,
            f"the client secret is not set: put it in {config.sso.client_secret_env}",
        )
    if not config.server.base_url:
        return Check(
            "Single sign-on",
            WARN,
            "set [server] base_url, so that the redirect address does not depend on how "
            "each request arrives",
        )
    return Check("Single sign-on", OK, config.sso.issuer)


def _mail(config: Config) -> Check:
    """Can the mail server be reached and signed in to? Nothing is sent."""
    from govwren import mail

    try:
        mail.SmtpSender(config.mail).check()
    except GovWrenError as exc:
        return Check("Email", FAIL, str(exc))
    return Check(
        "Email", OK, f"{config.mail.host}:{config.mail.port} as {config.mail.from_address}"
    )


def _python() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    return Check("Python", OK, version)


def _disk(home: DataHome) -> Check:
    free = shutil.disk_usage(home.root).free
    detail = f"{home.root} ({free / 1e9:.1f} GB free)"
    return Check("Data home", WARN if free < 1e9 else OK, detail)


def _database(config: Config) -> list[Check]:
    kind = "SQLite" if config.uses_sqlite else "PostgreSQL"
    db = None
    try:
        db = Database(config.database_url)
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        if db is not None:
            db.dispose()
        reason = str(getattr(exc, "orig", exc)).strip().splitlines()[0]
        return [Check("Database", FAIL, f"{kind} cannot be reached: {reason}")]
    try:
        checks = [Check("Database", OK, kind)]
        try:
            migrate.require_current(db.engine)
        except GovWrenError as exc:
            return [*checks, Check("Schema", FAIL, str(exc))]
        checks.append(Check("Schema", OK, f"migration {migrate.current_revision(db.engine)}"))
        with db.engine.connect() as conn:
            query = SQLITE_TRIGGERS if db.dialect == "sqlite" else POSTGRES_TRIGGERS
            present = {row[0] for row in conn.execute(text(query))}
            missing = EXPECTED_TRIGGERS[db.dialect] - present
            if missing:
                checks.append(
                    Check(
                        "History guard",
                        FAIL,
                        "the database no longer refuses changes to the history "
                        f"(missing: {', '.join(sorted(missing))})",
                    )
                )
            else:
                checks.append(Check("History guard", OK, "the database refuses changes to events"))
            report = chain.verify(conn)
        if report.ok:
            checks.append(Check("History", OK, f"{report.events} events verify"))
        else:
            checks.append(
                Check("History", FAIL, f"broken at event {report.broken_at}: {report.reason}")
            )
        return checks
    finally:
        db.dispose()
