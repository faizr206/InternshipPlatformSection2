"""P06 internship preparation, ported from Team P6/P7's acceptance checks
(legacy/p06-p07-waypoint/source/tests/acceptance_test.py P06-AC1..4, P06-X, P06-EXC) as API tests."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

S = {"actor_role": "student"}
COORD = {"actor_role": "coordinator"}
REV = {"actor_role": "reviewer"}
LAYLA = "COOP-B001"
GOOD = ("I created two work items for the sprint, gave every item an owner, and moved OPS-101 from To do through "
        "In progress to Done with a reason on each move so the team can follow what changed next.")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATA_SOURCE", "p01p03")
    with TestClient(app) as c:
        c.post("/api/demo/reset?scenario=fresh")
        yield c


def jira_gap_from_p05(client):
    recs = client.post(f"/api/students/{LAYLA}/recommendations").json()
    rec = next(r for r in recs if r["opportunity_id"] == "OP-028")
    return client.post(f"/api/recommendations/{rec['recommendation_id']}/gaps/SK-JIRA/handoff", json=S).json()


def prepare_board(client):
    client.put(f"/api/p06/students/{LAYLA}/board/items/OPS-101/assignee", json={**S, "assignee": "Layla Hassan"})
    client.post(f"/api/p06/students/{LAYLA}/board/items/OPS-101/move", json={**S, "to": "inprogress", "reason": "Started the cleaning work"})
    client.post(f"/api/p06/students/{LAYLA}/board/items/OPS-101/move", json={**S, "to": "done", "reason": "Cleaned file shared with team"})


def submit(client, text=GOOD):
    return client.post(f"/api/p06/students/{LAYLA}/submissions", json={**S, "module_id": "MOD-JIRA-101", "explanation": text})


def review(client, ev, decision, checklist, comment=None):
    return client.post(f"/api/p06/submissions/{ev}/review",
                       json={**REV, "decision": decision, "checklist": checklist, "comment": comment})


def test_catalogue_has_one_full_module_and_two_outlines(client):
    mods = {m["module_id"]: m for m in client.get("/api/p06/modules").json()}
    assert {k: m["status"] for k, m in mods.items()} == {"MOD-JIRA-101": "full", "MOD-SQL-101": "outline", "MOD-VIZ-101": "outline"}
    jira = mods["MOD-JIRA-101"]
    assert jira["outcome"] and jira["resource"]["parts"] and jira["task"] and len(jira["checklist"]) == 4


def test_p06_ac1_named_gap_leads_to_module_and_required_evidence(client):
    """AC1: Layla moves from a named Jira gap (live from P05) to the module and sees what evidence is needed."""
    gap = jira_gap_from_p05(client)
    assert gap["p06_status"] == "open"
    plan = client.get(f"/api/p06/students/{LAYLA}/plan").json()
    [g] = plan["gaps"]
    assert (g["gap_id"], g["skill_id"], g["source"], g["module_id"]) == (gap["gap_id"], "SK-JIRA", "P05", "MOD-JIRA-101")
    assert g["opportunity_id"] == "OP-028" and g["profile_version"] == 2 and g["recommendation_id"]
    assert [s["key"] for s in g["chain"]] == ["gap", "learn", "submit", "review", "demonstrated"]
    assert next(s for s in g["chain"] if s["current"])["key"] == "learn"
    assert plan["next_step"]["kind"] == "learn"


def test_p06_ac2_resource_completion_never_demonstrates(client):
    jira_gap_from_p05(client)
    r = client.post(f"/api/p06/students/{LAYLA}/resources/MOD-JIRA-101/complete", json=S).json()
    assert r["skill_status"] == "none" and "not demonstrated" in r["note"]
    plan = client.get(f"/api/p06/students/{LAYLA}/plan").json()
    assert plan["gaps"][0]["skill_status"] == "none" and plan["next_step"]["kind"] == "practise"
    jira = [s for s in client.get(f"/api/students/{LAYLA}").json()["skills"] if s["skill_id"] == "SK-JIRA"][0]
    assert jira["evidence_status"] == "self_declared"


def test_p06_ac3_board_needs_owner_reason_and_specific_summary(client):
    assert client.post(f"/api/p06/students/{LAYLA}/board/items", json={**S, "summary": "do it"}).status_code == 422
    board = client.post(f"/api/p06/students/{LAYLA}/board/items", json={**S, "summary": "Check gate-time gaps in March"}).json()
    key = board["items"][-1]["key"]
    assert key == "OPS-104" and board["items"][-1]["assignee"] == ""
    no_owner = client.post(f"/api/p06/students/{LAYLA}/board/items/{key}/move", json={**S, "to": "inprogress", "reason": "Starting this one now"})
    assert no_owner.status_code == 409 and "owner" in no_owner.json()["detail"]
    client.put(f"/api/p06/students/{LAYLA}/board/items/{key}/assignee", json={**S, "assignee": "Priya Nair"})
    assert client.post(f"/api/p06/students/{LAYLA}/board/items/{key}/move", json={**S, "to": "inprogress", "reason": "go"}).status_code == 422
    moved = client.post(f"/api/p06/students/{LAYLA}/board/items/{key}/move", json={**S, "to": "inprogress", "reason": "Priya started the extract"}).json()
    assert moved["log"][-1] == {"key": key, "from": "todo", "to": "inprogress", "reason": "Priya started the extract", "at": "2026-11-23"}
    assert client.put(f"/api/p06/students/{LAYLA}/board/items/{key}/assignee", json={**S, "assignee": "Someone Else"}).status_code == 422


def test_explanation_needs_25_words_and_outline_modules_are_closed(client):
    short = submit(client, "Moved one item.")
    assert short.status_code == 422 and "3 words" in short.json()["detail"]
    outline = client.post(f"/api/p06/students/{LAYLA}/submissions", json={**S, "module_id": "MOD-SQL-101", "explanation": GOOD})
    assert outline.status_code == 409


def test_p06_ac4_revision_then_demonstrated_reaches_p01_and_rematches(client):
    """AC4: revision requested, resubmission checked against the checklist, outcome recorded; P01 receives skill,
    evidence ID, outcome and review date -> a new profile version, and P05 matching reruns (P05-07)."""
    jira_gap_from_p05(client)
    prepare_board(client)
    ev = submit(client).json()["evidence_id"]
    assert ev == "EV-0001"
    assert client.get("/api/p06/review-queue").json()[0]["evidence_id"] == ev
    assert submit(client).status_code == 409  # already with the reviewer

    assert review(client, ev, "revision", [True, True, True, False]).status_code == 422  # comment required
    r = review(client, ev, "revision", [True, True, True, False], "Explain why each status changed.").json()
    assert r["status"] == "revision" and r["p01_profile_version"] is None
    assert client.get(f"/api/students/{LAYLA}").json()["profile_version"] == 2

    v2 = submit(client, GOOD + " Each reason now says what happens next.").json()
    assert [v["v"] for v in v2["versions"]] == [1, 2] and v2["status"] == "submitted"
    bad = review(client, ev, "demonstrated", [True, True, True, False])
    assert bad.status_code == 422 and "criteria" in bad.json()["detail"]
    done = review(client, ev, "demonstrated", [True, True, True, True]).json()
    assert done["status"] == "demonstrated" and done["p01_profile_version"] == 3 and done["rematched"]
    assert [x["decision"] for x in done["reviews"]] == ["revision", "demonstrated"]

    profile = client.get(f"/api/students/{LAYLA}").json()
    jira = [s for s in profile["skills"] if s["skill_id"] == "SK-JIRA"][0]
    assert (jira["evidence_status"], jira["evidence_id"], jira["reviewed_by"]) == ("reviewed", "EV-0001", "Maya Chen")
    runs = client.get(f"/api/students/{LAYLA}/recommendation-runs").json()
    assert [r["profile_version"] for r in runs] == [2, 3]
    latest = {r["opportunity_id"]: r for r in client.get(f"/api/students/{LAYLA}/recommendations").json()}
    assert not any("SK-JIRA" in g for g in latest["OP-028"]["gaps"])

    p01 = client.get(f"/api/handoffs?to_module=P01").json()
    assert [h["payload"]["outcome"] for h in p01] == ["needs_more_evidence", "demonstrated"]
    assert set(p01[-1]["payload"]) == {"student_id", "skill_id", "evidence_id", "outcome", "reviewer", "review_date"}
    plan = client.get(f"/api/p06/students/{LAYLA}/plan").json()
    assert plan["gaps"][0]["status"] == "closed" and plan["next_step"]["kind"] == "done"
    readiness = client.get(f"/api/p06/students/{LAYLA}/readiness").json()
    assert readiness["demonstrated"] == [{"skill_id": "SK-JIRA", "evidence_id": "EV-0001", "review_date": "2026-11-23"}]
    assert submit(client).status_code == 409  # already demonstrated


def test_not_yet_needs_comment_and_allows_retry(client):
    jira_gap_from_p05(client)
    ev = submit(client).json()["evidence_id"]
    r = review(client, ev, "not_yet", [False, True, False, False], "The board has no reasons yet.").json()
    assert r["status"] == "not_yet"
    assert client.get(f"/api/p06/students/{LAYLA}/plan").json()["next_step"]["kind"] == "retry"
    assert submit(client).status_code == 201


def test_manual_gap_and_duplicates(client):
    """P06-EXC: one open gap per skill; skills without a module are refused."""
    r = client.post(f"/api/p06/students/{LAYLA}/gaps", json={**COORD, "skill_id": "SK-VIZ", "reason": "Desirable for OP-028"})
    assert r.status_code == 201 and r.json()["source"] == "manual" and r.json()["created_by"] == "Sara Al Hammadi"
    dup = client.post(f"/api/p06/students/{LAYLA}/gaps", json={**COORD, "skill_id": "SK-VIZ", "reason": "Again please"})
    assert dup.status_code == 409
    nomod = client.post(f"/api/p06/students/{LAYLA}/gaps", json={**COORD, "skill_id": "SK-EXCEL", "reason": "Needs Excel"})
    assert nomod.status_code == 422 and "no preparation module" in nomod.json()["detail"]
    assert client.post(f"/api/p06/students/{LAYLA}/gaps", json={**COORD, "skill_id": "SK-SQL", "reason": "x"}).status_code == 422


def test_p05_gap_without_p06_module_is_recorded_not_planned(client):
    """A P05 gap for a skill P06 has no module for (e.g. Figma) is still handed off as a record, flagged
    no_p06_module, and never lands on the preparation plan."""
    recs = client.post("/api/students/COOP-B002/recommendations").json()
    rec = next((r for r in recs if any("(SK-" in g for g in r["gaps"])
                and not any(s in "".join(r["gaps"]) for s in ("SK-JIRA", "SK-SQL", "SK-VIZ"))), None)
    if rec is None:
        pytest.skip("no gap without a P06 module in the P01-P03 export")
    skill = next(g.rsplit("(", 1)[1].rstrip(")") for g in rec["gaps"] if "(SK-" in g)
    gap = client.post(f"/api/recommendations/{rec['recommendation_id']}/gaps/{skill}/handoff", json=S).json()
    assert gap["p06_status"] is None and gap["activity"] is None
    assert client.get("/api/handoffs?to_module=P06").json()[-1]["status"] == "no_p06_module"


def test_roles_are_enforced(client):
    assert client.post(f"/api/p06/students/{LAYLA}/gaps", json={**S, "skill_id": "SK-VIZ", "reason": "Desirable"}).status_code == 403
    jira_gap_from_p05(client)
    ev = submit(client).json()["evidence_id"]
    assert client.post(f"/api/p06/submissions/{ev}/review",
                       json={**S, "decision": "demonstrated", "checklist": [True] * 4}).status_code == 403
    assert client.post(f"/api/p06/students/{LAYLA}/resources/MOD-JIRA-101/complete", json=REV).status_code == 403


def test_generalised_to_other_students(client):
    """Waypoint followed Layla only; the platform works for every student."""
    r = client.post("/api/p06/students/COOP-B003/gaps", json={**COORD, "skill_id": "SK-JIRA", "reason": "Needed for OP-028"})
    assert r.status_code == 201
    assert client.get("/api/p06/students/COOP-B003/plan").json()["gaps"][0]["skill_id"] == "SK-JIRA"
    assert client.get(f"/api/p06/students/{LAYLA}/plan").json()["gaps"] == []
