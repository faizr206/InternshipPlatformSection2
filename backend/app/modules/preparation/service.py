"""P06 internship preparation: skill gaps, modules, the Jira practice board, evidence and review.

Ported from Team P6/P7's waypoint (legacy/p06-p07-waypoint/source/src/app.js and data.js), now on the
shared database and generalised from Layla (COOP-B001) to any student. Rules kept:
- one open gap per student and skill; only skills with a P06 module can be prepared (Jira full; SQL, VIZ outline);
- finishing the resource never marks the skill demonstrated (P06 AC2);
- board items need a specific summary (>= 8 characters) and an owner before they move;
  every status move needs a reason of at least three words (P06 AC3);
- evidence needs an explanation of at least 25 words; every submission is a new version (snapshot of the board);
- the reviewer records demonstrated only when every checklist item is met; revision and not_yet need a comment;
- every review outcome is sent to P01 (demonstrated -> reviewed skill evidence; P06 AC4) and a demonstrated
  skill closes the open gap and sends a readiness summary to P07.
"""
import json
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from app import db
from app.core.common import actor, get_student, log_event, next_id, record_handoff, today, words

CATALOGUE_FILE = Path(db.__file__).parent / "seed" / "p06" / "catalogue.json"
BOARD_STATUSES = ("todo", "inprogress", "done")
# Field names and outcome values as asked by P01 (10 Nov): P01 shows "reviewed" only for demonstrated.
P01_OUTCOME = {"demonstrated": "demonstrated", "revision": "needs_more_evidence", "not_yet": "not_demonstrated"}
SKILL_STATUS = {
    "none": "Not yet demonstrated", "submitted": "Awaiting review", "revision": "Revision requested",
    "not_yet": "Not yet demonstrated", "demonstrated": "Demonstrated",
}


@lru_cache
def catalogue() -> dict:
    return json.loads(CATALOGUE_FILE.read_text())


def modules() -> dict[str, dict]:
    return {m["module_id"]: m for m in catalogue()["modules"]}


def module_for_skill(skill_id: str) -> dict | None:
    return next((m for m in catalogue()["modules"] if m["skill_id"] == skill_id), None)


def outcomes() -> list[dict]:
    return catalogue()["outcomes"]


def require_student(conn, student_id: str) -> dict:
    student = get_student(conn, student_id)
    if not student:
        raise HTTPException(404, f"Student {student_id} not found")
    return student


# --- Gaps ---
def gap_row(row) -> dict:
    return dict(row)


def open_gap(conn, student_id: str, skill_id: str):
    return conn.execute("SELECT * FROM prep_gaps WHERE student_id = ? AND skill_id = ? AND status = 'open'",
                        (student_id, skill_id)).fetchone()


def add_gap(conn, student_id: str, skill_id: str, reason: str, source: str, created_by: str, *,
            gap_id: str | None = None, opportunity_id: str | None = None, opportunity_version: int | None = None,
            recommendation_id: str | None = None, profile_version: int | None = None) -> tuple[str, dict]:
    """Put a gap on the student's preparation plan. Returns ("added" | "existing", gap).

    A second open gap for the same skill is never created: a P05 handoff returns the existing one,
    a manual entry is refused (409) by the caller."""
    student = require_student(conn, student_id)
    module = module_for_skill(skill_id)
    if not module:
        have = ", ".join(m["skill_id"] for m in catalogue()["modules"])
        raise HTTPException(422, f"P06 has no preparation module for {skill_id} yet (modules exist for {have}). "
                                 "The coordinator follows up by hand.")
    existing = open_gap(conn, student_id, skill_id)
    if existing:
        return "existing", gap_row(existing)
    if gap_id and conn.execute("SELECT 1 FROM prep_gaps WHERE gap_id = ?", (gap_id,)).fetchone():
        return "existing", gap_row(conn.execute("SELECT * FROM prep_gaps WHERE gap_id = ?", (gap_id,)).fetchone())
    gap_id = gap_id or next_id(conn, "GAP", ["SELECT gap_id FROM prep_gaps", "SELECT gap_id FROM skill_gap_handoffs"], 4)
    conn.execute("INSERT INTO prep_gaps (gap_id, student_id, skill_id, opportunity_id, opportunity_version, "
                 "recommendation_id, profile_version, source, reason, created_at, created_by, status) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?, 'open')",
                 (gap_id, student_id, skill_id, opportunity_id, opportunity_version, recommendation_id,
                  profile_version, source, reason, today(conn), created_by))
    log_event(conn, "P06", "coordinator" if source == "manual" else "student", created_by, "gap_added",
              f"Skill gap {gap_id} ({module['title']}) added to {student['display_name']}'s plan "
              f"({'from P05 matching' if source == 'P05' else 'entered by coordinator'})", gap_id)
    return "added", gap_row(conn.execute("SELECT * FROM prep_gaps WHERE gap_id = ?", (gap_id,)).fetchone())


# --- Submissions ---
def submission_dict(row) -> dict:
    d = dict(row)
    d["versions"] = json.loads(d["versions"])
    d["reviews"] = json.loads(d["reviews"])
    d["status_label"] = SKILL_STATUS[d["status"]]
    return d


def submission_for(conn, student_id: str, skill_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM prep_submissions WHERE student_id = ? AND skill_id = ?",
                       (student_id, skill_id)).fetchone()
    return submission_dict(row) if row else None


def load_submission(conn, evidence_id: str) -> dict:
    row = conn.execute("SELECT * FROM prep_submissions WHERE evidence_id = ?", (evidence_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Submission {evidence_id} not found")
    return submission_dict(row)


def demonstrated(conn, student_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM prep_submissions WHERE student_id = ? AND status = 'demonstrated' "
                        "ORDER BY evidence_id", (student_id,)).fetchall()
    return [submission_dict(r) for r in rows]


# --- Plan (what the student sees) ---
def chain(conn, gap: dict) -> list[dict]:
    """The five steps from gap to demonstrated skill, with the current one marked (waypoint chainFor)."""
    module = module_for_skill(gap["skill_id"])
    learned = resource_done(conn, gap["student_id"], module["module_id"])
    sub = submission_for(conn, gap["student_id"], gap["skill_id"])
    status = sub["status"] if sub else "none"
    last = sub["reviews"][-1] if sub and sub["reviews"] else None
    steps = [
        {"key": "gap", "label": "Gap identified", "reached": True,
         "detail": f"{'From P05 matching' if gap['source'] == 'P05' else 'Entered by coordinator'}, {gap['created_at']}"},
        {"key": "learn", "label": "Learn", "reached": bool(learned),
         "detail": f"Resource complete, {learned}" if learned else
                   ("Short resource" if module["status"] == "full" else "Module in development")},
        {"key": "submit", "label": "Practise and submit", "reached": bool(sub) and status not in ("revision", "not_yet"),
         "detail": f"{sub['evidence_id']} v{len(sub['versions'])}, {sub['versions'][-1]['at']}" if sub else "Practical task"},
        {"key": "review", "label": "Reviewer decision", "reached": status == "demonstrated",
         "detail": {"submitted": "With reviewer", "revision": "Revision requested", "not_yet": "Not yet demonstrated"}.get(
             status, f"{last['by']}, {last['at']}" if last else "Checklist review")},
        {"key": "demonstrated", "label": "Demonstrated", "reached": status == "demonstrated",
         "detail": "Sent to profile (P01)" if status == "demonstrated" else "Needs reviewed evidence"},
    ]
    for step in steps:
        step["current"] = step["blocked"] = False
    if status in ("revision", "not_yet"):
        steps[3]["blocked"] = True
    elif status == "submitted":
        steps[2]["reached"] = True
        steps[3]["current"] = True
    else:
        current = next((s for s in steps if not s["reached"]), None)
        if current:
            current["current"] = True
    return steps


def next_step(conn, student_id: str, gaps: list[dict]) -> dict:
    """One plain-language next action for the student (waypoint studentNext)."""
    if not gaps:
        return {"kind": "none", "text": "No skill gaps yet. Gaps arrive from opportunity matching (P05) or a coordinator."}
    open_gaps = [g for g in gaps if g["status"] == "open"]
    for g in open_gaps:
        module = module_for_skill(g["skill_id"])
        if module["status"] != "full":
            continue
        sub = submission_for(conn, student_id, g["skill_id"])
        name, mid = module["title"], module["module_id"]
        if sub and sub["status"] == "revision":
            return {"kind": "revise", "module_id": mid,
                    "text": f"Revise your evidence for “{name}”. {sub['reviews'][-1]['by']} asked for changes."}
        if sub and sub["status"] == "not_yet":
            return {"kind": "retry", "module_id": mid, "text": f"Try the “{name}” task again."}
        if sub and sub["status"] == "submitted":
            return {"kind": "wait", "module_id": mid, "text": f"{sub['evidence_id']} is with the reviewer."}
        if not resource_done(conn, student_id, mid):
            return {"kind": "learn", "module_id": mid,
                    "text": f"Start with the “{name}” resource (about {module['resource']['minutes']} minutes)."}
        return {"kind": "practise", "module_id": mid,
                "text": f"Complete the practical task for “{name}”. Finishing the reading does not demonstrate the skill."}
    if open_gaps:
        return {"kind": "waiting_module",
                "text": f"{len(open_gaps)} gap(s) waiting for a module in development. Your coordinator will tell you when it opens."}
    return {"kind": "done", "text": "All current gaps are demonstrated. Your profile shows reviewed evidence for each."}


def plan(conn, student_id: str) -> dict:
    student = require_student(conn, student_id)
    rows = conn.execute("SELECT * FROM prep_gaps WHERE student_id = ? ORDER BY gap_id", (student_id,)).fetchall()
    gaps = []
    for r in rows:
        g = gap_row(r)
        module = module_for_skill(g["skill_id"])
        sub = submission_for(conn, student_id, g["skill_id"])
        gaps.append({**g, "skill_name": db.skill_names().get(g["skill_id"], g["skill_id"]),
                     "module_id": module["module_id"], "module_title": module["title"],
                     "module_status": module["status"],
                     "skill_status": sub["status"] if sub else "none",
                     "skill_status_label": SKILL_STATUS[sub["status"] if sub else "none"],
                     "chain": chain(conn, g)})
    return {"student_id": student_id, "display_name": student["display_name"], "today": today(conn),
            "gaps": gaps, "next_step": next_step(conn, student_id, gaps),
            "resources": {r["module_id"]: r["completed_at"] for r in conn.execute(
                "SELECT module_id, completed_at FROM prep_resources WHERE student_id = ?", (student_id,))},
            "submissions": [submission_dict(r) for r in conn.execute(
                "SELECT * FROM prep_submissions WHERE student_id = ? ORDER BY evidence_id", (student_id,))]}


# --- Resource ---
def resource_done(conn, student_id: str, module_id: str) -> str | None:
    row = conn.execute("SELECT completed_at FROM prep_resources WHERE student_id = ? AND module_id = ?",
                       (student_id, module_id)).fetchone()
    return row["completed_at"] if row else None


def complete_resource(conn, student_id: str, module_id: str) -> dict:
    student = require_student(conn, student_id)
    module = modules().get(module_id)
    if not module:
        raise HTTPException(404, f"Module {module_id} not found")
    if module["status"] != "full":
        raise HTTPException(409, f"{module['title']} is an outline; its resource is still in development.")
    if not resource_done(conn, student_id, module_id):
        conn.execute("INSERT INTO prep_resources (student_id, module_id, completed_at) VALUES (?,?,?)",
                     (student_id, module_id, today(conn)))
        log_event(conn, "P06", "student", student["display_name"], "resource_completed",
                  f"{student['display_name']} completed the resource for {module['title']}", module_id)
    return {"module_id": module_id, "completed_at": resource_done(conn, student_id, module_id),
            "skill_status": (submission_for(conn, student_id, module["skill_id"]) or {}).get("status", "none"),
            "note": "Activity complete. The skill is not demonstrated until reviewed evidence is recorded."}


# --- Jira practice board ---
def board(conn, student_id: str) -> dict:
    require_student(conn, student_id)
    row = conn.execute("SELECT data FROM prep_boards WHERE student_id = ?", (student_id,)).fetchone()
    if row:
        return json.loads(row["data"])
    start = catalogue()["board_start"]
    return {"items": [dict(i) for i in start], "log": [], "next": 104, "people": catalogue()["board_people"]}


def save_board(conn, student_id: str, data: dict) -> dict:
    conn.execute("INSERT OR REPLACE INTO prep_boards (student_id, data) VALUES (?,?)", (student_id, json.dumps(data)))
    return data


def board_item(data: dict, key: str) -> dict:
    item = next((i for i in data["items"] if i["key"] == key), None)
    if not item:
        raise HTTPException(404, f"Board item {key} not found")
    return item


def add_item(conn, student_id: str, summary: str) -> dict:
    summary = (summary or "").strip()
    if len(summary) < 8:
        raise HTTPException(422, "Write a specific summary of at least 8 characters.")
    data = board(conn, student_id)
    key = f"OPS-{data['next']}"
    data["next"] += 1
    data["items"].append({"key": key, "summary": summary, "assignee": "", "status": "todo", "created_by": "student"})
    return save_board(conn, student_id, data)


def assign_item(conn, student_id: str, key: str, assignee: str) -> dict:
    data = board(conn, student_id)
    people = data.get("people") or catalogue()["board_people"]
    student = require_student(conn, student_id)
    allowed = set(people) | {student["display_name"]}
    if assignee and assignee not in allowed:
        raise HTTPException(422, f"Assign the item to someone on the team: {', '.join(sorted(allowed))}.")
    board_item(data, key)["assignee"] = assignee or ""
    return save_board(conn, student_id, data)


def move_item(conn, student_id: str, key: str, to: str, reason: str) -> dict:
    if to not in BOARD_STATUSES:
        raise HTTPException(422, f"Status must be one of {', '.join(BOARD_STATUSES)}.")
    data = board(conn, student_id)
    item = board_item(data, key)
    if not item["assignee"]:
        raise HTTPException(409, f"Give {key} an owner before moving it.")
    if item["status"] == to:
        raise HTTPException(409, f"{key} is already in {to}.")
    if words(reason) < 3:
        raise HTTPException(422, "Give a reason of at least three words: what changed and what happens next.")
    data["log"].append({"key": key, "from": item["status"], "to": to, "reason": reason.strip(), "at": today(conn)})
    item["status"] = to
    return save_board(conn, student_id, data)


def submit_evidence(conn, student_id: str, module_id: str, explanation: str) -> dict:
    student = require_student(conn, student_id)
    module = modules().get(module_id)
    if not module:
        raise HTTPException(404, f"Module {module_id} not found")
    if module["status"] != "full":
        raise HTTPException(409, f"{module['title']} is an outline; its practical task is not open yet.")
    count = words(explanation)
    if count < 25:
        raise HTTPException(422, f"Your explanation has {count} words. Write at least 25 so the reviewer can follow "
                                 "your reasoning.")
    sub = submission_for(conn, student_id, module["skill_id"])
    if sub and sub["status"] == "submitted":
        raise HTTPException(409, f"{sub['evidence_id']} is already with the reviewer.")
    if sub and sub["status"] == "demonstrated":
        raise HTTPException(409, f"{module['title']} is already demonstrated ({sub['evidence_id']}).")
    snapshot = board(conn, student_id)
    version = {"v": (len(sub["versions"]) if sub else 0) + 1, "at": today(conn), "explanation": explanation.strip(),
               "board": snapshot}
    if sub:
        evidence_id = sub["evidence_id"]
        conn.execute("UPDATE prep_submissions SET status = 'submitted', versions = ? WHERE evidence_id = ?",
                     (json.dumps(sub["versions"] + [version]), evidence_id))
    else:
        evidence_id = next_id(conn, "EV", ["SELECT evidence_id FROM prep_submissions"], 4)
        conn.execute("INSERT INTO prep_submissions (evidence_id, student_id, skill_id, module_id, status, versions, "
                     "reviews) VALUES (?,?,?,?, 'submitted', ?, '[]')",
                     (evidence_id, student_id, module["skill_id"], module_id, json.dumps([version])))
    log_event(conn, "P06", "student", student["display_name"], "evidence_submitted",
              f"{student['display_name']} submitted {evidence_id} version {version['v']} for review", evidence_id)
    return load_submission(conn, evidence_id)


def readiness(conn, student_id: str) -> dict:
    """What P07 receives about preparation: demonstrated skills with evidence, and gaps still open."""
    return {
        "student_id": student_id,
        "demonstrated": [{"skill_id": s["skill_id"], "evidence_id": s["evidence_id"],
                          "review_date": s["reviews"][-1]["at"]} for s in demonstrated(conn, student_id)],
        "in_progress": [r["skill_id"] for r in conn.execute(
            "SELECT skill_id FROM prep_gaps WHERE student_id = ? AND status = 'open' ORDER BY gap_id", (student_id,))],
    }


def review(conn, evidence_id: str, decision: str, comment: str, checklist: list[bool], reviewer: str,
           on_demonstrated=None) -> dict:
    """Reviewer decision. `on_demonstrated(conn, student_id, skill_id, evidence_id, reviewer, review_date)` lets
    the live P06 -> P01 handoff run in the same transaction (new reviewed profile version + rematch)."""
    if decision not in P01_OUTCOME:
        raise HTTPException(422, "Decision must be demonstrated, revision or not_yet.")
    sub = load_submission(conn, evidence_id)
    if sub["status"] != "submitted":
        raise HTTPException(409, f"{evidence_id} is not waiting for review (status: {sub['status_label']}).")
    module = modules()[sub["module_id"]]
    if len(checklist) != len(module["checklist"]):
        raise HTTPException(422, f"Give one answer for each of the {len(module['checklist'])} checklist criteria.")
    comment = (comment or "").strip()
    if decision == "demonstrated" and not all(checklist):
        raise HTTPException(422, f"All {len(checklist)} criteria must be met to record the skill as demonstrated. "
                                 "Request a revision instead.")
    if decision != "demonstrated" and not comment:
        raise HTTPException(422, "Add a comment that tells the student what to change.")
    at = today(conn)
    entry = {"at": at, "by": reviewer, "decision": decision, "comment": comment or "All criteria met.",
             "checklist": checklist}
    conn.execute("UPDATE prep_submissions SET status = ?, reviews = ? WHERE evidence_id = ?",
                 (decision, json.dumps(sub["reviews"] + [entry]), evidence_id))
    student_id, skill_id = sub["student_id"], sub["skill_id"]
    p01_payload = {"student_id": student_id, "skill_id": skill_id, "evidence_id": evidence_id,
                   "outcome": P01_OUTCOME[decision], "reviewer": reviewer, "review_date": at}
    result = {"p01_profile_version": None, "rematched": False}
    if decision == "demonstrated":
        conn.execute("UPDATE prep_gaps SET status = 'closed', closed_at = ? WHERE student_id = ? AND skill_id = ? "
                     "AND status = 'open'", (at, student_id, skill_id))
        if on_demonstrated:
            result = on_demonstrated(conn, student_id, skill_id, evidence_id, reviewer, at) or result
        record_handoff(conn, "P06", "P01", "reviewed_skill", p01_payload, student_id, evidence_id)
        record_handoff(conn, "P06", "P07", "readiness_summary", readiness(conn, student_id), student_id, evidence_id)
        text = f"{reviewer} recorded {evidence_id} as demonstrated; sent to P01 and P07"
    else:
        record_handoff(conn, "P06", "P01", "reviewed_skill", p01_payload, student_id, evidence_id)
        text = (f"{reviewer} requested a revision on {evidence_id}" if decision == "revision"
                else f"{reviewer} recorded {evidence_id} as not yet demonstrated")
    log_event(conn, "P06", "reviewer", reviewer, f"evidence_{decision}", text, evidence_id)
    return {**load_submission(conn, evidence_id), **result}


def review_queue(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM prep_submissions WHERE status = 'submitted' ORDER BY evidence_id").fetchall()
    out = []
    for r in rows:
        sub = submission_dict(r)
        student = get_student(conn, sub["student_id"])
        out.append({**sub, "display_name": student["display_name"] if student else sub["student_id"],
                    "module": modules()[sub["module_id"]]})
    return out


def all_gaps(conn, status: str = "") -> list[dict]:
    query = "SELECT * FROM prep_gaps" + (" WHERE status = ?" if status else "") + " ORDER BY gap_id"
    out = []
    for r in conn.execute(query, (status,) if status else ()):
        g = gap_row(r)
        student = get_student(conn, g["student_id"])
        out.append({**g, "display_name": student["display_name"] if student else g["student_id"],
                    "skill_name": db.skill_names().get(g["skill_id"], g["skill_id"])})
    return out


def coordinator_name(conn, given: str | None) -> str:
    return actor("coordinator", given, conn)
