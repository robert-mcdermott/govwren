"""Running in production: what doctor looks at, and the operations view."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from govwren import backup, jobs
from govwren.cli import doctor, main
from govwren.config import load_config
from govwren.core.clock import frozen_at
from tests.conftest import Instance
from tests.people import People
from tests.test_review import MONDAY

Clients = Callable[[str | None], TestClient]


def _named(checks: list[doctor.Check]) -> dict[str, doctor.Check]:
    return {check.name: check for check in checks}


def test_what_production_asks_of_an_installation(
    instance: Instance, people: People, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plain = _named(doctor.run(str(instance.path)))
    assert "Address" not in plain and plain["History"].status == doctor.OK
    found = _named(doctor.run(str(instance.path), production=True))
    assert found["Address"].status == doctor.FAIL and "https" in found["Address"].detail
    assert found["Backup"].status == doctor.WARN and "never" in found["Backup"].detail
    assert found["Sign-in"].status == doctor.WARN
    assert found["Email for production"].status == doctor.WARN
    assert found["Scheduled work"].status == doctor.WARN  # switched off for the tests
    assert found["Administrators"].status == doctor.WARN  # the test people have one
    assert "Demo" not in found

    monkeypatch.setenv("GOVWREN_SERVER_BASE_URL", "https://ai.example.org")
    monkeypatch.setenv("GOVWREN_SERVER_SCHEDULER", "true")
    instance.home.root.chmod(0o700)
    with frozen_at(MONDAY):
        backup.create(instance.db.engine, instance.home, tmp_path / "saved.tar.gz")
        jobs.run_job(instance.db, load_config(instance.path), "tidy", force=True)
        better = _named(doctor.run(str(instance.path), production=True))
        assert better["Address"].status == doctor.OK
        assert (
            better["Backup"].status == doctor.OK
            and "last made 2026-11-02" in better["Backup"].detail
        )
        assert better["Scheduled work"].status == doctor.OK
        assert better["Data home access"].status == doctor.OK
    with frozen_at(MONDAY + timedelta(days=5)):
        later = _named(doctor.run(str(instance.path), production=True))
        assert later["Backup"].status == doctor.WARN and "5 days ago" in later["Backup"].detail
        assert later["Scheduled work"].status == doctor.WARN
    instance.home.root.chmod(0o755)
    loose = _named(doctor.run(str(instance.path), production=True))
    assert (
        loose["Data home access"].status == doctor.WARN
        and "chmod 700" in loose["Data home access"].detail
    )


def test_doctor_production_from_the_command_line(
    instance: Instance, people: People, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--config", str(instance.path), "doctor"]) == 0
    capsys.readouterr()
    assert main(["--config", str(instance.path), "doctor", "--production"]) == 1
    printed = capsys.readouterr().out
    assert "✗ Address" in printed and "! Backup" in printed


def test_the_operations_view(as_role: Clients, instance: Instance, tmp_path: Path) -> None:
    backup.create(instance.db.engine, instance.home, tmp_path / "saved.tar.gz")
    shown = as_role("admin").get("/api/v1/operations")
    assert shown.status_code == 200
    data = shown.json()["data"]
    assert data["database"] in ("SQLite", "PostgreSQL") and data["revision"] and data["version"]
    names = [check["name"] for check in data["checks"]]
    assert {"Data home", "Database", "History", "Address", "Backup"} <= set(names)
    assert data["backup"]["file"].endswith("saved.tar.gz")
    assert data["size"]["accounts"] >= 6 and data["size"]["events"] > 0
    assert {job["key"] for job in data["jobs"]} == set(jobs.JOBS)
    assert data["webhooks"] == {"set_up": 0, "paused": 0, "waiting": 0, "given_up": 0}
    assert data["mail"]["enabled"] is False
    assert as_role("governance").get("/api/v1/operations").status_code == 403
