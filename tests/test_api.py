import pytest
from fastapi.testclient import TestClient

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


def test_search_and_no_results(client):
    assert [o["opportunity_id"] for o in client.get("/api/opportunities?q=emirates").json()] == ["OP-028"]
    assert client.get("/api/opportunities?q=zzz").json() == []


def test_walking_skeleton_thread(client):
    # Layla gets rules-based recommendations
    recs = client.post("/api/students/COOP-B001/recommendations").json()
    op028 = next(r for r in recs if r["opportunity_id"] == "OP-028")
    assert op028["method_version"] == "rules-v1"
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
