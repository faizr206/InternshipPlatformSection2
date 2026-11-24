"""AI recommendation insights (P05-04 extension, ai-insights-v1): relevance, summary,
next steps, similar listings and the statement starter. Same bounds as term matching:
deterministic, offline, never changes the rules result, never invents a qualification."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.modules.matching.ai import (INSIGHTS_VERSION, gap_coach, relevance_scores, similar_opportunities,
                    statement_draft, summary, term_matches)
from app.main import app
from app.modules.matching.matching import RULES, is_eligible_listing, match, recommend

FIX = Path(__file__).parent.parent / "app" / "seed" / "fixtures"
STUDENTS = {s["student_id"]: s for s in json.loads((FIX / "students.json").read_text())}
OPPS = {o["opportunity_id"]: o for o in json.loads((FIX / "opportunities.json").read_text())}
SKILLS = {s["skill_id"]: s["name"] for s in json.loads((FIX / "skills.json").read_text())}
OPEN = [o for o in OPPS.values() if is_eligible_listing(o)]
LAYLA = STUDENTS["COOP-B001"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


def test_relevance_is_bounded_explainable_and_deterministic():
    a = relevance_scores(LAYLA, OPEN, SKILLS)
    assert a == relevance_scores(LAYLA, OPEN, SKILLS)
    assert set(a) == {o["opportunity_id"] for o in OPEN}
    assert all(0 <= v["relevance"] <= 100 for v in a.values())
    # Layla (aviation, analytics, SQL, Tableau) reads closest to the aviation analytics listing
    assert max(a, key=lambda k: a[k]["relevance"]) == "OP-028"
    assert "sql" in a["OP-028"]["top_terms"]


def test_gap_coach_reports_score_gain_and_verification_without_inventing_skills():
    tips = gap_coach(LAYLA, OPPS["OP-028"], OPEN, SKILLS, RULES["weights"])
    held = {s["skill_id"] for s in LAYLA["skills"]}
    learn = [t for t in tips if t["kind"] == "learn"]
    assert {t["skill_id"] for t in learn} == {"SK-JIRA"}  # the one missing required skill
    assert learn[0]["score_gain"] == RULES["weights"]["required_skill"]
    assert all(t["skill_id"] in held for t in tips if t["kind"] == "verify")
    assert tips == sorted(tips, key=lambda t: -t["score_gain"])  # biggest impact first


def test_summary_restates_the_rules_result():
    for oid in ("OP-028", "OP-033"):
        result = match(LAYLA, OPPS[oid], SKILLS)
        text = summary(LAYLA, OPPS[oid], result, term_matches(LAYLA, OPPS[oid], SKILLS), SKILLS)
        assert text.startswith("Layla")
        if result["eligibility"] == "ineligible":
            assert "not a fit" in text  # a mandatory conflict is never softened


def test_similar_listings_exclude_itself_and_only_include_open_listings():
    sims = similar_opportunities(OPPS["OP-033"], OPEN)
    ids = {s["opportunity_id"] for s in sims}
    assert "OP-033" not in ids and ids <= {o["opportunity_id"] for o in OPEN}
    assert all(0 < s["similarity"] <= 100 for s in sims)


def test_statement_draft_only_cites_skills_on_the_profile():
    d = statement_draft(LAYLA, OPPS["OP-028"], SKILLS)
    assert d["version"] == INSIGHTS_VERSION
    assert "Jira" not in d["draft"]  # missing skill is never claimed
    assert "SQL" in d["draft"] and "Emirates Group" in d["draft"]
    no_skills = {**LAYLA, "skills": []}
    assert statement_draft(no_skills, OPPS["OP-028"], SKILLS)["cited_skills"] == []


def test_insights_never_change_the_rules_result_or_order(client):
    before = recommend(copy.deepcopy(LAYLA), OPEN, SKILLS)
    recs = client.post("/api/students/COOP-B001/recommendations").json()
    rules_fields = ("opportunity_id", "score", "eligibility", "compatible", "reasons", "gaps", "unknowns")
    assert [{k: r[k] for k in rules_fields} for r in recs] == [{k: r[k] for k in rules_fields} for r in before]
    for r in recs:
        ins = r["ai_insights"]
        assert ins["version"] == INSIGHTS_VERSION
        assert {"relevance", "summary", "next_steps", "similar", "top_terms"} <= ins.keys()


def test_insights_are_stored_with_the_run(client):
    posted = client.post("/api/students/COOP-B001/recommendations").json()
    latest = client.get("/api/students/COOP-B001/recommendations").json()
    assert {r["opportunity_id"]: r["ai_insights"] for r in posted} == \
           {r["opportunity_id"]: r["ai_insights"] for r in latest}


def test_statement_draft_endpoint_saves_nothing(client):
    r = client.post("/api/ai/statement-draft", json={"student_id": "COOP-B001", "opportunity_id": "OP-028"})
    assert r.status_code == 200 and r.json()["draft"]
    assert client.get("/api/students/COOP-B001/applications").json() == []
    assert client.post("/api/ai/statement-draft",
                       json={"student_id": "NOPE", "opportunity_id": "OP-028"}).status_code == 400
