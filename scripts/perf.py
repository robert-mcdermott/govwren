#!/usr/bin/env python3
"""Measure the common pages against a large installation.

Builds a demo organization, multiplies its use cases with their owners, links, reviews,
decisions, and conditions until there are as many as asked for (each with its entry in the
history), then times the requests behind the pages people open most, signed in as
governance. Prints the median and the slowest of five calls for each, and exits with 1 if
a median is over the budget.

    uv run python scripts/perf.py                       10,000 use cases on SQLite
    uv run python scripts/perf.py --records 2000
    GOVWREN_DATABASE_URL=postgresql+psycopg://... uv run --extra postgres python scripts/perf.py

The PostgreSQL database must be empty: the demo is built on SQLite and moved into it with
a backup and a restore.

Development use only: it makes a throwaway installation in a temporary directory.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, func, insert, select, text

OFFSET = 1_000_000  # copy k of row n is row n + k * OFFSET
# table -> (columns that move with the copy, the column that says what kind of record)
COPIED: dict[str, tuple[dict[str, str | None], str | None]] = {
    "use_case": ({"id": None}, None),
    "record_owner": ({"id": None, "record_id": "record_type"}, "record_type"),
    "record_link": ({"id": None, "from_id": "from_type"}, "from_type"),
    "review": ({"id": None, "subject_id": "subject_type"}, "subject_type"),
    "review_task": ({"id": None, "review_id": None}, None),
    "decision": ({"id": None, "review_id": None}, None),
    "condition": ({"id": None, "decision_id": None, "subject_id": "subject_type"}, "subject_type"),
}
REQUESTS = [
    ("Home: my work", "/api/v1/me/work"),
    ("Use cases, first page", "/api/v1/use-cases?limit=50"),
    ("Use cases, searched", "/api/v1/use-cases?q=summar&limit=50"),
    ("Use cases, filtered and sorted", "/api/v1/use-cases?tier=3&sort=name&limit=50"),
    ("One use case", "/api/v1/use-cases/UC-0051"),
    ("Its history", "/api/v1/use-cases/UC-0051/history"),
    ("Its findings", "/api/v1/records/UC-0051/findings"),
    ("Its dossier", "/api/v1/records/UC-0051/dossier"),
    ("Review queue", "/api/v1/reviews"),
    ("Dashboard", "/api/v1/dashboard"),
    ("Measures", "/api/v1/measures"),
    ("Portfolio by unit", "/api/v1/portfolio?by=unit"),
    ("Portfolio by supplier", "/api/v1/portfolio?by=vendor"),
    ("Actions", "/api/v1/actions"),
    ("Risk register", "/api/v1/risks"),
    ("Control library", "/api/v1/controls"),
    ("AI systems", "/api/v1/systems?limit=50"),
    ("Catalog", "/api/v1/catalog"),
    ("Search everything", "/api/v1/search?q=imaging"),
    ("Inventory as it stood", "/api/v1/inventory/as-of?on=2026-06-30"),
    ("Notifications", "/api/v1/notifications"),
]


def multiply(engine: Any, wanted: int) -> int:
    """Copy the demo's use cases until there are ``wanted`` of them."""
    from govwren.core.clock import utc_now
    from govwren.events import chain

    metadata = MetaData()
    metadata.reflect(engine, only=list(COPIED))
    with engine.begin() as conn:
        source = {
            name: [dict(row._mapping) for row in conn.execute(select(metadata.tables[name]))]
            for name in COPIED
        }
        base = len(source["use_case"])
        copies = max(0, -(-(wanted - base) // base))
        for k in range(1, copies + 1):
            shift = k * OFFSET
            for name, (moving, kind) in COPIED.items():
                rows = []
                for row in source[name]:
                    if kind and row[kind] != "use_case":
                        continue
                    new = dict(row)
                    for column in moving:
                        if new[column] is not None:
                            new[column] += shift
                    if "ref" in new:
                        prefix, _, number = new["ref"].partition("-")
                        new["ref"] = f"{prefix}-{int(number) + shift}"
                    if name == "use_case":
                        new["name"] = f"{row['name']} ({k})"
                    rows.append(new)
                for start in range(0, len(rows), 500):
                    conn.execute(insert(metadata.tables[name]), rows[start : start + 500])
                if name == "use_case":
                    chain.append(
                        conn,
                        utc_now(),
                        [
                            {
                                "actor_kind": "command", "actor_id": None,
                                "actor_label": "Performance seed", "action": "created",
                                "subject_type": "use_case", "subject_id": new["id"],
                                "subject_ref": new["ref"], "parent_type": None, "parent_id": None,
                                "changes": {
                                    key: [None, chain.jsonable(value)]
                                    for key, value in new.items() if value is not None
                                },
                                "context": {},
                            }
                            for new in rows
                        ],
                    )  # fmt: skip
        if engine.dialect.name == "postgresql":
            for name in COPIED:
                conn.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('\"{name}\"', 'id'), "  # noqa: S608
                        f'(SELECT max(id) FROM "{name}"))'
                    )
                )
        return conn.execute(
            select(func.count()).select_from(metadata.tables["use_case"])
        ).scalar_one()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--records", type=int, default=10_000, help="use cases to measure with")
    parser.add_argument(
        "--budget", type=int, default=1000, help="the slowest median allowed, in ms"
    )
    args = parser.parse_args()
    os.environ["GOVWREN_SERVER_SCHEDULER"] = "false"

    from fastapi.testclient import TestClient

    from govwren.api.app import create_app
    from govwren.cli import main as govwren
    from govwren.config import load_config

    with tempfile.TemporaryDirectory(prefix="govwren-perf-") as root:
        started = time.perf_counter()
        if govwren(["--quiet", "demo", root]) != 0:
            return 1
        config = load_config(Path(root) / "govwren.toml")
        if os.environ.get("GOVWREN_DATABASE_URL"):
            # The demo is always built on SQLite. Move it, the way an installation is moved.
            from govwren import backup
            from govwren.db.engine import Database
            from govwren.home import DataHome

            home = DataHome(config.data.home)
            built = Database(load_config(Path(root) / "govwren.toml", env={}).database_url)
            target = Database(config.database_url)
            saved = Path(root) / "move.tar.gz"
            backup.create(built.engine, home, saved)
            backup.restore(target.engine, home, saved)
            built.dispose()
            target.dispose()
        app = create_app(config)
        with TestClient(app, base_url="http://127.0.0.1") as client:
            total = multiply(app.state.db.engine, args.records)
            events = 0
            with app.state.db.engine.connect() as conn:
                events = conn.execute(text("SELECT seq FROM chain_head")).scalar_one()
            print(
                f"{total:,} use cases and {events:,} events on {app.state.db.dialect}, "
                f"ready in {time.perf_counter() - started:.0f}s\n"
            )
            people = client.get("/api/v1/meta").json()["data"]["demo"]["accounts"]
            email = next(person["email"] for person in people if person["key"] == "governance")
            signed = client.post("/api/v1/session/demo", json={"email": email})
            if signed.status_code != 200:
                print(f"Could not sign in: {signed.status_code} {signed.text}", file=sys.stderr)
                return 1
            slow = []
            print(f"{'Request':34}{'median':>9}{'slowest':>9}")
            for label, path in REQUESTS:
                times = []
                for _ in range(5):
                    began = time.perf_counter()
                    answer = client.get(path)
                    times.append((time.perf_counter() - began) * 1000)
                    if answer.status_code != 200:
                        print(f"{label}: {answer.status_code} from {path}", file=sys.stderr)
                        return 1
                median = statistics.median(times)
                flag = "  over budget" if median > args.budget else ""
                print(f"{label:34}{median:8.0f}ms{max(times):7.0f}ms{flag}")
                if flag:
                    slow.append(label)
        if slow:
            print(f"\nOver {args.budget} ms: {', '.join(slow)}", file=sys.stderr)
            return 1
        print(f"\nEvery median is within {args.budget} ms.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
