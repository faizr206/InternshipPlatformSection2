"""Shared helpers used by every module: time, simulated roles, P01 profile and P03 listing reads.

Moved from the P04/P05 app (legacy/p04-p05-coop/app/main.py) without behaviour changes.
"""
import json
from datetime import datetime, timezone

from fastapi import HTTPException

# Supervisor contact comes from P03 and is passed on to P07 with a confirmed placement;
# it is never shown to students (agreed with P01-P03, 10 Nov).
PRIVATE_LISTING_FIELDS = ("supervisor_name", "supervisor_contact")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_student(conn, student_id: str) -> dict | None:
    """Effective profile: the latest correction revision if there is one, else the P01 fixture.

    P05 never edits the P01 fixture table; accepted corrections are stored as new
    versions in profile_revisions (P05-05 AC2).
    """
    rev = conn.execute(
        "SELECT profile_version, data FROM profile_revisions WHERE student_id = ? "
        "ORDER BY profile_version DESC LIMIT 1",
        (student_id,),
    ).fetchone()
    base = conn.execute("SELECT profile_version, data FROM students WHERE student_id = ?", (student_id,)).fetchone()
    # The newer version wins, so a newer P01 export is never hidden by an older local revision.
    row = rev if rev and (not base or rev["profile_version"] > base["profile_version"]) else base
    return json.loads(row["data"]) if row else None


def get_opportunity(conn, opportunity_id: str) -> dict | None:
    row = conn.execute("SELECT data FROM opportunities WHERE opportunity_id = ?", (opportunity_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def all_opportunities(conn) -> list[dict]:
    return [json.loads(r["data"]) for r in conn.execute("SELECT data FROM opportunities ORDER BY opportunity_id")]


def student_view(opp: dict) -> dict:
    return {k: v for k, v in opp.items() if k not in PRIVATE_LISTING_FIELDS}

def require_role(given: str, expected: str | tuple[str, ...], action: str) -> None:
    """Simulated role check (no login). Real access control is a recorded, deferred gap."""
    allowed = (expected,) if isinstance(expected, str) else expected
    if given not in allowed:
        raise HTTPException(
            403,
            f"Role '{given or 'none'}' is not allowed to {action}. "
            f"This action belongs to the {' or '.join(allowed)} role (simulated role switching; no login).",
        )


def student_and_opportunity(conn, student_id: str, opportunity_id: str) -> tuple[dict, dict]:
    student = get_student(conn, student_id)
    if not student:
        raise HTTPException(400, "Unknown student")
    opp = get_opportunity(conn, opportunity_id)
    if not opp:
        raise HTTPException(400, "Unknown opportunity")
    return student, opp

def new_profile_version(conn, new_profile: dict, source: str) -> int:
    """Store a changed profile as the next version. Earlier versions (and the P01
    fixture row) are never edited, so older recommendations keep their inputs."""
    current = get_student(conn, new_profile["student_id"])
    new_version = current["profile_version"] + 1
    new_profile["profile_version"] = new_version
    conn.execute(
        "INSERT INTO profile_revisions (student_id, profile_version, data, source, created_at) "
        "VALUES (?,?,?,?,?)",
        (new_profile["student_id"], new_version, json.dumps(new_profile), source, now()),
    )
    return new_version
