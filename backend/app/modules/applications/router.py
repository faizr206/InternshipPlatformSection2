"""P04 Discovery and application tracking: listings, applications, decisions, interviews,
offers, withdrawal, placement confirmation and the P07 handoff record.

Moved from legacy/p04-p05-coop/app/main.py without behaviour changes.
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import db
from app.core.common import (all_opportunities, get_opportunity, get_student, next_id, now, record_handoff,
                             require_role,
                             student_and_opportunity as _student_and_opportunity, student_view)
from app.modules.applications import live_jobs
from app.modules.matching.matching import is_eligible_listing
from app.modules.progress import service as p07

router = APIRouter(tags=["P04 applications"])

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

@router.get("/api/external-opportunities")
def external_opportunities():
    return live_jobs.catalogue()


@router.get("/api/data-sources")
def data_sources():
    return {
        "profiles": {"mode": db.data_source(), "label": "P01/P03 team export" if db.data_source() != "fixtures" else "Test fixtures"},
        "listings": {"mode": "public-feed", "label": " + ".join(source for source, _ in live_jobs.FEEDS)},
        "team_connections": {"P01": "file export", "P03": "file export", "P06": "file export", "P07": "mock outbox"},
    }


# --- Opportunities (P04-01; P03 stand-in) ---
@router.get("/api/opportunities")
def list_opportunities(q: str = "", work_mode: str = ""):
    with db.connect() as conn:
        opps = [o for o in all_opportunities(conn) if is_eligible_listing(o)]
    if q:
        ql = q.lower()
        opps = [o for o in opps if ql in o["title"].lower() or ql in o["employer_name"].lower()]
    if work_mode:
        opps = [o for o in opps if o["work_mode"] == work_mode]
    return [student_view(o) for o in opps]


@router.get("/api/opportunities/{opportunity_id}")
def read_opportunity(opportunity_id: str):
    with db.connect() as conn:
        opp = get_opportunity(conn, opportunity_id)
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    return student_view(opp)


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


@router.post("/api/applications", status_code=201)
def submit_application(body: ApplicationIn):
    require_role(body.actor_role, "student", "submit an application")
    with db.connect() as conn:
        return _do_submit(conn, body.student_id, body.opportunity_id, body.statement)


@router.post("/api/applications/draft", status_code=201)
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


@router.put("/api/applications/{application_id}")
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


@router.post("/api/applications/{application_id}/submit", status_code=201)
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


@router.get("/api/students/{student_id}/applications")
def list_applications(student_id: str):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM applications WHERE student_id = ? ORDER BY submitted_at, application_id",
            (student_id,),
        ).fetchall()
        return [application_dict(conn, r) for r in rows]


@router.get("/api/applications")
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


@router.post("/api/applications/{application_id}/decisions", status_code=201)
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


@router.post("/api/applications/{application_id}/interview", status_code=201)
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


@router.post("/api/applications/{application_id}/interview/complete")
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


@router.post("/api/applications/{application_id}/offer-response", status_code=201)
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


@router.post("/api/applications/{application_id}/withdraw", status_code=201)
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


@router.post("/api/applications/{application_id}/confirm-placement")
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
        # PL ids are shared with placements P07 received by file import, so take the next free one in both.
        placement_id = next_id(conn, "PL", ["SELECT placement_id FROM placements",
                                            "SELECT placement_id FROM p07_placements"], 4)
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
        # Live P04 -> P07 handoff: P07 checks and stores the placement in this transaction. The
        # p07_handoffs row stays as the agreed record of what was sent, with P07's receipt result.
        outcome, why = p07.receive_placement(conn, payload, confirmed_by)
        conn.execute(
            "INSERT INTO p07_handoffs (handoff_id, placement_id, payload, sent_at, receipt_status) "
            "VALUES (?,?,?,?,?)",
            (f"H07-{count + 1:04d}", placement_id, json.dumps(payload), ts,
             "received" if outcome == "added" else f"{outcome}: {why}"),
        )
        record_handoff(conn, "P04", "P07", "confirmed_placement", payload, row["student_id"], placement_id,
                       "delivered" if outcome == "added" else outcome)
        _set_status(conn, application_id, "Offer accepted", PLACEMENT_CONFIRMED)
        _add_event(conn, application_id, "Placement confirmed", "coordinator", confirmed_by, None, ts)
        placement = conn.execute("SELECT * FROM placements WHERE placement_id = ?", (placement_id,)).fetchone()
        return {**placement_dict(conn, placement), "already_confirmed": False}


@router.get("/api/placements")
def list_placements():
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM placements ORDER BY placement_id").fetchall()
        return [placement_dict(conn, r) for r in rows]


@router.get("/api/p07/handoffs")
def list_p07_handoffs():
    """Mock P07 outbox: what the learning-record module would receive."""
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM p07_handoffs ORDER BY handoff_id").fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]
