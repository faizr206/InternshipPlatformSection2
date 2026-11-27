"""P01 student profile workflow, ported from the P01-P03 team's store tests (latest submitted
version, append-only corrections, unchanged profile creates no version, Noor's missing data shown)
and extended to the binder's P01 acceptance evidence (draft, submit, clarification, review)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

STUDENT = {"actor_role": "student"}
COORD = {"actor_role": "coordinator", "actor_name": "COORD-01"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATA_SOURCE", "p01p03")
    with TestClient(app) as c:
        yield c


def test_layla_starts_at_latest_submitted_version(client):
    state = client.get("/api/students/COOP-B001/profile").json()
    assert state["profile"]["profile_version"] == 2
    assert state["status"] == "submitted" and state["draft"] is None


def test_noor_missing_interests_and_availability_are_shown_not_invented(client):
    noor = client.get("/api/students/COOP-B004/profile").json()["profile"]
    assert noor["interests"] == []
    assert noor["availability_start"] is None and noor["availability_end"] is None


def test_draft_does_not_change_the_current_version(client):
    r = client.put("/api/students/COOP-B001/profile/draft", json={**STUDENT, "goals": "Learn airline network planning"})
    assert r.status_code == 200
    state = r.json()
    assert state["draft"]["goals"] == "Learn airline network planning"
    assert state["profile"]["profile_version"] == 2
    assert client.get("/api/students/COOP-B001").json()["profile_version"] == 2


def test_submit_appends_a_version_and_keeps_reviewed_evidence(client):
    before = client.get("/api/students/COOP-B001").json()
    reviewed = [s for s in before["skills"] if s["evidence_status"] == "reviewed"]
    held = [s["skill_id"] for s in before["skills"]]
    client.put("/api/students/COOP-B001/profile/draft", json={**STUDENT, "skills": held + ["SK-PY"],
                                                               "goals": "Network planning analytics"})
    r = client.post("/api/students/COOP-B001/profile/submit", json=STUDENT)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["new_version"] is True and body["draft"] is None
    profile = body["profile"]
    assert profile["profile_version"] == 3 and profile["goals"] == "Network planning analytics"
    skills = {s["skill_id"]: s for s in profile["skills"]}
    assert skills["SK-PY"]["evidence_status"] == "self_declared" and skills["SK-PY"]["reviewed_by"] is None
    for s in reviewed:
        assert skills[s["skill_id"]] == s  # reviewed evidence reference kept as it was
    versions = client.get("/api/students/COOP-B001/profile-versions").json()
    assert [v["profile_version"] for v in versions] == [2, 3]
    assert versions[0]["profile"].get("goals") is None  # version 2 is never edited


def test_jira_stays_self_declared_after_a_student_edit(client):
    """P01 AC3: self-declared Jira stays labelled as self-declared until an evidence review."""
    jira = [s for s in client.get("/api/students/COOP-B001").json()["skills"] if s["skill_id"] == "SK-JIRA"]
    assert jira and jira[0]["evidence_status"] == "self_declared"
    client.put("/api/students/COOP-B001/profile/draft", json={**STUDENT, "display_name": "Layla H."})
    profile = client.post("/api/students/COOP-B001/profile/submit", json=STUDENT).json()["profile"]
    assert [s for s in profile["skills"] if s["skill_id"] == "SK-JIRA"][0]["evidence_status"] == "self_declared"


def test_unchanged_profile_creates_no_version(client):
    client.put("/api/students/COOP-B001/profile/draft", json={**STUDENT, "display_name": "Layla Hassan"})
    body = client.post("/api/students/COOP-B001/profile/submit", json=STUDENT).json()
    assert body["new_version"] is False and body["profile"]["profile_version"] == 2


def test_submit_without_draft_is_refused(client):
    assert client.post("/api/students/COOP-B001/profile/submit", json=STUDENT).status_code == 409


def test_required_fields_and_date_range_block_submission(client):
    """P01 AC2: missing items give a useful message and prevent submission (Noor has none yet)."""
    client.put("/api/students/COOP-B004/profile/draft", json={**STUDENT, "display_name": " "})
    r = client.post("/api/students/COOP-B004/profile/submit", json=STUDENT)
    assert r.status_code == 422
    assert set(r.json()["detail"]["errors"]) >= {"display_name", "interests", "availability"}
    client.put("/api/students/COOP-B004/profile/draft", json={
        **STUDENT, "display_name": "Noor Al Hashimi", "interests": ["health"],
        "availability_start": "2027-06-01", "availability_end": "2027-01-01"})
    r = client.post("/api/students/COOP-B004/profile/submit", json=STUDENT)
    assert r.status_code == 422 and "availability" in r.json()["detail"]["errors"]
    assert client.get("/api/students/COOP-B004").json()["profile_version"] == 1


def test_display_name_limit(client):
    client.put("/api/students/COOP-B001/profile/draft", json={**STUDENT, "display_name": "x" * 61})
    r = client.post("/api/students/COOP-B001/profile/submit", json=STUDENT)
    assert r.status_code == 422 and "display_name" in r.json()["detail"]["errors"]


def test_clarification_and_revision_binder_demo(client):
    """P01 AC1: submit, coordinator requests clarification with a comment, student revises;
    the latest status and comment are visible."""
    assert client.post("/api/students/COOP-B001/profile/review",
                       json={**COORD, "decision": "clarification_requested"}).status_code == 422
    r = client.post("/api/students/COOP-B001/profile/review",
                    json={**COORD, "decision": "clarification_requested", "comment": "Which roles in aviation?"})
    state = r.json()
    assert state["status"] == "clarification_requested"
    assert state["review"]["comment"] == "Which roles in aviation?" and state["review"]["actor_name"] == "COORD-01"

    client.put("/api/students/COOP-B001/profile/draft", json={**STUDENT, "goals": "Network planning analyst roles"})
    revised = client.post("/api/students/COOP-B001/profile/submit", json=STUDENT).json()
    assert revised["profile"]["profile_version"] == 3 and revised["status"] == "submitted"

    reviewed = client.post("/api/students/COOP-B001/profile/review", json={**COORD, "decision": "reviewed"}).json()
    assert reviewed["status"] == "reviewed"


def test_roles_are_enforced(client):
    assert client.put("/api/students/COOP-B001/profile/draft", json={"actor_role": "employer"}).status_code == 403
    assert client.post("/api/students/COOP-B001/profile/review",
                       json={"actor_role": "student", "decision": "reviewed"}).status_code == 403


def test_new_profile_version_reaches_matching(client):
    """P01 -> P05 (backlog P5-02): submitting a new version reruns matching on it; the earlier run is kept."""
    first = client.post("/api/students/COOP-B001/recommendations").json()
    assert {r["profile_version"] for r in first} == {2}
    client.put("/api/students/COOP-B001/profile/draft", json={**STUDENT, "interests": ["aviation", "energy"]})
    submitted = client.post("/api/students/COOP-B001/profile/submit", json=STUDENT).json()
    assert submitted["rematched"] is True
    latest = client.get("/api/students/COOP-B001/recommendations").json()
    assert {r["profile_version"] for r in latest} == {3}
    runs = client.get("/api/students/COOP-B001/recommendation-runs").json()
    assert [r["profile_version"] for r in runs] == [2, 3]


def test_no_rematch_before_the_first_run(client):
    """A student who never ran matching is not given a run they did not ask for."""
    client.put("/api/students/COOP-B002/profile/draft", json={**STUDENT, "goals": "Energy analytics"})
    assert client.post("/api/students/COOP-B002/profile/submit", json=STUDENT).json()["rematched"] is False
    assert client.get("/api/students/COOP-B002/recommendation-runs").json() == []
