import json
from pathlib import Path

from app.matching import recommend

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
    assert op033["compatible"] is False
    assert results[-1]["opportunity_id"] == "OP-033"


def test_missing_dates_are_unknown_not_satisfied():
    op032 = by_id(recommend(LAYLA, OPPS, SKILLS))["OP-032"]  # no dates
    assert any("Needs checking" in u for u in op032["unknowns"])
    assert not any("covers" in r for r in op032["reasons"])


def test_layla_op028_reasons_and_jira_gap():
    op028 = by_id(recommend(LAYLA, OPPS, SKILLS))["OP-028"]
    assert op028["compatible"] is True
    assert any("SK-JIRA-01" in g for g in op028["gaps"])
    assert any("aviation" in r for r in op028["reasons"])
    # SQL is self-declared and must not be labelled as reviewed
    assert any("SK-SQL-01, self-declared" in r for r in op028["reasons"])
    assert op028["profile_version"] == 1 and op028["opportunity_version"] == 2


def test_changing_a_skill_changes_the_result():
    with_jira = {**LAYLA, "skills": LAYLA["skills"] + [{"skill_id": "SK-JIRA-01", "evidence_status": "reviewed"}]}
    before = by_id(recommend(LAYLA, OPPS, SKILLS))["OP-028"]
    after = by_id(recommend(with_jira, OPPS, SKILLS))["OP-028"]
    assert after["score"] > before["score"]
    assert after["gaps"] == []
