"""Backup and restore: the whole installation as one file.

A backup is a gzipped tar holding every table as lines of JSON, every evidence and brand
file, and a manifest. It does not depend on the kind of database it came from, so the same
file restores into SQLite or PostgreSQL: that is also how an installation moves from one
to the other. The history is carried row for row, and is verified after a restore.
"""

from __future__ import annotations

import base64
import io
import json
import os
import tarfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Date, DateTime, LargeBinary, MetaData, Table, func, insert, select, text
from sqlalchemy.engine import Connection, Engine

from govwren import __version__
from govwren.core.clock import utc_now
from govwren.core.errors import GovWrenError
from govwren.db import migrate
from govwren.events import chain
from govwren.home import DataHome

FORMAT = "govwren-backup/1"
MANIFEST = "manifest.json"
LAST = "last-backup.json"
SKIP = {"alembic_version"}
BATCH = 500


@dataclass(frozen=True)
class Report:
    tables: int
    rows: int
    files: int
    revision: str
    events: int


def _tables(conn: Connection) -> list[Table]:
    """Every table as the database has it, parents before the rows that point at them."""
    metadata = MetaData()
    metadata.reflect(conn)
    return [table for table in metadata.sorted_tables if table.name not in SKIP]


def _kind(column: Any) -> str:
    if isinstance(column.type, DateTime):
        return "datetime"
    if isinstance(column.type, Date):
        return "date"
    if isinstance(column.type, LargeBinary):
        return "bytes"
    return "plain"


def _out(value: Any) -> Any:
    if isinstance(value, datetime):
        stamp = value if value.tzinfo else value.replace(tzinfo=UTC)
        return stamp.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes | memoryview):
        return base64.b64encode(bytes(value)).decode()
    return value


def _in(value: Any, kind: str, naive: bool) -> Any:
    if value is None:
        return None
    if kind == "datetime":
        stamp = datetime.fromisoformat(value)
        return stamp.replace(tzinfo=None) if naive else stamp
    if kind == "date":
        return date.fromisoformat(value)
    if kind == "bytes":
        return base64.b64decode(value)
    return value


def _add(archive: tarfile.TarFile, name: str, data: bytes, when: float) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = int(when)
    info.mode = 0o600
    archive.addfile(info, io.BytesIO(data))


def _files(root: Path) -> Iterator[Path]:
    if root.is_dir():
        yield from sorted(path for path in root.rglob("*") if path.is_file())


def create(engine: Engine, home: DataHome, out: Path) -> Report:
    """Write a backup. The tables are read in one transaction, so they agree with each other
    even while the server is running."""
    revision = migrate.current_revision(engine)
    if revision is None:
        raise GovWrenError("There is nothing to back up: the database has not been set up.")
    now = utc_now()
    counts: dict[str, int] = {}
    columns: dict[str, dict[str, str]] = {}
    partial = out.with_name(out.name + ".part")
    stored = 0
    # It holds everything, password hashes and signing secrets included: for its owner only.
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as raw, tarfile.open(fileobj=raw, mode="w:gz") as archive:
        with engine.connect() as conn:
            if engine.dialect.name == "postgresql":
                conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            for table in _tables(conn):
                keys = list(table.primary_key.columns) or list(table.columns)[:1]
                lines = [
                    json.dumps(
                        {key: _out(value) for key, value in row._mapping.items()},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    for row in conn.execute(select(table).order_by(*keys))
                ]
                counts[table.name] = len(lines)
                columns[table.name] = {
                    column.name: _kind(column)
                    for column in table.columns
                    if _kind(column) != "plain"
                }
                body = "\n".join(lines) + ("\n" if lines else "")
                _add(archive, f"tables/{table.name}.jsonl", body.encode(), now.timestamp())
            events = conn.execute(text("SELECT seq FROM chain_head")).scalar() or 0
        for label, root in (("files", home.files), ("brand", home.brand)):
            for path in _files(root):
                archive.add(path, f"{label}/{path.relative_to(root).as_posix()}", recursive=False)
                stored += 1
        manifest = {
            "format": FORMAT,
            "made_at": now.isoformat(),
            "made_by": f"GovWren {__version__}",
            "database": engine.dialect.name,
            "revision": revision,
            "events": events,
            "tables": counts,
            "columns": columns,
            "files": stored,
        }
        _add(archive, MANIFEST, json.dumps(manifest, indent=2).encode(), now.timestamp())
    partial.replace(out)
    # Noted in the data home, so that `doctor --production` can say how old the last one is.
    (home.root / LAST).write_text(
        json.dumps({"at": now.isoformat(), "file": str(out), "rows": sum(counts.values())}),
        encoding="utf-8",
    )
    return Report(len(counts), sum(counts.values()), stored, revision, events)


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        with tarfile.open(path, "r:gz") as archive:
            member = archive.extractfile(MANIFEST)
            manifest = json.loads(member.read()) if member else None
    except (OSError, tarfile.TarError, KeyError, ValueError) as exc:
        raise GovWrenError(f"{path} is not a GovWren backup: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise GovWrenError(f"{path} is not a GovWren backup this version can read.")
    return manifest


def _in_use(conn: Connection, tables: list[Table]) -> bool:
    by_name = {table.name: table for table in tables}
    return any(
        name in by_name
        and conn.execute(select(func.count()).select_from(by_name[name])).scalar_one() > 0
        for name in ("account", "event")
    )


def restore(engine: Engine, home: DataHome, path: Path) -> Report:
    """Load a backup into a database that holds nothing yet, and put its files back.

    The database is brought to the backup's own migration first, so the rows fit; upgrade it
    afterwards if this version is newer. Nothing is overwritten: a database that has
    accounts or history is refused."""
    manifest = read_manifest(path)
    revision = manifest["revision"]
    if revision not in migrate.script_revisions():
        raise GovWrenError(
            f"The backup is at migration {revision}, which this version of GovWren does not "
            "know. Restore it with the version that made it, or a newer one."
        )
    current = migrate.current_revision(engine)
    with engine.connect() as conn:
        if _in_use(conn, _tables(conn)):
            raise GovWrenError(
                "This database is in use: it has accounts or history. A backup is restored "
                "only into an empty database, so that nothing is overwritten."
            )
    if current is None:
        migrate.upgrade(engine, revision)
    elif current != revision:
        raise GovWrenError(
            f"The database is at migration {current} and the backup at {revision}. Restore "
            "into a database that has not been set up, then run: govwren db upgrade"
        )
    home.create()
    naive = engine.dialect.name == "sqlite"
    rows = 0
    restored = 0
    with tarfile.open(path, "r:gz") as archive, engine.begin() as conn:
        tables = _tables(conn)
        for table in reversed(tables):  # whatever the migrations put there gives way
            conn.execute(table.delete())
        for table in tables:
            member = archive.extractfile(f"tables/{table.name}.jsonl") if (
                table.name in manifest["tables"]
            ) else None  # fmt: skip
            if member is None:
                continue
            kinds = manifest["columns"].get(table.name, {})
            known = {column.name for column in table.columns}
            batch: list[dict[str, Any]] = []
            for line in member:
                if not line.strip():
                    continue
                row = json.loads(line)
                batch.append(
                    {
                        key: _in(value, kinds.get(key, "plain"), naive)
                        for key, value in row.items()
                        if key in known
                    }
                )
                if len(batch) == BATCH:
                    conn.execute(insert(table), batch)
                    rows += len(batch)
                    batch = []
            if batch:
                conn.execute(insert(table), batch)
                rows += len(batch)
            if rows and engine.dialect.name == "postgresql" and "id" in known:
                conn.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', 'id'), "  # noqa: S608 (names come from the database's own catalog)
                        f'(SELECT max(id) FROM "{table.name}")) '
                        f"WHERE pg_get_serial_sequence('\"{table.name}\"', 'id') IS NOT NULL "
                        f'AND (SELECT max(id) FROM "{table.name}") IS NOT NULL'
                    )
                )
        for member in archive.getmembers():
            label, _, rest = member.name.partition("/")
            if label not in ("files", "brand") or not member.isfile():
                continue
            root = home.files if label == "files" else home.brand
            target = (root / rest).resolve()
            if not target.is_relative_to(root.resolve()):
                raise GovWrenError(f"The backup holds a file outside the data home: {member.name}")
            source = archive.extractfile(member)
            if source is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())
            restored += 1
        counted = {
            table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
            for table in tables
            if table.name in manifest["tables"]
        }
        wrong = [name for name, count in counted.items() if count != manifest["tables"][name]]
        if wrong:
            raise GovWrenError(
                f"The restore did not complete: {', '.join(sorted(wrong))} did not load whole. "
                "Nothing was kept."
            )
    with engine.connect() as conn:
        checked = chain.verify(conn)
    if not checked.ok:
        raise GovWrenError(
            f"The restored history does not verify at event {checked.broken_at}: "
            f"{checked.reason}. The backup, or the installation it was made from, was damaged."
        )
    return Report(len(manifest["tables"]), rows, restored, revision, checked.events)


def last(home: DataHome) -> dict[str, Any] | None:
    """When `govwren backup` last ran here, or None if it never has."""
    try:
        noted = json.loads((home.root / LAST).read_text(encoding="utf-8"))
        return {**noted, "at": datetime.fromisoformat(noted["at"])}
    except (OSError, ValueError, KeyError):
        return None
