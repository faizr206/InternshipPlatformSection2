import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


def test_opportunity_list_only_shows_published_open(client):
    ids = {o["opportunity_id"] for o in client.get("/api/opportunities").json()}
    assert "OP-028" in ids
    assert "OP-034" not in ids and "OP-035" not in ids


def test_skills_vocabulary(client):
    assert client.get("/api/skills").json()["SK-JIRA"] == "Jira"


def test_search_and_no_results(client):
    assert [o["opportunity_id"] for o in client.get("/api/opportunities?q=emirates").json()] == ["OP-028"]
    assert client.get("/api/opportunities?q=zzz").json() == []


def test_walking_skeleton_thread(client):
    # Layla gets rules-based recommendations
    recs = client.post("/api/students/COOP-B001/recommendations").json()
    op028 = next(r for r in recs if r["opportunity_id"] == "OP-028")
    assert op028["method_version"] == "rules-v2"
    assert op028["recommendation_id"].startswith("REC-")
    assert any("SK-JIRA" in g for g in op028["gaps"])

    # Stored recommendations survive (re-read)
    stored = client.get("/api/students/COOP-B001/recommendations").json()
    assert {r["recommendation_id"] for r in stored} == {r["recommendation_id"] for r in recs}

    # Opening the opportunity does not create an application
    assert client.get("/api/opportunities/OP-028").json()["version"] == 2
    assert client.get("/api/students/COOP-B001/applications").json() == []

    # Submit
    res = client.post("/api/applications", json={"student_id": "COOP-B001", "opportunity_id": "OP-028"})
    assert res.status_code == 201
    app_rec = res.json()
    assert app_rec["application_status"] == "Submitted"
    assert app_rec["placement_status"] == "Not placed"
    assert (app_rec["profile_version"], app_rec["opportunity_version"]) == (1, 2)

    # Duplicate blocked, no extra record
    dup = client.post("/api/applications", json={"student_id": "COOP-B001", "opportunity_id": "OP-028"})
    assert dup.status_code == 409

    # Closed and unpublished listings blocked
    for opp in ("OP-034", "OP-035"):
        r = client.post("/api/applications", json={"student_id": "COOP-B001", "opportunity_id": opp})
        assert r.status_code == 400

    apps = client.get("/api/students/COOP-B001/applications").json()
    assert len(apps) == 1
    assert apps[0]["application_id"] == app_rec["application_id"]


def test_unknown_student_or_opportunity(client):
    assert client.post("/api/applications", json={"student_id": "NOPE", "opportunity_id": "OP-028"}).status_code == 400
    assert client.post("/api/applications", json={"student_id": "COOP-B001", "opportunity_id": "NOPE"}).status_code == 400
    assert client.post("/api/students/NOPE/recommendations").status_code == 404


@pytest.mark.parametrize("student_id", ["COOP-B001", "COOP-B003"])
def test_eligibility_and_ranking_survive_reloading(client, student_id):
    # Make unknown and conflicting opportunities score above the confirmed matches.
    with db.connect() as conn:
        for opportunity_id in ("OP-032", "OP-033"):
            row = conn.execute("SELECT data FROM opportunities WHERE opportunity_id = ?", (opportunity_id,)).fetchone()
            opportunity = json.loads(row["data"])
            opportunity.update(sector="aviation", required_skills=["SK-SQL", "SK-EXCEL", "SK-VIZ"])
            conn.execute("UPDATE opportunities SET data = ? WHERE opportunity_id = ?",
                         (json.dumps(opportunity), opportunity_id))
    response = client.post(f"/api/students/{student_id}/recommendations")
    assert response.status_code == 200
    results = response.json()
    assert client.get(f"/api/students/{student_id}/recommendations").json() == results
    assert all(r["compatible"] == (r["eligibility"] == "eligible") for r in results)
    if student_id == "COOP-B003":
        assert {r["eligibility"] for r in results} == {"unknown"}
    else:
        assert [r["eligibility"] for r in results] == ["eligible", "eligible", "unknown", "ineligible"]
        assert results[0]["score"] < results[2]["score"]


def test_malformed_fixture_records_are_skipped(tmp_path, monkeypatch, caplog):
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "students.json").write_text(json.dumps([
        {"student_id": "OK-1", "profile_version": 1, "display_name": "Valid"},
        {"student_id": "", "profile_version": 1},           # missing id
        {"student_id": "BAD-2", "profile_version": "one"},  # version not an integer
    ]))
    (fixtures / "opportunities.json").write_text(json.dumps([
        {"opportunity_id": "OP-OK", "version": 1},
        {"version": 2},                                     # missing id
    ]))
    monkeypatch.setattr(db, "FIXTURES", fixtures)
    monkeypatch.setenv("APP_DB", str(tmp_path / "malformed.db"))
    db.init_db()
    with db.connect() as conn:
        assert [r[0] for r in conn.execute("SELECT student_id FROM students")] == ["OK-1"]
        assert [r[0] for r in conn.execute("SELECT opportunity_id FROM opportunities")] == ["OP-OK"]
    assert caplog.text.count("Skipping malformed") == 3


def test_missing_required_application_field_is_rejected(client):
    assert client.post("/api/applications", json={"student_id": "COOP-B001"}).status_code == 422
    assert client.get("/api/students/COOP-B001/applications").json() == []


def test_rules_endpoint(client):
    rules = client.get("/api/rules").json()
    assert rules["version"] == "rules-v2" and "mandatory" in rules and "weights" in rules


def test_two_listings_can_be_compared_with_versions_and_requirements(client):
    a, b = (client.get(f"/api/opportunities/{i}").json() for i in ("OP-028", "OP-031"))
    for o in (a, b):
        assert {"version", "required_skills", "desirable_skills"} <= o.keys()
    assert (a["version"], b["version"]) == (2, 1)


def test_shared_skill_ids_from_p01_p06_agreement(client):
    assert set(client.get("/api/skills").json()) == {
        "SK-JIRA", "SK-SQL", "SK-VIZ", "SK-PY", "SK-EXCEL", "SK-FIGMA", "SK-COMM", "SK-DMKT"}


def test_reviewed_skills_carry_reviewer_and_evidence(client):
    for student in client.get("/api/students").json():
        for skill in student["skills"]:
            review = (skill["reviewed_by"], skill["reviewed_at"], skill["evidence_id"])
            if skill["evidence_status"] == "reviewed":
                assert all(review)
            else:
                assert review == (None, None, None)


def test_supervisor_contact_is_never_shown_to_students(client):
    listings = client.get("/api/opportunities").json() + [client.get("/api/opportunities/OP-028").json()]
    for o in listings:
        assert "supervisor_name" not in o and "supervisor_contact" not in o
        assert "submission_version" in o
    # ...but it is kept for the P07 placement handoff.
    with db.connect() as conn:
        row = conn.execute("SELECT data FROM opportunities WHERE opportunity_id = 'OP-028'").fetchone()
    assert json.loads(row["data"])["supervisor_contact"]


def test_fixture_changes_reach_an_existing_database(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "old.db"))
    db.init_db()
    with db.connect() as conn:
        old = json.loads(conn.execute("SELECT data FROM students WHERE student_id = 'COOP-B001'").fetchone()["data"])
        old["skills"] = [{"skill_id": "SK-JIRA-01", "evidence_status": "reviewed"}]
        conn.execute("UPDATE students SET data = ? WHERE student_id = 'COOP-B001'", (json.dumps(old),))
    db.init_db()  # restart
    with db.connect() as conn:
        data = json.loads(conn.execute("SELECT data FROM students WHERE student_id = 'COOP-B001'").fetchone()["data"])
    assert "SK-JIRA-01" not in json.dumps(data) and data["skills"][0]["skill_id"] == "SK-SQL"
