"""Bounded AI matching assistance (P05-04): skill-term similarity.

A deliberately bounded, deterministic, offline feature — no external model or paid
service is used or assumed. It recognises terms in the opportunity text that are
equivalent to a skill the student already holds (per the alias map) and reports
the exact term and field it used, alongside the student's evidence status.

Bounds (P05-04 AC2):
- It never changes the rules result: eligibility, compatible, score, gaps and
  unknowns come from the rules baseline (app/matching.py) only.
- It cannot invent a qualification: it only maps terms to skills already on the
  profile, and it never marks a missing required skill as satisfied.
- It is labelled as simulated AI in the interface; the rules baseline stays
  usable on its own.
"""
import json
import re
from pathlib import Path

AI_METHOD_VERSION = "ai-termmatch-v1"

_ALIASES_FILE = Path(__file__).parent / "fixtures" / "skill_aliases.json"
ALIASES: dict[str, list[str]] = {
    k: v for k, v in json.loads(_ALIASES_FILE.read_text()).items() if not k.startswith("_")
}

# Opportunity text fields scanned for equivalent terms; the field name is reported
# so the feature "identifies the terms it used" (P05-04 AC1).
TEXT_FIELDS = ("title", "description")


def _mentions(term: str, text: str) -> bool:
    # Word-boundary match with an optional plural "s", so "dashboard" also finds
    # "dashboards" but never "dashboarding".
    return re.search(rf"\b{re.escape(term)}s?\b", text, re.IGNORECASE) is not None


def term_matches(student: dict, opp: dict, skill_names: dict[str, str],
                 aliases: dict[str, list[str]] = ALIASES) -> list[dict]:
    """Terms in the opportunity text equivalent to skills the student already holds."""
    held = {s["skill_id"]: s["evidence_status"] for s in student.get("skills") or []}
    texts = {field: str(opp.get(field) or "") for field in TEXT_FIELDS}
    matches = []
    for skill_id, status in sorted(held.items()):
        for term in aliases.get(skill_id, []):
            field = next((f for f, t in texts.items() if _mentions(term, t)), None)
            if field:
                matches.append({
                    "term": term,
                    "field": field,
                    "skill_id": skill_id,
                    "skill_name": skill_names.get(skill_id, skill_id),
                    "evidence_status": "reviewed" if status == "reviewed" else "self-declared",
                })
                break
    return matches
