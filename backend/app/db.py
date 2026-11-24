"""SQLite storage. Fixtures stand in for P01 (profiles) and P03 (published listings).

Sprint 2 additions:
- applications gain `statement` (draft text, required at submission) and `updated_at`.
- recommendations gain `ai_method_version` / `ai_matches` (bounded AI assistance,
  recorded alongside — never changing — the rules result).
- application_events: the decision history with actor, reason and next action (P04-04).
- correction_requests: flagged recommendations and coordinator corrections (P05-05).
- profile_revisions: new profile versions created by accepted corrections. The P01
  fixture table is never overwritten (P05 does not silently edit P01/P03 records);
  a corrected profile is stored as a new version here and read as the effective one.

Sprint 3 additions (all new tables, so Sprint 1-2 databases upgrade in place):
- placements: one per confirmed accepted offer (P04-06), PL-0001 style IDs.
- p07_handoffs: the mock outbox to P07; one handoff per placement, never duplicated.
- skill_gap_handoffs: a named skill gap passed to P06 with its source versions (P05-06).
- profile_revisions also stores profile updates (availability, reviewed evidence) (P05-07).
"""
import json
import logging
import os
import sqlite3
from pathlib import Path

SEED = Path(__file__).parent / "seed"
FIXTURES = SEED / "fixtures"
# Data received from the P01-P03 team (file handoff, 24 Nov): latest submitted profiles and
# published listings, in the fields of our data dictionary v3. Kept exactly as delivered.
P01P03_DATA = SEED / "p01p03"


def data_source() -> str:
    """Where P01 profiles and P03 listings come from.

    "p01p03" (default): the P01-P03 team's export. "fixtures": our own synthetic set
    (6 profiles, 6 listings with the Sprint 1-3 test cases), used by the automated tests.
    """
    return os.environ.get("DATA_SOURCE", "p01p03")
log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS external_job_cache (
    cache_key TEXT PRIMARY KEY, checked_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interviews (
    application_id TEXT PRIMARY KEY,
    starts_at TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    mode TEXT NOT NULL,
    location TEXT NOT NULL,
    scheduled_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    profile_version INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS opportunities (
    opportunity_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    profile_version INTEGER NOT NULL,
    opportunity_id TEXT NOT NULL,
    opportunity_version INTEGER NOT NULL,
    method_version TEXT NOT NULL,
    score INTEGER NOT NULL,
    compatible INTEGER NOT NULL,
    reasons TEXT NOT NULL,
    gaps TEXT NOT NULL,
    unknowns TEXT NOT NULL,
    created_at TEXT NOT NULL,
    eligibility TEXT NOT NULL CHECK (eligibility IN ('eligible', 'unknown', 'ineligible')),
    ai_method_version TEXT,
    ai_matches TEXT,
    ai_insights TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    application_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    profile_version INTEGER NOT NULL,
    opportunity_id TEXT NOT NULL,
    opportunity_version INTEGER NOT NULL,
    application_status TEXT NOT NULL,
    placement_status TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    statement TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS application_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    reason TEXT,
    next_action TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS correction_requests (
    correction_id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    affected_field TEXT NOT NULL,
    source_module TEXT NOT NULL,
    source_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('flagged', 'recorded', 'accepted')),
    coordinator TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE TABLE IF NOT EXISTS profile_revisions (
    student_id TEXT NOT NULL,
    profile_version INTEGER NOT NULL,
    data TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (student_id, profile_version)
);
CREATE TABLE IF NOT EXISTS placements (
    placement_id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL UNIQUE,
    student_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    opportunity_version INTEGER NOT NULL,
    profile_version INTEGER NOT NULL,
    confirmed_by TEXT NOT NULL,
    confirmed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p07_handoffs (
    handoff_id TEXT PRIMARY KEY,
    placement_id TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    receipt_status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_gap_handoffs (
    gap_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    opportunity_version INTEGER NOT NULL,
    recommendation_id TEXT NOT NULL,
    profile_version INTEGER NOT NULL,
    activity_id TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (recommendation_id, skill_id)
);
"""


def db_path() -> str:
    return os.environ.get("APP_DB", "app.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate_recommendation_eligibility(conn)
        _migrate_sprint2_columns(conn)
        # P01/P03 records are read-only inputs, so the files are the source of truth: reload
        # them on every startup (and drop rows from the other source). Stored recommendations,
        # applications, events, corrections and profile revisions are never touched.
        conn.execute("DELETE FROM students")
        conn.execute("DELETE FROM opportunities")
        if data_source() == "fixtures":
            students = json.loads((FIXTURES / "students.json").read_text())
            listings = json.loads((FIXTURES / "opportunities.json").read_text())
        else:
            students = latest_submitted(json.loads((P01P03_DATA / "p01_student_profiles.json").read_text()))
            listings = json.loads((P01P03_DATA / "p03_published_listings.json").read_text())
        _load(conn, students, "students", "student_id", "profile_version")
        _load(conn, listings, "opportunities", "opportunity_id", "version")


def latest_submitted(profiles: list[dict]) -> list[dict]:
    """P01 rule: read the latest profile version with profile_status = submitted; ignore drafts."""
    latest: dict[str, dict] = {}
    for p in profiles:
        if p.get("profile_status", "submitted") != "submitted":
            continue
        current = latest.get(p.get("student_id"))
        if current is None or (p.get("profile_version") or 0) > (current.get("profile_version") or 0):
            latest[p.get("student_id")] = p
    return list(latest.values())


def _migrate_recommendation_eligibility(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(recommendations)")}
    if "eligibility" in columns:
        return
    # Keep the schema change and backfill atomic if startup is interrupted.
    conn.execute("BEGIN")
    conn.execute(
        "ALTER TABLE recommendations ADD COLUMN eligibility TEXT NOT NULL DEFAULT 'unknown' "
        "CHECK (eligibility IN ('eligible', 'unknown', 'ineligible'))"
    )
    # Recover the original assessment from its saved explanation, not today's profile/listing.
    for row in conn.execute("SELECT recommendation_id, compatible, unknowns FROM recommendations").fetchall():
        if not row["compatible"]:
            eligibility = "ineligible"
        elif any(u.startswith("Availability:") for u in json.loads(row["unknowns"])):
            eligibility = "unknown"
        else:
            eligibility = "eligible"
        conn.execute(
            "UPDATE recommendations SET eligibility = ?, compatible = ? WHERE recommendation_id = ?",
            (eligibility, int(eligibility == "eligible"), row["recommendation_id"]),
        )


def _migrate_sprint2_columns(conn: sqlite3.Connection) -> None:
    """Additive Sprint 2 columns for databases created in Sprint 1."""
    recommendation_columns = {row["name"] for row in conn.execute("PRAGMA table_info(recommendations)")}
    if "ai_method_version" not in recommendation_columns:
        conn.execute("ALTER TABLE recommendations ADD COLUMN ai_method_version TEXT")
        conn.execute("ALTER TABLE recommendations ADD COLUMN ai_matches TEXT")
        recommendation_columns.add("ai_matches")
    if "ai_insights" not in recommendation_columns:
        conn.execute("ALTER TABLE recommendations ADD COLUMN ai_insights TEXT")
    application_columns = {row["name"] for row in conn.execute("PRAGMA table_info(applications)")}
    if "statement" not in application_columns:
        conn.execute("ALTER TABLE applications ADD COLUMN statement TEXT")
        conn.execute("ALTER TABLE applications ADD COLUMN updated_at TEXT")


def _load(conn, records, table, id_field, version_field) -> None:
    for record in records:
        if not record.get(id_field) or not isinstance(record.get(version_field), int):
            log.warning("Skipping malformed %s record: %s", table, record)
            continue
        conn.execute(
            f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?)",
            (record[id_field], record[version_field], json.dumps(record)),
        )


P06_DATA = SEED / "p06"


def p06_activities() -> dict[str, dict]:
    """P06 preparation activities by skill, as sent by Team P6/P7 (24 Nov). Jira is a full
    module; SQL and VIZ are outlines; skills without a module (e.g. Excel, Figma) have none."""
    return {a["skill_id"]: a for a in json.loads((P06_DATA / "p06_activities.json").read_text())}


def skill_names() -> dict[str, str]:
    skills = json.loads((FIXTURES / "skills.json").read_text())
    return {s["skill_id"]: s["name"] for s in skills}
