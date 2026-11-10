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
    assert client.get("/api/skills").json()["SK-JIRA-01"] == "Jira"


def test_search_and_no_results(client):
    assert [o["opportunity_id"] for o in client.get("/api/opportunities?q=emirates").json()] == ["OP-028"]
    assert client.get("/api/opportunities?q=zzz").json() == []


def test_walking_skeleton_thread(client):
    # Layla gets rules-based recommendations
    recs = client.post("/api/students/COOP-B001/recommendations").json()
    op028 = next(r for r in recs if r["opportunity_id"] == "OP-028")
    assert op028["method_version"] == "rules-v2"
    assert op028["recommendation_id"].startswith("REC-")
    assert any("SK-JIRA-01" in g for g in op028["gaps"])

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
            opportunity.update(sector="aviation", required_skills=["SK-SQL-01", "SK-EXCEL-01", "SK-TABLEAU-01"])
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
