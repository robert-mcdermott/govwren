"""Scheduled work: the jobs GovWren runs by itself, and the scheduler that runs them.

The scheduler lives in the server process. Before a process runs a job it claims the job's
row in the database, so several server processes, or the server and ``govwren jobs run``
from a scheduled task, never run the same job at once. What is due is worked out from the
clock everything else uses, and from what is in the database, so a restart loses nothing.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from govwren import mail
from govwren.config import Config
from govwren.core.clock import utc_now
from govwren.core.errors import NotFound
from govwren.db.engine import Database
from govwren.db.models import Job, JobRun
from govwren.events.actor import Actor
from govwren.oversight import schedule

log = logging.getLogger("govwren.jobs")

LEASE = timedelta(minutes=15)  # a job claimed by a process that died is taken up after this
KEEP_RUNS = timedelta(days=90)
EVERY_SECONDS = 20  # how often the server looks for work that is due
SCHEDULER = Actor.system("Scheduler")


@dataclass(frozen=True)
class JobSpec:
    key: str
    label: str
    describes: str
    every: timedelta
    run: Callable[[Database, Config], dict[str, int]]


def _mail(db: Database, config: Config) -> dict[str, int]:
    return mail.run_once(db, config)


def _in_one(
    work: Callable[[Session], int], name: str
) -> Callable[[Database, Config], dict[str, int]]:
    def run(db: Database, _config: Config) -> dict[str, int]:
        with db.write(SCHEDULER, action=f"job.{name}") as session:
            return {name: work(session)}

    return run


def _tidy(db: Database, _config: Config) -> dict[str, int]:
    with db.bookkeeping() as session:
        gone = session.execute(delete(JobRun).where(JobRun.finished_at < utc_now() - KEEP_RUNS))
        return {"old_runs_removed": gone.rowcount or 0}  # type: ignore[attr-defined]


JOBS: dict[str, JobSpec] = {
    spec.key: spec
    for spec in (
        JobSpec("mail", "Email", "Queues notices and daily summaries, and sends what is waiting",
                timedelta(minutes=1), _mail),
        JobSpec("lapse", "Lapsed approvals",
                "Marks an approval as lapsed when its end date passes without renewal",
                timedelta(hours=1), _in_one(schedule.lapse_approvals, "lapsed")),
        JobSpec("periodic-reviews", "Periodic reviews",
                f"Opens a periodic review {schedule.LEAD_DAYS} days before an approval ends",
                timedelta(hours=1), _in_one(schedule.open_periodic_reviews, "periodic_reviews")),
        JobSpec("reminders", "Reminders",
                "Reminds people of work that is nearly due, and escalates what is late",
                timedelta(hours=1), _in_one(schedule.send_reminders, "reminders")),
        JobSpec("tidy", "Housekeeping", "Removes run records older than ninety days",
                timedelta(days=1), _tidy),
    )
}  # fmt: skip


def ensure(db: Database) -> None:
    """Give every job a row. A new job is due at once."""
    with db.bookkeeping() as session:
        known = set(session.scalars(select(Job.key)))
        for key in JOBS:
            if key not in known:
                session.add(Job(key=key, enabled=True, next_run_at=utc_now()))


def _claim(db: Database, key: str, *, force: bool) -> bool:
    now = utc_now()
    with db.bookkeeping() as session:
        row = session.scalars(
            select(Job).where(Job.key == key).with_for_update(skip_locked=True)
        ).first()
        if row is None or (row.claimed_until is not None and row.claimed_until > now):
            return False
        if not force and (not row.enabled or row.next_run_at > now):
            return False
        row.claimed_until = now + LEASE
        row.last_started_at = now
        return True


def _words(counts: dict[str, int]) -> str:
    done = [f"{value} {name.replace('_', ' ')}" for name, value in counts.items() if value]
    return ", ".join(done) or "Nothing to do"


def run_job(
    db: Database, config: Config, key: str, *, force: bool = False
) -> dict[str, Any] | None:
    """Run one job if it is due and nobody else has it. ``force`` runs it now whether or
    not it is due. Returns what happened, or None if it was not this process's to run."""
    spec = JOBS.get(key)
    if spec is None:
        raise NotFound(f"There is no job {key}.")
    if not _claim(db, key, force=force):
        return None
    started = utc_now()
    counts: dict[str, int] = {}
    error: str | None = None
    try:
        counts = spec.run(db, config)
    except Exception as exc:  # one bad run must not stop the scheduler
        log.exception("the %s job failed", key)
        error = f"{type(exc).__name__}: {exc}"[:600]
    finished = utc_now()
    status = "failed" if error else "ok"
    with db.bookkeeping() as session:
        row = session.get(Job, key)
        assert row is not None
        row.claimed_until = None
        row.last_finished_at = finished
        row.last_status = status
        row.last_summary = (error or _words(counts))[:300]
        row.next_run_at = started + spec.every
        if error or any(counts.values()):
            session.add(JobRun(job_key=key, started_at=started, finished_at=finished,
                               status=status, counts=counts, error=error))  # fmt: skip
    return {"key": key, "status": status, "counts": counts, "error": error,
            "summary": error or _words(counts)}  # fmt: skip


def run_due(db: Database, config: Config) -> list[dict[str, Any]]:
    """Run every job that is due. Safe to call from several processes at once."""
    ensure(db)
    results = []
    for key in JOBS:
        result = run_job(db, config, key)
        if result is not None:
            results.append(result)
    return results


def status(session: Session, *, runs: int = 12) -> list[dict[str, Any]]:
    rows = {row.key: row for row in session.scalars(select(Job))}
    recent = session.scalars(select(JobRun).order_by(JobRun.id.desc()).limit(200)).all()
    out = []
    for key, spec in JOBS.items():
        row = rows.get(key)
        out.append(
            {
                "key": key,
                "label": spec.label,
                "describes": spec.describes,
                "every_seconds": int(spec.every.total_seconds()),
                "enabled": row.enabled if row else True,
                "next_run_at": row.next_run_at if row else None,
                "running": bool(row and row.claimed_until and row.claimed_until > utc_now()),
                "last_finished_at": row.last_finished_at if row else None,
                "last_status": row.last_status if row else None,
                "last_summary": row.last_summary if row else None,
                "runs": [
                    {"started_at": run.started_at, "finished_at": run.finished_at,
                     "status": run.status, "summary": run.error or _words(run.counts)}
                    for run in recent if run.job_key == key
                ][:runs],
            }
        )  # fmt: skip
    return out


def set_enabled(db: Database, key: str, enabled: bool) -> None:
    if key not in JOBS:
        raise NotFound(f"There is no job {key}.")
    ensure(db)
    with db.bookkeeping() as session:
        row = session.get(Job, key)
        assert row is not None
        row.enabled = enabled


def start_worker(db: Database, config: Config) -> threading.Event:
    """Run the scheduler beside the server for as long as it is up. Returns an event that
    stops it when set."""
    stop = threading.Event()

    def work() -> None:
        while not stop.wait(EVERY_SECONDS):
            try:
                run_due(db, config)
            except Exception:  # the scheduler must outlive a bad turn
                log.exception("the scheduler failed this time and will try again")

    threading.Thread(target=work, name="govwren-jobs", daemon=True).start()
    return stop
