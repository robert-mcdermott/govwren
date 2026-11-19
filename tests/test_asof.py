"""A record, and the inventory, as they stood on a chosen date."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from govwren.core.clock import frozen_at
from govwren.core.errors import Invalid, NotFound
from govwren.db.engine import Database
from govwren.insight import asof
from govwren.inventory import records
from govwren.inventory.registry import USE_CASE, find
from tests.people import People
from tests.test_changes import linked
from tests.test_review import HIGH, MONDAY, request, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
DAY = MONDAY.date()


def _edited(db: Database, people: People) -> str:
    """A use approved on Monday whose summary and stage change ten days later."""
    use, _system, _model = linked(db, people)
    member = who(db, people, "member")
    with frozen_at(MONDAY + timedelta(days=10)), db.write(member.actor) as session:
        record = find(session, USE_CASE, use)
        records.update(
            session, member, USE_CASE, record,
            {"summary": "Summarize meeting notes and draft the minutes.", "stage": "pilot"},
            version=record.version,
        )  # fmt: skip
    return use


def test_a_record_as_it_stood(db: Database, people: People) -> None:
    use = _edited(db, people)
    member = who(db, people, "member")
    with frozen_at(MONDAY + timedelta(days=30)), db.read() as session:
        found = find(session, USE_CASE, use)
        then = asof.record(session, member, USE_CASE, found, DAY + timedelta(days=2))
        assert then["existed"] and then["on"] == DAY + timedelta(days=2)
        fields = {f["field"]: f for f in then["fields"]}
        assert fields["summary"]["changed"] and fields["stage"]["changed"]
        assert fields["summary"]["now"] == "Summarize meeting notes and draft the minutes."
        assert fields["summary"]["then"] != fields["summary"]["now"]
        assert not fields["status"]["changed"] and fields["status"]["then"].startswith("Approved")
        assert (
            fields["org_unit_id"]["then"] == "Hale Lab" and fields["org_unit_id"]["label"] == "Unit"
        )
        assert then["fields"][0]["changed"] and not then["fields"][-1]["changed"]
        assert "id" not in fields and "version" not in fields
        assert [o["kind"] for o in then["owners"]] and then["relies_on"] == [
            {"relation": "Uses", "name": "Lumen Assistant"}
        ]
        assert then["changes_since"] >= 1
        later = asof.record(session, member, USE_CASE, found, DAY + timedelta(days=12))
        assert not any(f["changed"] for f in later["fields"]) and later["changes_since"] == 0
        before = asof.record(session, member, USE_CASE, found, DAY - timedelta(days=1))
        assert not before["existed"] and before["fields"] == [] and before["created_on"] == str(DAY)
        with pytest.raises(NotFound):
            asof.record(session, who(db, people, "reviewer"), USE_CASE, found, DAY)
        for bad in ("", "tomorrow", str(DAY + timedelta(days=31))):
            with pytest.raises(Invalid):
                asof.parse(bad)


def test_the_inventory_as_it_stood(db: Database, people: People) -> None:
    use = _edited(db, people)
    with frozen_at(MONDAY + timedelta(days=20)):
        request(db, people, HIGH)
    with frozen_at(MONDAY + timedelta(days=30)), db.read() as session:
        assert asof.inventory(session, DAY - timedelta(days=1))["uses"] == []
        first = asof.inventory(session, DAY + timedelta(days=1))
        assert [(u["ref"], u["tier_label"], u["unit"]) for u in first["uses"]] == [
            (use, "Minimal", "Hale Lab")
        ]
        assert first["in_use"] == 1 and first["by_tier"] == {"Minimal": 1}
        now = asof.inventory(session, DAY + timedelta(days=30))
        assert len(now["uses"]) == 2 and now["in_use"] == 1 and now["changed_since"] == 0
        assert now["by_status"]["in_review"] == 1


def test_over_the_api(as_role: Clients, db: Database, people: People) -> None:
    use = _edited(db, people)
    on = {"on": str(DAY + timedelta(days=2))}
    with frozen_at(MONDAY + timedelta(days=30)):
        shown = as_role("member").get(f"/api/v1/records/{use}/as-of", params=on)
        assert shown.status_code == 200 and shown.json()["data"]["existed"]
        assert as_role("reviewer").get(f"/api/v1/records/{use}/as-of", params=on).status_code == 404
        assert as_role("member").get(f"/api/v1/records/{use}/as-of").status_code == 422
        listed = as_role("auditor").get("/api/v1/inventory/as-of", params=on)
        assert listed.status_code == 200 and listed.json()["data"]["in_use"] == 1
        assert as_role("member").get("/api/v1/inventory/as-of", params=on).status_code == 403
