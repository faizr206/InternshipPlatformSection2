"""P07 co-op learning progress: placement, learning agreement, logbook, milestones, outcome judgements,
support actions, employer feedback and the final review.

Ported from Team P6/P7's waypoint (legacy/p06-p07-waypoint/source/src/app.js) onto the shared database and
generalised to any student with a confirmed placement. Rules kept:
- P07 accepts only university_confirmed placements from P04, once each; one active placement per student;
  the listing must be published and the period a valid date range; the coordinator assigns the advisor;
- the learning agreement has exactly three goals, each mapped to at least one outcome; student, supervisor
  and advisor sign it (advisor only once assigned) and it locks when all three have;
- log entries need at least eight words; a supervisor acknowledges or requests detail (at least four words);
  a revision must change the text, and every version and feedback item is kept (P07 AC1);
- an outcome judgement above "none" must cite evidence; missing evidence stays visible (P07 AC2);
- support actions have an owner and a due date; overdue uses the demo date; closing needs closure evidence (AC3);
- employer feedback (>= 10 words) is kept apart from the advisor's final review; an outcome can be marked
  achieved only with evidence from this period or reviewed P06 evidence; later-period evidence never counts (AC4).
"""
import json
import re
from datetime import date

from fastapi import HTTPException

from app.core.common import ADVISORS, DEMO_PEOPLE, get_opportunity, get_student, log_event, next_id, today, words
from app.modules.preparation import service as prep

LEVELS = ("none", "developing", "achieved")
SIGNERS = ("student", "supervisor", "advisor")
ACTION_OWNERS = ("student", "supervisor", "advisor", "coordinator")
REQUIRED_PLACEMENT_FIELDS = ("placement_id", "status", "student_id", "opportunity_id", "employer_name",
                             "period_start", "period_end")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def outcome_ids() -> list[str]:
    return [o["outcome_id"] for o in prep.outcomes()]


# --- Placement ---
def load_placement(conn, placement_id: str) -> dict:
    row = conn.execute("SELECT data FROM p07_placements WHERE placement_id = ?", (placement_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Placement {placement_id} has not reached P07.")
    return json.loads(row["data"])


def placement_for(conn, student_id: str) -> dict | None:
    row = conn.execute("SELECT data FROM p07_placements WHERE student_id = ?", (student_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def save_placement(conn, placement: dict) -> None:
    conn.execute("INSERT OR REPLACE INTO p07_placements (placement_id, student_id, data) VALUES (?,?,?)",
                 (placement["placement_id"], placement["student_id"], json.dumps(placement)))


def receive_placement(conn, record: dict, received_by: str) -> tuple[str, str]:
    """Accept one P04 placement record. Returns ("added" | "skipped" | "rejected", explanation)."""
    pid = record.get("placement_id") or "(no placement_id)"
    missing = [f for f in REQUIRED_PLACEMENT_FIELDS if record.get(f) in (None, "")]
    if missing:
        return "rejected", f"{pid}: missing {', '.join(missing)}"
    if record["status"] != "university_confirmed":
        return "rejected", f"{pid}: status is “{record['status']}”. P07 accepts only university_confirmed placements."
    student = get_student(conn, record["student_id"])
    if not student:
        return "rejected", f"{pid}: {record['student_id']} is not in P01's student profiles"
    listing = get_opportunity(conn, record["opportunity_id"])
    if not listing or listing.get("publication_status") != "published":
        return "rejected", f"{pid}: {record['opportunity_id']} is not a published P03 listing"
    start, end = str(record["period_start"]), str(record["period_end"])
    if not DATE.match(start) or not DATE.match(end) or end <= start:
        return "rejected", f"{pid}: period {start} to {end} is not a valid date range"
    current = placement_for(conn, record["student_id"])
    if current and current["placement_id"] == record["placement_id"]:
        return "skipped", f"{pid}: already received. P04 sends each placement once."
    if current:
        return "rejected", f"{pid}: {student['display_name']} already has an active placement ({current['placement_id']})"
    placement = {
        "placement_id": record["placement_id"], "student_id": record["student_id"],
        "opportunity_id": record["opportunity_id"], "opportunity_version": record.get("opportunity_version"),
        "application_id": record.get("application_id"), "employer_name": record["employer_name"],
        "location": record.get("location") or "", "role": record.get("role") or "",
        "period_start": start, "period_end": end,
        "supervisor_name": record.get("supervisor_name") or listing.get("supervisor_name"),
        "supervisor_contact": record.get("supervisor_contact") or listing.get("supervisor_contact"),
        "academic_advisor": record.get("academic_advisor"), "advisor_assigned_by": None, "advisor_assigned_at": None,
        "status": record["status"], "confirmed_by": record.get("confirmed_by"),
        "confirmed_at": record.get("confirmed_at"), "received_at": today(conn), "received_by": received_by,
        "source": "P04",
    }
    save_placement(conn, placement)
    conn.execute("INSERT OR IGNORE INTO p07_agreements (placement_id, data) VALUES (?,?)",
                 (placement["placement_id"], json.dumps({"goals": [], "status": "draft",
                                                         "signoffs": {k: None for k in SIGNERS}})))
    differs = listing.get("start_date") and (start != listing.get("start_date") or end != listing.get("end_date"))
    note = f" (P03 listing says {listing.get('start_date')} to {listing.get('end_date')}; coordinator to check)" if differs else ""
    log_event(conn, "P07", "coordinator", received_by, "placement_received",
              f"P07 received confirmed placement {pid} for {student['display_name']}{note}"
              + ("" if placement["academic_advisor"] else ". No academic advisor yet."), pid)
    return "added", f"{pid}: {record['employer_name']}, {start} to {end}{note}"


def import_placements(conn, records: list[dict], received_by: str) -> dict:
    result = {"added": [], "skipped": [], "rejected": []}
    for record in records:
        outcome, why = receive_placement(conn, record, received_by)
        result[outcome].append(why)
    return result


def assign_advisor(conn, placement_id: str, advisor: str, by: str) -> dict:
    placement = load_placement(conn, placement_id)
    names = [a["name"] for a in ADVISORS]
    if advisor not in names:
        raise HTTPException(422, f"Choose an academic advisor: {', '.join(names)}.")
    placement.update(academic_advisor=advisor, advisor_assigned_by=by, advisor_assigned_at=today(conn))
    save_placement(conn, placement)
    log_event(conn, "P07", "coordinator", by, "advisor_assigned",
              f"Assigned academic advisor {advisor} to placement {placement_id}", placement_id)
    return placement


def period(placement: dict) -> dict:
    return {"period_id": "P1", "label": "Period 1", "start": placement["period_start"], "end": placement["period_end"]}


def week_of(placement: dict, on: str) -> int:
    return (date.fromisoformat(on) - date.fromisoformat(placement["period_start"])).days // 7 + 1


# --- Learning agreement ---
def agreement(conn, placement_id: str) -> dict:
    row = conn.execute("SELECT data FROM p07_agreements WHERE placement_id = ?", (placement_id,)).fetchone()
    return json.loads(row["data"]) if row else {"goals": [], "status": "draft", "signoffs": {k: None for k in SIGNERS}}


def save_agreement(conn, placement_id: str, data: dict) -> dict:
    conn.execute("INSERT OR REPLACE INTO p07_agreements (placement_id, data) VALUES (?,?)",
                 (placement_id, json.dumps(data)))
    return data


def add_goal(conn, placement_id: str, text: str, outcomes: list[str]) -> dict:
    load_placement(conn, placement_id)
    data = agreement(conn, placement_id)
    if data["status"] == "agreed":
        raise HTTPException(409, "The learning agreement is agreed and locked.")
    if len(data["goals"]) >= 3:
        raise HTTPException(409, "The agreement already has three goals. Remove one to change it.")
    text = (text or "").strip()
    if len(text) < 10:
        raise HTTPException(422, "Describe the goal in a full phrase.")
    unknown = [o for o in outcomes if o not in outcome_ids()]
    if not outcomes or unknown:
        raise HTTPException(422, "Map the goal to at least one learning outcome "
                                 f"({', '.join(outcome_ids())}).")
    data["goals"].append({"goal_id": f"G{len(data['goals']) + 1}", "text": text, "outcomes": list(dict.fromkeys(outcomes))})
    data["signoffs"] = {k: None for k in SIGNERS}  # changing the goals resets earlier sign-offs
    return save_agreement(conn, placement_id, data)


def remove_goal(conn, placement_id: str, goal_id: str) -> dict:
    data = agreement(conn, placement_id)
    if data["status"] == "agreed":
        raise HTTPException(409, "The learning agreement is agreed and locked.")
    if not any(g["goal_id"] == goal_id for g in data["goals"]):
        raise HTTPException(404, f"Goal {goal_id} not found")
    data["goals"] = [g for g in data["goals"] if g["goal_id"] != goal_id]
    for i, g in enumerate(data["goals"], start=1):
        g["goal_id"] = f"G{i}"
    data["signoffs"] = {k: None for k in SIGNERS}
    return save_agreement(conn, placement_id, data)


def sign(conn, placement_id: str, signer: str, name: str) -> dict:
    placement = load_placement(conn, placement_id)
    data = agreement(conn, placement_id)
    if data["status"] == "agreed":
        raise HTTPException(409, "The learning agreement is already agreed.")
    if len(data["goals"]) != 3:
        raise HTTPException(409, f"Sign-off opens when three goals are drafted ({len(data['goals'])} of 3).")
    if signer == "advisor" and not placement["academic_advisor"]:
        raise HTTPException(409, "Assign an academic advisor first; the advisor must agree the learning agreement.")
    if data["signoffs"][signer]:
        raise HTTPException(409, f"The {signer} has already agreed.")
    data["signoffs"][signer] = today(conn)
    log_event(conn, "P07", signer, name, "agreement_signed", f"{name} agreed the learning agreement as {signer}",
              placement_id)
    if all(data["signoffs"].values()):
        data["status"] = "agreed"
        log_event(conn, "P07", signer, name, "agreement_agreed", "Learning agreement agreed by all three parties",
                  placement_id)
    return save_agreement(conn, placement_id, data)


# --- Evidence ---
def evidence(conn, placement: dict) -> list[dict]:
    """Placement evidence plus reviewed P06 evidence for the same student (source P06)."""
    p06 = [{"evidence_id": s["evidence_id"], "title": f"{prep.modules()[s['module_id']]['title']} (reviewed in P06)",
            "date": s["reviews"][-1]["at"], "source": "P06"} for s in prep.demonstrated(conn, placement["student_id"])]
    own = [dict(r) for r in conn.execute("SELECT evidence_id, title, date, source FROM p07_evidence WHERE "
                                         "placement_id = ? ORDER BY evidence_id", (placement["placement_id"],))]
    return p06 + own


def add_evidence(conn, placement: dict, title: str, source: str) -> str:
    taken = [int(r[0].split("-")[1]) for r in conn.execute("SELECT evidence_id FROM p07_evidence")
             if r[0].split("-")[-1].isdigit()]
    evidence_id = f"EV-{max([100] + taken) + 1:04d}"
    conn.execute("INSERT INTO p07_evidence (evidence_id, placement_id, title, date, source) VALUES (?,?,?,?,?)",
                 (evidence_id, placement["placement_id"], title.strip(), today(conn), source))
    return evidence_id


def in_period(item: dict, placement: dict) -> bool:
    return placement["period_start"] <= item["date"] <= placement["period_end"]


# --- Logbook ---
def log_dict(row) -> dict:
    return {"log_id": row["log_id"], "placement_id": row["placement_id"], **json.loads(row["data"])}


def load_log(conn, log_id: str) -> dict:
    row = conn.execute("SELECT * FROM p07_logs WHERE log_id = ?", (log_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Log entry {log_id} not found")
    return log_dict(row)


def save_log(conn, log: dict) -> dict:
    data = {k: v for k, v in log.items() if k not in ("log_id", "placement_id")}
    conn.execute("INSERT OR REPLACE INTO p07_logs (log_id, placement_id, data) VALUES (?,?,?)",
                 (log["log_id"], log["placement_id"], json.dumps(data)))
    return log


def add_log(conn, placement_id: str, text: str, goal_id: str | None, evidence_ids: list[str],
            new_evidence_title: str | None, student_name: str) -> dict:
    placement = load_placement(conn, placement_id)
    if words(text) < 8:
        raise HTTPException(422, "Write at least eight words about what you did and learned.")
    goals = [g["goal_id"] for g in agreement(conn, placement_id)["goals"]]
    if goal_id and goal_id not in goals:
        raise HTTPException(422, f"Link the entry to a goal in the learning agreement ({', '.join(goals) or 'none yet'}).")
    known = {e["evidence_id"] for e in evidence(conn, placement)}
    unknown = [e for e in evidence_ids if e not in known]
    if unknown:
        raise HTTPException(422, f"Unknown evidence: {', '.join(unknown)}.")
    refs = list(dict.fromkeys(evidence_ids))
    if (new_evidence_title or "").strip():
        refs.append(add_evidence(conn, placement, new_evidence_title, "Student"))
    on = today(conn)
    log_id = next_id(conn, "LOG", ["SELECT log_id FROM p07_logs"], 2)
    log = {"log_id": log_id, "placement_id": placement_id, "week": week_of(placement, on), "date": on,
           "goal_id": goal_id, "status": "submitted", "period": "P1" if on <= placement["period_end"] else "P2",
           "versions": [{"v": 1, "at": on, "text": text.strip(), "evidence": refs}], "feedback": []}
    save_log(conn, log)
    log_event(conn, "P07", "student", student_name, "log_submitted", f"{student_name} submitted log entry {log_id}", log_id)
    return log


def revise_log(conn, log_id: str, text: str, student_name: str) -> dict:
    log = load_log(conn, log_id)
    if log["status"] not in ("submitted", "feedback"):
        raise HTTPException(409, f"{log_id} is {log['status']}; only an entry awaiting the supervisor or with a "
                                 "feedback request can be revised.")
    last = log["versions"][-1]
    if (text or "").strip() == last["text"]:
        raise HTTPException(422, "Change the entry to respond to the feedback.")
    if words(text) < 8:
        raise HTTPException(422, "Write at least eight words about what you did and learned.")
    log["versions"].append({"v": len(log["versions"]) + 1, "at": today(conn), "text": text.strip(),
                            "evidence": list(last["evidence"])})
    log["status"] = "revised"
    log_event(conn, "P07", "student", student_name, "log_revised", f"{student_name} revised {log_id}", log_id)
    return save_log(conn, log)


def acknowledge_log(conn, log_id: str, by: str) -> dict:
    log = load_log(conn, log_id)
    if log["status"] not in ("submitted", "revised"):
        raise HTTPException(409, f"{log_id} is not waiting for the supervisor (status: {log['status']}).")
    log["status"] = "acknowledged"
    log["feedback"].append({"at": today(conn), "by": by, "type": "note", "text": "Acknowledged."})
    log_event(conn, "P07", "supervisor", by, "log_acknowledged", f"{by} acknowledged {log_id}", log_id)
    return save_log(conn, log)


def request_detail(conn, log_id: str, text: str, by: str) -> dict:
    log = load_log(conn, log_id)
    if log["status"] not in ("submitted", "revised"):
        raise HTTPException(409, f"{log_id} is not waiting for the supervisor (status: {log['status']}).")
    if words(text) < 4:
        raise HTTPException(422, "Say specifically what to add (at least four words).")
    log["status"] = "feedback"
    log["feedback"].append({"at": today(conn), "by": by, "type": "request", "text": text.strip()})
    log_event(conn, "P07", "supervisor", by, "log_feedback_requested", f"{by} requested more detail on {log_id}", log_id)
    return save_log(conn, log)


# --- Milestones ---
def add_milestone(conn, placement_id: str, text: str, by: str) -> dict:
    load_placement(conn, placement_id)
    if len((text or "").strip()) < 5:
        raise HTTPException(422, "Describe the milestone.")
    milestone_id = next_id(conn, "MS", ["SELECT milestone_id FROM p07_milestones"], 1)
    conn.execute("INSERT INTO p07_milestones (milestone_id, placement_id, text, done, done_at) VALUES (?,?,?,0,NULL)",
                 (milestone_id, placement_id, text.strip()))
    log_event(conn, "P07", "supervisor", by, "milestone_added", f"{by} added host milestone {milestone_id}", placement_id)
    return dict(conn.execute("SELECT * FROM p07_milestones WHERE milestone_id = ?", (milestone_id,)).fetchone())


def set_milestone(conn, milestone_id: str, done: bool, by: str) -> dict:
    row = conn.execute("SELECT * FROM p07_milestones WHERE milestone_id = ?", (milestone_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Milestone {milestone_id} not found")
    conn.execute("UPDATE p07_milestones SET done = ?, done_at = ? WHERE milestone_id = ?",
                 (int(done), today(conn) if done else None, milestone_id))
    log_event(conn, "P07", "supervisor", by, "milestone_updated",
              f"{by} {'completed' if done else 'reopened'} host milestone: {row['text']}", row["placement_id"])
    return dict(conn.execute("SELECT * FROM p07_milestones WHERE milestone_id = ?", (milestone_id,)).fetchone())


# --- Judgements ---
def judge(conn, placement_id: str, outcome_id: str, level: str, evidence_ids: list[str], by: str) -> dict:
    placement = load_placement(conn, placement_id)
    if outcome_id not in outcome_ids():
        raise HTTPException(404, f"Unknown learning outcome {outcome_id}")
    if level not in LEVELS:
        raise HTTPException(422, f"Level must be one of {', '.join(LEVELS)}.")
    evidence_ids = list(dict.fromkeys(evidence_ids)) if level != "none" else []
    if level != "none" and not evidence_ids:
        raise HTTPException(422, "Link at least one piece of evidence, or keep the outcome as not yet evidenced. "
                                 "Completing a host milestone alone does not demonstrate an academic outcome.")
    known = {e["evidence_id"] for e in evidence(conn, placement)}
    unknown = [e for e in evidence_ids if e not in known]
    if unknown:
        raise HTTPException(422, f"Unknown evidence: {', '.join(unknown)}.")
    data = {"level": level, "evidence": evidence_ids, "by": by, "at": today(conn)}
    conn.execute("INSERT OR REPLACE INTO p07_judgements (placement_id, outcome_id, data) VALUES (?,?,?)",
                 (placement_id, outcome_id, json.dumps(data)))
    log_event(conn, "P07", "advisor", by, "judgement_recorded", f"{by} recorded {outcome_id}: {level}", placement_id)
    return {"outcome_id": outcome_id, **data}


def judgements(conn, placement: dict) -> list[dict]:
    stored = {r["outcome_id"]: json.loads(r["data"]) for r in conn.execute(
        "SELECT outcome_id, data FROM p07_judgements WHERE placement_id = ?", (placement["placement_id"],))}
    out = []
    for o in prep.outcomes():
        j = stored.get(o["outcome_id"], {"level": "none", "evidence": [], "by": None, "at": None})
        out.append({"outcome_id": o["outcome_id"], "name": o["name"], **j, "evidence_missing": not j["evidence"]})
    return out


# --- Actions ---
def action_dict(row, on: str) -> dict:
    d = {"action_id": row["action_id"], "placement_id": row["placement_id"], **json.loads(row["data"])}
    d["overdue"] = d["status"] == "open" and d["due"] < on
    return d


def add_action(conn, placement_id: str, text: str, owner: str, due: str, by: str) -> dict:
    load_placement(conn, placement_id)
    if len((text or "").strip()) < 8 or owner not in ACTION_OWNERS or not DATE.match(due or ""):
        raise HTTPException(422, "Every action needs a description (at least 8 characters), an owner "
                                 f"({', '.join(ACTION_OWNERS)}) and a due date (YYYY-MM-DD).")
    action_id = next_id(conn, "ACT", ["SELECT action_id FROM p07_actions"], 2)
    data = {"text": text.strip(), "owner": owner, "due": due, "status": "open", "closure": "", "closed_at": None,
            "created_at": today(conn), "created_by": by}
    conn.execute("INSERT INTO p07_actions (action_id, placement_id, data) VALUES (?,?,?)",
                 (action_id, placement_id, json.dumps(data)))
    log_event(conn, "P07", "advisor", by, "action_added", f"{by} added support action {action_id} (owner: {owner}, "
              f"due {due})", placement_id)
    return action_dict(conn.execute("SELECT * FROM p07_actions WHERE action_id = ?", (action_id,)).fetchone(), today(conn))


def close_action(conn, action_id: str, closure: str, role: str, by: str) -> dict:
    row = conn.execute("SELECT * FROM p07_actions WHERE action_id = ?", (action_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Action {action_id} not found")
    data = json.loads(row["data"])
    if role not in (data["owner"], "advisor"):
        raise HTTPException(403, f"Only the action owner ({data['owner']}) or the academic advisor can close {action_id}.")
    if data["status"] == "closed":
        raise HTTPException(409, f"{action_id} is already closed.")
    if len((closure or "").strip()) < 5:
        raise HTTPException(422, "Describe the evidence that shows this is done.")
    data.update(status="closed", closure=closure.strip(), closed_at=today(conn))
    conn.execute("UPDATE p07_actions SET data = ? WHERE action_id = ?", (json.dumps(data), action_id))
    log_event(conn, "P07", role, by, "action_closed", f"{by} closed {action_id} with closure evidence", row["placement_id"])
    return action_dict(conn.execute("SELECT * FROM p07_actions WHERE action_id = ?", (action_id,)).fetchone(), today(conn))


# --- Employer feedback and final review ---
def final_reviews(conn, placement_id: str) -> dict:
    row = conn.execute("SELECT * FROM p07_final_reviews WHERE placement_id = ?", (placement_id,)).fetchone()
    return {"employer": json.loads(row["employer"]) if row and row["employer"] else None,
            "advisor": json.loads(row["advisor"]) if row and row["advisor"] else None}


def _save_final(conn, placement_id: str, data: dict) -> dict:
    conn.execute("INSERT OR REPLACE INTO p07_final_reviews (placement_id, employer, advisor) VALUES (?,?,?)",
                 (placement_id, json.dumps(data["employer"]) if data["employer"] else None,
                  json.dumps(data["advisor"]) if data["advisor"] else None))
    return data


def employer_feedback(conn, placement_id: str, text: str, would_host: str, by: str) -> dict:
    load_placement(conn, placement_id)
    if words(text) < 10:
        raise HTTPException(422, "Write at least ten words of feedback.")
    if would_host not in ("yes", "maybe", "no"):
        raise HTTPException(422, "Would you host another student? Answer yes, maybe or no.")
    data = final_reviews(conn, placement_id)
    data["employer"] = {"by": by, "at": today(conn), "text": text.strip(), "would_host": would_host}
    log_event(conn, "P07", "supervisor", by, "employer_feedback", f"{by} submitted employer feedback for Period 1",
              placement_id)
    return _save_final(conn, placement_id, data)


def final_review(conn, placement_id: str, outcomes: dict[str, str], summary: str, next_goal: str, by: str) -> dict:
    placement = load_placement(conn, placement_id)
    data = final_reviews(conn, placement_id)
    if data["advisor"]:
        raise HTTPException(409, "The final review for Period 1 is already recorded.")
    errors = {}
    if words(summary) < 10:
        errors["summary"] = "Write at least ten words."
    if len((next_goal or "").strip()) < 8:
        errors["next_goal"] = "Set one goal for the next period."
    if set(outcomes) != set(outcome_ids()) or any(v not in LEVELS for v in outcomes.values()):
        errors["outcomes"] = f"Give a level ({', '.join(LEVELS)}) for each outcome {', '.join(outcome_ids())}."
    else:
        items = {e["evidence_id"]: e for e in evidence(conn, placement)}
        stored = {j["outcome_id"]: j for j in judgements(conn, placement)}
        bad = [o for o, level in outcomes.items() if level == "achieved" and not any(
            e in items and (in_period(items[e], placement) or items[e]["source"] == "P06")
            for e in stored[o]["evidence"])]
        if bad:
            errors["rule"] = (f"{', '.join(sorted(bad))} cannot be marked achieved without evidence from this period "
                              "(or reviewed P06 evidence).")
    if errors:
        raise HTTPException(422, {"message": "Fix the final review before recording it.", "errors": errors})
    data["advisor"] = {"by": by, "at": today(conn), "outcomes": outcomes, "summary": summary.strip(),
                       "next_goal": next_goal.strip(), "period": "P1"}
    log_event(conn, "P07", "advisor", by, "final_review", f"{by} recorded the final review for Period 1", placement_id)
    return _save_final(conn, placement_id, data)


# --- Whole record ---
def record(conn, student_id: str, viewer_role: str = "student") -> dict:
    student = prep.require_student(conn, student_id)
    placement = placement_for(conn, student_id)
    base = {"student_id": student_id, "display_name": student["display_name"], "today": today(conn),
            "outcomes": prep.outcomes(), "advisors": ADVISORS, "readiness": prep.readiness(conn, student_id)}
    if not placement:
        return {**base, "placement": None}
    on = today(conn)
    pid = placement["placement_id"]
    shown = dict(placement)
    if viewer_role == "student":
        shown.pop("supervisor_contact", None)  # P03 contact goes to P07 staff, never to students
    logs = [log_dict(r) for r in conn.execute("SELECT * FROM p07_logs WHERE placement_id = ? ORDER BY log_id", (pid,))]
    actions = [action_dict(r, on) for r in conn.execute("SELECT * FROM p07_actions WHERE placement_id = ? "
                                                        "ORDER BY action_id", (pid,))]
    items = evidence(conn, placement)
    return {**base, "placement": shown, "period": period(placement), "agreement": agreement(conn, pid),
            "logs": logs, "evidence": [{**e, "in_period": in_period(e, placement)} for e in items],
            "judgements": judgements(conn, placement),
            "milestones": [dict(r) | {"done": bool(r["done"])} for r in conn.execute(
                "SELECT * FROM p07_milestones WHERE placement_id = ? ORDER BY milestone_id", (pid,))],
            "actions": actions, "final": final_reviews(conn, pid),
            "counts": {"logs_awaiting_supervisor": sum(1 for l in logs if l["status"] in ("submitted", "revised")
                                                       and l["period"] == "P1"),
                       "overdue_actions": sum(1 for a in actions if a["overdue"])},
            "people": {"supervisor": placement.get("supervisor_name") or DEMO_PEOPLE["supervisor"]["name"],
                       "advisor": placement.get("academic_advisor")}}
