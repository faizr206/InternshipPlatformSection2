"""P02 employer submission and P03 review/publication, ported from the P01-P03 team's store tests
(legacy/p01-p03-ipp/tests/store.test.mjs) plus the binder acceptance cases they had not automated:
return for revision, decline, resubmission as a new version, publication of approved versions only,
and closing a listing so P04 blocks new applications."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

HR = {"actor_role": "employer", "hr_authorized": True}
COORD = {"actor_role": "coordinator", "actor_name": "COORD-01"}
LISTING = {"organization_name": "Emirates Group (fictional)", "title": "Network Planning Intern",
           "description": "Support route planning with SQL reports and weekly dashboards.",
           "location": "Dubai", "duration": "4 months", "work_mode": "On-site", "sector": "aviation",
           "start_date": "2027-02-01", "end_date": "2027-05-31", "required_skills": ["SK-SQL"],
           "desirable_skills": ["SK-VIZ"], "supervisor_name": "Rana Haddad",
           "supervisor_contact": "rana.haddad@example.test"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATA_SOURCE", "p01p03")
    with TestClient(app) as c:
        yield c


def submit(client, **overrides):
    return client.post("/api/submissions", json={**HR, **LISTING, **overrides})


def decide(client, opp_id, decision, reason=None):
    return client.post(f"/api/submissions/{opp_id}/decision", json={**COORD, "decision": decision, "reason": reason})


# --- P02 submission ---
def test_submission_gets_next_id_version_1_and_is_not_public(client):
    r = submit(client)
    assert r.status_code == 201, r.text
    opp = r.json()
    assert opp["opportunity_id"] == "OP-040"  # after the seed's OP-039
    assert (opp["version"], opp["submission_version"]) == (1, 1)
    assert (opp["publication_status"], opp["listing_status"], opp["status"]) == ("unpublished", "open", "Pending review")
    assert opp["work_mode"] == "on-site"
    assert "OP-040" not in {o["opportunity_id"] for o in client.get("/api/opportunities").json()}
    assert "OP-040" in {o["opportunity_id"] for o in client.get("/api/review-queue").json()}


def test_unauthorized_hr_is_blocked(client):
    r = client.post("/api/submissions", json={**LISTING, "actor_role": "employer", "hr_authorized": False})
    assert r.status_code == 403 and "authorized HR" in r.json()["detail"]


def test_wrong_role_cannot_submit(client):
    assert client.post("/api/submissions", json={**HR, **LISTING, "actor_role": "student"}).status_code == 403


@pytest.mark.parametrize("field", ["organization_name", "title", "description", "location"])
def test_required_fields(client, field):
    r = submit(client, **{field: "   "})
    assert r.status_code == 422
    assert field in r.json()["detail"]["errors"]


def test_length_limits_dates_and_skills_are_checked(client):
    r = submit(client, title="x" * 101, start_date="2027-06-01", end_date="2027-01-01", required_skills=["SK-NOPE"])
    errors = r.json()["detail"]["errors"]
    assert r.status_code == 422
    assert set(errors) == {"title", "end_date", "skills"}


def test_unknown_work_mode_falls_back_to_hybrid(client):
    assert submit(client, work_mode="moon base").json()["work_mode"] == "hybrid"


def test_employer_name_alias(client):
    body = {**HR, **{k: v for k, v in LISTING.items() if k != "organization_name"}, "employer_name": "Acme (fictional)"}
    assert client.post("/api/submissions", json=body).json()["employer_name"] == "Acme (fictional)"


# --- P03 decisions ---
def test_approve_is_separate_from_publish(client):
    opp_id = submit(client).json()["opportunity_id"]
    approved = decide(client, opp_id, "approve").json()
    assert (approved["status"], approved["publication_status"]) == ("Approved", "unpublished")
    assert opp_id not in {o["opportunity_id"] for o in client.get("/api/opportunities").json()}
    published = client.post(f"/api/opportunities/{opp_id}/publish", json=COORD)
    assert published.status_code == 201 and published.json()["status"] == "Published"
    students_see = client.get(f"/api/opportunities/{opp_id}").json()
    assert "supervisor_contact" not in students_see and "supervisor_name" not in students_see
    assert opp_id in {o["opportunity_id"] for o in client.get("/api/opportunities").json()}


def test_unapproved_version_cannot_be_published(client):
    opp_id = submit(client).json()["opportunity_id"]
    r = client.post(f"/api/opportunities/{opp_id}/publish", json=COORD)
    assert r.status_code == 409 and "approved" in r.json()["detail"]


@pytest.mark.parametrize("decision", ["return", "decline"])
def test_return_and_decline_need_a_reason_up_to_300_chars(client, decision):
    opp_id = submit(client).json()["opportunity_id"]
    assert decide(client, opp_id, decision, "  ").status_code == 422
    assert decide(client, opp_id, decision, "x" * 301).status_code == 422
    r = decide(client, opp_id, decision, "Name the workplace supervisor.")
    assert r.status_code == 201
    assert r.json()["review_reason"] == "Name the workplace supervisor."
    assert r.json()["reviewed_by"] == "COORD-01"


def test_declined_is_final(client):
    opp_id = submit(client).json()["opportunity_id"]
    decide(client, opp_id, "decline", "Not a learning placement.")
    assert decide(client, opp_id, "approve").status_code == 409
    assert client.post(f"/api/opportunities/{opp_id}/publish", json=COORD).status_code == 409
    resubmit = client.post(f"/api/submissions/{opp_id}/resubmit", json={**HR, **LISTING})
    assert resubmit.status_code == 409


def test_only_coordinator_decides(client):
    opp_id = submit(client).json()["opportunity_id"]
    r = client.post(f"/api/submissions/{opp_id}/decision", json={"actor_role": "employer", "decision": "approve"})
    assert r.status_code == 403


def test_binder_demo_return_revise_approve_publish_keeps_history(client):
    """P02/P03 final demonstration: returned, resubmitted as version 2, approved and published,
    with the earlier version and decision kept."""
    opp_id = submit(client, supervisor_name="").json()["opportunity_id"]
    decide(client, opp_id, "return", "Clarify the supervision arrangements.")
    employer_view = {o["opportunity_id"]: o for o in client.get("/api/submissions").json()}[opp_id]
    assert employer_view["status"] == "Returned for revision"
    assert employer_view["review_reason"] == "Clarify the supervision arrangements."

    v2 = client.post(f"/api/submissions/{opp_id}/resubmit", json={**HR, **LISTING}).json()
    assert (v2["opportunity_id"], v2["version"], v2["submission_version"], v2["status"]) == (opp_id, 2, 2, "Pending review")
    assert "review_reason" not in v2

    versions = client.get(f"/api/submissions/{opp_id}/versions").json()
    assert [(v["version"], v["current"], v["status"]) for v in versions] == [
        (1, False, "Returned for revision"), (2, True, "Pending review")]
    assert versions[0]["supervisor_name"] is None and versions[0]["archived_at"]

    decide(client, opp_id, "approve")
    client.post(f"/api/opportunities/{opp_id}/publish", json=COORD)
    history = client.get(f"/api/opportunities/{opp_id}/decisions").json()
    assert [(h["version"], h["decision"]) for h in history] == [(1, "returned"), (2, "approved"), (2, "published")]
    assert all(h["actor_name"] == "COORD-01" for h in history)


def test_resubmit_needs_a_returned_listing(client):
    opp_id = submit(client).json()["opportunity_id"]
    assert client.post(f"/api/submissions/{opp_id}/resubmit", json={**HR, **LISTING}).status_code == 409


def test_seed_unpublished_listing_is_in_the_queue_and_can_be_published(client):
    """OP-039 arrives unpublished in the P01-P03 export; the coordinator can approve and publish it."""
    assert "OP-039" in {o["opportunity_id"] for o in client.get("/api/review-queue").json()}
    decide(client, "OP-039", "approve")
    client.post("/api/opportunities/OP-039/publish", json=COORD)
    assert "OP-039" in {o["opportunity_id"] for o in client.get("/api/opportunities").json()}


def test_checklist_is_recorded_but_never_approves_by_itself(client):
    """P03 AC4: a completed checklist alone does not approve; the decision is explicit."""
    opp_id = submit(client).json()["opportunity_id"]
    checklist = client.get("/api/review/checklist").json()
    r = client.post(f"/api/submissions/{opp_id}/decision",
                                  json={**COORD, "decision": "return", "reason": "Tasks are too vague.",
                                        "checklist": checklist})
    assert r.json()["status"] == "Returned for revision"
    assert client.get(f"/api/opportunities/{opp_id}/decisions").json()[0]["checklist"] == checklist
    no_decision = client.post(f"/api/submissions/{opp_id}/decision", json={**COORD, "checklist": checklist})
    assert no_decision.status_code == 422


# --- Closing (new: the P01-P03 app had no close action) and the P04 downstream view ---
def test_closing_a_listing_blocks_new_applications(client):
    r = client.post("/api/opportunities/OP-028/close", json={**COORD, "reason": "Position filled"})
    assert r.status_code == 201 and r.json()["status"] == "Closed"
    assert "OP-028" not in {o["opportunity_id"] for o in client.get("/api/opportunities").json()}
    applied = client.post("/api/applications", json={"student_id": "COOP-B001", "opportunity_id": "OP-028",
                                                     "statement": "Aviation analytics fits my goals."})
    assert applied.status_code == 400 and "not open" in applied.json()["detail"]
    assert client.post("/api/opportunities/OP-028/close", json=COORD).status_code == 409


def test_publishing_never_reopens_a_closed_listing(client):
    assert client.post("/api/opportunities/OP-036/publish", json=COORD).status_code == 409
    assert client.get("/api/opportunities/OP-036").json()["listing_status"] == "closed"


def test_unpublished_listing_cannot_be_closed(client):
    opp_id = submit(client).json()["opportunity_id"]
    assert client.post(f"/api/opportunities/{opp_id}/close", json=COORD).status_code == 409


def test_published_listing_reaches_matching(client):
    """A listing published in P03 is visible to P05 matching in the same database."""
    opp_id = submit(client).json()["opportunity_id"]
    decide(client, opp_id, "approve")
    client.post(f"/api/opportunities/{opp_id}/publish", json=COORD)
    recs = client.post("/api/students/COOP-B001/recommendations").json()
    rec = {r["opportunity_id"]: r for r in recs}[opp_id]
    assert rec["opportunity_version"] == 1 and rec["eligibility"] == "eligible"


def test_events_record_actor_and_action(client):
    opp_id = submit(client, actor_name="Hana (HR)").json()["opportunity_id"]
    decide(client, opp_id, "return", "Add dates.")
    assert [e["action"] for e in client.get("/api/events?module=P02").json()] == ["opportunity_submitted"]
    events = client.get("/api/events").json()
    assert [(e["module"], e["action"], e["actor_name"]) for e in events[:2]] == [
        ("P03", "opportunity_returned", "COORD-01"), ("P02", "opportunity_submitted", "Hana (HR)")]
    assert all(e["ref"] == opp_id for e in events[:2])
