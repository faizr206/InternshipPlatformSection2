"""P07 co-op learning progress API (Team P6/P7). Rules: see service.py."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import db
from app.core.common import actor, require_role
from app.modules.progress import service

router = APIRouter(prefix="/api/p07", tags=["P07 progress"])


class Actor(BaseModel):
    actor_role: str
    actor_name: str | None = None


class ImportIn(Actor):
    records: list[dict]


class AdvisorIn(Actor):
    advisor: str


class GoalIn(Actor):
    text: str
    outcomes: list[str]


class LogIn(Actor):
    text: str
    goal_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    new_evidence_title: str | None = None


class TextIn(Actor):
    text: str


class MilestoneIn(Actor):
    done: bool


class JudgementIn(Actor):
    level: str
    evidence_ids: list[str] = Field(default_factory=list)


class ActionIn(Actor):
    text: str
    owner: str
    due: str


class CloseIn(Actor):
    closure: str


class FeedbackIn(Actor):
    text: str
    would_host: str


class FinalIn(Actor):
    outcomes: dict[str, str]
    summary: str
    next_goal: str


def _student_of(conn, placement_id: str) -> str:
    return service.load_placement(conn, placement_id)["student_id"]


@router.get("/students/{student_id}")
def read_record(student_id: str, viewer_role: str = "student"):
    """Everything P07 holds for the student's current placement (supervisor contact hidden from students)."""
    with db.connect() as conn:
        return service.record(conn, student_id, viewer_role)


@router.get("/placements")
def list_placements():
    with db.connect() as conn:
        return [service.load_placement(conn, r["placement_id"])
                for r in conn.execute("SELECT placement_id FROM p07_placements ORDER BY placement_id")]


@router.post("/placements/import", status_code=201)
def import_placements(body: ImportIn):
    """File handoff fallback: the coordinator imports P04 placement records (same checks as the live handoff)."""
    require_role(body.actor_role, "coordinator", "import placements")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        return service.import_placements(conn, body.records, actor("coordinator", body.actor_name))


@router.post("/placements/{placement_id}/advisor", status_code=201)
def assign_advisor(placement_id: str, body: AdvisorIn):
    require_role(body.actor_role, "coordinator", "assign an academic advisor")
    with db.connect() as conn:
        return service.assign_advisor(conn, placement_id, body.advisor, actor("coordinator", body.actor_name))


@router.post("/placements/{placement_id}/agreement/goals", status_code=201)
def add_goal(placement_id: str, body: GoalIn):
    require_role(body.actor_role, "student", "draft learning goals")
    with db.connect() as conn:
        return service.add_goal(conn, placement_id, body.text, body.outcomes)


@router.post("/placements/{placement_id}/agreement/goals/{goal_id}/remove")
def remove_goal(placement_id: str, goal_id: str, body: Actor):
    require_role(body.actor_role, "student", "remove a learning goal")
    with db.connect() as conn:
        return service.remove_goal(conn, placement_id, goal_id)


@router.post("/placements/{placement_id}/agreement/sign", status_code=201)
def sign_agreement(placement_id: str, body: Actor):
    """The caller signs as their own role: student, supervisor or advisor."""
    require_role(body.actor_role, service.SIGNERS, "agree the learning agreement")
    with db.connect() as conn:
        name = actor(body.actor_role, body.actor_name, conn, _student_of(conn, placement_id))
        if body.actor_role == "advisor":
            name = body.actor_name or service.load_placement(conn, placement_id)["academic_advisor"] or name
        return service.sign(conn, placement_id, body.actor_role, name)


@router.post("/placements/{placement_id}/logs", status_code=201)
def add_log(placement_id: str, body: LogIn):
    require_role(body.actor_role, "student", "write a log entry")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        name = actor("student", body.actor_name, conn, _student_of(conn, placement_id))
        return service.add_log(conn, placement_id, body.text, body.goal_id, body.evidence_ids,
                               body.new_evidence_title, name)


def _log_student(conn, log_id: str) -> str:
    return _student_of(conn, service.load_log(conn, log_id)["placement_id"])


@router.post("/logs/{log_id}/revise", status_code=201)
def revise_log(log_id: str, body: TextIn):
    require_role(body.actor_role, "student", "revise a log entry")
    with db.connect() as conn:
        return service.revise_log(conn, log_id, body.text, actor("student", body.actor_name, conn, _log_student(conn, log_id)))


@router.post("/logs/{log_id}/acknowledge", status_code=201)
def acknowledge_log(log_id: str, body: Actor):
    require_role(body.actor_role, "supervisor", "acknowledge a log entry")
    with db.connect() as conn:
        return service.acknowledge_log(conn, log_id, actor("supervisor", body.actor_name))


@router.post("/logs/{log_id}/request-detail", status_code=201)
def request_detail(log_id: str, body: TextIn):
    require_role(body.actor_role, "supervisor", "request more detail")
    with db.connect() as conn:
        return service.request_detail(conn, log_id, body.text, actor("supervisor", body.actor_name))


@router.post("/placements/{placement_id}/milestones", status_code=201)
def add_milestone(placement_id: str, body: TextIn):
    require_role(body.actor_role, "supervisor", "add a host milestone")
    with db.connect() as conn:
        return service.add_milestone(conn, placement_id, body.text, actor("supervisor", body.actor_name))


@router.put("/milestones/{milestone_id}")
def set_milestone(milestone_id: str, body: MilestoneIn):
    require_role(body.actor_role, "supervisor", "update a host milestone")
    with db.connect() as conn:
        return service.set_milestone(conn, milestone_id, body.done, actor("supervisor", body.actor_name))


@router.put("/placements/{placement_id}/judgements/{outcome_id}")
def judge(placement_id: str, outcome_id: str, body: JudgementIn):
    require_role(body.actor_role, "advisor", "record an outcome judgement")
    with db.connect() as conn:
        return service.judge(conn, placement_id, outcome_id, body.level, body.evidence_ids,
                             actor("advisor", body.actor_name))


@router.post("/placements/{placement_id}/actions", status_code=201)
def add_action(placement_id: str, body: ActionIn):
    require_role(body.actor_role, "advisor", "add a support action")
    with db.connect() as conn:
        return service.add_action(conn, placement_id, body.text, body.owner, body.due, actor("advisor", body.actor_name))


@router.post("/actions/{action_id}/close", status_code=201)
def close_action(action_id: str, body: CloseIn):
    if body.actor_role not in service.ACTION_OWNERS:
        raise HTTPException(403, f"Role '{body.actor_role}' cannot close support actions.")
    with db.connect() as conn:
        return service.close_action(conn, action_id, body.closure, body.actor_role,
                                    actor(body.actor_role, body.actor_name))


@router.post("/placements/{placement_id}/employer-feedback", status_code=201)
def employer_feedback(placement_id: str, body: FeedbackIn):
    require_role(body.actor_role, "supervisor", "give employer feedback")
    with db.connect() as conn:
        return service.employer_feedback(conn, placement_id, body.text, body.would_host,
                                         actor("supervisor", body.actor_name))


@router.post("/placements/{placement_id}/final-review", status_code=201)
def final_review(placement_id: str, body: FinalIn):
    require_role(body.actor_role, "advisor", "record the final review")
    with db.connect() as conn:
        return service.final_review(conn, placement_id, body.outcomes, body.summary, body.next_goal,
                                    actor("advisor", body.actor_name))
