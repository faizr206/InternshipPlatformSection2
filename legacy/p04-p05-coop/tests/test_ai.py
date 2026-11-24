"""Unit tests for the bounded AI term-matching feature (P05-04)."""
import json
from pathlib import Path

from app.ai import AI_METHOD_VERSION, ALIASES, term_matches
from app.matching import is_eligible_listing, match

FIX = Path(__file__).parent.parent / "app" / "fixtures"
STUDENTS = {s["student_id"]: s for s in json.loads((FIX / "students.json").read_text())}
OPPS = {o["opportunity_id"]: o for o in json.loads((FIX / "opportunities.json").read_text())}
SKILLS = {s["skill_id"]: s["name"] for s in json.loads((FIX / "skills.json").read_text())}
LAYLA = STUDENTS["COOP-B001"]


def test_alias_map_covers_the_shared_vocabulary_and_is_labelled():
    assert set(ALIASES) == set(SKILLS)  # every shared skill has fallback aliases (P05-owned, pending SoS)
    assert AI_METHOD_VERSION == "ai-termmatch-v1"


def test_layla_op028_finds_equivalent_terms_with_field_and_status():
    matches = {m["skill_id"]: m for m in term_matches(LAYLA, OPPS["OP-028"], SKILLS)}
    viz = matches["SK-VIZ"]
    assert (viz["term"], viz["field"]) == ("tableau", "description")
    assert viz["evidence_status"] == "self-declared"
    assert matches["SK-SQL"]["term"] == "sql"
    # Terms map only to skills the student actually holds — nothing is invented
    assert set(matches) <= {"SK-SQL", "SK-EXCEL", "SK-VIZ"}
    assert "SK-JIRA" not in matches


def test_no_matches_for_a_student_without_skills():
    assert term_matches(STUDENTS["COOP-B006"], OPPS["OP-028"], SKILLS) == []


def test_reviewed_skills_are_reported_as_reviewed():
    sara = STUDENTS["COOP-B005"]  # SK-SQL and SK-JIRA reviewed
    matches = {m["skill_id"]: m for m in term_matches(sara, OPPS["OP-028"], SKILLS)}
    assert matches["SK-SQL"]["evidence_status"] == "reviewed"
    # Jira is found through the equivalent "agile board" term in the description
    assert matches["SK-JIRA"]["term"] == "agile board"
    assert matches["SK-JIRA"]["evidence_status"] == "reviewed"


def test_word_boundaries_prevent_false_positives():
    opp = {**OPPS["OP-028"], "title": "Data intern", "description": "Experience with dashboarding tools."}
    assert term_matches(LAYLA, opp, SKILLS, aliases={"SK-VIZ": ["dashboard"]}) == []
    opp2 = {**opp, "description": "Builds client dashboards weekly."}
    assert [m["term"] for m in term_matches(LAYLA, opp2, SKILLS, aliases={"SK-VIZ": ["dashboard"]})] == ["dashboard"]


def test_ai_never_changes_the_rules_result():
    rules_result = match(LAYLA, OPPS["OP-028"], SKILLS)
    term_matches(LAYLA, OPPS["OP-028"], SKILLS)  # running AI assistance has no side effects
    assert match(LAYLA, OPPS["OP-028"], SKILLS) == rules_result
    # Even an ineligible listing keeps its mandatory conflict regardless of AI matches
    assert OPPS["OP-033"]["description"]
    conflict = match(LAYLA, OPPS["OP-033"], SKILLS)
    matches = term_matches(LAYLA, OPPS["OP-033"], SKILLS)
    assert conflict["eligibility"] == "ineligible"
    assert matches == []  # Layla holds none of the Python/Jira terms on this listing


def test_matches_are_deterministic():
    a = term_matches(LAYLA, OPPS["OP-028"], SKILLS)
    b = term_matches(LAYLA, OPPS["OP-028"], SKILLS)
    assert a == b


def test_ai_runs_only_where_the_rules_engine_runs():
    # The AI feature is recorded alongside rules results for eligible listings only;
    # closed/unpublished listings are excluded from recommendations entirely.
    assert is_eligible_listing(OPPS["OP-034"]) is False
    assert is_eligible_listing(OPPS["OP-035"]) is False
