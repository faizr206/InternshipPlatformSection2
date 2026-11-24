from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, live_jobs
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


def shortlisted(client):
    a = client.post("/api/applications", json={
        "student_id": "COOP-B001", "opportunity_id": "OP-028", "statement": "SQL reporting",
    }).json()
    for action in ("Under review", "Shortlisted"):
        r = client.post(f"/api/applications/{a['application_id']}/decisions",
                        json={"actor_role": "employer", "action": action})
        assert r.status_code == 201
    return a["application_id"]


def interview_payload(**changes):
    return {"actor_role": "employer", "starts_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "location": "Video link provided by the employer", "mode": "online",
            "duration_minutes": 30, **changes}


def test_interview_reschedule_offer_guard_complete_and_confirm(client):
    aid = shortlisted(client)
    url = f"/api/applications/{aid}"
    response = client.post(url + "/interview", json=interview_payload())
    assert response.status_code == 201
    assert response.json()["application_status"] == "Interview scheduled"
    assert response.json()["interview"]["duration_minutes"] == 30
    assert client.post(url + "/decisions", json={"action": "Offer", "actor_role": "employer"}).status_code == 409
    assert client.post(url + "/interview/complete", json={"actor_role": "employer"}).status_code == 409
    assert client.post(url + "/interview", json=interview_payload(location="Updated location")).status_code == 201
    duplicate = client.post("/api/applications", json={
        "student_id": "COOP-B001", "opportunity_id": "OP-028", "statement": "Duplicate"})
    assert duplicate.status_code == 409
    # Advance the stored schedule to simulate an interview that has started.
    with db.connect() as conn:
        conn.execute("UPDATE interviews SET starts_at = ? WHERE application_id = ?",
                     ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), aid))
    response = client.post(url + "/interview/complete", json={"actor_role": "employer"})
    assert response.status_code == 200
    assert response.json()["application_status"] == "Interview completed"
    assert response.json()["interview"]["completed_at"]
    assert any(e["action"] == "Interview rescheduled" for e in response.json()["history"])
    assert client.post(url + "/decisions", json={"action": "Offer", "actor_role": "employer"}).status_code == 201
    assert client.post(url + "/offer-response", json={"response": "accept", "actor_role": "student"}).status_code == 201
    confirmed = client.post(url + "/confirm-placement", json={"actor_role": "coordinator"})
    assert confirmed.status_code == 200
    assert len(client.get("/api/p07/handoffs").json()) == 1


def test_interview_validation_and_withdrawal(client):
    aid = shortlisted(client)
    url = f"/api/applications/{aid}/interview"
    for changes, status in [
        ({"actor_role": "student"}, 403),
        ({"starts_at": "2027-01-01T10:00:00"}, 422),
        ({"starts_at": "2020-01-01T10:00:00Z"}, 422),
        ({"location": "  "}, 422),
        ({"duration_minutes": 0}, 422),
    ]:
        assert client.post(url, json=interview_payload(**changes)).status_code == status
    assert client.post(url, json=interview_payload()).status_code == 201
    assert client.post(f"/api/applications/{aid}/withdraw", json={"actor_role": "student"}).status_code == 201
    assert client.post(url, json=interview_payload()).status_code == 409


def test_external_normalization_preserves_unknowns_and_safe_links():
    job = {"id": 12, "title": "Junior Python Engineer", "company_name": "Example",
           "url": "https://remotive.com/remote-jobs/software-dev/example-12",
           "description": "<b>Python</b> &amp; SQL", "candidate_required_location": "USA only",
           "job_type": "part_time"}
    row = live_jobs.normalize(job)
    assert row["degree_levels"] == [] and row["country_code"] is None
    assert row["location"] == "USA only"
    assert row["description"] == "Python & SQL"
    assert row["required_skills"] == [] and row["mentioned_skills"] == ["SK-PY", "SK-SQL"]
    assert live_jobs.normalize({**job, "url": "javascript:alert(1)"}) is None
    assert live_jobs.normalize({**job, "url": "https://remotive.com.evil.test/a"}) is None
    assert live_jobs.normalize({**job, "title": "Senior Python Engineer"}) is None


def test_live_feed_cache_stale_and_unavailable(client, monkeypatch):
    calls = []
    def fetch(url, **kwargs):
        calls.append(1)
        if "remoteok.com" in url:
            payload = []
        elif "arbeitnow.com" in url:
            payload = {"data": []}
        elif "remotive.com" in url:
            payload = {"jobs": [{"id": 1, "title": "Python Research Intern", "company_name": "Company",
                                 "url": "https://remotive.com/remote-jobs/software-dev/intern-1"}]}
        else:
            payload = {"jobs": []}
        return httpx.Response(200, request=httpx.Request("GET", url), json=payload)
    monkeypatch.setattr(live_jobs.httpx, "get", fetch)
    response = client.get("/api/external-opportunities").json()
    assert response["status"] == "current" and len(response["jobs"]) == 1
    client.get("/api/external-opportunities")
    assert len(calls) == 5
    with db.connect() as conn:
        conn.execute("UPDATE external_job_cache SET checked_at = '2000-01-01T00:00:00+00:00'")
    def fail(*args, **kwargs):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(live_jobs.httpx, "get", fail)
    stale = client.get("/api/external-opportunities").json()
    assert stale["status"] == "stale" and stale["jobs"] == response["jobs"]
    with db.connect() as conn:
        conn.execute("DELETE FROM external_job_cache")
    assert client.get("/api/external-opportunities").json()["status"] == "unavailable"


def test_old_database_receives_new_tables_and_keeps_applications(client):
    aid = shortlisted(client)
    db.init_db()
    with db.connect() as conn:
        assert conn.execute("SELECT application_id FROM applications WHERE application_id = ?", (aid,)).fetchone()
        assert conn.execute("SELECT * FROM interviews").fetchall() == []
    assert client.get("/api/data-sources").json()["team_connections"]["P07"] == "mock outbox"


def test_canonical_student_roles_and_link_boundary():
    job = {"id": 1, "title": "Graduate Software Engineer", "company_name": "Canonical",
           "url": "https://job-boards.greenhouse.io/canonical/jobs/1",
           "candidate_required_location": "Home based - Worldwide",
           "_work_mode": "remote", "description": "Python testing"}
    row = live_jobs.normalize(job, "Canonical")
    assert row["source"] == "Canonical" and row["opportunity_id"] == "CAN-1"
    assert row["location"] == job["candidate_required_location"]
    assert live_jobs.normalize({**job, "title": "Senior Software Engineer"}, "Canonical") is None
    assert live_jobs.normalize({**job, "url": "https://job-boards.greenhouse.io/other/jobs/1"}, "Canonical") is None


@pytest.mark.parametrize("source, raw, prefix, mode", [
    ("Arbeitnow", {"slug": "python-intern", "title": "Python Intern", "company_name": "A",
                   "url": "https://www.arbeitnow.com/view/python-intern",
                   "location": "Berlin, Germany", "remote": False, "job_types": ["full_time"],
                   "created_at": 1795500000}, "ARB", "unknown"),
    ("Remote OK", {"id": "42", "position": "Data Analyst", "company": "B",
                   "url": "https://remoteok.com/remote-jobs/42", "location": "USA",
                   "date": "2026-11-24T00:00:00Z"}, "ROK", "remote"),
    ("Jobicy", {"id": 43, "jobTitle": "Machine Learning Intern", "companyName": "C",
                "url": "https://jobicy.com/jobs/43", "jobGeo": "Europe",
                "jobType": ["Part-Time"], "jobIndustry": ["Data Science"],
                "jobDescription": "&lt;p&gt;Python&lt;/p&gt;",
                "pubDate": "2026-11-24"}, "JOB", "remote"),
])
def test_additional_provider_fields(source, raw, prefix, mode):
    from app.job_feeds import adapt
    row = live_jobs.normalize(adapt(source, raw), source)
    assert row["opportunity_id"].startswith(prefix + "-")
    assert row["source"] == source and row["work_mode"] == mode
    assert row["source_url"] == raw["url"]
    assert row["degree_levels"] == [] and row["country_code"] is None
    assert not live_jobs.safe_link("https://evil.test/jobs/43", source)
    assert not live_jobs.safe_link("https://jobicy.com.evil.test/jobs/43", source)


def test_remoteok_metadata_and_feed_shapes():
    from app.job_feeds import adapt, feed_rows
    assert live_jobs.normalize(adapt("Remote OK", {"legal": "Attribution required"}), "Remote OK") is None
    assert feed_rows("Remote OK", []) == []
    assert feed_rows("Arbeitnow", {"data": []}) == []
    with pytest.raises(ValueError):
        feed_rows("Jobicy", {"jobs": {}})
