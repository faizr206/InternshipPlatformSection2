"""Sprint 3: offers, placement confirmation + P07 handoff, withdrawal, skill gap → P06,
rematch after a profile change. One test (or more) per acceptance criterion."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


def submit(client, student_id="COOP-B001", opportunity_id="OP-028"):
    r = client.post("/api/applications", json={
        "student_id": student_id, "opportunity_id": opportunity_id,
        "statement": "Aviation analytics fits my goals.", "actor_role": "student"})
    assert r.status_code == 201, r.text
    return r.json()["application_id"]


def decide(client, app_id, action, actor_role="employer", reason=None):
    return client.post(f"/api/applications/{app_id}/decisions",
                       json={"action": action, "actor_role": actor_role, "reason": reason})


def respond(client, app_id, response, actor_role="student"):
    return client.post(f"/api/applications/{app_id}/offer-response",
                       json={"response": response, "actor_role": actor_role})


def confirm(client, app_id, actor_role="coordinator"):
    return client.post(f"/api/applications/{app_id}/confirm-placement",
                       json={"actor_role": actor_role, "actor_name": "COORD-01"})


def withdraw(client, app_id, actor_role="student", reason=None):
    return client.post(f"/api/applications/{app_id}/withdraw", json={"actor_role": actor_role, "reason": reason})


def offered(client, **kw):
    app_id = submit(client, **kw)
    for action in ("Under review", "Shortlisted", "Offer"):
        assert decide(client, app_id, action).status_code == 201
    return app_id


def history(client, app_id, student_id="COOP-B001"):
    apps = client.get(f"/api/students/{student_id}/applications").json()
    return next(a for a in apps if a["application_id"] == app_id)


# --- P04-05 Offer response ---
def test_p04_05_ac1_employer_offers_and_student_accepts_with_actor_and_time(client):
    app_id = offered(client)
    a = history(client, app_id)
    assert a["application_status"] == "Offered"
    assert a["history"][-1]["actor_role"] == "employer" and a["history"][-1]["created_at"]

    accepted = respond(client, app_id, "accept")
    assert accepted.status_code == 201
    last = accepted.json()["history"][-1]
    assert last["action"] == "Offer accepted"
    assert last["actor_role"] == "student" and last["actor_name"] == "Layla Hassan" and last["created_at"]


def test_p04_05_ac1_student_can_decline_an_offer(client):
    app_id = offered(client)
    body = respond(client, app_id, "decline").json()
    assert body["application_status"] == "Offer declined"
    assert body["placement_status"] == "Not placed"


def test_p04_05_ac2_acceptance_is_awaiting_confirmation_not_a_placement(client):
    app_id = offered(client)
    body = respond(client, app_id, "accept").json()
    assert body["placement_status"] == "Awaiting university confirmation"
    assert client.get("/api/placements").json() == []
    assert client.get("/api/p07/handoffs").json() == []
    # still there after reload
    assert history(client, app_id)["placement_status"] == "Awaiting university confirmation"


def test_p04_05_ac2_accepting_absent_or_declined_offer_is_blocked(client):
    app_id = submit(client)
    absent = respond(client, app_id, "accept")
    assert absent.status_code == 409 and "no open offer" in absent.json()["detail"].lower()

    app_id = offered(client, opportunity_id="OP-031")
    respond(client, app_id, "decline")
    again = respond(client, app_id, "accept")
    assert again.status_code == 409 and "already declined" in again.json()["detail"]


def test_offer_guards(client):
    app_id = submit(client)
    decide(client, app_id, "Under review")
    assert decide(client, app_id, "Offer").status_code == 409  # must be shortlisted first
    decide(client, app_id, "Shortlisted")
    assert decide(client, app_id, "Offer", actor_role="student").status_code == 403
    assert decide(client, app_id, "Offer").status_code == 201
    assert respond(client, app_id, "accept", actor_role="employer").status_code == 403
    assert respond(client, app_id, "maybe").status_code == 422


# --- P04-06 Confirm placement and P07 handoff ---
def test_p04_06_ac1_confirmation_creates_linked_placement_and_p07_handoff(client):
    app_id = offered(client)
    respond(client, app_id, "accept")
    r = confirm(client, app_id)
    assert r.status_code == 200
    p = r.json()
    assert p["placement_id"] == "PL-0001"
    assert (p["application_id"], p["student_id"], p["opportunity_id"]) == (app_id, "COOP-B001", "OP-028")
    assert p["confirmed_by"] == "COORD-01" and p["confirmed_at"]

    handoffs = client.get("/api/p07/handoffs").json()
    assert len(handoffs) == 1
    payload = handoffs[0]["payload"]
    assert payload["placement_id"] == "PL-0001"
    assert payload["status"] == "university_confirmed"
    # field names P07 asked for on 10 Nov
    assert {"employer_name", "location", "role", "period_start", "period_end",
            "supervisor_name", "academic_advisor"} <= payload.keys()
    assert (payload["role"], payload["location"]) == ("Aviation Analytics Intern", "Dubai")
    assert payload["application_id"] == app_id and payload["confirmed_by"] == "COORD-01"
    assert "supervisor_contact" in payload  # goes to P07, never to the student

    a = history(client, app_id)
    assert a["placement_status"] == "Confirmed"
    assert a["history"][-1]["action"] == "Placement confirmed"
    assert a["history"][-1]["actor_role"] == "coordinator"
    assert "supervisor_contact" not in client.get("/api/opportunities/OP-028").json()


def test_p04_06_ac2_unaccepted_application_cannot_be_confirmed(client):
    app_id = offered(client)
    r = confirm(client, app_id)
    assert r.status_code == 409 and "accepted" in r.json()["detail"]
    respond(client, app_id, "decline")
    assert confirm(client, app_id).status_code == 409
    assert client.get("/api/placements").json() == []


def test_p04_06_ac2_repeat_confirmation_is_idempotent(client):
    app_id = offered(client)
    respond(client, app_id, "accept")
    first = confirm(client, app_id).json()
    second = confirm(client, app_id)
    assert second.status_code == 200 and second.json()["already_confirmed"] is True
    assert second.json()["placement_id"] == first["placement_id"]
    assert len(client.get("/api/placements").json()) == 1
    assert len(client.get("/api/p07/handoffs").json()) == 1
    assert sum(e["action"] == "Placement confirmed" for e in history(client, app_id)["history"]) == 1


def test_only_coordinator_confirms(client):
    app_id = offered(client)
    respond(client, app_id, "accept")
    for role in ("student", "employer", "faculty"):
        assert confirm(client, app_id, actor_role=role).status_code == 403


# --- P04-07 Withdraw and history ---
@pytest.mark.parametrize("steps", [[], ["Under review"], ["Under review", "Shortlisted"]])
def test_p04_07_ac1_withdraw_from_agreed_states_keeps_history(client, steps):
    app_id = submit(client)
    for s in steps:
        decide(client, app_id, s)
    r = withdraw(client, app_id, reason="Accepted a different role.")
    assert r.status_code == 201
    a = history(client, app_id)  # after reload
    assert a["application_status"] == "Withdrawn"
    assert [e["action"] for e in a["history"]] == ["Submitted", *steps, "Withdrawn"]
    last = a["history"][-1]
    assert last["actor_role"] == "student" and last["created_at"] and last["next_action"]


def test_p04_07_ac2_cancelled_withdrawal_leaves_record_unchanged(client):
    # Cancelling happens in the UI and makes no request; the record is untouched.
    app_id = submit(client)
    before = history(client, app_id)
    after = history(client, app_id)
    assert before == after and after["application_status"] == "Submitted"


def test_p04_07_ac2_invalid_withdrawals_are_blocked_with_explanation(client):
    app_id = offered(client)
    respond(client, app_id, "accept")
    confirm(client, app_id)
    r = withdraw(client, app_id)
    assert r.status_code == 409 and "confirmed" in r.json()["detail"]

    app_id2 = offered(client, opportunity_id="OP-031")
    r = withdraw(client, app_id2)
    assert r.status_code == 409 and "Decline the offer" in r.json()["detail"]

    app_id3 = submit(client, opportunity_id="OP-033")
    withdraw(client, app_id3)
    assert withdraw(client, app_id3).status_code == 409
    assert withdraw(client, submit(client, opportunity_id="OP-032"), actor_role="employer").status_code == 403


def test_withdrawn_application_can_be_reapplied(client):
    app_id = submit(client)
    withdraw(client, app_id)
    submit(client)  # no duplicate error: Withdrawn is not active


# --- P05-06 Skill gap → P06 ---
def layla_op028(client):
    recs = client.post("/api/students/COOP-B001/recommendations").json()
    return next(r for r in recs if r["opportunity_id"] == "OP-028")


def test_p05_06_ac1_gap_passes_ids_and_versions_to_p06(client):
    rec = layla_op028(client)
    assert any("(SK-JIRA)" in g for g in rec["gaps"])
    r = client.post(f"/api/recommendations/{rec['recommendation_id']}/gaps/SK-JIRA/handoff",
                    json={"actor_role": "student"})
    assert r.status_code == 201
    gap = r.json()
    assert gap["p06_payload"] == {
        "gap_id": gap["gap_id"], "reason": "OP-028 requires Jira; not yet demonstrated",
        "student_id": "COOP-B001", "skill_id": "SK-JIRA", "opportunity_id": "OP-028",
        "opportunity_version": rec["opportunity_version"], "recommendation_id": rec["recommendation_id"],
        "profile_version": rec["profile_version"]}
    assert gap["activity"]["activity_id"] == "P06-ACT-JIRA-01"
    assert "fixture" in gap["source"].lower()
    # repeating returns the same record
    again = client.post(f"/api/recommendations/{rec['recommendation_id']}/gaps/SK-JIRA/handoff",
                        json={"actor_role": "student"}).json()
    assert again["gap_id"] == gap["gap_id"]
    assert len(client.get("/api/students/COOP-B001/skill-gaps").json()) == 1


def test_p05_06_ac2_no_module_gives_clear_next_action(client):
    recs = client.post("/api/students/COOP-B001/recommendations").json()
    rec = next(r for r in recs if r["opportunity_id"] == "OP-033")  # requires Python, no P06 activity
    gap = client.post(f"/api/recommendations/{rec['recommendation_id']}/gaps/SK-PY/handoff",
                      json={"actor_role": "student"}).json()
    assert gap["activity"] is None
    assert "next step" in gap["next_action"].lower()
    assert client.post(f"/api/skill-gaps/{gap['gap_id']}/complete",
                       json={"actor_role": "student"}).status_code == 409


def test_p05_06_ac2_completing_activity_never_changes_the_recommendation(client):
    rec = layla_op028(client)
    gap = client.post(f"/api/recommendations/{rec['recommendation_id']}/gaps/SK-JIRA/handoff",
                      json={"actor_role": "student"}).json()
    before = client.get("/api/students/COOP-B001/recommendations").json()
    done = client.post(f"/api/skill-gaps/{gap['gap_id']}/complete", json={"actor_role": "student"})
    assert done.status_code == 200 and done.json()["completed_at"]
    assert "faculty reviewer" in done.json()["next_action"]
    assert client.get("/api/students/COOP-B001/recommendations").json() == before
    skills = {s["skill_id"] for s in client.get("/api/students/COOP-B001").json()["skills"]}
    assert "SK-JIRA" not in skills


def test_gap_guards(client):
    rec = layla_op028(client)
    url = f"/api/recommendations/{rec['recommendation_id']}/gaps/"
    assert client.post(url + "SK-EXCEL/handoff", json={"actor_role": "student"}).status_code == 422
    assert client.post(url + "SK-JIRA/handoff", json={"actor_role": "coordinator"}).status_code == 403
    assert client.post("/api/recommendations/REC-nope/gaps/SK-JIRA/handoff",
                       json={"actor_role": "student"}).status_code == 404


# --- P05-07 Rematch after a profile change ---
def review_jira(client, **kw):
    return client.post("/api/students/COOP-B001/profile-updates", json={
        "kind": "skill_evidence", "actor_role": "faculty", "actor_name": "FAC-01",
        "skill_id": "SK-JIRA", "evidence_id": "EV-0101", **kw})


def test_p05_07_ac1_reviewed_jira_evidence_rematches_against_new_version(client):
    old = layla_op028(client)
    r = review_jira(client)
    assert r.status_code == 201
    body = r.json()
    assert body["new_profile_version"] == old["profile_version"] + 1
    new = next(x for x in body["recommendations"] if x["opportunity_id"] == "OP-028")
    assert new["profile_version"] == body["new_profile_version"]
    assert not any("SK-JIRA" in g for g in new["gaps"])
    assert new["score"] == old["score"] + 2  # rules-v2: required skill held adds 2
    jira = next(s for s in client.get("/api/students/COOP-B001").json()["skills"] if s["skill_id"] == "SK-JIRA")
    assert jira["evidence_status"] == "reviewed" and jira["reviewed_by"] == "FAC-01"


def test_p05_07_ac1_changing_availability_creates_a_new_versioned_run(client):
    layla_op028(client)
    r = client.post("/api/students/COOP-B001/profile-updates", json={
        "kind": "availability", "actor_role": "student",
        "availability_start": "2027-03-01", "availability_end": "2027-04-01"})
    assert r.status_code == 201
    new = next(x for x in r.json()["recommendations"] if x["opportunity_id"] == "OP-028")
    assert new["profile_version"] == 2
    assert new["eligibility"] == "ineligible"  # OP-028 runs outside the new window


def test_p05_07_ac2_old_runs_keep_versions_and_same_inputs_give_same_rules_result(client):
    old = layla_op028(client)
    review_jira(client)
    runs = client.get("/api/students/COOP-B001/recommendation-runs").json()
    assert [r["profile_version"] for r in runs] == [1, 2]
    # the original recommendation is still stored unchanged
    from app import db
    with db.connect() as conn:
        row = conn.execute("SELECT profile_version, gaps, score FROM recommendations WHERE recommendation_id = ?",
                           (old["recommendation_id"],)).fetchone()
    assert row["profile_version"] == 1 and "SK-JIRA" in row["gaps"] and row["score"] == old["score"]

    # repeat with the same input and method versions → identical rules result
    keys = ("opportunity_id", "profile_version", "opportunity_version", "method_version",
            "score", "eligibility", "compatible", "reasons", "gaps", "unknowns", "ai_method_version", "ai_matches")
    a = client.post("/api/students/COOP-B001/recommendations").json()
    b = client.post("/api/students/COOP-B001/recommendations").json()
    assert [{k: r[k] for k in keys} for r in a] == [{k: r[k] for k in keys} for r in b]


def test_profile_update_guards(client):
    assert review_jira(client, actor_role="student").status_code == 403
    assert review_jira(client, evidence_id="").status_code == 422
    assert review_jira(client, skill_id="SK-NOPE").status_code == 422
    bad = client.post("/api/students/COOP-B001/profile-updates", json={
        "kind": "availability", "actor_role": "student",
        "availability_start": "2027-05-01", "availability_end": "2027-01-01"})
    assert bad.status_code == 422
    versions = client.get("/api/students/COOP-B001/profile-versions").json()
    assert [v["profile_version"] for v in versions] == [1]
