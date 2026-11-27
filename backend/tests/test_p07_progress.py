"""P07 co-op learning progress, ported from Team P6/P7's acceptance checks
(legacy/p06-p07-waypoint/source/tests/acceptance_test.py P07-AC1..4, P07-X, P07-EXC) and integration checks
(S3-PL: placement import rules) as API tests."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

S = {"actor_role": "student"}
COORD = {"actor_role": "coordinator"}
SUP = {"actor_role": "supervisor"}
ADV = {"actor_role": "advisor"}
LAYLA = "COOP-B001"
PL = {"placement_id": "PL-0001", "status": "university_confirmed", "student_id": LAYLA, "opportunity_id": "OP-028",
      "employer_name": "Emirates Group", "location": "Dubai", "role": "Aviation Analytics Intern",
      "period_start": "2027-02-01", "period_end": "2027-05-31", "academic_advisor": None, "opportunity_version": 2}
GOALS = [("Build a weekly on-time-performance dashboard the team uses", ["LO1", "LO2"]),
         ("Present one analysis to the station operations meeting", ["LO2", "LO3"]),
         ("Keep a weekly reflective log on professional practice", ["LO4"])]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATA_SOURCE", "p01p03")
    with TestClient(app) as c:
        c.post("/api/demo/reset?scenario=fresh")
        yield c


def today(client, value):
    client.put("/api/demo/today", json={"today": value})


def with_placement(client):
    r = client.post("/api/p07/placements/import", json={**COORD, "records": [PL]}).json()
    assert r["added"], r
    return "PL-0001"


def agreed(client):
    pid = with_placement(client)
    client.post(f"/api/p07/placements/{pid}/advisor", json={**COORD, "advisor": "Dr. Ahmed Youssef"})
    for text, los in GOALS:
        client.post(f"/api/p07/placements/{pid}/agreement/goals", json={**S, "text": text, "outcomes": los})
    for role in (S, SUP, ADV):
        assert client.post(f"/api/p07/placements/{pid}/agreement/sign", json=role).status_code == 201
    return pid


def log(client, pid, text="Mapped the on-time performance data sources and agreed the weekly cut-off.", **extra):
    return client.post(f"/api/p07/placements/{pid}/logs", json={**S, "text": text, "goal_id": "G1", **extra})


# --- Placement receipt (S3-PL) ---
def test_only_university_confirmed_placements_are_accepted(client):
    r = client.post("/api/p07/placements/import", json={**COORD, "records": [
        {**PL, "placement_id": "PL-0002", "status": "Awaiting university confirmation"},
        {**PL, "placement_id": "PL-0003", "period_end": "2027-01-01"},
        {**PL, "placement_id": "PL-0004", "opportunity_id": "OP-039"},
        {**PL, "placement_id": "PL-0005", "student_id": "COOP-B999"},
        {k: v for k, v in PL.items() if k != "employer_name"},
    ]}).json()
    assert r["added"] == [] and len(r["rejected"]) == 5
    assert "university_confirmed" in r["rejected"][0] and "date range" in r["rejected"][1]
    assert "published" in r["rejected"][2] and "P01" in r["rejected"][3] and "employer_name" in r["rejected"][4]
    assert client.get(f"/api/p07/students/{LAYLA}").json()["placement"] is None


def test_placement_once_and_one_active_per_student(client):
    with_placement(client)
    again = client.post("/api/p07/placements/import", json={**COORD, "records": [PL, {**PL, "placement_id": "PL-0009"}]}).json()
    assert len(again["skipped"]) == 1 and "already received" in again["skipped"][0]
    assert len(again["rejected"]) == 1 and "active placement" in again["rejected"][0]


def test_supervisor_contact_hidden_from_students(client):
    with_placement(client)
    student = client.get(f"/api/p07/students/{LAYLA}").json()["placement"]
    staff = client.get(f"/api/p07/students/{LAYLA}?viewer_role=advisor").json()["placement"]
    assert "supervisor_contact" not in student
    assert staff["supervisor_contact"] and staff["supervisor_name"]  # filled from the P03 listing


# --- Learning agreement ---
def test_agreement_needs_three_mapped_goals_and_an_assigned_advisor(client):
    pid = with_placement(client)
    assert client.post(f"/api/p07/placements/{pid}/agreement/goals", json={**S, "text": "Too short", "outcomes": ["LO1"]}).status_code == 422
    assert client.post(f"/api/p07/placements/{pid}/agreement/goals", json={**S, "text": GOALS[0][0], "outcomes": []}).status_code == 422
    for text, los in GOALS[:2]:
        client.post(f"/api/p07/placements/{pid}/agreement/goals", json={**S, "text": text, "outcomes": los})
    early = client.post(f"/api/p07/placements/{pid}/agreement/sign", json=S)
    assert early.status_code == 409 and "three goals" in early.json()["detail"]
    client.post(f"/api/p07/placements/{pid}/agreement/goals", json={**S, "text": GOALS[2][0], "outcomes": GOALS[2][1]})
    assert client.post(f"/api/p07/placements/{pid}/agreement/goals", json={**S, "text": GOALS[0][0], "outcomes": ["LO1"]}).status_code == 409
    no_adv = client.post(f"/api/p07/placements/{pid}/agreement/sign", json=ADV)
    assert no_adv.status_code == 409 and "advisor" in no_adv.json()["detail"]
    client.post(f"/api/p07/placements/{pid}/advisor", json={**COORD, "advisor": "Dr. Ahmed Youssef"})
    for role in (S, SUP):
        client.post(f"/api/p07/placements/{pid}/agreement/sign", json=role)
    assert client.get(f"/api/p07/students/{LAYLA}").json()["agreement"]["status"] == "draft"
    done = client.post(f"/api/p07/placements/{pid}/agreement/sign", json=ADV).json()
    assert done["status"] == "agreed" and all(done["signoffs"].values())
    locked = client.post(f"/api/p07/placements/{pid}/agreement/goals/G1/remove", json=S)
    assert locked.status_code == 409


def test_only_coordinator_assigns_a_known_advisor(client):
    pid = with_placement(client)
    assert client.post(f"/api/p07/placements/{pid}/advisor", json={**S, "advisor": "Dr. Ahmed Youssef"}).status_code == 403
    assert client.post(f"/api/p07/placements/{pid}/advisor", json={**COORD, "advisor": "Prof. Nobody"}).status_code == 422


# --- AC1: log, feedback request, revision ---
def test_p07_ac1_log_feedback_and_revision_keep_history(client):
    pid = agreed(client)
    today(client, "2027-02-18")
    assert log(client, pid, "Too short").status_code == 422
    entry = log(client, pid, "Finished the dashboard and shared it with the team today.",
                new_evidence_title="OTP dashboard v1, screenshot and notes").json()
    assert (entry["log_id"], entry["week"], entry["period"], entry["versions"][0]["evidence"]) == ("LOG-01", 3, "P1", ["EV-0101"])
    assert client.post(f"/api/p07/logs/LOG-01/request-detail", json={**SUP, "text": "More"}).status_code == 422
    req = client.post(f"/api/p07/logs/LOG-01/request-detail",
                      json={**SUP, "text": "Say what it shows and who uses it."}).json()
    assert req["status"] == "feedback" and req["feedback"][-1]["type"] == "request"
    same = client.post(f"/api/p07/logs/LOG-01/revise", json={**S, "text": entry["versions"][0]["text"]})
    assert same.status_code == 422
    today(client, "2027-02-21")
    rev = client.post(f"/api/p07/logs/LOG-01/revise", json={**S, "text": "Released dashboard v1 with three views: daily OTP, "
                                                              "delay causes and gate turnaround for the ops leads."}).json()
    assert rev["status"] == "revised" and [v["v"] for v in rev["versions"]] == [1, 2]
    assert rev["versions"][1]["evidence"] == ["EV-0101"]
    ack = client.post(f"/api/p07/logs/LOG-01/acknowledge", json=SUP).json()
    assert ack["status"] == "acknowledged"
    assert [f["type"] for f in ack["feedback"]] == ["request", "note"]  # original, revision and feedback all kept
    assert client.post(f"/api/p07/logs/LOG-01/acknowledge", json=SUP).status_code == 409


# --- AC2: judgements need evidence; milestones are not outcomes ---
def test_p07_ac2_judgement_needs_evidence_and_missing_evidence_is_shown(client):
    pid = agreed(client)
    today(client, "2027-02-18")
    log(client, pid, new_evidence_title="OTP dashboard v1, screenshot and notes")
    client.post(f"/api/p07/placements/{pid}/milestones", json={**SUP, "text": "Dashboard v1 released"})
    client.put("/api/p07/milestones/MS-1", json={**SUP, "done": True})
    no_ev = client.put(f"/api/p07/placements/{pid}/judgements/LO1", json={**ADV, "level": "developing"})
    assert no_ev.status_code == 422 and "milestone" in no_ev.json()["detail"]
    assert client.put(f"/api/p07/placements/{pid}/judgements/LO1",
                      json={**ADV, "level": "developing", "evidence_ids": ["EV-9999"]}).status_code == 422
    ok = client.put(f"/api/p07/placements/{pid}/judgements/LO1", json={**ADV, "level": "developing", "evidence_ids": ["EV-0101"]})
    assert ok.json()["by"] == "Dr. Ahmed Youssef"
    record = client.get(f"/api/p07/students/{LAYLA}").json()
    by_lo = {j["outcome_id"]: j for j in record["judgements"]}
    assert by_lo["LO1"]["evidence_missing"] is False and by_lo["LO3"]["evidence_missing"] is True
    assert record["milestones"][0]["done"] is True


# --- AC3: actions with owner, due date, closure; overdue visible ---
def test_p07_ac3_actions_overdue_and_closure(client):
    pid = agreed(client)
    today(client, "2027-03-02")
    assert client.post(f"/api/p07/placements/{pid}/actions", json={**ADV, "text": "Agree a date", "owner": "boss", "due": "2027-03-10"}).status_code == 422
    act = client.post(f"/api/p07/placements/{pid}/actions",
                      json={**ADV, "text": "Agree a date to present at the ops meeting", "owner": "supervisor", "due": "2027-03-10"}).json()
    assert act["action_id"] == "ACT-01" and act["overdue"] is False
    today(client, "2027-03-18")
    record = client.get(f"/api/p07/students/{LAYLA}").json()
    assert record["actions"][0]["overdue"] is True and record["counts"]["overdue_actions"] == 1
    assert client.post("/api/p07/actions/ACT-01/close", json={**S, "closure": "Done it already"}).status_code == 403
    assert client.post("/api/p07/actions/ACT-01/close", json={**SUP, "closure": "ok"}).status_code == 422
    closed = client.post("/api/p07/actions/ACT-01/close", json={**SUP, "closure": "Meeting date agreed for 8 April"}).json()
    assert (closed["status"], closed["overdue"], closed["closed_at"]) == ("closed", False, "2027-03-18")


# --- AC4: employer feedback separate; achieved needs in-period evidence ---
def test_p07_ac4_final_review_rules(client):
    pid = agreed(client)
    today(client, "2027-02-18")
    log(client, pid, new_evidence_title="OTP dashboard v1")                     # EV-0101, in period
    today(client, "2027-06-02")
    late = log(client, pid, "Planned the night-shift dashboard for the next period with ops.",
               new_evidence_title="Night-shift plan (Period 2)").json()          # EV-0102, Period 2
    assert late["period"] == "P2"
    client.put(f"/api/p07/placements/{pid}/judgements/LO1", json={**ADV, "level": "achieved", "evidence_ids": ["EV-0101"]})
    client.put(f"/api/p07/placements/{pid}/judgements/LO2", json={**ADV, "level": "developing", "evidence_ids": ["EV-0102"]})
    assert client.post(f"/api/p07/placements/{pid}/employer-feedback", json={**SUP, "text": "Good work", "would_host": "yes"}).status_code == 422
    fb = client.post(f"/api/p07/placements/{pid}/employer-feedback", json={
        **SUP, "would_host": "yes", "text": "Layla delivered a dashboard the team now uses every week and presented well."}).json()
    assert fb["employer"]["by"] == "R. Khan" and fb["advisor"] is None

    final = {**ADV, "summary": "Strong period with a dashboard in weekly use and a clear presentation to managers.",
             "next_goal": "Own one analysis end to end"}
    bad = client.post(f"/api/p07/placements/{pid}/final-review",
                      json={**final, "outcomes": {"LO1": "achieved", "LO2": "achieved", "LO3": "none", "LO4": "none"}})
    assert bad.status_code == 422 and "LO2" in bad.json()["detail"]["errors"]["rule"]  # only Period 2 evidence
    incomplete = client.post(f"/api/p07/placements/{pid}/final-review", json={**final, "outcomes": {"LO1": "achieved"}})
    assert "outcomes" in incomplete.json()["detail"]["errors"]
    ok = client.post(f"/api/p07/placements/{pid}/final-review",
                     json={**final, "outcomes": {"LO1": "achieved", "LO2": "developing", "LO3": "none", "LO4": "none"}}).json()
    assert ok["advisor"]["period"] == "P1" and ok["employer"]["text"].startswith("Layla")  # kept separately
    assert client.post(f"/api/p07/placements/{pid}/final-review", json={**final, "outcomes": ok["advisor"]["outcomes"]}).status_code == 409


def test_reviewed_p06_evidence_counts_for_achieved(client):
    """Reviewed P06 evidence (dated before the period) may support an outcome; that is the agreed exception."""
    client.post("/api/demo/reset?scenario=reviewed")
    pid = agreed(client)
    record = client.get(f"/api/p07/students/{LAYLA}").json()
    p06 = [e for e in record["evidence"] if e["source"] == "P06"]
    assert p06 and p06[0]["evidence_id"] == "EV-0001" and p06[0]["in_period"] is False
    assert record["readiness"]["demonstrated"][0]["skill_id"] == "SK-JIRA"
    client.put(f"/api/p07/placements/{pid}/judgements/LO3", json={**ADV, "level": "achieved", "evidence_ids": ["EV-0001"]})
    ok = client.post(f"/api/p07/placements/{pid}/final-review", json={
        **ADV, "summary": "Teamwork shown through the reviewed Jira board work and weekly stand-ups with the team.",
        "next_goal": "Lead one sprint board", "outcomes": {"LO1": "none", "LO2": "none", "LO3": "achieved", "LO4": "none"}})
    assert ok.status_code == 201


def test_roles_are_enforced(client):
    pid = agreed(client)
    assert log(client, pid, actor_role="supervisor").status_code == 403
    assert client.put(f"/api/p07/placements/{pid}/judgements/LO1", json={**SUP, "level": "none"}).status_code == 403
    assert client.post(f"/api/p07/placements/{pid}/final-review", json={**COORD, "outcomes": {}, "summary": "", "next_goal": ""}).status_code == 403
