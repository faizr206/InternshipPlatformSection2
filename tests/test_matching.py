import json
from pathlib import Path

import pytest

from app.matching import match, recommend

FIX = Path(__file__).parent.parent / "app" / "fixtures"
STUDENTS = {s["student_id"]: s for s in json.loads((FIX / "students.json").read_text())}
OPPS = json.loads((FIX / "opportunities.json").read_text())
SKILLS = {s["skill_id"]: s["name"] for s in json.loads((FIX / "skills.json").read_text())}
LAYLA = STUDENTS["COOP-B001"]


def by_id(results):
    return {r["opportunity_id"]: r for r in results}


def test_fixtures_have_at_least_six_of_each():
    assert len(STUDENTS) >= 6 and len(OPPS) >= 6


def test_same_input_gives_same_ranking():
    first = [r["opportunity_id"] for r in recommend(LAYLA, OPPS, SKILLS)]
    second = [r["opportunity_id"] for r in recommend(LAYLA, OPPS, SKILLS)]
    assert first == second


def test_closed_and_unpublished_listings_are_excluded():
    ids = by_id(recommend(LAYLA, OPPS, SKILLS))
    assert "OP-034" not in ids  # closed
    assert "OP-035" not in ids  # unpublished


def test_availability_conflict_is_flagged_and_ranked_last():
    results = recommend(LAYLA, OPPS, SKILLS)
    op033 = by_id(results)["OP-033"]  # Aug-Nov, Layla is Jan-Jun
    assert op033["eligibility"] == "ineligible"
    assert op033["compatible"] is False
    assert results[-1]["opportunity_id"] == "OP-033"


def test_missing_dates_are_unknown_not_satisfied():
    op032 = by_id(recommend(LAYLA, OPPS, SKILLS))["OP-032"]  # no dates
    assert op032["eligibility"] == "unknown"
    assert op032["compatible"] is False
    assert any("Needs checking" in u for u in op032["unknowns"])
    assert not any("covers" in r for r in op032["reasons"])


def test_layla_op028_reasons_and_jira_gap():
    op028 = by_id(recommend(LAYLA, OPPS, SKILLS))["OP-028"]
    assert op028["eligibility"] == "eligible"
    assert op028["compatible"] is True
    assert any("SK-JIRA" in g for g in op028["gaps"])
    assert any("aviation" in r for r in op028["reasons"])
    # SQL is self-declared and must not be labelled as reviewed
    assert any("SK-SQL, self-declared" in r for r in op028["reasons"])
    assert op028["profile_version"] == 1 and op028["opportunity_version"] == 2


def test_changing_a_skill_changes_the_result():
    with_jira = {**LAYLA, "skills": LAYLA["skills"] + [{"skill_id": "SK-JIRA", "evidence_status": "reviewed"}]}
    before = by_id(recommend(LAYLA, OPPS, SKILLS))["OP-028"]
    after = by_id(recommend(with_jira, OPPS, SKILLS))["OP-028"]
    assert after["score"] > before["score"]
    assert after["gaps"] == []


@pytest.mark.parametrize("missing", [None, ""])
@pytest.mark.parametrize("field", ["availability_start", "availability_end", "start_date", "end_date"])
def test_each_missing_date_leaves_eligibility_unknown(field, missing):
    student, opportunity = dict(LAYLA), dict(OPPS[0])
    (student if field.startswith("availability_") else opportunity)[field] = missing
    result = match(student, opportunity, SKILLS)
    assert result["eligibility"] == "unknown"
    assert result["compatible"] is False
    assert any("Availability: Needs checking" in u for u in result["unknowns"])
    assert not any("covers" in reason for reason in result["reasons"])


def test_eligibility_takes_priority_over_score():
    confirmed = {**OPPS[0], "opportunity_id": "confirmed", "sector": "other",
                 "required_skills": [], "desirable_skills": []}
    unknown = {**OPPS[0], "opportunity_id": "unknown", "start_date": None}
    conflict = {**OPPS[0], "opportunity_id": "conflict",
                "start_date": "2028-01-01", "end_date": "2028-06-30"}
    results = recommend(LAYLA, [conflict, unknown, confirmed], SKILLS)
    assert [r["opportunity_id"] for r in results] == ["confirmed", "unknown", "conflict"]
    assert results[0]["score"] < results[1]["score"]


def test_missing_preferences_do_not_make_mandatory_eligibility_unknown():
    result = match({**LAYLA, "interests": []}, OPPS[0], SKILLS)
    assert result["unknowns"] == ["Interests: not provided"]
    assert result["eligibility"] == "eligible"
    assert result["compatible"] is True


def test_mandatory_rule_can_be_switched_off_in_rules_config():
    from app.matching import RULES
    no_mandatory = {**RULES, "mandatory": {"availability_covers_dates": False}}
    op033 = by_id(recommend(LAYLA, OPPS, SKILLS, no_mandatory))["OP-033"]
    assert op033["eligibility"] == "eligible"
    # Switching off a mandatory rule never changes preference scoring
    assert op033["score"] == by_id(recommend(LAYLA, OPPS, SKILLS))["OP-033"]["score"]


def test_rules_config_separates_mandatory_from_preferences():
    from app.matching import RULES
    assert RULES["version"] == "rules-v2"
    assert set(RULES["mandatory"]) == {"availability_covers_dates"}
    assert set(RULES["weights"]) == {"interest", "required_skill", "desirable_skill"}
