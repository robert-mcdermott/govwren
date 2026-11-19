"""The ``govwren`` command line. It runs the same code as the web app."""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
from collections.abc import Callable, Sequence
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
        if packs.ensure_defaults(session, principal):
            print("Program: loaded the default intake form and scoring model")


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
            if accounts.active_admins(session) == 0:
                raise GovWrenError(
                    "Nobody could sign in: there is no administrator yet. Create one first:\n"
                    "  govwren users add you@example.org --name 'Your Name' --role admin"
                )
    finally:
        db.dispose()
    host = args.host or config.server.host
    port = args.port or config.server.port
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
    if report["vocabularies"]:
        print(f"Vocabularies changed: {', '.join(report['vocabularies'])}")
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
    serve.set_defaults(handler=cmd_serve)

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
