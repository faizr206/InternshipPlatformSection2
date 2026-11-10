import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import db
from app.matching import RULES, is_eligible_listing, recommend

ACTIVE_STATUSES = ("Submitted",)  # extend as the lifecycle grows (Under review, Shortlisted, ...)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Coop Platform P04/P05 walking skeleton", lifespan=lifespan)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_student(conn, student_id: str) -> dict | None:
    row = conn.execute("SELECT data FROM students WHERE student_id = ?", (student_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def get_opportunity(conn, opportunity_id: str) -> dict | None:
    row = conn.execute("SELECT data FROM opportunities WHERE opportunity_id = ?", (opportunity_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def all_opportunities(conn) -> list[dict]:
    return [json.loads(r["data"]) for r in conn.execute("SELECT data FROM opportunities ORDER BY opportunity_id")]


def rec_row_to_dict(r) -> dict:
    d = dict(r)
    d["compatible"] = bool(d["compatible"])
    for k in ("reasons", "gaps", "unknowns"):
        d[k] = json.loads(d[k])
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


# --- Students (P01 stand-in) ---
@app.get("/api/students")
def list_students():
    with db.connect() as conn:
        return [json.loads(r["data"]) for r in conn.execute("SELECT data FROM students ORDER BY student_id")]


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
    return opps


@app.get("/api/opportunities/{opportunity_id}")
def read_opportunity(opportunity_id: str):
    with db.connect() as conn:
        opp = get_opportunity(conn, opportunity_id)
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    return opp


# --- Recommendations (P05-02, P05-03) ---
@app.post("/api/students/{student_id}/recommendations")
def run_recommendations(student_id: str):
    with db.connect() as conn:
        student = get_student(conn, student_id)
        if not student:
            raise HTTPException(404, "Student not found")
        results = recommend(student, all_opportunities(conn), db.skill_names())
        run_id, created_at = uuid.uuid4().hex[:8], now()
        for r in results:
            r["recommendation_id"] = f"REC-{uuid.uuid4().hex[:8]}"
            r["run_id"], r["created_at"] = run_id, created_at
            conn.execute(
                "INSERT INTO recommendations "
                "(recommendation_id, run_id, student_id, profile_version, opportunity_id, opportunity_version, "
                "method_version, score, compatible, reasons, gaps, unknowns, created_at, eligibility) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["recommendation_id"], run_id, r["student_id"], r["profile_version"],
                 r["opportunity_id"], r["opportunity_version"], r["method_version"], r["score"],
                 int(r["compatible"]), json.dumps(r["reasons"]), json.dumps(r["gaps"]),
                 json.dumps(r["unknowns"]), created_at, r["eligibility"]),
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


# --- Applications (P04-03) ---
class ApplicationIn(BaseModel):
    student_id: str
    opportunity_id: str


@app.post("/api/applications", status_code=201)
def submit_application(body: ApplicationIn):
    with db.connect() as conn:
        student = get_student(conn, body.student_id)
        if not student:
            raise HTTPException(400, "Unknown student")
        opp = get_opportunity(conn, body.opportunity_id)
        if not opp:
            raise HTTPException(400, "Unknown opportunity")
        if not is_eligible_listing(opp):
            raise HTTPException(400, f"Opportunity is not open for applications "
                                     f"({opp['publication_status']}, {opp['listing_status']})")
        dup = conn.execute(
            f"SELECT application_id FROM applications WHERE student_id = ? AND opportunity_id = ? "
            f"AND application_status IN ({','.join('?' * len(ACTIVE_STATUSES))})",
            (body.student_id, body.opportunity_id, *ACTIVE_STATUSES),
        ).fetchone()
        if dup:
            raise HTTPException(409, f"Duplicate: active application {dup['application_id']} already exists")
        count = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        application = {
            "application_id": f"APP-{count + 1:04d}",
            "student_id": student["student_id"],
            "profile_version": student["profile_version"],
            "opportunity_id": opp["opportunity_id"],
            "opportunity_version": opp["version"],
            "application_status": "Submitted",
            "placement_status": "Not placed",
            "submitted_at": now(),
        }
        conn.execute("INSERT INTO applications VALUES (?,?,?,?,?,?,?,?)", tuple(application.values()))
    return application


@app.get("/api/students/{student_id}/applications")
def list_applications(student_id: str):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM applications WHERE student_id = ? ORDER BY submitted_at, application_id",
            (student_id,),
        ).fetchall()
    return [dict(r) for r in rows]
