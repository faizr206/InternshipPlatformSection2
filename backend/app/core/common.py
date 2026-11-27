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
    """Effective listing: the platform copy (created by P02 or changed by P03) if it is at least as
    new as the seed row, else the seed row. Seed rows are never edited."""
    platform = conn.execute("SELECT version, data FROM listings WHERE opportunity_id = ?", (opportunity_id,)).fetchone()
    seed = conn.execute("SELECT version, data FROM opportunities WHERE opportunity_id = ?", (opportunity_id,)).fetchone()
    row = platform if platform and (not seed or platform["version"] >= seed["version"]) else seed
    return json.loads(row["data"]) if row else None


def all_opportunities(conn) -> list[dict]:
    ids = sorted({r[0] for r in conn.execute("SELECT opportunity_id FROM opportunities UNION "
                                             "SELECT opportunity_id FROM listings")})
    return [get_opportunity(conn, i) for i in ids]


def next_id(conn, prefix: str, queries: list[str], width: int = 3) -> str:
    """Next ID after the highest numeric suffix across the given ID queries, e.g. OP-040."""
    highest = 0
    for query in queries:
        for (value,) in conn.execute(query):
            tail = str(value).rsplit("-", 1)[-1]
            if tail.isdigit():
                highest = max(highest, int(tail))
    return f"{prefix}-{highest + 1:0{width}d}"


def log_event(conn, module: str, actor_role: str, actor_name: str, action: str, text: str, ref: str = "") -> None:
    """Platform activity feed shared by every module (who did what, when, to which record)."""
    conn.execute("INSERT INTO events (at, module, actor_role, actor_name, action, ref, text) VALUES (?,?,?,?,?,?,?)",
                 (now(), module, actor_role, actor_name, action, ref, text))


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


# --- Demo people and the demo clock (shared by every module) ---
# Synthetic actors agreed for the demo (Team P6/P7 data.js PEOPLE). The student actor is the
# selected student's display name.
DEMO_PEOPLE = {
    "employer": {"id": "EMP-HR01", "name": "Emirates Group HR (synthetic)", "role": "Employer HR / reviewer"},
    "coordinator": {"id": "STF-C002", "name": "Sara Al Hammadi", "role": "Co-op coordinator"},
    "reviewer": {"id": "STF-R014", "name": "Maya Chen", "role": "Learning reviewer"},
    "supervisor": {"id": "EMP-S310", "name": "R. Khan", "role": "Workplace supervisor"},
    "advisor": {"id": "FAC-A021", "name": "Dr. Ahmed Youssef", "role": "Academic advisor"},
}
ADVISORS = [{"id": "FAC-A021", "name": "Dr. Ahmed Youssef"}, {"id": "FAC-A034", "name": "Dr. Lina Farouk"}]


def actor(role: str, given: str | None = None, conn=None, student_id: str | None = None) -> str:
    """Name to record for an action: the given name, else the demo person for the role
    (for students, their display name)."""
    if given and given.strip():
        return given.strip()
    if role == "student" and conn is not None and student_id:
        student = get_student(conn, student_id)
        if student:
            return student["display_name"]
    return DEMO_PEOPLE.get(role, {}).get("name", role)


def today(conn) -> str:
    """The demo date (YYYY-MM-DD). Scenarios set it (e.g. midpoint = 2027-03-18); otherwise the real date.
    P06/P07 business dates (log dates, due dates, overdue checks, review periods) use it."""
    row = conn.execute("SELECT value FROM demo_settings WHERE key = 'today'").fetchone()
    return row["value"] if row else datetime.now(timezone.utc).date().isoformat()


def words(text: str | None) -> int:
    return len((text or "").split())


def record_handoff(conn, from_module: str, to_module: str, kind: str, payload: dict,
                   student_id: str | None = None, ref: str | None = None, status: str = "delivered") -> str:
    """Store a cross-module handoff record (contract evidence; GET /api/handoffs)."""
    handoff_id = next_id(conn, "HO", ["SELECT handoff_id FROM handoffs"], width=4)
    conn.execute("INSERT INTO handoffs (handoff_id, from_module, to_module, kind, student_id, ref, payload, status, "
                 "created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (handoff_id, from_module, to_module, kind, student_id, ref, json.dumps(payload), status, now()))
    return handoff_id
