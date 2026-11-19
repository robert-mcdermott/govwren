"""The ``govwren`` command line. It runs the same code as the web app."""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

import sqlalchemy.exc

from govwren import PRODUCT_NAME, TAGLINE, __version__
from govwren.access.principal import Principal
from govwren.cli import users
from govwren.config import (
    CONFIG_NAME,
    ENV_CONFIG,
    Config,
    config_warnings,
    example_config_text,
    find_config_path,
    load_config,
)
from govwren.core import log as logs
from govwren.core.errors import GovWrenError
from govwren.db import migrate
from govwren.db.engine import Database
from govwren.demo import build as demo_build
from govwren.events import chain
from govwren.home import DataHome
from govwren.people import accounts
from govwren.program import packs

log = logging.getLogger("govwren.cli")

EXIT_OK = 0
EXIT_ERROR = 1


def _load(args: argparse.Namespace) -> tuple[Config, DataHome]:
    config = load_config(args.config)
    home = DataHome(config.data.home)
    if home.is_initialized():
        logs.configure(args.verbose, quiet=args.quiet, log_dir=home.logs)
    return config, home


def _database(config: Config, *, current: bool = True) -> Database:
    """Open the database, refusing one whose schema is not what this version expects."""
    db = Database(config.database_url)
    if current:
        try:
            migrate.require_current(db.engine)
        except GovWrenError:
            db.dispose()
            raise
    return db


def cmd_init(args: argparse.Namespace) -> int:
    path = find_config_path(args.config)
    if path.exists() and not args.force:
        print(f"Using the configuration at {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(example_config_text(), encoding="utf-8")
        print(f"Wrote {path}")
    config = load_config(path)
    home = DataHome(config.data.home)
    home.create()
    print(f"Data home: {home.root}")
    db = Database(config.database_url)
    try:
        before = migrate.current_revision(db.engine)
        migrate.upgrade(db.engine)
        after = migrate.current_revision(db.engine)
    finally:
        db.dispose()
    kind = "SQLite" if config.uses_sqlite else "PostgreSQL"
    if before == after:
        print(f"Database: {kind}, already at migration {after}")
    else:
        print(f"Database: {kind}, now at migration {after}")
    db = Database(config.database_url)
    try:
        _default_program(db)
        users.first_admin(db, config, args)
    finally:
        db.dispose()
    for warning in config_warnings(config):
        print(f"Note: {warning}")
    print("\nNext: run `govwren doctor`, then `govwren serve`.")
    return EXIT_OK


def _default_program(db: Database) -> None:
    """A new installation gets the default forms and scoring model, so it works at once."""
    principal = Principal.for_command()
    with db.write(principal.actor) as session:
        for part in packs.ensure_defaults(session, principal):
            print(f"Program: loaded the default {part.removeprefix('the ')}")


def _port_free(host: str, port: int) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    config, home = _load(args)
    home.require()
    db = _database(config)  # refuses a schema that is behind
    try:
        with db.read() as session:
            is_demo = demo_build.marker(session) is not None
            if accounts.active_admins(session) == 0:
                raise GovWrenError(
                    "Nobody could sign in: there is no administrator yet. Create one first:\n"
                    "  govwren users add you@example.org --name 'Your Name' --role admin"
                )
    finally:
        db.dispose()
    host = args.host or config.server.host
    port = args.port or config.server.port
    if is_demo:
        if args.demo_on_network:
            os.environ["GOVWREN_DEMO_ON_NETWORK"] = "1"
        elif host not in ("127.0.0.1", "localhost", "::1"):
            raise GovWrenError(
                "This is a demo organization: anyone who can reach it can sign in as any of "
                "its sample people.\nIt listens only on this machine unless you say otherwise: "
                "govwren serve --demo-on-network"
            )
    workers = 1 if args.reload else (args.workers or config.server.workers)
    if not _port_free(host, port):
        raise GovWrenError(
            f"Port {port} on {host} is already in use. Stop what is using it, or pick "
            f"another: govwren serve --port {port + 1}"
        )
    for warning in config_warnings(config):
        log.warning(warning)
    # Each worker process rebuilds the app from the configuration, so name it for them.
    os.environ[ENV_CONFIG] = str(config.path)
    print(f"{PRODUCT_NAME} {__version__} on http://{host}:{port}")
    uvicorn.run(
        "govwren.api.app:create_app_from_env",
        factory=True,
        host=host,
        port=port,
        workers=workers if workers > 1 else None,
        reload=args.reload,
        reload_dirs=[str(Path(__file__).resolve().parent.parent)] if args.reload else None,
        log_level="warning" if args.quiet else "info",
        server_header=False,
    )
    return EXIT_OK


def cmd_jobs(args: argparse.Namespace) -> int:
    from govwren import jobs

    config, home = _load(args)
    home.require()
    db = _database(config)
    try:
        if args.action == "run":
            if args.key:
                result = jobs.run_job(db, config, args.key, force=True)
                results = [result] if result else []
                if result is None:
                    print(f"{args.key} is being run by another process. Nothing was done.")
            else:
                results = jobs.run_due(db, config)
                if not results:
                    print("Nothing is due.")
            for result in results:
                print(f"{result['key']}: {result['summary']}")
            return EXIT_ERROR if any(r["status"] == "failed" for r in results) else EXIT_OK
        jobs.ensure(db)
        with db.read() as session:
            for job in jobs.status(session):
                state = "paused" if not job["enabled"] else job["last_status"] or "not run yet"
                due = f"{job['next_run_at']:%Y-%m-%d %H:%M} UTC" if job["next_run_at"] else "-"
                print(f"{job['key']:<18} {state:<12} next {due}  {job['last_summary'] or ''}")
    finally:
        db.dispose()
    return EXIT_OK


def cmd_mail(args: argparse.Namespace) -> int:
    from govwren import mail

    config, home = _load(args)
    home.require()
    if not config.mail.enabled:
        raise GovWrenError(
            "Email is not set up. Give [mail] a host and a from address in the configuration."
        )
    db = _database(config)
    try:
        if args.action == "test":
            with db.read() as session:
                account = accounts.by_email(session, accounts.normalize_email(args.email))
            if account is None:
                raise GovWrenError(f"There is no account for {args.email}.")
            mail.send_test(db, config, account)
            print(f"Sent a test message to {account.email}.")
        else:
            done = mail.run_once(db, config)
            print(
                f"Email: {done['queued']} notices and {done['digests']} summaries queued, "
                f"{done['sent']} sent, {done['failed']} could not be sent."
            )
            return EXIT_ERROR if done["failed"] else EXIT_OK
    finally:
        db.dispose()
    return EXIT_OK


DEMO_MARKER = ".govwren-demo"


def cmd_demo(args: argparse.Namespace) -> int:
    import shutil
    import time

    root = Path(args.path).expanduser().resolve()
    marker = root / DEMO_MARKER
    if root.exists() and any(root.iterdir()):
        if not marker.is_file():
            raise GovWrenError(f"{root} is not empty and is not a demo. Choose another directory.")
        if not args.force:
            raise GovWrenError(
                f"There is already a demo in {root}. Start it with:\n"
                f"  govwren --config {root / CONFIG_NAME} serve\n"
                "or rebuild it with --force."
            )
        for name in ("var", CONFIG_NAME):  # only what this command made
            target = root / name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
    root.mkdir(parents=True, exist_ok=True)
    marker.write_text("A GovWren demo organization. Safe to delete.\n", encoding="utf-8")
    path = root / CONFIG_NAME
    path.write_text(
        example_config_text().replace("port = 8000", f"port = {args.port}"), encoding="utf-8"
    )
    config = load_config(path, env={})
    DataHome(config.data.home).create()
    started = time.monotonic()
    db = Database(config.database_url)
    try:
        migrate.upgrade(db.engine)
        summary = demo_build.build(db, seed=args.seed, files_dir=DataHome(config.data.home).files)
        with db.engine.connect() as conn:
            report = chain.verify(conn)
    finally:
        db.dispose()
    counts = summary.counts
    print(f"Built the {demo_build.ORGANIZATION} in {root}")
    print(
        f"  {counts.get('units', 0)} units, {counts.get('accounts', 0)} people, "
        f"{counts.get('vendors', 0)} vendors, {counts.get('systems', 0)} AI systems, "
        f"{counts.get('models', 0)} models, {counts.get('datasets', 0)} datasets, "
        f"{counts.get('use_cases', 0)} use cases, {counts.get('reviews', 0)} reviews, "
        f"{counts.get('evidence', 0)} pieces of evidence"
    )
    print(
        f"  {report.events} events of history, which "
        f"{'verify' if report.ok else 'DO NOT verify'}; {time.monotonic() - started:.0f} seconds"
    )
    print("\nStart it, then open the address it prints and choose who to sign in as:")
    print(f"  govwren --config {path} serve")
    return EXIT_OK if report.ok else EXIT_ERROR


def cmd_db_upgrade(args: argparse.Namespace) -> int:
    config, home = _load(args)
    home.require()
    db = _database(config, current=False)
    try:
        before = migrate.current_revision(db.engine)
        if before is not None and before not in migrate.script_revisions():
            migrate.require_current(db.engine)  # explains that the database is newer
        migrate.upgrade(db.engine)
        after = migrate.current_revision(db.engine)
        print(
            f"Already at migration {after}." if before == after else f"Upgraded {before} → {after}."
        )
        _default_program(db)
    finally:
        db.dispose()
    return EXIT_OK


def cmd_db_current(args: argparse.Namespace) -> int:
    config, _ = _load(args)
    db = _database(config, current=False)
    try:
        current = migrate.current_revision(db.engine)
    finally:
        db.dispose()
    head = migrate.head_revision()
    print(f"Database: {current or 'empty'}")
    print(f"This version of {PRODUCT_NAME}: {head}")
    return EXIT_OK if current == head else EXIT_ERROR


def cmd_program_export(args: argparse.Namespace) -> int:
    config, _ = _load(args)
    db = _database(config)
    try:
        with db.read() as session:
            text = json.dumps(packs.export(session), indent=2, ensure_ascii=False) + "\n"
    finally:
        db.dispose()
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        sys.stdout.write(text)
    return EXIT_OK


def cmd_program_import(args: argparse.Namespace) -> int:
    config, _ = _load(args)
    try:
        pack = json.loads(Path(args.file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GovWrenError(f"{args.file} could not be read as a pack: {exc}") from exc
    found = packs.problems(pack)
    if found:
        print(f"{args.file} was not loaded. {len(found)} problem(s):", file=sys.stderr)
        for problem in found:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_ERROR
    if args.check:
        print(f"{args.file} is a valid program pack. Nothing was changed.")
        return EXIT_OK
    db = _database(config)
    principal = Principal.for_command()
    try:
        with db.write(principal.actor) as session:
            report = packs.apply(session, principal, pack)
    finally:
        db.dispose()
    for key, outcome in report["forms"].items():
        print(f"Form {key}: {outcome}")
    print(f"Scoring model: {report['scoring_model']}")
    print(f"Routing rules: {report['review']}")
    if report["vocabularies"]:
        print(f"Vocabularies changed: {', '.join(report['vocabularies'])}")
    return EXIT_OK


def cmd_dossier_make(args: argparse.Namespace) -> int:
    from govwren.insight import dossier
    from govwren.inventory.registry import find_any

    config, home = _load(args)
    db = _database(config)
    principal = Principal.for_command()
    try:
        with db.read() as session:
            document = dossier.build(session, principal, *find_any(session, args.ref))
            data = dossier.package(session, home.files, document)
    finally:
        db.dispose()
    out = Path(args.out or f"{document['record']['ref']}-dossier.zip")
    out.write_bytes(data)
    print(f"Wrote {out}: {len(document['evidence'])} pieces of evidence, "
          f"{len(document['history'])} events of history.")  # fmt: skip
    return EXIT_OK


def cmd_dossier_verify(args: argparse.Namespace) -> int:
    from govwren.insight import dossier

    try:
        data = Path(args.file).read_bytes()
    except OSError as exc:
        raise GovWrenError(f"{args.file} could not be read: {exc}") from exc
    if args.history:
        config, _ = _load(args)
        db = _database(config)
        try:
            with db.read() as session:
                ok, lines = dossier.check(data, session)
        finally:
            db.dispose()
    else:
        ok, lines = dossier.check(data)
    for line in lines:
        print(line, file=sys.stdout if ok else sys.stderr)
    return EXIT_OK if ok else EXIT_ERROR


def cmd_register_build(args: argparse.Namespace) -> int:
    from govwren.insight import register

    config, _ = _load(args)
    db = _database(config)
    try:
        with db.read() as session:
            count = register.write(session, Path(args.out))
    finally:
        db.dispose()
    print(f"Wrote the register to {args.out}: {count} uses, an index, and a stylesheet.")
    return EXIT_OK


def cmd_backup(args: argparse.Namespace) -> int:
    from govwren import backup

    config, home = _load(args)
    home.require()
    db = _database(config)
    out = Path(args.out or f"govwren-backup-{datetime.now():%Y%m%d-%H%M%S}.tar.gz")
    try:
        report = backup.create(db.engine, home, out)
    finally:
        db.dispose()
    print(
        f"Wrote {out}: {report.rows} rows in {report.tables} tables, {report.files} files, "
        f"{report.events} events of history, at migration {report.revision}."
    )
    return EXIT_OK


def cmd_restore(args: argparse.Namespace) -> int:
    from govwren import backup

    config, home = _load(args)
    home.create()  # a restore may be the first thing done on a new server
    db = _database(config, current=False)
    try:
        report = backup.restore(db.engine, home, Path(args.file))
        behind = not migrate.is_current(db.engine)
    finally:
        db.dispose()
    print(
        f"Restored {report.rows} rows in {report.tables} tables and {report.files} files. "
        f"The history holds: {report.events} events verify."
    )
    if behind:
        print(f"The backup was at migration {report.revision}. Now run: govwren db upgrade")
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    config, _ = _load(args)
    db = _database(config)
    try:
        with db.engine.connect() as conn:
            report = chain.verify(conn)
    finally:
        db.dispose()
    if report.ok:
        print(f"The history holds: {report.events} events, each following the last.")
        print(f"Head: {report.head}")
        return EXIT_OK
    print(f"The history is broken at event {report.broken_at}: {report.reason}.", file=sys.stderr)
    print(f"{report.events} events before it verify.", file=sys.stderr)
    return EXIT_ERROR


def cmd_doctor(args: argparse.Namespace) -> int:
    from govwren.cli import doctor

    checks = doctor.run(args.config)
    width = max(len(check.name) for check in checks)
    for check in checks:
        print(f"{doctor.MARKS[check.status]} {check.name.ljust(width)}  {check.detail}")
    failed = sum(check.status == doctor.FAIL for check in checks)
    warned = sum(check.status == doctor.WARN for check in checks)
    print()
    if failed:
        print(f"{failed} problem{'s' if failed != 1 else ''} to fix.")
        return EXIT_ERROR
    print(
        "Everything checks out." if not warned else f"Working, with {warned} thing(s) to look at."
    )
    return EXIT_OK


def _users(action: str) -> Callable[[argparse.Namespace], int]:
    def handler(args: argparse.Namespace) -> int:
        config, _ = _load(args)
        db = _database(config)
        try:
            if action == "disable":
                return users.set_status(db, args, "disabled")
            if action == "enable":
                return users.set_status(db, args, "active")
            run = {
                "add": users.add,
                "list": users.list_,
                "reset-password": users.reset_password,
                "roles": users.roles,
            }[action]
            return run(db, args)
        finally:
            db.dispose()

    return handler


ROLE_HELP = (
    "a role: admin, governance, auditor, reviewer, reviewer=function:KEY, or "
    "steward=unit:CODE (may be repeated)"
)
STDIN_HELP = "read the password from standard input instead of asking"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="govwren",
        description=f"{PRODUCT_NAME}: {TAGLINE}",
        epilog="Documentation: the docs/ folder of the repository.",
    )
    parser.add_argument("--version", action="version", version=f"{PRODUCT_NAME} {__version__}")
    parser.add_argument(
        "-c",
        "--config",
        metavar="FILE",
        help=f"the configuration file (default: ${ENV_CONFIG}, then ./{CONFIG_NAME})",
    )
    noise = parser.add_mutually_exclusive_group()
    noise.add_argument("-v", "--verbose", action="count", default=0, help="say more")
    noise.add_argument("-q", "--quiet", action="store_true", help="say only what went wrong")
    commands = parser.add_subparsers(title="commands", metavar="COMMAND")

    init = commands.add_parser(
        "init",
        help="set up a new installation",
        description="Write a configuration file if there is none, create the data home, "
        "create or upgrade the database, and create the first administrator if there is "
        "none. Safe to run again.",
    )
    init.add_argument(
        "--force", action="store_true", help="overwrite an existing configuration file"
    )
    init.add_argument(
        "--admin-email", metavar="EMAIL", help="create the first administrator with this address"
    )
    init.add_argument("--admin-name", metavar="NAME", help="the first administrator's name")
    init.add_argument("--password-stdin", action="store_true", help=STDIN_HELP)
    init.set_defaults(handler=cmd_init)

    serve = commands.add_parser(
        "serve",
        help="run the web server",
        description="Run GovWren's web server. It refuses to start on a database whose schema "
        "is behind; run `govwren db upgrade` first.",
    )
    serve.add_argument("--host", help="address to listen on (default: from the configuration)")
    serve.add_argument(
        "--port", type=int, help="port to listen on (default: from the configuration)"
    )
    serve.add_argument(
        "--workers", type=int, help="server processes (default: from the configuration)"
    )
    serve.add_argument(
        "--reload", action="store_true", help="restart when the code changes (development)"
    )
    serve.add_argument(
        "--demo-on-network",
        action="store_true",
        help="let a demo organization listen beyond this machine (anyone who reaches it can "
        "sign in as its sample people)",
    )
    serve.set_defaults(handler=cmd_serve)

    demo = commands.add_parser(
        "demo",
        help="build a fictional organization to explore",
        description="Build the Alderpoint Institute for Medical Research, a fictional "
        "organization with thirty months of history, in its own directory. Everything in it "
        "is made by the same code the app uses. Start it with the command it prints.",
    )
    demo.add_argument(
        "path",
        nargs="?",
        default="demo",
        metavar="PATH",
        help="where to build it (default: ./demo)",
    )
    demo.add_argument(
        "--seed", type=int, default=1, help="a different number gives a different Alderpoint"
    )
    demo.add_argument(
        "--port", type=int, default=8010, help="the port its server will use (default: 8010)"
    )
    demo.add_argument("--force", action="store_true", help="rebuild a demo that is already there")
    demo.set_defaults(handler=cmd_demo)

    db = commands.add_parser(
        "db", help="look after the database schema", description="Look after the database schema."
    )
    db_commands = db.add_subparsers(title="commands", metavar="COMMAND")
    upgrade = db_commands.add_parser(
        "upgrade",
        help="bring the schema up to this version",
        description="Apply any migrations the database has not had. Export first: "
        "an upgrade cannot be undone except by restoring.",
    )
    upgrade.set_defaults(handler=cmd_db_upgrade)
    current = db_commands.add_parser(
        "current",
        help="show which migration the database is at",
        description="Show which migration the database is at, and which this version expects. "
        "Exits with 1 when they differ.",
    )
    current.set_defaults(handler=cmd_db_current)
    db.set_defaults(handler=lambda _args: db.print_help() or EXIT_OK)

    people = commands.add_parser(
        "users",
        help="manage accounts from the command line",
        description="Manage accounts from the command line: for setting up, and for getting "
        "back in when nobody can sign in. Everyday account management is in the app, under "
        "Admin. Changes made here are recorded in the history as made at the command line.",
    )
    people_commands = people.add_subparsers(title="commands", metavar="COMMAND")
    add = people_commands.add_parser(
        "add",
        help="add an account",
        description="Add an account. It asks for a password unless --password-stdin or "
        "--invite is given.",
    )
    add.add_argument("email", metavar="EMAIL", help="the email address the person signs in with")
    add.add_argument("--name", required=True, help="the person's name")
    add.add_argument("--title", help="their job title")
    add.add_argument("--role", action="append", metavar="ROLE", help=ROLE_HELP)
    add.add_argument(
        "--unit",
        action="append",
        metavar="CODE",
        help="a unit they work in, by code (may be repeated)",
    )
    secret = add.add_mutually_exclusive_group()
    secret.add_argument("--password-stdin", action="store_true", help=STDIN_HELP)
    secret.add_argument(
        "--invite",
        action="store_true",
        help="add them without a password: they can be named on records now, and sign in "
        "once they are given a password or use single sign-on",
    )
    add.set_defaults(handler=_users("add"))
    listing = people_commands.add_parser(
        "list", help="list accounts", description="List every account with its status and roles."
    )
    listing.set_defaults(handler=_users("list"))
    disable = people_commands.add_parser(
        "disable",
        help="stop an account signing in",
        description="Stop an account signing in and end its sessions. Its records and history "
        "are kept. The last active administrator cannot be disabled.",
    )
    enable = people_commands.add_parser(
        "enable",
        help="let a disabled account sign in again",
        description="Let a disabled account sign in again.",
    )
    for name, command in (("disable", disable), ("enable", enable)):
        command.add_argument("email", metavar="EMAIL", help="the account's email address")
        command.set_defaults(handler=_users(name))
    reset = people_commands.add_parser(
        "reset-password",
        help="give an account a new password",
        description="Give an account a new password and end its sessions.",
    )
    reset.add_argument("email", metavar="EMAIL", help="the account's email address")
    reset.add_argument("--password-stdin", action="store_true", help=STDIN_HELP)
    reset.set_defaults(handler=_users("reset-password"))
    role_command = people_commands.add_parser(
        "roles",
        help="show or set an account's roles",
        description="Show an account's roles, or with --set replace the roles granted in "
        "GovWren. Roles mapped from an identity provider are left alone. The last active "
        "administrator cannot lose that role.",
    )
    role_command.add_argument("email", metavar="EMAIL", help="the account's email address")
    role_command.add_argument(
        "--set", nargs="*", metavar="ROLE", help=ROLE_HELP + "; with none, removes every role"
    )
    role_command.set_defaults(handler=_users("roles"))
    people.set_defaults(handler=lambda _args: people.print_help() or EXIT_OK)

    scheduled = commands.add_parser(
        "jobs",
        help="list scheduled work, or run what is due",
        description="GovWren does some work by itself: it opens periodic reviews, marks "
        "approvals that have run out, sends reminders, and sends email. The server does this "
        "while it runs. With no command, this lists each job and when it is next due.",
    )
    job_commands = scheduled.add_subparsers(title="commands", metavar="COMMAND")
    job_run = job_commands.add_parser(
        "run",
        help="run the jobs that are due, or one job now",
        description="Run every job that is due, once, and exit. Give a job's name to run "
        "that one now whether or not it is due. Safe to run while the server is up: a job "
        "is never run by two processes at once. Exits with 1 if a job failed.",
    )
    job_run.add_argument("key", metavar="JOB", nargs="?", help="the job to run now")
    job_run.set_defaults(handler=cmd_jobs, action="run")
    scheduled.set_defaults(handler=cmd_jobs, action="list")

    mailer = commands.add_parser(
        "mail",
        help="send waiting email, or test the mail settings",
        description="The server sends email by itself while it runs. These commands are for "
        "testing the settings, and for sending what is waiting when the server is not running.",
    )
    mail_commands = mailer.add_subparsers(title="commands", metavar="COMMAND")
    mail_run = mail_commands.add_parser(
        "run",
        help="queue and send what is waiting, once",
        description="Turn waiting notices into messages, put together daily summaries if it "
        "is time, and send what is in the outbox. Exits with 1 if anything could not be sent.",
    )
    mail_run.set_defaults(handler=cmd_mail, action="run")
    mail_test = mail_commands.add_parser(
        "test",
        help="send a test message to one account",
        description="Send one message now, to the address of an existing account, and say "
        "whether the mail server accepted it.",
    )
    mail_test.add_argument("email", metavar="EMAIL", help="the account to send it to")
    mail_test.set_defaults(handler=cmd_mail, action="test")
    mailer.set_defaults(handler=lambda _args: mailer.print_help() or EXIT_OK)

    program = commands.add_parser(
        "program",
        help="export or load the governance program as a file",
        description="The governance program (forms, the scoring model, and vocabularies) "
        "can be written out as one file, kept under version control, reviewed, and loaded "
        "into another installation.",
    )
    program_commands = program.add_subparsers(title="commands", metavar="COMMAND")
    exporting = program_commands.add_parser(
        "export",
        help="write the program out as a pack",
        description="Write the published forms, the scoring model, and every vocabulary as "
        "one program pack.",
    )
    exporting.add_argument("--out", metavar="FILE", help="write to this file instead of the screen")
    exporting.set_defaults(handler=cmd_program_export)
    importing = program_commands.add_parser(
        "import",
        help="load a program pack",
        description="Load a program pack. The whole file is checked first, and nothing is "
        "loaded if anything is wrong. What differs from the published program becomes a new "
        "version; earlier versions are kept, so past requests still show the form they were "
        "answered on.",
    )
    importing.add_argument("file", metavar="FILE", help="the pack to load")
    importing.add_argument("--check", action="store_true", help="check the file and change nothing")
    importing.set_defaults(handler=cmd_program_import)
    program.set_defaults(handler=lambda _args: program.print_help() or EXIT_OK)

    dossier = commands.add_parser(
        "dossier",
        help="make or check the complete package for one record",
        description="A dossier is everything the record holds about one thing, as a zip with "
        "a manifest that lists each file with its SHA-256.",
    )
    dossier_commands = dossier.add_subparsers(dest="dossier_command", metavar="<command>")
    making = dossier_commands.add_parser(
        "make",
        help="write the dossier of a record",
        description="Write the dossier of one record as a zip: the record as data and as a "
        "page to print, its evidence files, and a manifest.",
    )
    making.add_argument("ref", help="the record's reference, such as UC-0042")
    making.add_argument(
        "--out", metavar="FILE", help="where to write it (default: REF-dossier.zip)"
    )
    making.set_defaults(handler=cmd_dossier_make)
    checking = dossier_commands.add_parser(
        "verify",
        help="check a dossier against its manifest",
        description="Recompute the SHA-256 of every file in a dossier and compare it with the "
        "manifest. Exits with 1 if a file was altered, added, or removed. Needs no "
        "installation unless --history is given.",
    )
    checking.add_argument("file", help="the dossier, a zip")
    checking.add_argument(
        "--history",
        action="store_true",
        help="also check that the event the manifest names is in this installation's history",
    )
    checking.set_defaults(handler=cmd_dossier_verify)
    dossier.set_defaults(handler=lambda _args: dossier.print_help() or EXIT_OK)

    public = commands.add_parser(
        "register",
        help="publish the transparency register",
        description="The transparency register is the set of approved uses governance has "
        "chosen to publish, as plain pages for any web server.",
    )
    public_commands = public.add_subparsers(dest="register_command", metavar="<command>")
    building = public_commands.add_parser(
        "build",
        help="write the register's pages into a directory",
        description="Write an index, a page for each use on the register whose approval is "
        "in force, and a stylesheet. Pages for uses no longer on the register are removed. "
        "Run it on a schedule to keep a published copy current.",
    )
    building.add_argument("--out", metavar="DIR", required=True, help="where to write the pages")
    building.set_defaults(handler=cmd_register_build)
    public.set_defaults(handler=lambda _args: public.print_help() or EXIT_OK)

    saving = commands.add_parser(
        "backup",
        help="write the whole installation to one file",
        description="Write every table, every evidence and brand file, and a manifest to one "
        "gzipped tar. It can be made while the server is running. The file does not depend on "
        "the kind of database, so it restores into SQLite or PostgreSQL. It holds everything "
        "in the installation: keep it as carefully as the database itself.",
    )
    saving.add_argument(
        "--out", metavar="FILE", help="where to write it (default: govwren-backup-DATE.tar.gz)"
    )
    saving.set_defaults(handler=cmd_backup)
    loading = commands.add_parser(
        "restore",
        help="load a backup into an empty installation",
        description="Load a backup into the configured database and data home. The database "
        "must hold no accounts and no history: nothing is ever overwritten. The history is "
        "verified once it is loaded. To move between SQLite and PostgreSQL, back up, point "
        "the configuration at the new database, and restore.",
    )
    loading.add_argument("file", help="the backup, a .tar.gz written by govwren backup")
    loading.set_defaults(handler=cmd_restore)

    verify = commands.add_parser(
        "verify",
        help="check that the history has not been altered",
        description="Recompute the hash chain over every event in the history and report the "
        "first one that does not hold. Exits with 1 if the history is broken.",
    )
    verify.set_defaults(handler=cmd_verify)

    doctor = commands.add_parser(
        "doctor",
        help="check that this installation is healthy",
        description="Check the configuration, the data home, the database and its schema, "
        "and the history. Exits with 1 if anything must be fixed.",
    )
    doctor.set_defaults(handler=cmd_doctor)

    parser.set_defaults(handler=lambda _args: parser.print_help() or EXIT_OK)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logs.configure(args.verbose, quiet=args.quiet)
    try:
        return int(args.handler(args) or EXIT_OK)
    except GovWrenError as exc:
        print(f"govwren: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.InterfaceError) as exc:
        reason = str(getattr(exc, "orig", exc)).strip().splitlines()[0]
        print(f"govwren: the database cannot be reached: {reason}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130
