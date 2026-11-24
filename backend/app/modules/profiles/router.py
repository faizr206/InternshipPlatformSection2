"""P01 student profiles: current profile, append-only profile versions, and profile
updates that trigger a rematch (P05-07).

Moved from legacy/p04-p05-coop/app/main.py without behaviour changes; the full P01 workflow
(drafts, coordinator clarification) is added in the P01-P03 port.
"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db
from app.core.common import get_student, new_profile_version as _new_profile_version, now, require_role
from app.modules.matching.router import _run_matching

router = APIRouter(tags=["P01 profiles"])

# --- Students (P01 stand-in + correction revisions) ---
@router.get("/api/students")
def list_students():
    with db.connect() as conn:
        ids = [r["student_id"] for r in conn.execute("SELECT student_id FROM students ORDER BY student_id")]
        return [get_student(conn, i) for i in ids]


@router.get("/api/students/{student_id}")
def read_student(student_id: str):
    with db.connect() as conn:
        student = get_student(conn, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    return student

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


@router.post("/api/students/{student_id}/profile-updates", status_code=201)
def update_profile(student_id: str, body: ProfileUpdateIn):
    """A profile change creates a new profile version and (by default) a new run tied to it.
    Older runs keep their original versions and reasons (P05-07 AC2)."""
    if body.kind == "availability":
        require_role(body.actor_role, "student", "change availability")
    elif body.kind == "skill_evidence":
        require_role(body.actor_role, ("reviewer", "faculty"), "review skill evidence")
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


@router.get("/api/students/{student_id}/profile-versions")
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
