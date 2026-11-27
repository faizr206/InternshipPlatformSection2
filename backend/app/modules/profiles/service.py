"""P01 profile services used by other modules inside one transaction (live handoffs)."""
import json

from fastapi import HTTPException

from app.core.common import get_student, log_event, new_profile_version
from app.modules.matching.router import _run_matching


def apply_reviewed_evidence(conn, student_id: str, skill_id: str, evidence_id: str, reviewer: str,
                            review_date: str, rematch: bool = True) -> dict:
    """P06 -> P01: a demonstrated skill becomes reviewed evidence on a NEW profile version (the earlier
    version is never edited), then P05 matching reruns against it (P05-07). Older runs keep their versions."""
    student = get_student(conn, student_id)
    if not student:
        raise HTTPException(404, f"Student {student_id} not found")
    profile = json.loads(json.dumps(student))
    entry = {"skill_id": skill_id, "evidence_status": "reviewed", "reviewed_by": reviewer,
             "reviewed_at": review_date, "evidence_id": evidence_id}
    profile["skills"] = [s for s in profile.get("skills", []) if s["skill_id"] != skill_id] + [entry]
    version = new_profile_version(conn, profile, f"P06:reviewed_skill:{evidence_id}")
    log_event(conn, "P01", "reviewer", reviewer, "skill_reviewed",
              f"{student['display_name']}'s {skill_id} is now reviewed evidence ({evidence_id}) on profile v{version}",
              student_id)
    if rematch:
        _run_matching(conn, get_student(conn, student_id))
    return {"p01_profile_version": version, "rematched": rematch}
