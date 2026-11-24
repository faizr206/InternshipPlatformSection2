import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db, live_jobs
from app.ai import AI_METHOD_VERSION, insights, relevance_scores, statement_draft, term_matches
from app.matching import RULES, is_eligible_listing, recommend

# Active = an application that blocks a duplicate for the same student+opportunity
# (agreed active statuses, see docs/data-dictionary.md). Drafts, Declined, Offer declined
# and Withdrawn are not active.
ACTIVE_STATUSES = ("Submitted", "Under review", "Shortlisted", "Interview scheduled", "Interview completed", "Offered", "Offer accepted")

# Employer transition matrix (P04-04, extended for offers in P04-05). Declined is
# terminal and can never be followed by an offer (P04-04 AC2).
DECISION_TRANSITIONS = {
    "Submitted": {"Under review"},
    "Under review": {"Shortlisted", "Declined"},
    "Shortlisted": {"Offered", "Declined"},
    "Interview completed": {"Offered", "Declined"},
    "Interview scheduled": {"Declined"},
}
EMPLOYER_ACTIONS = {"Under review": "Under review", "Shortlisted": "Shortlisted",
                    "Declined": "Declined", "Offer": "Offered"}

# P04-07: the agreed withdrawable states.
WITHDRAWABLE = ("Submitted", "Under review", "Shortlisted", "Interview scheduled", "Interview completed")

NEXT_ACTIONS = {
    "Draft": "Finish the statement and submit while the listing is open",
    "Submitted": "Await employer review",
    "Under review": "Await employer decision (shortlist or decline)",
    "Shortlisted": "Await interview invitation or employer offer",
    "Interview rescheduled": "Attend the interview at the updated time",
    "Interview scheduled": "Attend the interview at the scheduled time",
    "Interview completed": "Await employer decision",
    "Declined": "Browse other opportunities or address the decline reason",
    "Offered": "Accept or decline the offer",
    "Offer accepted": "Await university confirmation (this is not yet a placement)",
    "Offer declined": "Browse other opportunities",
    "Withdrawn": "No further action; apply again while the listing is open",
    "Placement confirmed": "Placement handed to P07 to start the learning record",
}

# Placement status is shown separately from the application status.
PLACEMENT_NOT_PLACED = "Not placed"
PLACEMENT_AWAITING = "Awaiting university confirmation"
PLACEMENT_CONFIRMED = "Confirmed"

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
    rev = conn.execute(
        "SELECT profile_version, data FROM profile_revisions WHERE student_id = ? "
        "ORDER BY profile_version DESC LIMIT 1",
        (student_id,),
    ).fetchone()
    base = conn.execute("SELECT profile_version, data FROM students WHERE student_id = ?", (student_id,)).fetchone()
    # The newer version wins, so a newer P01 export is never hidden by an older local revision.
    row = rev if rev and (not base or rev["profile_version"] > base["profile_version"]) else base
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
    d["ai_insights"] = json.loads(d["ai_insights"]) if d.get("ai_insights") else None
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
    interview = conn.execute("SELECT * FROM interviews WHERE application_id = ?", (d["application_id"],)).fetchone()
    d["interview"] = dict(interview) if interview else None
    opp = get_opportunity(conn, d["opportunity_id"])
    d["opportunity_title"] = opp["title"] if opp else d["opportunity_id"]
    d["employer_name"] = opp.get("employer_name") if opp else None
    return d


def _new_profile_version(conn, new_profile: dict, source: str) -> int:
    """Store a changed profile as the next version. Earlier versions (and the P01
    fixture row) are never edited, so older recommendations keep their inputs."""
    current = get_student(conn, new_profile["student_id"])
    new_version = current["profile_version"] + 1
    new_profile["profile_version"] = new_version
    conn.execute(
        "INSERT INTO profile_revisions (student_id, profile_version, data, source, created_at) "
        "VALUES (?,?,?,?,?)",
        (new_profile["student_id"], new_version, json.dumps(new_profile), source, now()),
    )
    return new_version


def correction_dict(conn, row) -> dict:
    d = dict(row)
    d["source_version"] = json.loads(d["source_version"])
    student = get_student(conn, d["student_id"])
    d["student_name"] = student["display_name"] if student else d["student_id"]
    return d


STUDENT_PREVIEW = Path(__file__).parent / "static" / "student-preview"
app.mount("/student-preview/assets", StaticFiles(directory=STUDENT_PREVIEW / "assets"), name="student-preview-assets")


@app.get("/", include_in_schema=False)
def index():
    """Main app: the Coop design (student view plus simulated employer, coordinator and
    faculty views), backed by the real API."""
    return FileResponse(STUDENT_PREVIEW / "index.html")


@app.get("/student-preview", include_in_schema=False)
def student_preview():
    return FileResponse(STUDENT_PREVIEW / "index.html")


@app.get("/classic", include_in_schema=False)
def classic():
    """The earlier four-role layout, kept for traceability views."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/skills")
def list_skills():
    return db.skill_names()


@app.get("/api/rules")
def read_rules():
    return RULES


@app.get("/api/external-opportunities")
def external_opportunities():
    return live_jobs.catalogue()


@app.get("/api/data-sources")
def data_sources():
    return {
        "profiles": {"mode": db.data_source(), "label": "P01/P03 team export" if db.data_source() != "fixtures" else "Test fixtures"},
        "listings": {"mode": "public-feed", "label": "Canonical + Remotive"},
        "team_connections": {"P01": "file export", "P03": "file export", "P06": "file export", "P07": "mock outbox"},
    }


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


class StatementDraftIn(BaseModel):
    student_id: str
    opportunity_id: str


@app.post("/api/ai/statement-draft")
def ai_statement_draft(body: StatementDraftIn):
    """AI starter statement for the apply dialog. It is returned to the student to edit;
    nothing is saved or submitted here (P05-04 bounds: cites only skills on the profile)."""
    with db.connect() as conn:
        student, opp = _student_and_opportunity(conn, body.student_id, body.opportunity_id)
    return statement_draft(student, opp, db.skill_names())


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


def _load_application(conn, application_id: str):
    row = conn.execute("SELECT * FROM applications WHERE application_id = ?", (application_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Application not found")
    return row


def _set_status(conn, application_id: str, status: str, placement_status: str | None = None) -> str:
    ts = now()
    if placement_status:
        conn.execute("UPDATE applications SET application_status = ?, placement_status = ?, updated_at = ? "
                     "WHERE application_id = ?", (status, placement_status, ts, application_id))
    else:
        conn.execute("UPDATE applications SET application_status = ?, updated_at = ? WHERE application_id = ?",
                     (status, ts, application_id))
    return ts


@app.post("/api/applications/{application_id}/decisions", status_code=201)
def decide(application_id: str, body: DecisionIn):
    require_role(body.actor_role, "employer", "decide on an application")
    if body.action not in EMPLOYER_ACTIONS:
        raise HTTPException(422, f"Unknown action '{body.action}'. "
                                 f"Allowed: {', '.join(EMPLOYER_ACTIONS)}.")
    target = EMPLOYER_ACTIONS[body.action]
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _load_application(conn, application_id)
        current = row["application_status"]
        if target == "Offered" and current == "Declined":
            raise HTTPException(409, "An offer can never follow a Declined application.")
        allowed = DECISION_TRANSITIONS.get(current, set())
        if target not in allowed:
            options = ", ".join(sorted(allowed)) or "none (this status is final for the employer)"
            raise HTTPException(409, f"Cannot move {current} → {target}. Allowed next steps: {options}.")
        if target == "Declined" and not (body.reason or "").strip():
            raise HTTPException(422, "A reason is required when declining, so the student knows what to do next.")
        ts = _set_status(conn, application_id, target)
        _add_event(conn, application_id, target, "employer",
                   (body.actor_name or "Employer reviewer (simulated)").strip() or "Employer reviewer (simulated)",
                   (body.reason or "").strip() or None, ts)
        return application_dict(conn, _load_application(conn, application_id))


# Interview is optional for legacy shortlisted applications. Once scheduled, it must
# be completed before an offer. P04 owns scheduling; no P01/P03/P06/P07 payload changes.
class InterviewIn(BaseModel):
    starts_at: datetime
    duration_minutes: int = Field(default=30, ge=15, le=240)
    mode: str = "online"
    location: str = Field(min_length=1, max_length=500)
    actor_role: str
    actor_name: str | None = None


class InterviewCompleteIn(BaseModel):
    actor_role: str
    actor_name: str | None = None


@app.post("/api/applications/{application_id}/interview", status_code=201)
def schedule_interview(application_id: str, body: InterviewIn):
    require_role(body.actor_role, "employer", "schedule an interview")
    if body.starts_at.utcoffset() is None:
        raise HTTPException(422, "Include the interview time zone.")
    if body.starts_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "Choose a future interview time.")
    if body.mode not in ("online", "in-person") or not body.location.strip():
        raise HTTPException(422, "Choose online or in-person and provide a meeting link or location.")
    actor = (body.actor_name or "Employer reviewer").strip() or "Employer reviewer"
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _load_application(conn, application_id)
        if row["application_status"] not in ("Shortlisted", "Interview scheduled"):
            raise HTTPException(409, "Only shortlisted applications or scheduled interviews can be scheduled.")
        rescheduled = row["application_status"] == "Interview scheduled"
        ts = _set_status(conn, application_id, "Interview scheduled")
        conn.execute("INSERT OR REPLACE INTO interviews VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                     (application_id, body.starts_at.astimezone(timezone.utc).isoformat(),
                      body.duration_minutes, body.mode, body.location.strip(), actor, ts))
        details = f"{body.starts_at.isoformat()} · {body.duration_minutes} min · {body.mode} · {body.location.strip()}"
        _add_event(conn, application_id, "Interview rescheduled" if rescheduled else "Interview scheduled",
                   "employer", actor, details, ts)
        return application_dict(conn, _load_application(conn, application_id))


@app.post("/api/applications/{application_id}/interview/complete")
def complete_interview(application_id: str, body: InterviewCompleteIn):
    require_role(body.actor_role, "employer", "complete an interview")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _load_application(conn, application_id)
        interview = conn.execute("SELECT * FROM interviews WHERE application_id = ?", (application_id,)).fetchone()
        if row["application_status"] != "Interview scheduled" or not interview:
            raise HTTPException(409, "This application has no scheduled interview to complete.")
        if datetime.fromisoformat(interview["starts_at"]) > datetime.now(timezone.utc):
            raise HTTPException(409, "The interview has not started yet.")
        ts = _set_status(conn, application_id, "Interview completed")
        conn.execute("UPDATE interviews SET completed_at = ?, updated_at = ? WHERE application_id = ?",
                     (ts, ts, application_id))
        _add_event(conn, application_id, "Interview completed", "employer",
                   (body.actor_name or "Employer reviewer").strip(), None, ts)
        return application_dict(conn, _load_application(conn, application_id))


# --- Offer response (P04-05) ---
class OfferResponseIn(BaseModel):
    response: str  # "accept" | "decline"
    actor_role: str
    reason: str | None = None


@app.post("/api/applications/{application_id}/offer-response", status_code=201)
def respond_to_offer(application_id: str, body: OfferResponseIn):
    """Accepting records the student's answer only: placement becomes *Awaiting university
    confirmation*, never Confirmed (P04-05 AC2). Only the coordinator confirms (P04-06)."""
    require_role(body.actor_role, "student", "respond to an offer")
    if body.response not in ("accept", "decline"):
        raise HTTPException(422, "Response must be 'accept' or 'decline'.")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _load_application(conn, application_id)
        current = row["application_status"]
        if current != "Offered":
            if current == "Offer declined":
                detail = "This offer was already declined, so it can no longer be accepted."
            elif current == "Offer accepted":
                detail = "This offer was already accepted; it is awaiting university confirmation."
            else:
                detail = f"There is no open offer on this application (status: {current})."
            raise HTTPException(409, detail)
        student = get_student(conn, row["student_id"])
        if body.response == "accept":
            status, placement = "Offer accepted", PLACEMENT_AWAITING
        else:
            status, placement = "Offer declined", PLACEMENT_NOT_PLACED
        ts = _set_status(conn, application_id, status, placement)
        _add_event(conn, application_id, status, "student", student["display_name"],
                   (body.reason or "").strip() or None, ts)
        return application_dict(conn, _load_application(conn, application_id))


# --- Withdrawal (P04-07) ---
class WithdrawIn(BaseModel):
    actor_role: str
    reason: str | None = None


@app.post("/api/applications/{application_id}/withdraw", status_code=201)
def withdraw(application_id: str, body: WithdrawIn):
    """Withdraw from an agreed withdrawable state. Prior events are kept (P04-07 AC1).
    Cancelling in the UI makes no call, so the record is unchanged (AC2)."""
    require_role(body.actor_role, "student", "withdraw an application")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _load_application(conn, application_id)
        current = row["application_status"]
        if row["placement_status"] == PLACEMENT_CONFIRMED:
            raise HTTPException(409, "This placement is already confirmed by the university, so it cannot be "
                                     "withdrawn here. Contact your coordinator.")
        if current not in WITHDRAWABLE:
            hint = {
                "Offered": " Decline the offer instead.",
                "Offer accepted": " You accepted the offer; contact your coordinator before confirmation.",
                "Draft": " A draft was never submitted, so there is nothing to withdraw.",
            }.get(current, "")
            raise HTTPException(409, f"Cannot withdraw an application that is {current}. "
                                     f"Withdrawable: {', '.join(WITHDRAWABLE)}.{hint}")
        student = get_student(conn, row["student_id"])
        ts = _set_status(conn, application_id, "Withdrawn")
        _add_event(conn, application_id, "Withdrawn", "student", student["display_name"],
                   (body.reason or "").strip() or None, ts)
        return application_dict(conn, _load_application(conn, application_id))


# --- Placement confirmation and P07 handoff (P04-06) ---
class ConfirmPlacementIn(BaseModel):
    actor_role: str
    actor_name: str | None = None


def placement_dict(conn, row) -> dict:
    d = dict(row)
    h = conn.execute("SELECT * FROM p07_handoffs WHERE placement_id = ?", (d["placement_id"],)).fetchone()
    d["p07_handoff"] = ({**dict(h), "payload": json.loads(h["payload"])} if h else None)
    student = get_student(conn, d["student_id"])
    opp = get_opportunity(conn, d["opportunity_id"])
    d["student_name"] = student["display_name"] if student else d["student_id"]
    d["opportunity_title"] = opp["title"] if opp else d["opportunity_id"]
    d["employer_name"] = opp.get("employer_name") if opp else None
    return d


@app.post("/api/applications/{application_id}/confirm-placement")
def confirm_placement(application_id: str, body: ConfirmPlacementIn):
    """Create one placement per accepted offer and hand it to P07 (mock outbox).
    Repeating the call returns the existing placement: no second placement and no
    duplicate handoff (P04-06 AC2)."""
    require_role(body.actor_role, "coordinator", "confirm a placement")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _load_application(conn, application_id)
        existing = conn.execute("SELECT * FROM placements WHERE application_id = ?", (application_id,)).fetchone()
        if existing:
            return {**placement_dict(conn, existing), "already_confirmed": True}
        if row["application_status"] != "Offer accepted":
            raise HTTPException(409, f"Only an offer the student has accepted can be confirmed "
                                     f"(this application is {row['application_status']}).")
        opp = get_opportunity(conn, row["opportunity_id"]) or {}
        count = conn.execute("SELECT COUNT(*) FROM placements").fetchone()[0]
        placement_id = f"PL-{count + 1:04d}"
        confirmed_by = (body.actor_name or "COORD-01 (simulated coordinator)").strip()
        ts = now()
        conn.execute(
            "INSERT INTO placements (placement_id, application_id, student_id, opportunity_id, "
            "opportunity_version, profile_version, confirmed_by, confirmed_at) VALUES (?,?,?,?,?,?,?,?)",
            (placement_id, application_id, row["student_id"], row["opportunity_id"],
             row["opportunity_version"], row["profile_version"], confirmed_by, ts),
        )
        # Fields agreed with P07 at Scrum of Scrums (10 Nov): only university-confirmed
        # placements, with application_id, confirmed_by and confirmed_at; supervisor
        # contact from P03 goes to P07 and is never shown to students.
        # Names follow P07's requested record (Zhengxi, 10 Nov): placement_id, student_id,
        # opportunity_id, employer/location/role, period_start/period_end, supervisor,
        # academic_advisor, status. Agreed with Team P6/P7 (24 Nov): placement_id format PL-0001;
        # academic_advisor stays null because the coordinator assigns it in P07.
        payload = {
            "placement_id": placement_id,
            "status": "university_confirmed",
            "student_id": row["student_id"],
            "opportunity_id": row["opportunity_id"],
            "employer_name": opp.get("employer_name"),
            "location": opp.get("location"),
            "role": opp.get("title"),
            "period_start": opp.get("start_date"),
            "period_end": opp.get("end_date"),
            "supervisor_name": opp.get("supervisor_name"),
            "supervisor_contact": opp.get("supervisor_contact"),
            "academic_advisor": None,
            "application_id": application_id,
            "opportunity_version": row["opportunity_version"],
            "confirmed_by": confirmed_by,
            "confirmed_at": ts,
        }
        conn.execute(
            "INSERT INTO p07_handoffs (handoff_id, placement_id, payload, sent_at, receipt_status) "
            "VALUES (?,?,?,?, 'mock-received')",
            (f"H07-{count + 1:04d}", placement_id, json.dumps(payload), ts),
        )
        _set_status(conn, application_id, "Offer accepted", PLACEMENT_CONFIRMED)
        _add_event(conn, application_id, "Placement confirmed", "coordinator", confirmed_by, None, ts)
        placement = conn.execute("SELECT * FROM placements WHERE placement_id = ?", (placement_id,)).fetchone()
        return {**placement_dict(conn, placement), "already_confirmed": False}


@app.get("/api/placements")
def list_placements():
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM placements ORDER BY placement_id").fetchall()
        return [placement_dict(conn, r) for r in rows]


@app.get("/api/p07/handoffs")
def list_p07_handoffs():
    """Mock P07 outbox: what the learning-record module would receive."""
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM p07_handoffs ORDER BY handoff_id").fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]


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


@app.post("/api/recommendations/{recommendation_id}/gaps/{skill_id}/handoff", status_code=201)
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
        count = conn.execute("SELECT COUNT(*) FROM skill_gap_handoffs").fetchone()[0]
        gap_id = f"GAP-{count + 1:04d}"
        conn.execute(
            "INSERT INTO skill_gap_handoffs (gap_id, student_id, skill_id, opportunity_id, opportunity_version, "
            "recommendation_id, profile_version, activity_id, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (gap_id, rec["student_id"], skill_id, rec["opportunity_id"], rec["opportunity_version"],
             recommendation_id, rec["profile_version"], activity["activity_id"] if activity else None, now()),
        )
        row = conn.execute("SELECT * FROM skill_gap_handoffs WHERE gap_id = ?", (gap_id,)).fetchone()
        return gap_dict(conn, row)


@app.post("/api/skill-gaps/{gap_id}/complete")
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


@app.get("/api/students/{student_id}/skill-gaps")
def list_skill_gaps(student_id: str):
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM skill_gap_handoffs WHERE student_id = ? ORDER BY gap_id",
                            (student_id,)).fetchall()
        return [gap_dict(conn, r) for r in rows]


@app.get("/api/p06/activities")
def list_p06_activities():
    return list(db.p06_activities().values())


# --- Profile updates and rematching (P05-07; simulated P01 update) ---
class ProfileUpdateIn(BaseModel):
    kind: str  # "availability" (student) | "skill_evidence" (faculty reviewer)
    actor_role: str
    actor_name: str | None = None
    availability_start: str | None = None
    availability_end: str | None = None
    skill_id: str | None = None
    evidence_id: str | None = None
    rematch: bool = True


@app.post("/api/students/{student_id}/profile-updates", status_code=201)
def update_profile(student_id: str, body: ProfileUpdateIn):
    """A profile change creates a new profile version and (by default) a new run tied to it.
    Older runs keep their original versions and reasons (P05-07 AC2)."""
    if body.kind == "availability":
        require_role(body.actor_role, "student", "change availability")
    elif body.kind == "skill_evidence":
        require_role(body.actor_role, "faculty", "review skill evidence")
    else:
        raise HTTPException(422, "kind must be 'availability' or 'skill_evidence'.")
    with db.connect() as conn:
        student = get_student(conn, student_id)
        if not student:
            raise HTTPException(404, "Student not found")
        new_profile = json.loads(json.dumps(student))
        if body.kind == "availability":
            start, end = (body.availability_start or "").strip(), (body.availability_end or "").strip()
            if not (start and end):
                raise HTTPException(422, "Provide both availability_start and availability_end.")
            if start > end:
                raise HTTPException(422, "Availability start must be on or before the end date.")
            new_profile["availability_start"], new_profile["availability_end"] = start, end
            source = "profile-update:availability"
        else:
            skills = db.skill_names()
            if body.skill_id not in skills:
                raise HTTPException(422, f"Unknown skill '{body.skill_id}'. Use a shared skill ID.")
            if not (body.evidence_id or "").strip():
                raise HTTPException(422, "An evidence_id is required: a reviewed skill must cite its evidence.")
            reviewer = (body.actor_name or "FAC-01 (simulated faculty reviewer)").strip()
            entry = {"skill_id": body.skill_id, "evidence_status": "reviewed", "reviewed_by": reviewer,
                     "reviewed_at": now(), "evidence_id": body.evidence_id.strip()}
            new_profile["skills"] = [s for s in new_profile.get("skills", []) if s["skill_id"] != body.skill_id]
            new_profile["skills"].append(entry)
            source = f"profile-update:skill_evidence:{body.skill_id}"
        new_version = _new_profile_version(conn, new_profile, source)
        results = _run_matching(conn, get_student(conn, student_id)) if body.rematch else None
        return {"student_id": student_id, "new_profile_version": new_version, "source": source,
                "rematched": body.rematch, "recommendations": results}


@app.get("/api/students/{student_id}/profile-versions")
def profile_versions(student_id: str):
    """The P01 version plus every later revision, oldest first."""
    with db.connect() as conn:
        base = conn.execute("SELECT data FROM students WHERE student_id = ?", (student_id,)).fetchone()
        if not base:
            raise HTTPException(404, "Student not found")
        base = json.loads(base["data"])
        out = [{"profile_version": base["profile_version"], "source": "P01 fixture", "created_at": None,
                "profile": base}]
        for r in conn.execute("SELECT * FROM profile_revisions WHERE student_id = ? ORDER BY profile_version",
                              (student_id,)):
            out.append({"profile_version": r["profile_version"], "source": r["source"],
                        "created_at": r["created_at"], "profile": json.loads(r["data"])})
        return out
