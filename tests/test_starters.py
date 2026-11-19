"""Starter programs and content packs: what comes with GovWren to begin from."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

from govwren.access.principal import Principal
from govwren.assurance import content
from govwren.cli import main
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Control, RiskStatement
from govwren.program import packs, vocab
from tests.conftest import Instance
from tests.people import People
from tests.test_intake import SIMPLE
from tests.test_review import request, who

ROOT = Path(__file__).resolve().parent.parent
COMMAND = Principal.for_command("Tester")


def test_the_starters_are_what_the_script_writes() -> None:
    checked = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build-packs.py"), "--check"],
        capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip
    assert checked.returncode == 0, checked.stderr


def test_every_starter_is_a_whole_program() -> None:
    listed = packs.starters()
    assert [item["key"] for item in listed] == [
        "starter-academic-medical-center",
        "starter-research-institute",
        "starter-university",
    ]
    for item in listed:
        pack = packs.starter(item["key"])
        assert packs.problems(pack) == [], item["key"]
        assert pack["forms"] and pack["scoring_model"] and pack["review"]["rules"]
        assert item["description"] and pack["pack"]["based_on"].startswith("default-program")
    with pytest.raises(NotFound, match="starter-university"):
        packs.starter("starter-bakery")
    with pytest.raises(NotFound):
        packs.starter("default-program")


def test_a_university_begins_with_its_own_words_and_rules(
    instance: Instance, db: Database, people: People
) -> None:
    with db.write(COMMAND.actor) as session:
        report = packs.apply(session, COMMAND, packs.starter("starter-university"))
        packs.ensure_defaults(session, COMMAND)  # the libraries; the program is left alone
        assert set(report["vocabularies"]) == {"unit_kinds", "domains", "affected_groups"}
        labels = vocab.labels(session, "unit_kinds")
        assert labels["division"] == "School or college" and labels["organization"] == "University"
        assert "student_services" in vocab.labels(session, "domains")
        rules = {rule["key"] for rule in packs.published_rules(session).definition["rules"]}  # type: ignore[union-attr]
        assert {"student-data", "decisions-about-people"} <= rules and "patients" not in rules
        assert packs.published_rules(session).version == 1  # type: ignore[union-attr]
    request(db, people, SIMPLE)  # and it takes a request on its first day
    with db.read() as session:
        from govwren.db.models import UseCase

        assert session.scalars(select(UseCase.status)).one() == "approved_with_conditions"


def test_a_content_pack_adds_and_retires_nothing(
    db: Database, people: People, program: None
) -> None:
    assert [(p["key"], p["risks"], p["controls"]) for p in content.builtin()] == [
        ("content-health", 6, 5),
        ("content-research", 6, 4),
    ]
    governance = who(db, people, "governance")

    def counts() -> tuple[int, int, int]:
        with db.read() as session:
            return (
                session.execute(select(func.count()).select_from(RiskStatement)).scalar_one(),
                session.execute(select(func.count()).select_from(Control)).scalar_one(),
                session.execute(
                    select(func.count()).select_from(Control).where(Control.retired.is_(True))
                ).scalar_one(),
            )

    risks, controls, _ = counts()
    with db.write(governance.actor) as session:
        assert content.load(session, governance, content.read("content-health")) == {
            "risks": 6, "controls": 5,
        }  # fmt: skip
        content.load(session, governance, content.read("content-health"))  # again changes nothing
        content.load(session, governance, content.read("content-research"))
    assert counts() == (risks + 12, controls + 9, 0)
    with db.read() as session:
        added = session.scalars(select(Control).where(Control.key == "validated-locally")).one()
        assert added.applies_when == {"field": "record.domain", "op": "eq", "value": "clinical"}
        assert added.category_label == "Match review to risk"
    with db.write(governance.actor) as session:
        with pytest.raises(PermissionDenied):
            content.load(session, who(db, people, "auditor"), content.read("content-health"))
        with pytest.raises(Invalid):
            content.load(
                session, governance, {"pack": {"kind": "content", "key": "x", "title": "X"}}
            )
        broken = content.read("content-health")
        broken["risks"][0]["category"] = "weather"
        with pytest.raises(Invalid) as refused:
            content.load(session, governance, broken)
        assert "category" in refused.value.errors["pack"]
    with pytest.raises(NotFound):
        content.read("content-astrology")


def test_from_the_command_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = ["--config", str(tmp_path / "govwren.toml")]
    assert main([*config, "init", "--program", "starter-academic-medical-center"]) == 0
    printed = capsys.readouterr().out
    assert "started from academic medical center" in printed
    assert "loaded the default intake form" not in printed and "risk library" in printed
    assert main([*config, "program", "packs"]) == 0
    printed = capsys.readouterr().out
    assert "starter-university" in printed and "content-health  (6 risks, 5 controls)" in printed
    assert main([*config, "program", "import", "content-health", "--check"]) == 0
    assert "valid content pack" in capsys.readouterr().out
    assert main([*config, "program", "import", "content-health"]) == 0
    assert "Added or updated 6 risks and 5 controls" in capsys.readouterr().out
    assert main([*config, "program", "import", "starter-university"]) == 0
    assert "Routing rules: version 2" in capsys.readouterr().out
    assert main([*config, "init", "--program", "starter-university"]) == 1
    assert "already has a program" in capsys.readouterr().err
    assert main([*config, "program", "import", "starter-bakery"]) == 1


def test_a_framework_of_your_own_loads_from_a_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    config = ["--config", str(tmp_path / "govwren.toml")]
    assert main([*config, "init"]) == 0
    own = {
        "pack": {"key": "funder-terms", "kind": "framework", "title": "Funder's AI terms",
                 "version": "2026", "text_policy": "summary"},
        "requirements": [
            {"code": "F-1", "title": "Keep an inventory", "text": "Know what AI is in use."},
            {"code": "F-2", "title": "Name an owner", "text": "Someone answers for each use."},
        ],
        "crosswalk": {"F-1": ["inventory-kept"], "F-2": ["named-owner"]},
    }  # fmt: skip
    path = tmp_path / "funder.json"
    path.write_text(json.dumps(own))
    capsys.readouterr()
    assert main([*config, "program", "import", str(path), "--check"]) == 0
    assert "valid framework" in capsys.readouterr().out
    assert main([*config, "program", "import", str(path)]) == 0
    assert "Loaded the framework Funder's AI terms." in capsys.readouterr().out
    own["crosswalk"]["F-2"] = ["no-such-control"]
    path.write_text(json.dumps(own))
    assert main([*config, "program", "import", str(path)]) == 1
