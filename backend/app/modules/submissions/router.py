"""P02 employer opportunity submission: submit, resubmit after a return, list and version history."""
from fastapi import APIRouter
from pydantic import BaseModel

from app import db
from app.core.common import all_opportunities, require_role
from app.modules.submissions import service

router = APIRouter(tags=["P02 submissions"])

DEFAULT_HR = "Employer HR (simulated)"


class ListingIn(BaseModel):
    actor_role: str
    actor_name: str | None = None
    hr_authorized: bool = False
    organization_name: str | None = None
    employer_name: str | None = None  # accepted as an alias of organization_name
    title: str | None = None
    description: str | None = None
    location: str | None = None
    duration: str | None = None
    work_mode: str | None = None
    sector: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    required_skills: list[str] | None = None
    desirable_skills: list[str] | None = None
    supervisor_name: str | None = None
    supervisor_contact: str | None = None


@router.post("/api/submissions", status_code=201)
def submit_opportunity(body: ListingIn):
    """A submission creates a stable opportunity ID and version but never makes it public (P02 AC2)."""
    require_role(body.actor_role, "employer", "submit an opportunity")
    with db.connect() as conn:
        return service.with_status(service.submit(conn, body, (body.actor_name or DEFAULT_HR).strip()))


@router.post("/api/submissions/{opportunity_id}/resubmit", status_code=201)
def resubmit_opportunity(opportunity_id: str, body: ListingIn):
    require_role(body.actor_role, "employer", "resubmit an opportunity")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        return service.with_status(service.resubmit(conn, opportunity_id, body,
                                                    (body.actor_name or DEFAULT_HR).strip()))


@router.get("/api/submissions")
def list_submissions(status: str = ""):
    """Every listing with its review status (employer workspace and coordinator queue).
    Filter by status label, e.g. "Pending review", "Returned for revision", "Published"."""
    with db.connect() as conn:
        listings = [service.with_status(o) for o in all_opportunities(conn)]
    return [o for o in listings if not status or o["status"] == status]


@router.get("/api/submissions/{opportunity_id}/versions")
def listing_versions(opportunity_id: str):
    """Earlier submitted versions, oldest first, then the current one (P02 AC4)."""
    with db.connect() as conn:
        return service.versions(conn, opportunity_id)
