"""Shared demo controls: demo date, scenario reset, demo people, and the handoff records."""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db
from app.core.common import ADVISORS, DEMO_PEOPLE, today
from app.modules.demo import scenarios

router = APIRouter(prefix="/api", tags=["Demo and records"])

# Every table that holds platform activity. Seed tables (students, opportunities) are reloaded from
# app/seed on every start and are never cleared here; the external job cache is kept too.
ACTIVITY_TABLES = (
    "recommendations", "applications", "application_events", "interviews", "correction_requests",
    "profile_revisions", "placements", "p07_handoffs", "skill_gap_handoffs", "events", "listings",
    "listing_versions", "listing_decisions", "profile_drafts", "profile_reviews", "handoffs",
    "prep_gaps", "prep_resources", "prep_boards", "prep_submissions", "p07_placements", "p07_agreements",
    "p07_logs", "p07_evidence", "p07_judgements", "p07_milestones", "p07_actions", "p07_final_reviews",
    "demo_settings",
)


class TodayIn(BaseModel):
    today: str


def settings() -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT value FROM demo_settings WHERE key = 'scenario'").fetchone()
        scenario = row["value"] if row else "fresh"
        return {"today": today(conn), "scenario": scenario, "scenarios": scenarios.SCENARIOS}


@router.get("/demo/settings")
def read_settings():
    return settings()


@router.put("/demo/today")
def set_demo_today(body: TodayIn):
    """Move the demo clock (drives log dates, due dates and overdue actions)."""
    value = body.today.strip()
    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise HTTPException(422, "Use a date like 2027-03-18.")
    scenarios.set_today(value)
    return settings()


@router.post("/demo/reset")
def reset(scenario: str = "fresh"):
    """Clear all platform activity and rebuild the chosen scenario through the real endpoints."""
    if scenario not in scenarios.SCENARIOS:
        raise HTTPException(422, f"Unknown scenario. Choose one of: {', '.join(scenarios.SCENARIOS)}.")
    with db.connect() as conn:
        for table in ACTIVITY_TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence")
    scenarios.build(scenario)
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO demo_settings (key, value) VALUES ('today', ?)",
                     (scenarios.SCENARIOS[scenario]["today"],))
        conn.execute("INSERT OR REPLACE INTO demo_settings (key, value) VALUES ('scenario', ?)", (scenario,))
    return settings()


@router.get("/people")
def people():
    """Synthetic demo actors per simulated role, and the academic advisors the coordinator can assign."""
    return {"people": DEMO_PEOPLE, "advisors": ADVISORS}


@router.get("/handoffs")
def handoffs(to_module: str = "", student_id: str = ""):
    """Every cross-module handoff record, oldest first (contract evidence; export as JSON from the UI)."""
    clauses, params = [], []
    if to_module:
        clauses.append("to_module = ?")
        params.append(to_module)
    if student_id:
        clauses.append("student_id = ?")
        params.append(student_id)
    query = "SELECT * FROM handoffs" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY handoff_id"
    with db.connect() as conn:
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in conn.execute(query, params)]
