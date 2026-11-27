"""P06 internship preparation API (Team P6/P7). Rules: see service.py."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db
from app.core.common import actor, require_role
from app.modules.preparation import service
from app.modules.profiles.service import apply_reviewed_evidence

router = APIRouter(prefix="/api/p06", tags=["P06 preparation"])


class Actor(BaseModel):
    actor_role: str
    actor_name: str | None = None


class GapIn(Actor):
    skill_id: str
    reason: str
    opportunity_id: str | None = None


class ItemIn(Actor):
    summary: str


class AssignIn(Actor):
    assignee: str


class MoveIn(Actor):
    to: str
    reason: str


class EvidenceIn(Actor):
    module_id: str
    explanation: str


class ReviewIn(Actor):
    decision: str  # demonstrated | revision | not_yet
    comment: str | None = None
    checklist: list[bool]


@router.get("/modules")
def list_modules():
    return list(service.modules().values())


@router.get("/modules/{module_id}")
def read_module(module_id: str):
    module = service.modules().get(module_id)
    if not module:
        raise HTTPException(404, "Module not found")
    return module


@router.get("/outcomes")
def list_outcomes():
    """Programme learning outcomes used by P07 learning agreements."""
    return service.outcomes()


@router.get("/students/{student_id}/plan")
def read_plan(student_id: str):
    with db.connect() as conn:
        return service.plan(conn, student_id)


@router.get("/gaps")
def list_gaps(status: str = ""):
    """Coordinator view of every student's gaps."""
    with db.connect() as conn:
        return service.all_gaps(conn, status)


@router.post("/students/{student_id}/gaps", status_code=201)
def add_manual_gap(student_id: str, body: GapIn):
    """Coordinator enters a gap by hand (e.g. a desirable skill). A second open gap is refused."""
    require_role(body.actor_role, "coordinator", "enter a skill gap")
    reason = (body.reason or "").strip()
    if len(reason) < 5:
        raise HTTPException(422, "Say why this gap matters.")
    opportunity_id = (body.opportunity_id or "").strip().upper() or None
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        outcome, gap = service.add_gap(conn, student_id, body.skill_id, reason, "manual",
                                       actor("coordinator", body.actor_name), opportunity_id=opportunity_id)
        if outcome == "existing":
            raise HTTPException(409, f"This student already has an open gap for {body.skill_id} ({gap['gap_id']}).")
        return gap


@router.post("/students/{student_id}/resources/{module_id}/complete", status_code=201)
def complete_resource(student_id: str, module_id: str, body: Actor):
    require_role(body.actor_role, "student", "mark a resource complete")
    with db.connect() as conn:
        return service.complete_resource(conn, student_id, module_id)


@router.get("/students/{student_id}/board")
def read_board(student_id: str):
    with db.connect() as conn:
        return service.board(conn, student_id)


@router.post("/students/{student_id}/board/items", status_code=201)
def add_board_item(student_id: str, body: ItemIn):
    require_role(body.actor_role, "student", "add a board item")
    with db.connect() as conn:
        return service.add_item(conn, student_id, body.summary)


@router.put("/students/{student_id}/board/items/{key}/assignee")
def assign_board_item(student_id: str, key: str, body: AssignIn):
    require_role(body.actor_role, "student", "assign a board item")
    with db.connect() as conn:
        return service.assign_item(conn, student_id, key, body.assignee)


@router.post("/students/{student_id}/board/items/{key}/move", status_code=201)
def move_board_item(student_id: str, key: str, body: MoveIn):
    require_role(body.actor_role, "student", "move a board item")
    with db.connect() as conn:
        return service.move_item(conn, student_id, key, body.to, body.reason)


@router.post("/students/{student_id}/submissions", status_code=201)
def submit_evidence(student_id: str, body: EvidenceIn):
    require_role(body.actor_role, "student", "submit evidence")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        return service.submit_evidence(conn, student_id, body.module_id, body.explanation)


@router.get("/review-queue")
def review_queue():
    with db.connect() as conn:
        return service.review_queue(conn)


@router.get("/submissions/{evidence_id}")
def read_submission(evidence_id: str):
    with db.connect() as conn:
        sub = service.load_submission(conn, evidence_id)
        return {**sub, "module": service.modules()[sub["module_id"]]}


@router.post("/submissions/{evidence_id}/review", status_code=201)
def review_submission(evidence_id: str, body: ReviewIn):
    """Reviewer decision. Demonstrated closes the gap, adds reviewed evidence to the P01 profile as a new
    version, reruns P05 matching and sends a readiness summary to P07, all in one transaction."""
    require_role(body.actor_role, ("reviewer", "faculty"), "review evidence")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        return service.review(conn, evidence_id, body.decision, body.comment or "", body.checklist,
                              actor("reviewer", body.actor_name), on_demonstrated=apply_reviewed_evidence)


@router.get("/students/{student_id}/readiness")
def read_readiness(student_id: str):
    with db.connect() as conn:
        service.require_student(conn, student_id)
        return service.readiness(conn, student_id)
