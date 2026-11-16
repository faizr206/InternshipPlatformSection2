import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import db
from app.ai import AI_METHOD_VERSION, term_matches
from app.matching import RULES, is_eligible_listing, recommend

# Active = an application that blocks a duplicate for the same student+opportunity
# (agreed active statuses, see docs/data-dictionary.md). Drafts and Declined are not active.
ACTIVE_STATUSES = ("Submitted", "Under review", "Shortlisted")

# P04-04 transition matrix. Declined is terminal this sprint; offers arrive in
# Sprint 3 (P04-05) and can never follow a Declined application (P04-04 AC2).
DECISION_TRANSITIONS = {
    "Submitted": {"Under review"},
    "Under review": {"Shortlisted", "Declined"},
    "Shortlisted": {"Declined"},
}
NEXT_ACTIONS = {
    "Draft": "Finish the statement and submit while the listing is open",
    "Submitted": "Await employer review",
    "Under review": "Await employer decision (shortlist or decline)",
    "Shortlisted": "Await employer offer",
    "Declined": "Browse other opportunities or address the decline reason",
}

# P05-05 correction fields, mapped to the module that owns the record.
P01_FIELDS = ("availability", "interests", "skills")
P03_FIELDS = ("listing dates", "required skills", "listing status")

# Supervisor contact comes from P03 and is passed on to P07 with a confirmed placement;
# it is never shown to students (agreed with P01-P03, 10 Nov).
PRIVATE_LISTING_FIELDS = ("supervisor_name", "supervisor_contact")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Coop Platform P04/P05", lifespan=lifespan)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_student(conn, student_id: str) -> dict | None:
    """Effective profile: the latest correction revision if there is one, else the P01 fixture.

    P05 never edits the P01 fixture table; accepted corrections are stored as new
    versions in profile_revisions (P05-05 AC2).
    """
    row = conn.execute(
        "SELECT data FROM profile_revisions WHERE student_id = ? ORDER BY profile_version DESC LIMIT 1",
        (student_id,),
    ).fetchone()
    if not row:
        row = conn.execute("SELECT data FROM students WHERE student_id = ?", (student_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def get_opportunity(conn, opportunity_id: str) -> dict | None:
    row = conn.execute("SELECT data FROM opportunities WHERE opportunity_id = ?", (opportunity_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def all_opportunities(conn) -> list[dict]:
    return [json.loads(r["data"]) for r in conn.execute("SELECT data FROM opportunities ORDER BY opportunity_id")]


def student_view(opp: dict) -> dict:
    return {k: v for k, v in opp.items() if k not in PRIVATE_LISTING_FIELDS}


def rec_row_to_dict(r) -> dict:
    d = dict(r)
    d["compatible"] = bool(d["compatible"])
    for k in ("reasons", "gaps", "unknowns"):
        d[k] = json.loads(d[k])
    d["ai_matches"] = json.loads(d["ai_matches"]) if d.get("ai_matches") else []
    return d


def require_role(given: str, expected: str, action: str) -> None:
    """Simulated role check (no login). Real access control is a recorded, deferred gap."""
    if given != expected:
        raise HTTPException(
            403,
            f"Role '{given or 'none'}' is not allowed to {action}. "
            f"This action belongs to the {expected} role (simulated role switching; no login).",
        )


def _student_and_opportunity(conn, student_id: str, opportunity_id: str) -> tuple[dict, dict]:
    student = get_student(conn, student_id)
    if not student:
        raise HTTPException(400, "Unknown student")
    opp = get_opportunity(conn, opportunity_id)
    if not opp:
        raise HTTPException(400, "Unknown opportunity")
    return student, opp


def _add_event(conn, application_id: str, action: str, actor_role: str, actor_name: str,
               reason: str | None, created_at: str) -> None:
    conn.execute(
        "INSERT INTO application_events (application_id, action, actor_role, actor_name, reason, next_action, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (application_id, action, actor_role, actor_name, reason, NEXT_ACTIONS.get(action, ""), created_at),
    )


def application_dict(conn, row) -> dict:
    d = dict(row)
    d["history"] = [dict(e) for e in conn.execute(
        "SELECT action, actor_role, actor_name, reason, next_action, created_at FROM application_events "
        "WHERE application_id = ? ORDER BY event_id",
        (d["application_id"],),
    )]
    student = get_student(conn, d["student_id"])
    d["student_name"] = student["display_name"] if student else d["student_id"]
    opp = get_opportunity(conn, d["opportunity_id"])
    d["opportunity_title"] = opp["title"] if opp else d["opportunity_id"]
    d["employer_name"] = opp.get("employer_name") if opp else None
    return d


def correction_dict(conn, row) -> dict:
    d = dict(row)
    d["source_version"] = json.loads(d["source_version"])
    student = get_student(conn, d["student_id"])
    d["student_name"] = student["display_name"] if student else d["student_id"]
    return d


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/skills")
def list_skills():
    return db.skill_names()


@app.get("/api/rules")
def read_rules():
    return RULES


# --- Students (P01 stand-in + correction revisions) ---
@app.get("/api/students")
def list_students():
    with db.connect() as conn:
        ids = [r["student_id"] for r in conn.execute("SELECT student_id FROM students ORDER BY student_id")]
        return [get_student(conn, i) for i in ids]


@app.get("/api/students/{student_id}")
def read_student(student_id: str):
    with db.connect() as conn:
        student = get_student(conn, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    return student


# --- Opportunities (P04-01; P03 stand-in) ---
@app.get("/api/opportunities")
def list_opportunities(q: str = "", work_mode: str = ""):
    with db.connect() as conn:
        opps = [o for o in all_opportunities(conn) if is_eligible_listing(o)]
    if q:
        ql = q.lower()
        opps = [o for o in opps if ql in o["title"].lower() or ql in o["employer_name"].lower()]
    if work_mode:
        opps = [o for o in opps if o["work_mode"] == work_mode]
    return [student_view(o) for o in opps]


@app.get("/api/opportunities/{opportunity_id}")
def read_opportunity(opportunity_id: str):
    with db.connect() as conn:
        opp = get_opportunity(conn, opportunity_id)
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    return student_view(opp)


# --- Recommendations (P05-02, P05-03; AI assistance P05-04) ---
@app.post("/api/students/{student_id}/recommendations")
def run_recommendations(student_id: str):
    with db.connect() as conn:
        student = get_student(conn, student_id)
        if not student:
            raise HTTPException(404, "Student not found")
        opps = all_opportunities(conn)
        skills = db.skill_names()
        results = recommend(student, opps, skills)
        opps_by_id = {o["opportunity_id"]: o for o in opps}
        run_id, created_at = uuid.uuid4().hex[:8], now()
        for r in results:
            # Bounded AI assistance runs alongside the rules result and never
            # changes eligibility, score, gaps or unknowns (P05-04 AC2).
            r["ai_method_version"] = AI_METHOD_VERSION
            r["ai_matches"] = term_matches(student, opps_by_id[r["opportunity_id"]], skills)
            r["recommendation_id"] = f"REC-{uuid.uuid4().hex[:8]}"
            r["run_id"], r["created_at"] = run_id, created_at
            conn.execute(
                "INSERT INTO recommendations "
                "(recommendation_id, run_id, student_id, profile_version, opportunity_id, opportunity_version, "
                "method_version, score, compatible, reasons, gaps, unknowns, created_at, eligibility, "
                "ai_method_version, ai_matches) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["recommendation_id"], run_id, r["student_id"], r["profile_version"],
                 r["opportunity_id"], r["opportunity_version"], r["method_version"], r["score"],
                 int(r["compatible"]), json.dumps(r["reasons"]), json.dumps(r["gaps"]),
                 json.dumps(r["unknowns"]), created_at, r["eligibility"],
                 r["ai_method_version"], json.dumps(r["ai_matches"])),
            )
    return results


@app.get("/api/students/{student_id}/recommendations")
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


@app.get("/api/students/{student_id}/recommendation-runs")
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


# --- Applications (P04-03 submit; P04-02 drafts) ---
class ApplicationIn(BaseModel):
    student_id: str
    opportunity_id: str
    statement: str = ""
    actor_role: str = "student"


class DraftIn(BaseModel):
    student_id: str
    opportunity_id: str
    statement: str = ""
    actor_role: str = "student"


class DraftUpdateIn(BaseModel):
    statement: str | None = None  # None = keep the stored draft statement; "" = deliberately empty
    actor_role: str = "student"


def _do_submit(conn, student_id: str, opportunity_id: str, statement: str) -> dict:
    """Shared by direct submission and submit-from-draft. An existing draft for the
    same student+opportunity is converted, so no orphan draft is left behind."""
    student, opp = _student_and_opportunity(conn, student_id, opportunity_id)
    if not is_eligible_listing(opp):
        raise HTTPException(400, f"Opportunity is not open for applications "
                                 f"({opp['publication_status']}, {opp['listing_status']})")
    if not (statement or "").strip():
        raise HTTPException(422, "Statement is required before submission: write one or two sentences "
                                 "about why this role fits. Your draft is preserved.")
    dup = conn.execute(
        f"SELECT application_id FROM applications WHERE student_id = ? AND opportunity_id = ? "
        f"AND application_status IN ({','.join('?' * len(ACTIVE_STATUSES))})",
        (student_id, opportunity_id, *ACTIVE_STATUSES),
    ).fetchone()
    if dup:
        raise HTTPException(409, f"Duplicate: active application {dup['application_id']} already exists")
    ts = now()
    statement = statement.strip()
    draft = conn.execute(
        "SELECT application_id FROM applications WHERE student_id = ? AND opportunity_id = ? "
        "AND application_status = 'Draft'",
        (student_id, opportunity_id),
    ).fetchone()
    if draft:
        application_id = draft["application_id"]
        conn.execute(
            "UPDATE applications SET statement = ?, profile_version = ?, opportunity_version = ?, "
            "application_status = 'Submitted', placement_status = 'Not placed', "
            "submitted_at = ?, updated_at = ? WHERE application_id = ?",
            (statement, student["profile_version"], opp["version"], ts, ts, application_id),
        )
    else:
        count = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        application_id = f"APP-{count + 1:04d}"
        conn.execute(
            "INSERT INTO applications (application_id, student_id, profile_version, opportunity_id, "
            "opportunity_version, application_status, placement_status, submitted_at, statement, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (application_id, student["student_id"], student["profile_version"],
             opp["opportunity_id"], opp["version"], "Submitted", "Not placed", ts, statement, ts),
        )
    _add_event(conn, application_id, "Submitted", "student", student["display_name"], None, ts)
    row = conn.execute("SELECT * FROM applications WHERE application_id = ?", (application_id,)).fetchone()
    return application_dict(conn, row)


@app.post("/api/applications", status_code=201)
def submit_application(body: ApplicationIn):
    require_role(body.actor_role, "student", "submit an application")
    with db.connect() as conn:
        return _do_submit(conn, body.student_id, body.opportunity_id, body.statement)


@app.post("/api/applications/draft", status_code=201)
def save_draft(body: DraftIn):
    """Save or update a draft. Saving never submits (P04-02 AC2)."""
    require_role(body.actor_role, "student", "save a draft")
    with db.connect() as conn:
        student, opp = _student_and_opportunity(conn, body.student_id, body.opportunity_id)
        if not is_eligible_listing(opp):
            raise HTTPException(400, f"Opportunity is not open for applications "
                                     f"({opp['publication_status']}, {opp['listing_status']})")
        dup = conn.execute(
            f"SELECT application_id FROM applications WHERE student_id = ? AND opportunity_id = ? "
            f"AND application_status IN ({','.join('?' * len(ACTIVE_STATUSES))})",
            (body.student_id, body.opportunity_id, *ACTIVE_STATUSES),
        ).fetchone()
        if dup:
            raise HTTPException(409, f"You already applied to this opportunity ({dup['application_id']})")
        ts = now()
        existing = conn.execute(
            "SELECT application_id FROM applications WHERE student_id = ? AND opportunity_id = ? "
            "AND application_status = 'Draft'",
            (body.student_id, body.opportunity_id),
        ).fetchone()
        if existing:
            application_id = existing["application_id"]
            conn.execute(
                "UPDATE applications SET statement = ?, profile_version = ?, opportunity_version = ?, "
                "updated_at = ? WHERE application_id = ?",
                (body.statement, student["profile_version"], opp["version"], ts, application_id),
            )
        else:
            count = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
            application_id = f"APP-{count + 1:04d}"
            conn.execute(
                "INSERT INTO applications (application_id, student_id, profile_version, opportunity_id, "
                "opportunity_version, application_status, placement_status, submitted_at, statement, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (application_id, student["student_id"], student["profile_version"],
                 opp["opportunity_id"], opp["version"], "Draft", "Not placed", ts, body.statement, ts),
            )
        _add_event(conn, application_id, "Draft saved", "student", student["display_name"], None, ts)
        row = conn.execute("SELECT * FROM applications WHERE application_id = ?", (application_id,)).fetchone()
        return application_dict(conn, row)


@app.put("/api/applications/{application_id}")
def update_draft(application_id: str, body: DraftUpdateIn):
    """Edit a draft: saving keeps it a Draft (P04-02 AC1/AC2)."""
    require_role(body.actor_role, "student", "edit a draft")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM applications WHERE application_id = ?", (application_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Application not found")
        if row["application_status"] != "Draft":
            raise HTTPException(409, f"Only drafts can be edited; this application is {row['application_status']}")
        student = get_student(conn, row["student_id"])
        conn.execute(
            "UPDATE applications SET statement = ?, updated_at = ? WHERE application_id = ?",
            (body.statement, now(), application_id),
        )
        _add_event(conn, application_id, "Draft saved", "student", student["display_name"], None, now())
        fresh = conn.execute("SELECT * FROM applications WHERE application_id = ?", (application_id,)).fetchone()
        return application_dict(conn, fresh)


@app.post("/api/applications/{application_id}/submit", status_code=201)
def submit_draft(application_id: str, body: DraftUpdateIn):
    require_role(body.actor_role, "student", "submit an application")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM applications WHERE application_id = ?", (application_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Application not found")
        if row["application_status"] != "Draft":
            raise HTTPException(409, f"Only drafts can be submitted this way; "
                                     f"this application is {row['application_status']}")
        statement = body.statement if body.statement is not None else (row["statement"] or "")
        return _do_submit(conn, row["student_id"], row["opportunity_id"], statement)


@app.get("/api/students/{student_id}/applications")
def list_applications(student_id: str):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM applications WHERE student_id = ? ORDER BY submitted_at, application_id",
            (student_id,),
        ).fetchall()
        return [application_dict(conn, r) for r in rows]


@app.get("/api/applications")
def all_applications():
    """Every application with its history (employer queue and read-only faculty view)."""
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM applications ORDER BY submitted_at, application_id").fetchall()
        return [application_dict(conn, r) for r in rows]


# --- Employer decisions (P04-04) ---
class DecisionIn(BaseModel):
    action: str
    actor_role: str
    actor_name: str | None = None
    reason: str | None = None


@app.post("/api/applications/{application_id}/decisions", status_code=201)
def decide(application_id: str, body: DecisionIn):
    require_role(body.actor_role, "employer", "decide on an application")
    if body.action == "Offer":
        raise HTTPException(422, "Offers are not part of this sprint (P04-05, Sprint 3) — and an offer "
                                 "can never follow a Declined application.")
    if body.action not in ("Under review", "Shortlisted", "Declined"):
        raise HTTPException(422, f"Unknown action '{body.action}'. "
                                 f"Allowed: Under review, Shortlisted, Declined.")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM applications WHERE application_id = ?", (application_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Application not found")
        current = row["application_status"]
        allowed = DECISION_TRANSITIONS.get(current, set())
        if body.action not in allowed:
            options = ", ".join(sorted(allowed)) or "none (this status is final)"
            raise HTTPException(409, f"Cannot move {current} → {body.action}. Allowed next steps: {options}.")
        if body.action == "Declined" and not (body.reason or "").strip():
            raise HTTPException(422, "A reason is required when declining, so the student knows what to do next.")
        ts = now()
        conn.execute("UPDATE applications SET application_status = ?, updated_at = ? WHERE application_id = ?",
                     (body.action, ts, application_id))
        _add_event(conn, application_id, body.action, "employer",
                   (body.actor_name or "Employer reviewer (simulated)").strip() or "Employer reviewer (simulated)",
                   (body.reason or "").strip() or None, ts)
        fresh = conn.execute("SELECT * FROM applications WHERE application_id = ?", (application_id,)).fetchone()
        return application_dict(conn, fresh)


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


@app.post("/api/recommendations/{recommendation_id}/flags", status_code=201)
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


@app.get("/api/corrections")
def list_corrections():
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM correction_requests ORDER BY created_at, correction_id").fetchall()
        return [correction_dict(conn, r) for r in rows]


@app.post("/api/corrections/{correction_id}/record")
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


@app.post("/api/corrections/{correction_id}/accept")
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
        new_version = student["profile_version"] + 1
        new_profile["profile_version"] = new_version
        conn.execute(
            "INSERT INTO profile_revisions (student_id, profile_version, data, source, created_at) "
            "VALUES (?,?,?,?,?)",
            (row["student_id"], new_version, json.dumps(new_profile),
             f"correction:{correction_id}", now()),
        )
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
