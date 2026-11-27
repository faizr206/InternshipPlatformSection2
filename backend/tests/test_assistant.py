"""One co-op assistant: Team P6/P7's retrieval engine and guards plus the P01-P03 coordinator loop
(ported from legacy/p06-p07-waypoint/source/tests/ai_test.py and legacy/p01-p03-ipp/tests/faq.test.mjs)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.assistant import router as assistant

COORD = {"actor_role": "coordinator"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATA_SOURCE", "p01p03")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with TestClient(app) as c:
        c.post("/api/demo/reset?scenario=fresh")
        yield c


def ask(client, q, student_id="COOP-B001"):
    return client.post("/api/assistant/ask", json={"question": q, "role": "student", "student_id": student_id}).json()


@pytest.mark.parametrize("question,faq_id", [
    ("Which internships fit me?", "FAQ-01"), ("Who approves my placement?", "FAQ-02"),
    ("Does applying mean I got the placement?", "FAQ-02"), ("How do I close a skill gap such as Jira?", "FAQ-03"),
    ("Does finishing the module mean I have the skill?", "FAQ-04"), ("What does the reviewer check for Jira?", "FAQ-05"),
    ("Who signs the learning agreement?", "FAQ-07"), ("Can I intern remotely?", "FAQ-13"),
    ("Can I work abroad?", "FAQ-14"), ("How do I resubmit my listing?", "FAQ-19"),
])
def test_answers_quote_approved_entries_with_source(client, question, faq_id):
    r = ask(client, question)
    assert (r["kind"], r["faq_id"], r["mode"], r["confident"]) == ("answer", faq_id, "retrieval", True)
    assert r["source"]


def test_both_teams_faqs_are_merged(client):
    teams = {e["team"] for e in client.get("/api/assistant/faq").json()}
    assert teams == {"P06/P07", "P01–P03"}


def test_policy_topic_goes_to_the_coordinator(client):
    r = ask(client, "Are co-op students paid?")
    assert (r["kind"], r["guard"]) == ("handoff", "policy") and r["question_id"] == "Q-001"
    again = ask(client, "are co-op students paid")
    assert again["question_id"] == "Q-001"  # counted, not duplicated
    [q] = client.get("/api/assistant/questions?status=open").json()
    assert q["count"] == 2 and q["student_id"] == "COOP-B001"


def test_low_confidence_goes_to_the_coordinator(client):
    r = ask(client, "What are the weather plans")
    assert (r["kind"], r["guard"]) == ("handoff", "confidence")


def test_other_student_gets_privacy_answer_and_no_data(client):
    r = ask(client, "What is Arjun's GPA?")
    assert (r["kind"], r["guard"], r["faq_id"]) == ("answer", "privacy", "FAQ-10")
    assert "Arjun" not in r["answer"]


def test_personal_information_is_refused_and_not_stored(client):
    r = ask(client, "My email is layla@example.com, can I apply?")
    assert (r["kind"], r["guard"]) == ("refused", "pii")
    assert client.get("/api/assistant/questions").json() == []


def test_greeting_gets_a_friendly_reply(client):
    r = ask(client, "hello")
    assert r["kind"] == "chat" and r["answer"].startswith("Hi Layla")


def test_coordinator_loop_reply_draft_approve(client):
    """P01-P03 loop: unanswered -> coordinator writes an entry (pending, unused) -> approve -> answered."""
    qid = ask(client, "Are co-op students paid?")["question_id"]
    assert client.post(f"/api/assistant/questions/{qid}/reply", json={**COORD, "reply": "Ask"}).status_code == 422
    entry = client.post("/api/assistant/entries", json={**COORD, "topic": "Placements", "question_id": qid,
                                                       "question": "Is a co-op placement paid?",
                                                       "answer": "Pay depends on the employer and is stated in the offer."})
    assert entry.status_code == 201 and entry.json()["status"] == "pending"
    assert ask(client, "Is a co-op placement paid?")["kind"] == "handoff"  # pending entries are never used
    approved = client.post(f"/api/assistant/entries/{entry.json()['faq_id']}/approve", json=COORD).json()
    assert approved["status"] == "approved" and qid in approved["answered_questions"]
    q = client.get("/api/assistant/questions").json()[0]
    assert q["status"] == "answered" and q["replied_by"] == "Sara Al Hammadi"


def test_entry_validation(client):
    dup = client.post("/api/assistant/entries", json={**COORD, "topic": "Matching", "question": "Which internships fit me?",
                                                     "answer": "Something else."})
    assert dup.status_code == 422 and "question" in dup.json()["detail"]["errors"]
    pii = client.post("/api/assistant/entries", json={**COORD, "topic": "Contact", "question": "Who do I email?",
                                                     "answer": "Email sara@example.com"})
    assert pii.status_code == 422
    assert client.post("/api/assistant/entries", json={"actor_role": "student", "topic": "x", "question": "y",
                                                      "answer": "z"}).status_code == 403


def test_reply_closes_a_question(client):
    qid = ask(client, "Is there a deadline to apply?")["question_id"]
    r = client.post(f"/api/assistant/questions/{qid}/reply", json={**COORD, "reply": "Apply while the listing is open."})
    assert r.json()["status"] == "answered"
    assert client.post(f"/api/assistant/questions/{qid}/reply", json={**COORD, "reply": "Again and again here."}).status_code == 409


def test_llm_mode_cites_only_sent_entries_and_never_sees_privacy_questions(client, monkeypatch):
    calls = []

    def fake_model(question, entries, key, model):
        calls.append((question, [e["faq_id"] for e in entries]))
        return assistant.validate_reply(
            '{"answer": "Matching ranks open roles on skills, interests and location.", '
            '"faq_ids": ["FAQ-01", "FAQ-99"], "needs_coordinator": false, "reason": "fits FAQ-01"}',
            {e["faq_id"] for e in entries})

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(assistant, "ask_model", fake_model)
    r = ask(client, "Which internships fit me?")
    assert (r["mode"], r["faq_ids"], r["confident"]) == ("llm", ["FAQ-01"], True)  # FAQ-99 was never sent
    assert r["approved_text"][0]["faq_id"] == "FAQ-01"
    privacy = ask(client, "What is Arjun's GPA?")
    assert privacy["mode"] == "retrieval" and len(calls) == 1
    assert client.get("/api/assistant/status").json()["mode"] == "llm"


def test_llm_failure_falls_back_to_approved_text(client, monkeypatch):
    def broken(*_):
        raise TimeoutError

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(assistant, "ask_model", broken)
    r = ask(client, "Who approves my placement?")
    assert (r["mode"], r["faq_id"]) == ("retrieval", "FAQ-02") and "Model unavailable" in r["reason"]


def test_validate_reply_rules():
    assert assistant.validate_reply("not json", {"FAQ-01"})["needs_coordinator"] is True
    assert assistant.validate_reply('{"answer": "", "faq_ids": [], "needs_coordinator": false, "reason": ""}',
                                    set())["needs_coordinator"] is True
