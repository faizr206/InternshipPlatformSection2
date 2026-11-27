"""Home page data: journey across P01-P07, role to-dos and sidebar counts, computed from module records."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATA_SOURCE", "p01p03")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with TestClient(app) as c:
        yield c


def stages(client, sid="COOP-B001"):
    return {s["owner"]: s for s in client.get(f"/api/home/journey/{sid}").json()["stages"]}


def test_journey_has_seven_stages_in_order(client):
    client.post("/api/demo/reset?scenario=fresh")
    j = client.get("/api/home/journey/COOP-B001").json()
    assert [s["owner"] for s in j["stages"]] == ["P01", "P02", "P03", "P05", "P06", "P04", "P07"]
    s = stages(client)
    assert s["P01"]["status"] == "done" and s["P05"]["status"] == "current" and s["P07"]["status"] == "upcoming"
    assert stages(client, "COOP-B004")["P01"]["status"] == "current"  # Noor: no interests or availability


def test_journey_follows_the_scenarios(client):
    client.post("/api/demo/reset?scenario=reviewed")
    s = stages(client)
    assert s["P05"]["status"] == "done" and "v3" in s["P05"]["detail"]
    assert s["P06"]["status"] == "current"  # the manual Data visualisation gap is still open
    client.post("/api/demo/reset?scenario=midpoint")
    s = stages(client)
    assert s["P04"]["status"] == "done" and s["P07"]["status"] == "current" and "week" in s["P07"]["detail"]
    client.post("/api/demo/reset?scenario=end")
    assert stages(client)["P07"]["status"] == "current"


@pytest.mark.parametrize("scenario,role,expected", [
    ("fresh", "student", {"run-matching"}),
    ("fresh", "coordinator", {"review-queue"}),               # OP-039 arrives unpublished
    ("reviewed", "student", set()),
    ("midpoint", "supervisor", {"logs-PL-0001", "action-ACT-01"}),
    ("midpoint", "advisor", {"judge-PL-0001", "action-ACT-01"}),
    ("end", "advisor", {"final-PL-0001", "judge-PL-0001"}),
    ("end", "supervisor", set()),                            # all Period 1 logs read; feedback given
])
def test_todos_per_role(client, scenario, role, expected):
    client.post(f"/api/demo/reset?scenario={scenario}")
    ids = {t["id"] for t in client.get(f"/api/home/todos?role={role}&student_id=COOP-B001").json()}
    assert expected <= ids, ids


def test_counts_feed_the_sidebar(client):
    client.post("/api/demo/reset?scenario=midpoint")
    counts = client.get("/api/home/counts?role=supervisor&student_id=COOP-B001").json()
    assert counts == {"placement": 2}
    assert client.get("/api/home/todos?role=wizard").status_code == 422


def test_events_filter_by_student_and_frontend_aliases(client):
    client.post("/api/demo/reset?scenario=reviewed")
    events = client.get("/api/events?student_id=COOP-B001&limit=100").json()
    assert events and all({"id", "actor", "role", "owner", "text"} <= set(e) for e in events)
    assert {e["owner"] for e in events} >= {"P01", "P06"}
    assert client.get("/api/events?student_id=COOP-B003").json() == []
