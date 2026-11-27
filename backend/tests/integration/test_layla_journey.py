"""Cross-team journey on one database: every handoff between P01-P07 is a live call.

The binder's demonstration thread (docs/PLAN.md "Target demo"): an employer listing goes through P02/P03,
Layla's Jira gap from P05 is prepared in P06, the reviewed evidence reaches P01 and matching reruns, the P04
offer is confirmed and P07 runs the placement to the final review."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

S, EMP, COORD = {"actor_role": "student"}, {"actor_role": "employer"}, {"actor_role": "coordinator"}
REV, SUP, ADV = {"actor_role": "reviewer"}, {"actor_role": "supervisor"}, {"actor_role": "advisor"}
LAYLA = "COOP-B001"
EXPLANATION = ("I created two work items, gave every item an owner, and moved OPS-101 from To do through In progress "
               "to Done. Each move has a reason so Omar and Priya can see what changed and what happens next.")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATA_SOURCE", "p01p03")
    with TestClient(app) as c:
        assert c.post("/api/demo/reset?scenario=fresh").json()["today"] == "2026-11-23"
        yield c


def ok(response, code=(200, 201)):
    assert response.status_code in ((code,) if isinstance(code, int) else code), response.text
    return response.json()


def test_layla_end_to_end(client):
    # P02 -> P03: a new listing is submitted, returned, resubmitted as v2, approved and published.
    opp = ok(client.post("/api/submissions", json={
        **EMP, "hr_authorized": True, "organization_name": "Emirates Group (fictional)", "title": "Ground Ops Data Intern",
        "description": "Weekly ground-operations reporting.", "location": "Dubai", "work_mode": "on-site",
        "sector": "aviation", "start_date": "2027-02-01", "end_date": "2027-05-31", "required_skills": ["SK-SQL"]}))
    oid = opp["opportunity_id"]
    ok(client.post(f"/api/submissions/{oid}/decision", json={**COORD, "decision": "return", "reason": "Name the supervisor."}))
    ok(client.post(f"/api/submissions/{oid}/resubmit", json={
        **EMP, "hr_authorized": True, "organization_name": "Emirates Group (fictional)", "title": "Ground Ops Data Intern",
        "description": "Weekly ground-operations reporting.", "location": "Dubai", "work_mode": "on-site",
        "sector": "aviation", "start_date": "2027-02-01", "end_date": "2027-05-31", "required_skills": ["SK-SQL"],
        "supervisor_name": "R. Khan", "supervisor_contact": "r.khan@example.test"}))
    ok(client.post(f"/api/submissions/{oid}/decision", json={**COORD, "decision": "approve"}))
    ok(client.post(f"/api/opportunities/{oid}/publish", json=COORD))

    # P01 -> P05: Layla's profile v2 is matched; OP-028 lists Jira (self-declared) as an evidence gap.
    recs = ok(client.post(f"/api/students/{LAYLA}/recommendations"))
    by_id = {r["opportunity_id"]: r for r in recs}
    assert oid in by_id and by_id[oid]["opportunity_version"] == 2
    rec = by_id["OP-028"]
    assert rec["profile_version"] == 2 and any("SK-JIRA" in g for g in rec["gaps"])

    # P05 -> P06: Prepare -> the gap is on her plan straight away.
    gap = ok(client.post(f"/api/recommendations/{rec['recommendation_id']}/gaps/SK-JIRA/handoff", json=S))
    assert gap["p06_status"] == "open"
    ok(client.post(f"/api/p06/students/{LAYLA}/resources/MOD-JIRA-101/complete", json=S))
    ok(client.put(f"/api/p06/students/{LAYLA}/board/items/OPS-101/assignee", json={**S, "assignee": "Layla Hassan"}))
    ok(client.post(f"/api/p06/students/{LAYLA}/board/items/OPS-101/move", json={**S, "to": "done", "reason": "Cleaned file is shared"}))
    ev = ok(client.post(f"/api/p06/students/{LAYLA}/submissions", json={**S, "module_id": "MOD-JIRA-101", "explanation": EXPLANATION}))
    ok(client.post(f"/api/p06/submissions/{ev['evidence_id']}/review",
                   json={**REV, "decision": "revision", "checklist": [True, True, False, True], "comment": "Move one item through In progress."}))
    ok(client.post(f"/api/p06/students/{LAYLA}/submissions", json={**S, "module_id": "MOD-JIRA-101", "explanation": EXPLANATION + " Revised."}))

    # P06 -> P01 -> P05: demonstrated -> profile v3 with reviewed Jira -> matching reruns, old run kept.
    done = ok(client.post(f"/api/p06/submissions/{ev['evidence_id']}/review",
                          json={**REV, "decision": "demonstrated", "checklist": [True] * 4}))
    assert done["p01_profile_version"] == 3
    runs = ok(client.get(f"/api/students/{LAYLA}/recommendation-runs"))
    assert [r["profile_version"] for r in runs] == [2, 3]
    rerun = {r["opportunity_id"]: r for r in ok(client.get(f"/api/students/{LAYLA}/recommendations"))}
    assert not any("SK-JIRA" in g for g in rerun["OP-028"]["gaps"])

    # P04: apply on v3, employer review, offer, acceptance (not yet a placement).
    client.put("/api/demo/today", json={"today": "2026-12-01"})
    app_ = ok(client.post("/api/applications", json={**S, "student_id": LAYLA, "opportunity_id": "OP-028",
                                                      "statement": "Aviation analytics is my goal."}))
    assert app_["profile_version"] == 3
    aid = app_["application_id"]
    for action in ("Under review", "Shortlisted", "Offer"):
        ok(client.post(f"/api/applications/{aid}/decisions", json={**EMP, "action": action}))
    accepted = ok(client.post(f"/api/applications/{aid}/offer-response", json={**S, "response": "accept"}))
    assert accepted["placement_status"] == "Awaiting university confirmation"
    assert ok(client.get(f"/api/p07/students/{LAYLA}"))["placement"] is None

    # P04 -> P07: the coordinator confirms once; P07 receives it in the same transaction.
    placement = ok(client.post(f"/api/applications/{aid}/confirm-placement", json=COORD))
    pid = placement["placement_id"]
    assert placement["p07_handoff"]["receipt_status"] == "received"
    again = ok(client.post(f"/api/applications/{aid}/confirm-placement", json=COORD))
    assert again["already_confirmed"] and len(ok(client.get("/api/p07/placements"))) == 1
    record = ok(client.get(f"/api/p07/students/{LAYLA}"))
    assert record["placement"]["placement_id"] == pid and record["placement"]["academic_advisor"] is None
    assert record["readiness"]["demonstrated"][0]["evidence_id"] == ev["evidence_id"]  # P06 -> P07

    # P07: advisor, agreement, a revised log, a midpoint action, the final review.
    ok(client.post(f"/api/p07/placements/{pid}/advisor", json={**COORD, "advisor": "Dr. Ahmed Youssef"}))
    for text, los in (("Build a weekly on-time-performance dashboard", ["LO1"]), ("Present one analysis to station ops", ["LO2"]),
                      ("Keep a weekly reflective practice log", ["LO4"])):
        ok(client.post(f"/api/p07/placements/{pid}/agreement/goals", json={**S, "text": text, "outcomes": los}))
    for role in (S, SUP, ADV):
        ok(client.post(f"/api/p07/placements/{pid}/agreement/sign", json=role))
    client.put("/api/demo/today", json={"today": "2027-02-18"})
    entry = ok(client.post(f"/api/p07/placements/{pid}/logs", json={**S, "goal_id": "G1", "text": "Finished the dashboard and shared it with the team today.",
                                                                     "new_evidence_title": "OTP dashboard v1"}))
    ok(client.post(f"/api/p07/logs/{entry['log_id']}/request-detail", json={**SUP, "text": "Say who uses it and why."}))
    ok(client.post(f"/api/p07/logs/{entry['log_id']}/revise", json={**S, "text": "Released dashboard v1 with three views that the ops leads use every Monday."}))
    ok(client.post(f"/api/p07/logs/{entry['log_id']}/acknowledge", json=SUP))
    ok(client.post(f"/api/p07/placements/{pid}/actions", json={**ADV, "text": "Agree a date for the ops meeting", "owner": "supervisor", "due": "2027-03-10"}))
    ok(client.put(f"/api/p07/placements/{pid}/judgements/LO1", json={**ADV, "level": "achieved", "evidence_ids": ["EV-0101"]}))
    client.put("/api/demo/today", json={"today": "2027-06-04"})
    ok(client.post(f"/api/p07/placements/{pid}/employer-feedback", json={**SUP, "would_host": "yes",
                   "text": "Layla delivered a dashboard the team now uses weekly and presented clearly."}))
    final = ok(client.post(f"/api/p07/placements/{pid}/final-review", json={
        **ADV, "summary": "A dashboard in weekly use and a clear presentation; teamwork evidence still to come.",
        "next_goal": "Own one analysis end to end", "outcomes": {"LO1": "achieved", "LO2": "developing", "LO3": "none", "LO4": "none"}}))
    assert final["advisor"]["outcomes"]["LO1"] == "achieved"

    # Every handoff left a record, in order.
    kinds = [(h["from_module"], h["to_module"], h["kind"]) for h in ok(client.get("/api/handoffs"))]
    assert kinds == [("P05", "P06", "skill_gap"), ("P06", "P01", "reviewed_skill"), ("P06", "P01", "reviewed_skill"),
                     ("P06", "P07", "readiness_summary"), ("P04", "P07", "confirmed_placement")]
    modules = {e["module"] for e in ok(client.get("/api/events?limit=500"))}
    assert modules >= {"P01", "P02", "P03", "P06", "P07"}


def test_negative_cases_across_modules(client):
    # Closed listing: no application.
    ok(client.post("/api/opportunities/OP-028/close", json=COORD))
    closed = client.post("/api/applications", json={**S, "student_id": LAYLA, "opportunity_id": "OP-028", "statement": "x"})
    assert closed.status_code == 400
    # Duplicate active application.
    ok(client.post("/api/applications", json={**S, "student_id": LAYLA, "opportunity_id": "OP-031", "statement": "Energy data fits."}))
    dup = client.post("/api/applications", json={**S, "student_id": LAYLA, "opportunity_id": "OP-031", "statement": "Again"})
    assert dup.status_code == 409
    # Placement that is not university confirmed never reaches P07.
    r = ok(client.post("/api/p07/placements/import", json={**COORD, "records": [{
        "placement_id": "PL-0002", "status": "Awaiting university confirmation", "student_id": LAYLA, "opportunity_id": "OP-031",
        "employer_name": "Desert Grid Energy", "period_start": "2027-02-01", "period_end": "2027-05-31"}]}))
    assert r["rejected"] and ok(client.get(f"/api/p07/students/{LAYLA}"))["placement"] is None
    # Confirming an application without an accepted offer is blocked.
    apps = ok(client.get(f"/api/students/{LAYLA}/applications"))
    assert client.post(f"/api/applications/{apps[0]['application_id']}/confirm-placement", json=COORD).status_code == 409
    # Gap for a skill without a P06 module is refused on the plan.
    assert client.post(f"/api/p06/students/{LAYLA}/gaps", json={**COORD, "skill_id": "SK-FIGMA", "reason": "Design work"}).status_code == 422


@pytest.mark.parametrize("scenario,today,profile_version,has_placement", [
    ("fresh", "2026-11-23", 2, False), ("reviewed", "2026-11-28", 3, False),
    ("midpoint", "2027-03-18", 3, True), ("end", "2027-06-04", 3, True)])
def test_scenarios_load_through_the_real_endpoints(client, scenario, today, profile_version, has_placement):
    settings = ok(client.post(f"/api/demo/reset?scenario={scenario}"))
    assert (settings["scenario"], settings["today"]) == (scenario, today)
    assert ok(client.get(f"/api/students/{LAYLA}"))["profile_version"] == profile_version
    record = ok(client.get(f"/api/p07/students/{LAYLA}"))
    assert (record["placement"] is not None) == has_placement
    if scenario == "midpoint":
        assert record["agreement"]["status"] == "agreed" and len(record["logs"]) == 3
        assert record["counts"]["overdue_actions"] == 1  # ACT-01 was due 10 Mar
    if scenario == "end":
        assert record["final"]["employer"] and record["final"]["advisor"] is None
        assert [l["period"] for l in record["logs"]][-1] == "P2"


def test_reset_clears_activity_but_keeps_seed(client):
    ok(client.post("/api/demo/reset?scenario=end"))
    ok(client.post("/api/demo/reset?scenario=fresh"))
    assert ok(client.get("/api/handoffs")) == [] and ok(client.get("/api/applications")) == []
    assert len(ok(client.get("/api/students"))) == 4
    assert client.post("/api/demo/reset?scenario=nope").status_code == 422
