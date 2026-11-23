import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

FIX = Path(__file__).parent.parent / "app" / "fixtures"
STUDENT_FIXTURES = {s["student_id"]: s for s in json.loads((FIX / "students.json").read_text())}
OPP_FIXTURES = {o["opportunity_id"]: o for o in json.loads((FIX / "opportunities.json").read_text())}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


def submit(client, student_id="COOP-B001", opportunity_id="OP-028",
           statement="Aviation analytics fits my goals and studies."):
    return client.post("/api/applications", json={
        "student_id": student_id, "opportunity_id": opportunity_id,
        "statement": statement, "actor_role": "student"})


def decide(client, application_id, action, actor_role="employer", reason=None):
    return client.post(f"/api/applications/{application_id}/decisions", json={
        "action": action, "actor_role": actor_role,
        "actor_name": "Employer reviewer (simulated)", "reason": reason})


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
    res = submit(client)
    assert res.status_code == 201
    app_rec = res.json()
    assert app_rec["application_status"] == "Submitted"
    assert app_rec["placement_status"] == "Not placed"
    assert (app_rec["profile_version"], app_rec["opportunity_version"]) == (1, 2)
    assert app_rec["history"][0]["action"] == "Submitted"

    # Duplicate blocked, no extra record
    dup = submit(client)
    assert dup.status_code == 409

    # Closed and unpublished listings blocked
    for opp in ("OP-034", "OP-035"):
        r = submit(client, opportunity_id=opp)
        assert r.status_code == 400

    apps = client.get("/api/students/COOP-B001/applications").json()
    assert len(apps) == 1
    assert apps[0]["application_id"] == app_rec["application_id"]


def test_unknown_student_or_opportunity(client):
    assert submit(client, student_id="NOPE").status_code == 400
    assert submit(client, opportunity_id="NOPE").status_code == 400
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


# ---------------------------------------------------------------- P04-02 drafts
def test_statement_is_required_for_submission(client):
    missing = submit(client, statement="")
    assert missing.status_code == 422
    assert "Statement is required" in missing.json()["detail"]
    assert client.get("/api/students/COOP-B001/applications").json() == []


def test_draft_save_edit_and_submit_lifecycle(client):
    # Save a draft linked to the student, opportunity and profile versions (AC1)
    draft = client.post("/api/applications/draft", json={
        "student_id": "COOP-B001", "opportunity_id": "OP-028",
        "statement": "First version of my statement.", "actor_role": "student"})
    assert draft.status_code == 201
    body = draft.json()
    assert body["application_status"] == "Draft"
    assert (body["student_id"], body["opportunity_id"]) == ("COOP-B001", "OP-028")
    assert body["placement_status"] == "Not placed"

    # Draft survives a re-read (reload) with its Draft label
    apps = client.get("/api/students/COOP-B001/applications").json()
    assert [a["application_status"] for a in apps] == ["Draft"]
    assert apps[0]["statement"] == "First version of my statement."

    # Editing and saving does NOT submit (AC2); still exactly one Draft row
    edited = client.put(f"/api/applications/{body['application_id']}", json={
        "statement": "Second version, more detail.", "actor_role": "student"})
    assert edited.status_code == 200
    assert edited.json()["application_status"] == "Draft"
    assert len(client.get("/api/students/COOP-B001/applications").json()) == 1

    # Submitting with a missing required field shows a useful error and preserves data
    empty = client.post(f"/api/applications/{body['application_id']}/submit", json={
        "statement": "", "actor_role": "student"})
    assert empty.status_code == 422
    preserved = client.get("/api/students/COOP-B001/applications").json()[0]
    assert preserved["application_status"] == "Draft"
    assert preserved["statement"] == "Second version, more detail."

    # A valid submission converts the draft (no orphan draft left behind)
    sent = client.post(f"/api/applications/{body['application_id']}/submit", json={
        "statement": "Final statement.", "actor_role": "student"})
    assert sent.status_code == 201
    assert sent.json()["application_status"] == "Submitted"
    apps = client.get("/api/students/COOP-B001/applications").json()
    assert len(apps) == 1 and apps[0]["application_status"] == "Submitted"
    assert [e["action"] for e in apps[0]["history"]] == ["Draft saved", "Draft saved", "Submitted"]


def test_draft_upsert_one_per_student_and_opportunity(client):
    for statement in ("draft one", "draft two"):
        r = client.post("/api/applications/draft", json={
            "student_id": "COOP-B001", "opportunity_id": "OP-031",
            "statement": statement, "actor_role": "student"})
        assert r.status_code == 201
    apps = client.get("/api/students/COOP-B001/applications").json()
    assert len(apps) == 1 and apps[0]["statement"] == "draft two"

    # A draft is not active: a direct submission for the same opportunity converts it
    direct = submit(client, opportunity_id="OP-031", statement="Direct final statement.")
    assert direct.status_code == 201
    assert direct.json()["application_id"] == apps[0]["application_id"]
    assert direct.json()["application_status"] == "Submitted"
    assert len(client.get("/api/students/COOP-B001/applications").json()) == 1

    # Once active, saving another draft for the same opportunity is blocked
    again = client.post("/api/applications/draft", json={
        "student_id": "COOP-B001", "opportunity_id": "OP-031",
        "statement": "again", "actor_role": "student"})
    assert again.status_code == 409


def test_draft_for_closed_listing_and_wrong_role_blocked(client):
    assert client.post("/api/applications/draft", json={
        "student_id": "COOP-B001", "opportunity_id": "OP-034",
        "statement": "x", "actor_role": "student"}).status_code == 400
    assert client.post("/api/applications/draft", json={
        "student_id": "COOP-B001", "opportunity_id": "OP-028",
        "statement": "x", "actor_role": "employer"}).status_code == 403
    assert client.get("/api/students/COOP-B001/applications").json() == []


def test_only_drafts_can_be_edited(client):
    app_id = submit(client).json()["application_id"]
    edit = client.put(f"/api/applications/{app_id}", json={
        "statement": "too late", "actor_role": "student"})
    assert edit.status_code == 409
    assert "Only drafts" in edit.json()["detail"]


# ---------------------------------------------------------------- P04-04 decisions
def test_decision_flow_records_actor_timestamp_and_next_action(client):
    app_id = submit(client).json()["application_id"]

    step1 = decide(client, app_id, "Under review")
    assert step1.status_code == 201
    assert step1.json()["application_status"] == "Under review"
    assert step1.json()["placement_status"] == "Not placed"

    step2 = decide(client, app_id, "Shortlisted")
    assert step2.status_code == 201
    assert step2.json()["application_status"] == "Shortlisted"

    # The student sees every decision with actor, timestamp and next action (AC1)
    apps = client.get("/api/students/COOP-B001/applications").json()
    history = apps[0]["history"]
    assert [e["action"] for e in history] == ["Submitted", "Under review", "Shortlisted"]
    for event in history[1:]:
        assert event["actor_role"] == "employer" and event["actor_name"]
        assert event["created_at"] and event["next_action"]
    assert history[-1]["next_action"] == "Await employer offer"

    # Active statuses now block duplicates across the whole lifecycle
    assert submit(client).status_code == 409


def test_decline_requires_reason_and_is_shown_to_the_student(client):
    app_id = submit(client, opportunity_id="OP-031", statement="Interested in analytics.").json()["application_id"]
    decide(client, app_id, "Under review")

    no_reason = decide(client, app_id, "Declined")
    assert no_reason.status_code == 422
    assert "reason is required" in no_reason.json()["detail"].lower()

    declined = decide(client, app_id, "Declined", reason="Requires reviewed SQL evidence we could not verify.")
    assert declined.status_code == 201
    apps = client.get("/api/students/COOP-B001/applications").json()
    assert apps[0]["application_status"] == "Declined"
    decline_event = apps[0]["history"][-1]
    assert decline_event["reason"] == "Requires reviewed SQL evidence we could not verify."
    assert "Browse other opportunities" in decline_event["next_action"]
    assert apps[0]["placement_status"] == "Not placed"


def test_invalid_transitions_and_unauthorised_roles_are_blocked(client):
    app_id = submit(client).json()["application_id"]

    # Skipping Under review is not allowed
    assert decide(client, app_id, "Shortlisted").status_code == 409
    # Unknown action
    assert decide(client, app_id, "Teleport").status_code == 422
    # An offer needs a shortlisted application (Sprint 3, P04-05)
    assert decide(client, app_id, "Offer").status_code == 409
    # Wrong roles are blocked with a clear message (AC2)
    for role in ("student", "coordinator", "faculty"):
        denied = decide(client, app_id, "Under review", actor_role=role)
        assert denied.status_code == 403
        assert role in denied.json()["detail"]

    decide(client, app_id, "Under review")
    decide(client, app_id, "Declined", reason="Not a fit for this role.")
    # Declined is terminal: no resurrection, no review, no shortlist
    for action in ("Under review", "Shortlisted", "Declined"):
        assert decide(client, app_id, action, reason="try again").status_code == 409
    # ...and an offer can never follow a decline (AC2)
    offer = decide(client, app_id, "Offer")
    assert offer.status_code == 409 and "never" in offer.json()["detail"].lower()


def test_all_applications_endpoint_shows_everything_with_history(client):
    assert client.get("/api/applications").json() == []
    app_id = submit(client).json()["application_id"]
    client.post("/api/applications/draft", json={
        "student_id": "COOP-B002", "opportunity_id": "OP-031",
        "statement": "", "actor_role": "student"})
    decide(client, app_id, "Under review")

    everything = client.get("/api/applications").json()
    assert {a["application_status"] for a in everything} == {"Draft", "Under review"}
    assert all("history" in a and "student_name" in a and "opportunity_title" in a for a in everything)


# ---------------------------------------------------------------- P05-04 AI assistance
def test_ai_terms_recorded_alongside_the_separate_rules_result(client):
    from app.matching import match
    recs = client.post("/api/students/COOP-B001/recommendations").json()
    op028 = next(r for r in recs if r["opportunity_id"] == "OP-028")

    # The bounded feature identifies the terms it used and records its method version (AC1)
    assert op028["ai_method_version"] == "ai-termmatch-v1"
    by_skill = {m["skill_id"]: m for m in op028["ai_matches"]}
    assert by_skill["SK-VIZ"]["term"] == "tableau" and by_skill["SK-VIZ"]["field"] == "description"
    assert by_skill["SK-VIZ"]["evidence_status"] == "self-declared"
    assert by_skill["SK-SQL"]["term"] == "sql"

    # It cannot invent a qualification: Layla does not hold SK-JIRA, so no Jira match (AC2)
    assert "SK-JIRA" not in by_skill
    assert any("SK-JIRA" in g for g in op028["gaps"])  # the gap is unchanged

    # The rules result is byte-for-byte the pure rules engine's output
    pure = match(STUDENT_FIXTURES["COOP-B001"], OPP_FIXTURES["OP-028"], client.get("/api/skills").json())
    for key in ("score", "eligibility", "compatible", "reasons", "gaps", "unknowns"):
        assert op028[key] == pure[key]


def test_ai_finds_nothing_when_the_student_has_no_relevant_skills(client):
    recs = client.post("/api/students/COOP-B006/recommendations").json()  # Ravi: no skills
    assert recs
    assert all(r["ai_matches"] == [] for r in recs)
    assert all(r["ai_method_version"] == "ai-termmatch-v1" for r in recs)  # version still recorded
    assert all(r["method_version"] == "rules-v2" for r in recs)  # rules baseline still usable


# ---------------------------------------------------------------- P05-05 corrections
def test_flag_correction_accept_and_rematch_stays_traceable(client):
    # Mei Chen (COOP-B003, profile v2, availability unknown) gets recommendations
    first_run = client.post("/api/students/COOP-B003/recommendations").json()
    op028 = next(r for r in first_run if r["opportunity_id"] == "OP-028")
    assert op028["eligibility"] == "unknown"

    # The student flags the result; the coordinator sees reason, field and versions (AC1)
    flag = client.post(f"/api/recommendations/{op028['recommendation_id']}/flags", json={
        "reason": "My availability was updated but matching still says dates are missing.",
        "affected_field": "availability", "actor_role": "student"})
    assert flag.status_code == 201
    cr = flag.json()
    assert cr["correction_id"] == "CR-0001"
    assert (cr["source_module"], cr["status"]) == ("P01", "flagged")
    assert cr["source_version"]["profile_version"] == 2
    assert cr["source_version"]["opportunity_id"] == "OP-028"

    # Only the coordinator can record it
    denied = client.post("/api/corrections/CR-0001/record", json={
        "note": "x", "actor_role": "student"})
    assert denied.status_code == 403
    recorded = client.post("/api/corrections/CR-0001/record", json={
        "note": "Availability looks stale; corrected dates supplied by P01.",
        "actor_role": "coordinator", "actor_name": "COORD-01 (simulated coordinator)"})
    assert recorded.json()["status"] == "recorded"
    assert recorded.json()["coordinator"].startswith("COORD-01")

    # An accepted correction uses a NEW input version and can be rematched (AC2)
    accepted = client.post("/api/corrections/CR-0001/accept", json={
        "actor_role": "coordinator",
        "availability_start": "2027-01-01", "availability_end": "2027-06-30"})
    assert accepted.status_code == 200
    assert accepted.json()["new_profile_version"] == 3

    # The effective profile now has the corrected data and version...
    student = client.get("/api/students/COOP-B003").json()
    assert student["profile_version"] == 3
    assert (student["availability_start"], student["availability_end"]) == ("2027-01-01", "2027-06-30")

    # ...while the P01 fixture table is never silently overwritten
    with db.connect() as conn:
        fixture_row = conn.execute(
            "SELECT profile_version, data FROM students WHERE student_id = 'COOP-B003'").fetchone()
    assert fixture_row["profile_version"] == 2
    assert json.loads(fixture_row["data"])["availability_start"] is None

    # Rematch: the new run uses profile v3 and OP-028 becomes eligible...
    second_run = client.post("/api/students/COOP-B003/recommendations").json()
    op028_new = next(r for r in second_run if r["opportunity_id"] == "OP-028")
    assert op028_new["profile_version"] == 3
    assert op028_new["eligibility"] == "eligible"

    # ...and the original recommendation stays traceable and unchanged (AC2)
    with db.connect() as conn:
        old = conn.execute(
            "SELECT profile_version, eligibility FROM recommendations "
            "WHERE recommendation_id = ?", (op028["recommendation_id"],)).fetchone()
    assert (old["profile_version"], old["eligibility"]) == (2, "unknown")

    runs = client.get("/api/students/COOP-B003/recommendation-runs").json()
    assert len(runs) == 2
    assert [r["profile_version"] for r in runs] == [2, 3]


def test_correction_flow_guards(client):
    recs = client.post("/api/students/COOP-B001/recommendations").json()
    rec_id = recs[0]["recommendation_id"]

    # Missing reason / unknown field / unknown recommendation
    assert client.post(f"/api/recommendations/{rec_id}/flags", json={
        "reason": "", "affected_field": "availability"}).status_code == 422
    assert client.post(f"/api/recommendations/{rec_id}/flags", json={
        "reason": "wrong field", "affected_field": "hair colour"}).status_code == 422
    assert client.post("/api/recommendations/REC-nope/flags", json={
        "reason": "x", "affected_field": "availability"}).status_code == 404

    # Accepting requires recording first, and recording twice is blocked
    cr = client.post(f"/api/recommendations/{rec_id}/flags", json={
        "reason": "check my availability", "affected_field": "availability"}).json()
    too_early = client.post(f"/api/corrections/{cr['correction_id']}/accept", json={"actor_role": "coordinator"})
    assert too_early.status_code == 409
    client.post(f"/api/corrections/{cr['correction_id']}/record", json={"actor_role": "coordinator", "note": "n"})
    twice = client.post(f"/api/corrections/{cr['correction_id']}/record", json={"actor_role": "coordinator", "note": "n"})
    assert twice.status_code == 409

    # Availability acceptances need both dates
    incomplete = client.post(f"/api/corrections/{cr['correction_id']}/accept", json={
        "actor_role": "coordinator", "availability_start": "2027-01-01"})
    assert incomplete.status_code == 422


def test_p03_and_skill_corrections_are_recorded_only(client):
    recs = client.post("/api/students/COOP-B001/recommendations").json()

    listing = client.post(f"/api/recommendations/{recs[0]['recommendation_id']}/flags", json={
        "reason": "dates on the listing look wrong", "affected_field": "listing dates"}).json()
    assert listing["source_module"] == "P03"
    client.post(f"/api/corrections/{listing['correction_id']}/record", json={"actor_role": "coordinator", "note": "n"})
    p03 = client.post(f"/api/corrections/{listing['correction_id']}/accept", json={"actor_role": "coordinator"})
    assert p03.status_code == 422 and "P03" in p03.json()["detail"]

    skills = client.post(f"/api/recommendations/{recs[1]['recommendation_id']}/flags", json={
        "reason": "my SQL evidence is missing", "affected_field": "skills"}).json()
    client.post(f"/api/corrections/{skills['correction_id']}/record", json={"actor_role": "coordinator", "note": "n"})
    p01_skills = client.post(f"/api/corrections/{skills['correction_id']}/accept", json={"actor_role": "coordinator"})
    assert p01_skills.status_code == 422 and "P01/P06" in p01_skills.json()["detail"]

    # Both stay recorded, visible in the coordinator queue
    corrections = client.get("/api/corrections").json()
    assert [c["status"] for c in corrections] == ["recorded", "recorded"]
