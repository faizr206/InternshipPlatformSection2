"""P02 employer opportunity submission and the listing records shared with P03.

Ported from the P01-P03 team's store (legacy/p01-p03-ipp/src/store.js: readListingInput,
submitOpportunity, resubmitOpportunity). Rules kept as they were:
- only a (simulated) authorized HR representative can submit;
- organization name, title, description and location are required, with length limits;
- unknown work modes fall back to hybrid;
- a submission gets a stable OP-id and version 1 and is NOT public (publication_status unpublished);
- only a listing returned for revision can be resubmitted: same ID, version + 1, the returned
  version is archived untouched and the new one goes back into the review queue.

Added for the integrated platform (binder P02 scope; needed by P05 matching): optional sector,
dates, required/desirable skills and supervisor contact, with date-order and skill-ID checks.
"""
import json

from fastapi import HTTPException

from app import db
from app.core.common import get_opportunity, log_event, next_id, now

LIMITS = {"organization_name": 80, "title": 100, "location": 80, "description": 600, "duration": 40,
          "sector": 60, "supervisor_name": 80, "supervisor_contact": 120}
FIELD_LABELS = {"organization_name": "Organization name", "title": "Title", "description": "Description",
                "location": "Location", "duration": "Duration", "sector": "Sector",
                "supervisor_name": "Supervisor name", "supervisor_contact": "Supervisor contact"}
REQUIRED_FIELDS = ("organization_name", "title", "description", "location")
WORK_MODES = ("on-site", "hybrid", "remote")
REASON_LIMIT = 300

# Display status for a listing, derived from its separate fields (approval stays separate from publication).
PENDING, APPROVED, PUBLISHED, CLOSED, RETURNED, DECLINED = (
    "Pending review", "Approved", "Published", "Closed", "Returned for revision", "Declined")


def status_label(opp: dict) -> str:
    review = opp.get("review_status")
    if review == "declined":
        return DECLINED
    if review == "returned":
        return RETURNED
    if opp.get("publication_status") == "published":
        return CLOSED if opp.get("listing_status") == "closed" else PUBLISHED
    if review == "approved":
        return APPROVED
    return PENDING


def with_status(opp: dict) -> dict:
    return {**opp, "status": status_label(opp)}


def validation_error(message: str, errors: dict) -> HTTPException:
    return HTTPException(422, {"message": message, "errors": errors})


def read_listing_input(body) -> dict:
    """Shared by first submissions and resubmissions: authorization, trimming and validation."""
    if not body.hr_authorized:
        raise HTTPException(403, "Submission blocked: only an authorized HR representative can submit "
                                 "opportunities. (Simulated control; real authorization is deferred.)")
    values = {field: (getattr(body, field) or "").strip() for field in LIMITS}
    if not values["organization_name"] and body.employer_name:
        values["organization_name"] = body.employer_name.strip()
    errors = {}
    for field in REQUIRED_FIELDS:
        if not values[field]:
            errors[field] = f"{FIELD_LABELS[field]} is required."
    for field, limit in LIMITS.items():
        if field not in errors and len(values[field]) > limit:
            errors[field] = f"{FIELD_LABELS[field]} must be {limit} characters or fewer."
    start, end = (body.start_date or "").strip() or None, (body.end_date or "").strip() or None
    if start and end and start > end:
        errors["end_date"] = "The end date must be on or after the start date."
    skills = db.skill_names()
    unknown = [s for s in (body.required_skills or []) + (body.desirable_skills or []) if s not in skills]
    if unknown:
        errors["skills"] = f"Unknown skill IDs: {', '.join(unknown)}. Use the shared skill vocabulary."
    if errors:
        raise validation_error("Fix the highlighted fields and submit again.", errors)
    mode = (body.work_mode or "hybrid").strip().lower()
    return {
        "employer_name": values["organization_name"],
        "title": values["title"],
        "description": values["description"],
        "sector": values["sector"],
        "location": values["location"],
        "work_mode": mode if mode in WORK_MODES else "hybrid",
        "start_date": start,
        "end_date": end,
        "duration": values["duration"] or "Not specified",
        "required_skills": list(dict.fromkeys(body.required_skills or [])),
        "desirable_skills": list(dict.fromkeys(body.desirable_skills or [])),
        "supervisor_name": values["supervisor_name"] or None,
        "supervisor_contact": values["supervisor_contact"] or None,
    }


def save_listing(conn, opp: dict) -> None:
    """Write the platform copy of a listing (the seed row, if any, is never edited)."""
    conn.execute("INSERT OR REPLACE INTO listings (opportunity_id, version, data, updated_at) VALUES (?,?,?,?)",
                 (opp["opportunity_id"], opp["version"], json.dumps(opp), now()))


def load_listing(conn, opportunity_id: str) -> dict:
    opp = get_opportunity(conn, opportunity_id)
    if not opp:
        raise HTTPException(404, f"Opportunity {opportunity_id} does not exist.")
    return opp


def submit(conn, body, actor_name: str) -> dict:
    values = read_listing_input(body)
    opportunity_id = next_id(conn, "OP", ["SELECT opportunity_id FROM opportunities",
                                          "SELECT opportunity_id FROM listings"])
    opp = {"opportunity_id": opportunity_id, "version": 1, "submission_version": 1, **values,
           "publication_status": "unpublished", "listing_status": "open", "review_status": "pending",
           "origin": "platform", "submitted_at": now()}
    save_listing(conn, opp)
    log_event(conn, "P02", "employer", actor_name, "opportunity_submitted",
              f"Employer HR submitted “{opp['title']}” for review", opportunity_id)
    return opp


def resubmit(conn, opportunity_id: str, body, actor_name: str) -> dict:
    opp = load_listing(conn, opportunity_id)
    if opp.get("review_status") != "returned":
        raise HTTPException(409, "Only a listing returned for revision can be resubmitted.")
    values = read_listing_input(body)
    conn.execute("INSERT INTO listing_versions (opportunity_id, version, data, archived_at) VALUES (?,?,?,?)",
                 (opportunity_id, opp["version"], json.dumps(opp), now()))
    new = {**opp, **values,
           "version": int(opp.get("version") or 1) + 1,
           "submission_version": int(opp.get("submission_version") or 1) + 1,
           "publication_status": "unpublished", "listing_status": "open", "review_status": "pending",
           "submitted_at": now()}
    for field in ("review_reason", "reviewed_at", "reviewed_by"):
        new.pop(field, None)
    save_listing(conn, new)
    log_event(conn, "P02", "employer", actor_name, "opportunity_resubmitted",
              f"Employer HR resubmitted “{new['title']}” as version {new['version']}", opportunity_id)
    return new


def versions(conn, opportunity_id: str) -> list[dict]:
    """Earlier versions, oldest first, then the current one."""
    load_listing(conn, opportunity_id)
    rows = conn.execute("SELECT data, archived_at FROM listing_versions WHERE opportunity_id = ? ORDER BY version",
                        (opportunity_id,)).fetchall()
    earlier = [{**with_status(json.loads(r["data"])), "archived_at": r["archived_at"], "current": False} for r in rows]
    return earlier + [{**with_status(get_opportunity(conn, opportunity_id)), "archived_at": None, "current": True}]
