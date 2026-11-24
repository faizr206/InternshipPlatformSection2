"""P01 student profiles: current profile, append-only profile versions, and profile
updates that trigger a rematch (P05-07).

Moved from legacy/p04-p05-coop/app/main.py without behaviour changes; the full P01 workflow
(drafts, coordinator clarification) is added in the P01-P03 port.
"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db
from app.core.common import get_student, log_event, new_profile_version as _new_profile_version, now, require_role
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


# --- P01 profile workflow: draft, submit, coordinator clarification and review ---
# Ported from legacy/p01-p03-ipp/src/store.js (latestSubmitted, updateDisplayName: corrections
# append a version, an unchanged profile creates none) and extended to the binder's P01 scope:
# draft / submitted / clarification requested / reviewed, required fields and date ranges checked,
# self-declared skills stay self-declared until a separate evidence review (P06) is recorded.
PROFILE_LIMITS = {"display_name": 60, "goals": 400, "preferred_location": 80}
EDITABLE_FIELDS = ("display_name", "goals", "interests", "preferred_location", "availability_start",
                   "availability_end", "skills")


class ProfileDraftIn(BaseModel):
    actor_role: str
    display_name: str | None = None
    goals: str | None = None
    interests: list[str] | None = None
    preferred_location: str | None = None
    availability_start: str | None = None
    availability_end: str | None = None
    skills: list[str] | None = None  # skill IDs the student declares


class ProfileSubmitIn(BaseModel):
    actor_role: str


class ProfileReviewIn(BaseModel):
    decision: str  # clarification_requested | reviewed
    actor_role: str
    actor_name: str | None = None
    comment: str | None = None


def _latest_review(conn, student_id: str, profile_version: int) -> dict | None:
    row = conn.execute("SELECT * FROM profile_reviews WHERE student_id = ? AND profile_version = ? "
                       "ORDER BY review_id DESC LIMIT 1", (student_id, profile_version)).fetchone()
    return dict(row) if row else None


def _profile_state(conn, student_id: str) -> dict:
    current = get_student(conn, student_id)
    if not current:
        raise HTTPException(404, "Student not found")
    draft = conn.execute("SELECT data, updated_at FROM profile_drafts WHERE student_id = ?", (student_id,)).fetchone()
    review = _latest_review(conn, student_id, current["profile_version"])
    return {
        "student_id": student_id,
        "profile": current,
        "status": review["decision"] if review else "submitted",
        "review": review,
        "draft": {**json.loads(draft["data"]), "updated_at": draft["updated_at"]} if draft else None,
    }


def _validate_profile(values: dict) -> dict:
    errors = {}
    name = (values.get("display_name") or "").strip()
    if not name:
        errors["display_name"] = "Display name is required."
    for field, limit in PROFILE_LIMITS.items():
        if field not in errors and len((values.get(field) or "").strip()) > limit:
            errors[field] = f"{field.replace('_', ' ').capitalize()} must be {limit} characters or fewer."
    if not [i for i in values.get("interests") or [] if i.strip()]:
        errors["interests"] = "Add at least one interest (a sector or role you want to explore)."
    start, end = values.get("availability_start"), values.get("availability_end")
    if not start or not end:
        errors["availability"] = "Availability start and end dates are required."
    elif start > end:
        errors["availability"] = "Availability start must be on or before the end date."
    unknown = [s for s in values.get("skills") or [] if s not in db.skill_names()]
    if unknown:
        errors["skills"] = f"Unknown skill IDs: {', '.join(unknown)}. Use the shared skill vocabulary."
    if errors:
        raise HTTPException(422, {"message": "Fix the highlighted fields before submitting.", "errors": errors})
    return values


@router.get("/api/students/{student_id}/profile")
def read_profile(student_id: str):
    """Current submitted profile, its review status and comment, and any working draft."""
    with db.connect() as conn:
        return _profile_state(conn, student_id)


@router.put("/api/students/{student_id}/profile/draft")
def save_profile_draft(student_id: str, body: ProfileDraftIn):
    """Save a working draft. Saving never submits; the current version stays what P04/P05 read."""
    require_role(body.actor_role, "student", "edit a profile")
    with db.connect() as conn:
        state = _profile_state(conn, student_id)
        base = state["draft"] or {f: state["profile"].get(f) for f in EDITABLE_FIELDS}
        if base.get("skills") and isinstance(base["skills"][0], dict):
            base["skills"] = [s["skill_id"] for s in base["skills"]]
        base.pop("updated_at", None)
        for field in EDITABLE_FIELDS:
            value = getattr(body, field)
            if value is not None:
                base[field] = value.strip() if isinstance(value, str) else value
        conn.execute("INSERT OR REPLACE INTO profile_drafts (student_id, data, updated_at) VALUES (?,?,?)",
                     (student_id, json.dumps(base), now()))
        return _profile_state(conn, student_id)


@router.post("/api/students/{student_id}/profile/submit", status_code=201)
def submit_profile(student_id: str, body: ProfileSubmitIn):
    """Submit the draft as the next profile version. Earlier versions are never edited. Reviewed
    skill evidence is kept; newly declared skills are self-declared (P01 AC3)."""
    require_role(body.actor_role, "student", "submit a profile")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        state = _profile_state(conn, student_id)
        if not state["draft"]:
            raise HTTPException(409, "There is no draft to submit. Edit your profile first.")
        values = _validate_profile({k: v for k, v in state["draft"].items() if k in EDITABLE_FIELDS})
        current = state["profile"]
        held = {s["skill_id"]: s for s in current.get("skills", [])}
        skills = [held.get(skill_id) or {"skill_id": skill_id, "evidence_status": "self_declared",
                                         "reviewed_by": None, "reviewed_at": None, "evidence_id": None}
                  for skill_id in dict.fromkeys(values.get("skills") or [])]
        new_profile = {**json.loads(json.dumps(current)),
                       "display_name": values["display_name"].strip(),
                       "goals": (values.get("goals") or "").strip() or None,
                       "interests": [i.strip() for i in values["interests"] if i.strip()],
                       "preferred_location": (values.get("preferred_location") or "").strip() or None,
                       "availability_start": values["availability_start"],
                       "availability_end": values["availability_end"],
                       "skills": skills, "profile_status": "submitted"}
        conn.execute("DELETE FROM profile_drafts WHERE student_id = ?", (student_id,))
        compare = lambda p: {k: p.get(k) for k in EDITABLE_FIELDS}  # noqa: E731
        if compare(new_profile) == compare(current):
            return {**_profile_state(conn, student_id), "new_version": False}
        version = _new_profile_version(conn, new_profile, "P01:student-submission")
        log_event(conn, "P01", "student", new_profile["display_name"], "profile_submitted",
                  f"{new_profile['display_name']} submitted profile version {version}", student_id)
        return {**_profile_state(conn, student_id), "new_version": True}


@router.post("/api/students/{student_id}/profile/review", status_code=201)
def review_profile(student_id: str, body: ProfileReviewIn):
    """Coordinator asks for clarification (comment required) or marks the current version reviewed."""
    require_role(body.actor_role, "coordinator", "review a student profile")
    if body.decision not in ("clarification_requested", "reviewed"):
        raise HTTPException(422, "decision must be 'clarification_requested' or 'reviewed'.")
    comment = (body.comment or "").strip()
    if body.decision == "clarification_requested" and not comment:
        raise HTTPException(422, "Write what the student should clarify.")
    actor = (body.actor_name or "COORD-01 (simulated coordinator)").strip()
    with db.connect() as conn:
        state = _profile_state(conn, student_id)
        version = state["profile"]["profile_version"]
        conn.execute("INSERT INTO profile_reviews (student_id, profile_version, decision, comment, actor_name, "
                     "created_at) VALUES (?,?,?,?,?,?)",
                     (student_id, version, body.decision, comment or None, actor, now()))
        text = (f"Coordinator asked {state['profile']['display_name']} to clarify profile v{version}"
                if body.decision == "clarification_requested"
                else f"Coordinator reviewed {state['profile']['display_name']}'s profile v{version}")
        log_event(conn, "P01", "coordinator", actor, f"profile_{body.decision}", text, student_id)
        return _profile_state(conn, student_id)
