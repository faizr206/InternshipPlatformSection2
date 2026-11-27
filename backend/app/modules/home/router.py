"""Home page data (shared): one student's journey across P01-P07, each role's to-do list and sidebar badges.

Everything is computed from the modules' own records; nothing here is stored."""
import json

from fastapi import APIRouter, HTTPException

from app import db
from app.core.common import get_opportunity, get_student, today
from app.modules.preparation import service as prep
from app.modules.progress import service as p07
from app.modules.review.router import is_pending

router = APIRouter(prefix="/api/home", tags=["Home"])

ACTIVE = ("Submitted", "Under review", "Shortlisted", "Interview scheduled", "Interview completed", "Offered",
          "Offer accepted")
NAV_FOR_HREF = {"/profile": "profile", "/opportunities": "opportunities", "/applications": "applications",
                "/matching": "matching", "/preparation": "preparation", "/placement": "placement",
                "/assistant": "assistant", "/records": "records"}


def stage(owner, label, status, detail, ref=None):
    return {"owner": owner, "label": label, "status": status, "detail": detail, "ref": ref}


def _focus_application(conn, student_id: str):
    rows = conn.execute("SELECT * FROM applications WHERE student_id = ? ORDER BY updated_at DESC, application_id DESC",
                        (student_id,)).fetchall()
    confirmed = [r for r in rows if r["placement_status"] == "Confirmed"]
    active = [r for r in rows if r["application_status"] in ACTIVE]
    return (confirmed or active or rows or [None])[0]


def journey_for(conn, student_id: str) -> dict:
    student = get_student(conn, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    stages = []

    # P01 profile
    review = conn.execute("SELECT decision FROM profile_reviews WHERE student_id = ? AND profile_version = ? "
                          "ORDER BY review_id DESC LIMIT 1", (student_id, student["profile_version"])).fetchone()
    missing = [f for f, ok in (("interests", student.get("interests")),
                               ("availability", student.get("availability_start") and student.get("availability_end"))) if not ok]
    if review and review["decision"] == "clarification_requested":
        stages.append(stage("P01", "Profile", "blocked", f"v{student['profile_version']}: clarification requested", student_id))
    elif missing:
        stages.append(stage("P01", "Profile", "current", f"v{student['profile_version']}: add {' and '.join(missing)}", student_id))
    else:
        stages.append(stage("P01", "Profile", "done", f"v{student['profile_version']} submitted"
                            + (", reviewed" if review else ""), student_id))

    app = _focus_application(conn, student_id)
    rec = conn.execute("SELECT * FROM recommendations WHERE student_id = ? AND run_id = (SELECT run_id FROM "
                       "recommendations WHERE student_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1) "
                       "ORDER BY CASE eligibility WHEN 'eligible' THEN 0 WHEN 'unknown' THEN 1 ELSE 2 END, score DESC",
                       (student_id, student_id)).fetchall()
    opp_id = app["opportunity_id"] if app else (rec[0]["opportunity_id"] if rec else "OP-028")
    opp = get_opportunity(conn, opp_id) or {}

    # P02 / P03 listing
    stages.append(stage("P02", "Employer listing", "done" if opp else "upcoming",
                        f"{opp_id} v{opp.get('version')} from {opp.get('employer_name')}" if opp else "No listing yet", opp_id))
    if opp.get("listing_status") == "closed":
        stages.append(stage("P03", "Review & publication", "blocked", f"{opp_id} is closed", opp_id))
    elif opp.get("publication_status") == "published":
        stages.append(stage("P03", "Review & publication", "done", f"{opp_id} published and open", opp_id))
    else:
        stages.append(stage("P03", "Review & publication", "current" if opp else "upcoming",
                            f"{opp_id} awaiting university review" if opp else "Waiting for a listing", opp_id))

    # P05 matching
    if rec:
        eligible = sum(1 for r in rec if r["eligibility"] == "eligible")
        gaps = sum(len(json.loads(r["gaps"])) for r in rec if r["opportunity_id"] == opp_id)
        stages.append(stage("P05", "Matching", "done",
                            f"{eligible} eligible on profile v{rec[0]['profile_version']}"
                            + (f"; {gaps} gap(s) on {opp_id}" if gaps else ""), rec[0]["run_id"]))
    else:
        stages.append(stage("P05", "Matching", "current", "Run matching to see explained recommendations"))

    # P06 preparation
    gaps = conn.execute("SELECT status FROM prep_gaps WHERE student_id = ?", (student_id,)).fetchall()
    open_gaps = sum(1 for g in gaps if g["status"] == "open")
    demonstrated = prep.demonstrated(conn, student_id)
    if open_gaps:
        stages.append(stage("P06", "Preparation", "current", f"{open_gaps} open gap(s); {len(demonstrated)} skill(s) demonstrated"))
    elif gaps:
        stages.append(stage("P06", "Preparation", "done", f"{len(demonstrated)} skill(s) demonstrated with reviewed evidence"))
    else:
        stages.append(stage("P06", "Preparation", "upcoming", "No skill gaps sent yet"))

    # P04 application (shown before P07; ordered P01..P07 by owner below)
    if not app:
        stages.append(stage("P04", "Application", "upcoming", "Not applied yet"))
    elif app["placement_status"] == "Confirmed":
        stages.append(stage("P04", "Application", "done", f"{app['application_id']}: placement confirmed", app["application_id"]))
    elif app["application_status"] in ("Declined", "Withdrawn", "Offer declined"):
        stages.append(stage("P04", "Application", "blocked", f"{app['application_id']}: {app['application_status']}", app["application_id"]))
    else:
        detail = app["application_status"] + (" — awaiting university confirmation" if app["application_status"] == "Offer accepted" else "")
        stages.append(stage("P04", "Application", "current", f"{app['application_id']}: {detail}", app["application_id"]))

    # P07 co-op progress
    placement = p07.placement_for(conn, student_id)
    if not placement:
        stages.append(stage("P07", "Co-op progress", "upcoming", "Starts when the university confirms a placement"))
    else:
        final = p07.final_reviews(conn, placement["placement_id"])
        agreement = p07.agreement(conn, placement["placement_id"])
        if final["advisor"]:
            stages.append(stage("P07", "Co-op progress", "done", "Period 1 final review recorded", placement["placement_id"]))
        else:
            detail = (f"{placement['placement_id']}: agreement {agreement['status']}"
                      if agreement["status"] != "agreed" else f"{placement['placement_id']}: week "
                      f"{max(1, p07.week_of(placement, today(conn)))} of Period 1")
            stages.append(stage("P07", "Co-op progress", "current", detail, placement["placement_id"]))

    order = ["P01", "P02", "P03", "P05", "P06", "P04", "P07"]
    stages.sort(key=lambda s: order.index(s["owner"]))
    return {"student_id": student_id, "display_name": student["display_name"], "stages": stages}


def todo(id_, title, detail, owner, href, priority="normal", count=None, due=None):
    return {"id": id_, "title": title, "detail": detail, "owner": owner, "href": href, "priority": priority,
            "count": count, "due": due}


def todos_for(conn, role: str, student_id: str) -> list[dict]:
    out = []
    on = today(conn)
    if role == "student":
        student = get_student(conn, student_id)
        if not student:
            raise HTTPException(404, "Student not found")
        review = conn.execute("SELECT decision, comment FROM profile_reviews WHERE student_id = ? AND profile_version = ? "
                              "ORDER BY review_id DESC LIMIT 1", (student_id, student["profile_version"])).fetchone()
        if review and review["decision"] == "clarification_requested":
            out.append(todo("profile-clarify", "Clarify your profile", review["comment"], "P01", "/profile", "high"))
        if conn.execute("SELECT 1 FROM profile_drafts WHERE student_id = ?", (student_id,)).fetchone():
            out.append(todo("profile-draft", "Submit your profile draft", "Your draft is saved but not submitted", "P01", "/profile"))
        if not conn.execute("SELECT 1 FROM recommendations WHERE student_id = ?", (student_id,)).fetchone():
            out.append(todo("run-matching", "See your recommendations", "Explained matches for your profile", "P05", "/matching"))
        for r in conn.execute("SELECT application_id, opportunity_id FROM applications WHERE student_id = ? AND "
                              "application_status = 'Offered'", (student_id,)):
            out.append(todo(f"offer-{r['application_id']}", "Respond to your offer", f"{r['opportunity_id']} ({r['application_id']})",
                            "P04", "/applications", "high"))
        step = prep.plan(conn, student_id)["next_step"]
        if step["kind"] in ("learn", "practise", "revise", "retry"):
            out.append(todo("prep-next", "Preparation: next step", step["text"], "P06", "/preparation",
                            "high" if step["kind"] == "revise" else "normal"))
        placement = p07.placement_for(conn, student_id)
        if placement:
            pid = placement["placement_id"]
            agreement = p07.agreement(conn, pid)
            if agreement["status"] != "agreed" and len(agreement["goals"]) < 3:
                out.append(todo("goals", "Draft your learning goals", f"{len(agreement['goals'])} of 3 goals", "P07", "/placement"))
            elif agreement["status"] != "agreed" and not agreement["signoffs"]["student"]:
                out.append(todo("sign-student", "Agree your learning agreement", "Three goals are ready", "P07", "/placement"))
            for row in conn.execute("SELECT * FROM p07_logs WHERE placement_id = ?", (pid,)):
                log = p07.log_dict(row)
                if log["status"] == "feedback":
                    out.append(todo(f"log-{log['log_id']}", f"Revise {log['log_id']}", log["feedback"][-1]["text"], "P07",
                                    "/placement", "high"))
            out += _actions(conn, pid, "student", on)
    elif role == "employer":
        pending = [r for r in conn.execute("SELECT application_id, application_status FROM applications WHERE "
                                           "application_status IN ('Submitted','Under review','Shortlisted','Interview completed')")]
        if pending:
            out.append(todo("decide", "Review applications", f"{len(pending)} application(s) waiting for a decision",
                            "P04", "/applications", "high", len(pending)))
        returned = [o for o in _listings(conn) if o.get("review_status") == "returned"]
        if returned:
            out.append(todo("resubmit", "Revise returned listings", ", ".join(o["opportunity_id"] for o in returned),
                            "P02", "/opportunities", "high", len(returned)))
    elif role == "coordinator":
        queue = [o for o in _listings(conn) if is_pending(o)]
        if queue:
            out.append(todo("review-queue", "Review submitted listings", f"{len(queue)} waiting", "P03", "/opportunities",
                            "high", len(queue)))
        accepted = conn.execute("SELECT COUNT(*) FROM applications WHERE application_status = 'Offer accepted' AND "
                                "placement_status != 'Confirmed'").fetchone()[0]
        if accepted:
            out.append(todo("confirm", "Confirm placements", f"{accepted} accepted offer(s) awaiting confirmation",
                            "P04", "/applications", "high", accepted))
        flagged = conn.execute("SELECT COUNT(*) FROM correction_requests WHERE status != 'accepted'").fetchone()[0]
        if flagged:
            out.append(todo("corrections", "Check flagged recommendations", f"{flagged} correction request(s)", "P05",
                            "/matching", "normal", flagged))
        no_advisor = [p for p in (json.loads(r["data"]) for r in conn.execute("SELECT data FROM p07_placements"))
                      if not p["academic_advisor"]]
        if no_advisor:
            out.append(todo("advisor", "Assign academic advisors", ", ".join(p["placement_id"] for p in no_advisor), "P07",
                            "/placement", "high", len(no_advisor)))
        questions = conn.execute("SELECT COUNT(*) FROM assistant_questions WHERE status = 'open'").fetchone()[0]
        pending_entries = conn.execute("SELECT COUNT(*) FROM assistant_entries WHERE status = 'pending'").fetchone()[0]
        if questions or pending_entries:
            out.append(todo("assistant", "Answer assistant questions",
                            f"{questions} handed over, {pending_entries} answer(s) to approve", "P06", "/assistant",
                            "normal", questions + pending_entries))
        clarify = conn.execute("SELECT COUNT(DISTINCT student_id) FROM profile_drafts").fetchone()[0]
        if clarify:
            out.append(todo("drafts", "Profiles in draft", f"{clarify} student(s) editing their profile", "P01", "/profile",
                            "low", clarify))
    elif role == "reviewer":
        queue = prep.review_queue(conn)
        if queue:
            out.append(todo("evidence", "Review submitted evidence",
                            ", ".join(f"{s['evidence_id']} ({s['display_name']})" for s in queue), "P06", "/preparation",
                            "high", len(queue)))
    elif role in ("supervisor", "advisor"):
        for raw in conn.execute("SELECT data FROM p07_placements"):
            placement = json.loads(raw["data"])
            pid = placement["placement_id"]
            agreement = p07.agreement(conn, pid)
            if agreement["status"] != "agreed" and len(agreement["goals"]) == 3 and not agreement["signoffs"][role] \
                    and (role != "advisor" or placement["academic_advisor"]):
                out.append(todo(f"sign-{pid}", "Agree the learning agreement", pid, "P07", "/placement", "high"))
            if role == "supervisor":
                waiting = [p07.log_dict(r) for r in conn.execute("SELECT * FROM p07_logs WHERE placement_id = ?", (pid,))]
                waiting = [l for l in waiting if l["status"] in ("submitted", "revised") and l["period"] == "P1"]
                if waiting:
                    out.append(todo(f"logs-{pid}", "Read log entries", ", ".join(l["log_id"] for l in waiting), "P07",
                                    "/placement", "high", len(waiting)))
                if on > placement["period_end"] and not p07.final_reviews(conn, pid)["employer"]:
                    out.append(todo(f"feedback-{pid}", "Give employer feedback", f"Period 1 ended {placement['period_end']}",
                                    "P07", "/placement", "high"))
            else:
                missing = [j["outcome_id"] for j in p07.judgements(conn, placement) if j["evidence_missing"]]
                if missing and agreement["status"] == "agreed":
                    out.append(todo(f"judge-{pid}", "Outcomes without evidence", ", ".join(missing), "P07", "/placement",
                                    "normal", len(missing)))
                if on > placement["period_end"] and not p07.final_reviews(conn, pid)["advisor"]:
                    out.append(todo(f"final-{pid}", "Record the final review", f"Period 1 ended {placement['period_end']}",
                                    "P07", "/placement", "high"))
            out += _actions(conn, pid, role, on)
    else:
        raise HTTPException(422, "Unknown role")
    return out


def _actions(conn, placement_id: str, owner: str, on: str) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM p07_actions WHERE placement_id = ?", (placement_id,)):
        a = p07.action_dict(r, on)
        if a["status"] == "open" and (a["owner"] == owner or (owner == "advisor" and a["overdue"])):
            out.append(todo(f"action-{a['action_id']}", f"{'Overdue: ' if a['overdue'] else ''}{a['action_id']}", a["text"],
                            "P07", "/placement", "high" if a["overdue"] else "normal", due=a["due"]))
    return out


def _listings(conn) -> list[dict]:
    from app.core.common import all_opportunities
    return all_opportunities(conn)


@router.get("/journey/{student_id}")
def journey(student_id: str):
    with db.connect() as conn:
        return journey_for(conn, student_id)


@router.get("/todos")
def todos(role: str, student_id: str = "COOP-B001"):
    with db.connect() as conn:
        return todos_for(conn, role, student_id)


@router.get("/counts")
def counts(role: str, student_id: str = "COOP-B001"):
    """Sidebar badges: the number of to-dos per nav item."""
    out: dict[str, int] = {}
    with db.connect() as conn:
        for t in todos_for(conn, role, student_id):
            key = NAV_FOR_HREF.get(t["href"])
            if key:
                out[key] = out.get(key, 0) + (t["count"] or 1)
    return out
