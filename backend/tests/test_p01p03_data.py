"""Integration with the P01-P03 export (app/data/p01p03, received 24 Nov).

Checks the test cases the P01-P03 team built into their data (_meta.expected_test_results)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

DATA = Path(__file__).parent.parent / "app" / "seed" / "p01p03"
META = json.loads((DATA / "ipp_sample_data.json").read_text())["_meta"]["expected_test_results"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATA_SOURCE", "p01p03")
    with TestClient(app) as c:
        yield c


def test_profiles_and_listings_come_from_the_p01_p03_export(client):
    students = {s["student_id"]: s for s in client.get("/api/students").json()}
    assert set(students) == {"COOP-B001", "COOP-B002", "COOP-B003", "COOP-B004"}
    assert students["COOP-B002"]["display_name"] == "Arjun Mehta"
    opp = client.get("/api/opportunities/OP-031").json()
    assert opp["employer_name"] == "Desert Grid Energy (fictional)"


def test_layla_is_read_at_her_latest_submitted_version(client):
    layla = client.get("/api/students/COOP-B001").json()
    assert layla["profile_version"] == 2  # edge case: two submitted versions, use 2
    skills = {s["skill_id"]: s for s in layla["skills"]}
    assert skills["SK-SQL"]["evidence_status"] == "reviewed" and skills["SK-SQL"]["evidence_id"] == "E-SQL-01"
    assert skills["SK-JIRA"]["evidence_status"] == "self_declared"


def test_only_published_open_listings_are_listed_or_recommended(client):
    listed = {o["opportunity_id"] for o in client.get("/api/opportunities").json()}
    assert listed == set(META["eligible_for_recommendation"])
    for student in ("COOP-B001", "COOP-B002", "COOP-B003", "COOP-B004"):
        recs = client.post(f"/api/students/{student}/recommendations").json()
        assert {r["opportunity_id"] for r in recs} == set(META["eligible_for_recommendation"])
        assert not {"OP-036", "OP-039"} & {r["opportunity_id"] for r in recs}


def test_closed_and_unpublished_listings_cannot_be_applied_to(client):
    for opp_id in META["not_eligible"]:
        r = client.post("/api/applications", json={"student_id": "COOP-B001", "opportunity_id": opp_id,
                                                   "statement": "Interested.", "actor_role": "student"})
        assert r.status_code == 400


def test_missing_interests_and_availability_stay_unknown(client):
    recs = client.post("/api/students/COOP-B004/recommendations").json()
    assert {r["eligibility"] for r in recs} == {"unknown"}
    assert all(not r["compatible"] for r in recs)
    for r in recs:
        assert any(u.startswith("Availability") for u in r["unknowns"])
        assert any(u.startswith("Interests") for u in r["unknowns"])


def test_supervisor_contact_from_p03_is_never_shown_to_students(client):
    for o in client.get("/api/opportunities").json():
        assert "supervisor_contact" not in o and "supervisor_name" not in o


def test_draft_profiles_are_ignored():
    rows = [
        {"student_id": "S1", "profile_version": 1, "profile_status": "submitted"},
        {"student_id": "S1", "profile_version": 2, "profile_status": "draft"},
    ]
    assert [r["profile_version"] for r in db.latest_submitted(rows)] == [1]


def test_jira_story_with_p01_data_gap_prepare_review_rematch(client):
    """Layla v2 holds Jira only as self_declared: OP-028 lists it as an evidence gap (rules-v3),
    it can go to P06, and faculty-reviewed evidence closes it on profile v3."""
    recs = client.post("/api/students/COOP-B001/recommendations").json()
    op028 = next(r for r in recs if r["opportunity_id"] == "OP-028")
    assert op028["profile_version"] == 2 and op028["eligibility"] == "eligible"
    assert op028["gaps"] == ["Required skill Jira is self-declared; reviewed evidence needed (SK-JIRA)"]

    gap = client.post(f"/api/recommendations/{op028['recommendation_id']}/gaps/SK-JIRA/handoff",
                      json={"actor_role": "student"}).json()
    assert gap["p06_payload"]["reason"] == "OP-028 requires Jira; not yet demonstrated"
    assert gap["activity"]["activity_id"] == "MOD-JIRA-101"

    upd = client.post("/api/students/COOP-B001/profile-updates", json={
        "kind": "skill_evidence", "actor_role": "faculty", "actor_name": "FAC-01",
        "skill_id": "SK-JIRA", "evidence_id": "EV-0101"}).json()
    assert upd["new_profile_version"] == 3
    new = next(r for r in upd["recommendations"] if r["opportunity_id"] == "OP-028")
    assert new["gaps"] == [] and new["profile_version"] == 3
    assert new["score"] == op028["score"]
