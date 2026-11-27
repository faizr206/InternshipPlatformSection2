"""P05 AI-assisted matching: rules baseline, bounded AI, recommendation runs, correction
requests (P05-05) and skill gaps passed to P06 (P05-06).

Moved from legacy/p04-p05-coop/app/main.py without behaviour changes.
"""
import json
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db
from app.core.common import (all_opportunities, get_student, new_profile_version as _new_profile_version, now,
                             next_id, record_handoff, require_role, student_and_opportunity as _student_and_opportunity)
from app.modules.matching.ai import AI_METHOD_VERSION, insights, relevance_scores, statement_draft, term_matches
from app.modules.matching.matching import RULES, is_eligible_listing, recommend
from app.modules.preparation import service as prep

router = APIRouter(tags=["P05 matching"])

# P05-05 correction fields, mapped to the module that owns the record.
P01_FIELDS = ("availability", "interests", "skills")
P03_FIELDS = ("listing dates", "required skills", "listing status")

def rec_row_to_dict(r) -> dict:
    d = dict(r)
    d["compatible"] = bool(d["compatible"])
    for k in ("reasons", "gaps", "unknowns"):
        d[k] = json.loads(d[k])
    d["ai_matches"] = json.loads(d["ai_matches"]) if d.get("ai_matches") else []
    d["ai_insights"] = json.loads(d["ai_insights"]) if d.get("ai_insights") else None
    return d

def correction_dict(conn, row) -> dict:
    d = dict(row)
    d["source_version"] = json.loads(d["source_version"])
    student = get_student(conn, d["student_id"])
    d["student_name"] = student["display_name"] if student else d["student_id"]
    return d

@router.get("/api/skills")
def list_skills():
    return db.skill_names()


@router.get("/api/rules")
def read_rules():
    return RULES


# --- Recommendations (P05-02, P05-03; AI assistance P05-04) ---
@router.post("/api/students/{student_id}/recommendations")
def run_recommendations(student_id: str):
    with db.connect() as conn:
        student = get_student(conn, student_id)
        if not student:
            raise HTTPException(404, "Student not found")
        return _run_matching(conn, student)


def _run_matching(conn, student: dict) -> list[dict]:
    """Store a new run against the student's current profile version (P05-02, P05-07)."""
    opps = all_opportunities(conn)
    skills = db.skill_names()
    results = recommend(student, opps, skills)
    opps_by_id = {o["opportunity_id"]: o for o in opps}
    open_opps = [o for o in opps if is_eligible_listing(o)]
    relevance = relevance_scores(student, open_opps, skills)
    run_id, created_at = uuid.uuid4().hex[:8], now()
    for r in results:
        # Bounded AI assistance runs alongside the rules result and never
        # changes eligibility, score, gaps or unknowns (P05-04 AC2).
        r["ai_method_version"] = AI_METHOD_VERSION
        o = opps_by_id[r["opportunity_id"]]
        r["ai_matches"] = term_matches(student, o, skills)
        r["ai_insights"] = insights(student, o, r, r["ai_matches"], open_opps, skills,
                                    RULES["weights"], relevance[r["opportunity_id"]])
        r["recommendation_id"] = f"REC-{uuid.uuid4().hex[:8]}"
        r["run_id"], r["created_at"] = run_id, created_at
        conn.execute(
            "INSERT INTO recommendations "
            "(recommendation_id, run_id, student_id, profile_version, opportunity_id, opportunity_version, "
            "method_version, score, compatible, reasons, gaps, unknowns, created_at, eligibility, "
            "ai_method_version, ai_matches, ai_insights) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["recommendation_id"], run_id, r["student_id"], r["profile_version"],
             r["opportunity_id"], r["opportunity_version"], r["method_version"], r["score"],
             int(r["compatible"]), json.dumps(r["reasons"]), json.dumps(r["gaps"]),
             json.dumps(r["unknowns"]), created_at, r["eligibility"],
             r["ai_method_version"], json.dumps(r["ai_matches"]), json.dumps(r["ai_insights"])),
        )
    return results


@router.get("/api/students/{student_id}/recommendations")
def latest_recommendations(student_id: str):
    with db.connect() as conn:
        last = conn.execute(
            "SELECT run_id FROM recommendations WHERE student_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (student_id,),
        ).fetchone()
        if not last:
            return []
        rows = conn.execute(
            "SELECT * FROM recommendations WHERE run_id = ? "
            "ORDER BY CASE eligibility WHEN 'eligible' THEN 0 WHEN 'unknown' THEN 1 ELSE 2 END, "
            "score DESC, opportunity_id",
            (last["run_id"],),
        ).fetchall()
    return [rec_row_to_dict(r) for r in rows]


class StatementDraftIn(BaseModel):
    student_id: str
    opportunity_id: str


@router.post("/api/ai/statement-draft")
def ai_statement_draft(body: StatementDraftIn):
    """AI starter statement for the apply dialog. It is returned to the student to edit;
    nothing is saved or submitted here (P05-04 bounds: cites only skills on the profile)."""
    with db.connect() as conn:
        student, opp = _student_and_opportunity(conn, body.student_id, body.opportunity_id)
    return statement_draft(student, opp, db.skill_names())


@router.get("/api/students/{student_id}/recommendation-runs")
def recommendation_runs(student_id: str):
    """Every stored run for the student, so earlier recommendations stay traceable
    after a correction and rematch (P05-05 AC2)."""
    with db.connect() as conn:
        if not get_student(conn, student_id):
            raise HTTPException(404, "Student not found")
        rows = conn.execute(
            "SELECT run_id, MIN(created_at) AS created_at, profile_version, method_version, "
            "MIN(ai_method_version) AS ai_method_version, COUNT(*) AS results, "
            "SUM(CASE WHEN eligibility = 'eligible' THEN 1 ELSE 0 END) AS eligible "
            "FROM recommendations WHERE student_id = ? GROUP BY run_id ORDER BY MIN(rowid)",
            (student_id,),
        ).fetchall()
    return [dict(r) for r in rows]

# --- Correction requests (P05-05) ---
class FlagIn(BaseModel):
    reason: str
    affected_field: str
    actor_role: str = "student"


class RecordIn(BaseModel):
    note: str = ""
    actor_role: str
    actor_name: str | None = None


class AcceptCorrectionIn(BaseModel):
    actor_role: str
    actor_name: str | None = None
    availability_start: str | None = None
    availability_end: str | None = None
    interests: list[str] | None = None


@router.post("/api/recommendations/{recommendation_id}/flags", status_code=201)
def flag_recommendation(recommendation_id: str, body: FlagIn):
    require_role(body.actor_role, "student", "flag a recommendation")
    if not body.reason.strip():
        raise HTTPException(422, "A reason is required so the coordinator knows what to check.")
    if body.affected_field in P01_FIELDS:
        source_module = "P01"
    elif body.affected_field in P03_FIELDS:
        source_module = "P03"
    else:
        raise HTTPException(422, f"Unsupported field '{body.affected_field}'. "
                                 f"Profile fields: {', '.join(P01_FIELDS)}; listing fields: {', '.join(P03_FIELDS)}.")
    with db.connect() as conn:
        rec = conn.execute("SELECT * FROM recommendations WHERE recommendation_id = ?",
                           (recommendation_id,)).fetchone()
        if not rec:
            raise HTTPException(404, "Recommendation not found")
        count = conn.execute("SELECT COUNT(*) FROM correction_requests").fetchone()[0]
        correction_id = f"CR-{count + 1:04d}"
        # Snapshot the input versions the student is challenging (P05-05 AC1).
        source_version = json.dumps({
            "profile_version": rec["profile_version"],
            "opportunity_id": rec["opportunity_id"],
            "opportunity_version": rec["opportunity_version"],
            "method_version": rec["method_version"],
        })
        conn.execute(
            "INSERT INTO correction_requests (correction_id, recommendation_id, student_id, reason, "
            "affected_field, source_module, source_version, status, coordinator, note, created_at, decided_at) "
            "VALUES (?,?,?,?,?,?,?, 'flagged', NULL, NULL, ?, NULL)",
            (correction_id, recommendation_id, rec["student_id"], body.reason.strip(),
             body.affected_field, source_module, source_version, now()),
        )
        row = conn.execute("SELECT * FROM correction_requests WHERE correction_id = ?",
                           (correction_id,)).fetchone()
        return correction_dict(conn, row)


@router.get("/api/corrections")
def list_corrections():
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM correction_requests ORDER BY created_at, correction_id").fetchall()
        return [correction_dict(conn, r) for r in rows]


@router.post("/api/corrections/{correction_id}/record")
def record_correction(correction_id: str, body: RecordIn):
    require_role(body.actor_role, "coordinator", "record a correction request")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM correction_requests WHERE correction_id = ?",
                           (correction_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Correction request not found")
        if row["status"] != "flagged":
            raise HTTPException(409, f"This request is already {row['status']}.")
        coordinator = (body.actor_name or "COORD-01 (simulated coordinator)").strip()
        conn.execute(
            "UPDATE correction_requests SET status = 'recorded', coordinator = ?, note = ?, decided_at = ? "
            "WHERE correction_id = ?",
            (coordinator, body.note.strip(), now(), correction_id),
        )
        fresh = conn.execute("SELECT * FROM correction_requests WHERE correction_id = ?",
                             (correction_id,)).fetchone()
        return correction_dict(conn, fresh)


@router.post("/api/corrections/{correction_id}/accept")
def accept_correction(correction_id: str, body: AcceptCorrectionIn):
    """Accept a correction: the owning module applies it as a NEW input version,
    which can then be rematched. The original recommendation stays traceable."""
    require_role(body.actor_role, "coordinator", "accept a correction")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM correction_requests WHERE correction_id = ?",
                           (correction_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Correction request not found")
        if row["status"] != "recorded":
            raise HTTPException(409, "Record the correction request for the owning module before accepting it.")
        if row["source_module"] == "P03":
            raise HTTPException(422, "Listing corrections are for the P03 owning module. A new listing version "
                                     "needs the live P03 interface (deferred); this request stays recorded.")
        student = get_student(conn, row["student_id"])
        if not student:
            raise HTTPException(404, "Student not found")
        field = row["affected_field"]
        new_profile = json.loads(json.dumps(student))  # deep copy; the fixture row is never edited
        if field == "availability":
            if not (body.availability_start and body.availability_end):
                raise HTTPException(422, "Provide availability_start and availability_end for this correction.")
            new_profile["availability_start"] = body.availability_start.strip()
            new_profile["availability_end"] = body.availability_end.strip()
        elif field == "interests":
            if not body.interests:
                raise HTTPException(422, "Provide the corrected interests list for this correction.")
            new_profile["interests"] = [i.strip() for i in body.interests if i.strip()]
        else:  # skills
            raise HTTPException(422, "Skill-evidence corrections are reviewed by P01/P06 with evidence; "
                                     "applying one here is deferred (recorded only).")
        new_version = _new_profile_version(conn, new_profile, f"correction:{correction_id}")
        conn.execute(
            "UPDATE correction_requests SET status = 'accepted', decided_at = ? WHERE correction_id = ?",
            (now(), correction_id),
        )
        return {
            "correction_id": correction_id,
            "status": "accepted",
            "student_id": row["student_id"],
            "affected_field": field,
            "new_profile_version": new_version,
            "decided_at": now(),
        }


# --- Skill gap → P06 preparation (P05-06) ---
GAP_NO_MODULE_ACTION = ("Team P6/P7 has no preparation module for this skill yet. Next step: ask your "
                        "coordinator for a preparation route, or check the P06 plan again later.")
GAP_EVIDENCE_NOTE = ("Completing an activity does not by itself show the skill. A faculty reviewer must "
                     "review your evidence before matching treats it as reviewed.")


class GapHandoffIn(BaseModel):
    actor_role: str


class GapCompleteIn(BaseModel):
    actor_role: str


def gap_dict(conn, row) -> dict:
    d = dict(row)
    activity = db.p06_activities().get(d["skill_id"]) if d["activity_id"] else None
    d["skill_name"] = db.skill_names().get(d["skill_id"], d["skill_id"])
    d["activity"] = activity
    d["source"] = "P06 activity list from Team P6/P7 (file, 24 Nov; live P06 module not connected)"
    d["next_action"] = (GAP_EVIDENCE_NOTE if activity else GAP_NO_MODULE_ACTION)
    p06 = conn.execute("SELECT status FROM prep_gaps WHERE gap_id = ?", (d["gap_id"],)).fetchone()
    d["p06_status"] = p06["status"] if p06 else None
    # P06's requested record (Zhengxi, 10 Nov): gap_id, student_id, skill_id, opportunity_id,
    # reason; plus the three trace fields we agreed to add.
    d["p06_payload"] = {
        "gap_id": d["gap_id"], "student_id": d["student_id"], "skill_id": d["skill_id"],
        "opportunity_id": d["opportunity_id"],
        "reason": f"{d['opportunity_id']} requires {d['skill_name']}; not yet demonstrated",
        "recommendation_id": d["recommendation_id"], "opportunity_version": d["opportunity_version"],
        "profile_version": d["profile_version"],
    }
    return d


@router.post("/api/recommendations/{recommendation_id}/gaps/{skill_id}/handoff", status_code=201)
def handoff_gap(recommendation_id: str, skill_id: str, body: GapHandoffIn):
    """Pass a named gap to P06 with its source IDs and versions (P05-06 AC1). Repeating
    it for the same recommendation and skill returns the same record."""
    require_role(body.actor_role, "student", "send a skill gap to preparation")
    with db.connect() as conn:
        rec = conn.execute("SELECT * FROM recommendations WHERE recommendation_id = ?",
                           (recommendation_id,)).fetchone()
        if not rec:
            raise HTTPException(404, "Recommendation not found")
        if not any(g.endswith(f"({skill_id})") for g in json.loads(rec["gaps"])):
            raise HTTPException(422, f"{skill_id} is not a gap in this recommendation.")
        existing = conn.execute("SELECT * FROM skill_gap_handoffs WHERE recommendation_id = ? AND skill_id = ?",
                                (recommendation_id, skill_id)).fetchone()
        if existing:
            return gap_dict(conn, existing)
        activity = db.p06_activities().get(skill_id)
        # GAP ids are shared with gaps the coordinator enters in P06, so take the next free one in both.
        gap_id = next_id(conn, "GAP", ["SELECT gap_id FROM skill_gap_handoffs", "SELECT gap_id FROM prep_gaps"], 4)
        conn.execute(
            "INSERT INTO skill_gap_handoffs (gap_id, student_id, skill_id, opportunity_id, opportunity_version, "
            "recommendation_id, profile_version, activity_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (gap_id, rec["student_id"], skill_id, rec["opportunity_id"], rec["opportunity_version"],
             recommendation_id, rec["profile_version"], activity["activity_id"] if activity else None, now()),
        )
        row = conn.execute("SELECT * FROM skill_gap_handoffs WHERE gap_id = ?", (gap_id,)).fetchone()
        payload = gap_dict(conn, row)["p06_payload"]
        # Live P05 -> P06 handoff: skills with a P06 module go straight onto the preparation plan
        # (one open gap per skill); the handoff record keeps the agreed v3 payload as evidence.
        if prep.module_for_skill(skill_id):
            student = get_student(conn, rec["student_id"])
            prep.add_gap(conn, rec["student_id"], skill_id, payload["reason"], "P05", student["display_name"],
                         gap_id=gap_id, opportunity_id=rec["opportunity_id"],
                         opportunity_version=rec["opportunity_version"], recommendation_id=recommendation_id,
                         profile_version=rec["profile_version"])
            status = "delivered"
        else:
            status = "no_p06_module"
        record_handoff(conn, "P05", "P06", "skill_gap", payload, rec["student_id"], gap_id, status)
        return gap_dict(conn, row)


@router.post("/api/skill-gaps/{gap_id}/complete")
def complete_gap_activity(gap_id: str, body: GapCompleteIn):
    """Record that the student finished the P06 activity. This never changes a
    recommendation or marks the skill as reviewed (P05-06 AC2)."""
    require_role(body.actor_role, "student", "mark a preparation activity done")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM skill_gap_handoffs WHERE gap_id = ?", (gap_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Skill gap not found")
        if not row["activity_id"]:
            raise HTTPException(409, GAP_NO_MODULE_ACTION)
        conn.execute("UPDATE skill_gap_handoffs SET completed_at = COALESCE(completed_at, ?) WHERE gap_id = ?",
                     (now(), gap_id))
        return gap_dict(conn, conn.execute("SELECT * FROM skill_gap_handoffs WHERE gap_id = ?",
                                           (gap_id,)).fetchone())


@router.get("/api/students/{student_id}/skill-gaps")
def list_skill_gaps(student_id: str):
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM skill_gap_handoffs WHERE student_id = ? ORDER BY gap_id",
                            (student_id,)).fetchall()
        return [gap_dict(conn, r) for r in rows]


@router.get("/api/p06/activities")
def list_p06_activities():
    return list(db.p06_activities().values())
