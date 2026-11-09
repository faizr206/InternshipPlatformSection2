"""SQLite storage. Fixtures stand in for P01 (profiles) and P03 (published listings)."""
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
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
    application_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    profile_version INTEGER NOT NULL,
    opportunity_id TEXT NOT NULL,
    opportunity_version INTEGER NOT NULL,
    application_status TEXT NOT NULL,
    placement_status TEXT NOT NULL,
    submitted_at TEXT NOT NULL
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
        if conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
            _load(conn, "students.json", "students", "student_id", "profile_version")
        if conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0] == 0:
            _load(conn, "opportunities.json", "opportunities", "opportunity_id", "version")


def _load(conn, filename, table, id_field, version_field) -> None:
    for record in json.loads((FIXTURES / filename).read_text()):
        if not record.get(id_field) or not isinstance(record.get(version_field), int):
            log.warning("Skipping malformed %s record: %s", table, record)
            continue
        conn.execute(
            f"INSERT INTO {table} VALUES (?, ?, ?)",
            (record[id_field], record[version_field], json.dumps(record)),
        )


def skill_names() -> dict[str, str]:
    skills = json.loads((FIXTURES / "skills.json").read_text())
    return {s["skill_id"]: s["name"] for s in skills}
