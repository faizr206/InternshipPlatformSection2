"""P03 university review and publication.

Ported from legacy/p01-p03-ipp/src/store.js (approveOpportunity, reviewOpportunity) with the
binder's P03 rules made explicit:
- decisions on a pending listing: approve, return for revision or decline; return and decline
  need a reason (at most 300 characters); declined is final;
- approval is separate from publication; only an approved, current version can be published
  (the P01-P03 app's single "Approve" maps to approve + publish);
- a published, open listing can be closed; a closed listing accepts no new applications (P04);
- every decision records actor, time and reason; a completed checklist never approves by itself.
"""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db
from app.core.common import all_opportunities, log_event, now, require_role
from app.modules.submissions import service

router = APIRouter(tags=["P03 review"])

DEFAULT_COORDINATOR = "COORD-01 (simulated coordinator)"
# The seven checks agreed in the product backlog (P3-03) and the P01-P03 approved FAQ ("How is an opportunity
# approved?"): completeness, on-site, duration, supervisor, learning value, employer reliability, workplace safety.
CHECKLIST = ("Complete: all required details are filled in", "On-site placement (remote roles are not approved)",
             "Suitable duration and dates", "Named workplace supervisor", "Clear learning value",
             "Reliable employer", "Safe workplace")


class DecisionIn(BaseModel):
    decision: str  # approve | return | decline
    actor_role: str
    actor_name: str | None = None
    reason: str | None = None
    checklist: list[str] | None = None


class PublishIn(BaseModel):
    actor_role: str
    actor_name: str | None = None
    reason: str | None = None


def is_pending(opp: dict) -> bool:
    return opp.get("publication_status") == "unpublished" and opp.get("review_status") in (None, "pending")


def _record(conn, opp: dict, decision: str, actor: str, reason: str | None, checklist: list[str] | None) -> None:
    conn.execute("INSERT INTO listing_decisions (opportunity_id, version, decision, reason, checklist, actor_name, "
                 "created_at) VALUES (?,?,?,?,?,?,?)",
                 (opp["opportunity_id"], opp["version"], decision, reason,
                  json.dumps(checklist) if checklist is not None else None, actor, now()))


@router.get("/api/review/checklist")
def review_checklist():
    return list(CHECKLIST)


@router.get("/api/review-queue")
def review_queue():
    """Submitted listings waiting for a decision, current versions only."""
    with db.connect() as conn:
        return [service.with_status(o) for o in all_opportunities(conn) if is_pending(o)]


@router.post("/api/submissions/{opportunity_id}/decision", status_code=201)
def decide(opportunity_id: str, body: DecisionIn):
    require_role(body.actor_role, "coordinator", "review an opportunity")
    if body.decision not in ("approve", "return", "decline"):
        raise HTTPException(422, "Choose approve, return for revision or decline.")
    actor = (body.actor_name or DEFAULT_COORDINATOR).strip()
    reason = (body.reason or "").strip()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        opp = service.load_listing(conn, opportunity_id)
        if opp.get("publication_status") == "published":
            raise HTTPException(409, f"{opportunity_id} is already published.")
        if not is_pending(opp):
            raise HTTPException(409, f"{opportunity_id} already has a review decision "
                                     f"({service.status_label(opp).lower()}).")
        if body.decision in ("return", "decline"):
            if not reason:
                raise service.validation_error("A reason is required.", {"reason": "A reason is required."})
            if len(reason) > service.REASON_LIMIT:
                message = f"The reason must be {service.REASON_LIMIT} characters or fewer."
                raise service.validation_error(message, {"reason": message})
        unknown = [c for c in (body.checklist or []) if c not in CHECKLIST]
        if unknown:
            raise HTTPException(422, f"Unknown checklist items: {', '.join(unknown)}.")
        status = {"approve": "approved", "return": "returned", "decline": "declined"}[body.decision]
        updated = {**opp, "review_status": status, "review_reason": reason or None,
                   "reviewed_at": now(), "reviewed_by": actor}
        service.save_listing(conn, updated)
        _record(conn, updated, status, actor, reason or None, body.checklist)
        text = {"approved": f"Coordinator approved “{opp['title']}” (not yet published)",
                "returned": f"Coordinator returned “{opp['title']}” for revision",
                "declined": f"Coordinator declined “{opp['title']}”"}[status]
        log_event(conn, "P03", "coordinator", actor, f"opportunity_{status}", text, opportunity_id)
        return service.with_status(updated)


@router.post("/api/opportunities/{opportunity_id}/publish", status_code=201)
def publish(opportunity_id: str, body: PublishIn):
    """Publish the approved current version. Unapproved, returned or declined versions cannot be
    published (P03 AC2); publishing never reopens a closed listing."""
    require_role(body.actor_role, "coordinator", "publish an opportunity")
    actor = (body.actor_name or DEFAULT_COORDINATOR).strip()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        opp = service.load_listing(conn, opportunity_id)
        if opp.get("publication_status") == "published":
            raise HTTPException(409, f"{opportunity_id} is already published.")
        if opp.get("review_status") != "approved":
            raise HTTPException(409, f"Only an approved version can be published; {opportunity_id} is "
                                     f"{service.status_label(opp).lower()}.")
        updated = {**opp, "publication_status": "published", "published_at": now(), "published_by": actor}
        service.save_listing(conn, updated)
        _record(conn, updated, "published", actor, None, None)
        log_event(conn, "P03", "coordinator", actor, "opportunity_published",
                  f"Coordinator published “{opp['title']}” version {opp['version']}", opportunity_id)
        return service.with_status(updated)


@router.post("/api/opportunities/{opportunity_id}/close", status_code=201)
def close(opportunity_id: str, body: PublishIn):
    """Close a published listing: it stays visible in history but accepts no new applications."""
    require_role(body.actor_role, "coordinator", "close an opportunity")
    actor = (body.actor_name or DEFAULT_COORDINATOR).strip()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        opp = service.load_listing(conn, opportunity_id)
        if opp.get("publication_status") != "published":
            raise HTTPException(409, f"Only a published listing can be closed; {opportunity_id} is "
                                     f"{service.status_label(opp).lower()}.")
        if opp.get("listing_status") == "closed":
            raise HTTPException(409, f"{opportunity_id} is already closed.")
        reason = (body.reason or "").strip() or None
        updated = {**opp, "listing_status": "closed", "closed_at": now(), "closed_by": actor}
        service.save_listing(conn, updated)
        _record(conn, updated, "closed", actor, reason, None)
        log_event(conn, "P03", "coordinator", actor, "opportunity_closed",
                  f"Coordinator closed “{opp['title']}”", opportunity_id)
        return service.with_status(updated)


@router.get("/api/opportunities/{opportunity_id}/decisions")
def decision_history(opportunity_id: str):
    """Every P03 decision on any version of this listing, oldest first."""
    with db.connect() as conn:
        service.load_listing(conn, opportunity_id)
        rows = conn.execute("SELECT * FROM listing_decisions WHERE opportunity_id = ? ORDER BY decision_id",
                            (opportunity_id,)).fetchall()
    return [{**dict(r), "checklist": json.loads(r["checklist"]) if r["checklist"] else None} for r in rows]
