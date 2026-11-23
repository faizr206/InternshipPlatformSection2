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
"""
import json
import logging
import os
import sqlite3
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
log = logging.getLogger(__name__)

SCHEMA = """
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
        # Fixtures are read-only stand-ins for P01/P03, so the files are the source of truth:
        # refresh them on every startup (e.g. after the shared skill IDs changed).
        # Stored recommendations, applications, events, corrections and profile
        # revisions are never touched.
        _load(conn, "students.json", "students", "student_id", "profile_version")
        _load(conn, "opportunities.json", "opportunities", "opportunity_id", "version")


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


def _load(conn, filename, table, id_field, version_field) -> None:
    for record in json.loads((FIXTURES / filename).read_text()):
        if not record.get(id_field) or not isinstance(record.get(version_field), int):
            log.warning("Skipping malformed %s record: %s", table, record)
            continue
        conn.execute(
            f"INSERT OR REPLACE INTO {table} VALUES (?, ?, ?)",
            (record[id_field], record[version_field], json.dumps(record)),
        )


def skill_names() -> dict[str, str]:
    skills = json.loads((FIXTURES / "skills.json").read_text())
    return {s["skill_id"]: s["name"] for s in skills}
