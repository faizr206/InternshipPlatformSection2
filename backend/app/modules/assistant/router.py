"""Co-op assistant API: one assistant for the platform (owned by P06/P07, merges the P01-P03 FAQ bot).

- Retrieval only by default: quotes an approved entry with its source (engine.py).
- Optional LLM (Team P6/P7's Sprint 3 design, legacy/p06-p07-waypoint/source/server.py): with
  OPENROUTER_API_KEY in .env, the model rephrases the closest approved entries. Only the question and those
  entries are sent, never student records; privacy and personal-information questions never reach the model;
  citations of entries we did not send are dropped; on any model error the approved text is shown instead.
- Coordinator loop (P01-P03 design, legacy/p01-p03-ipp/src/faq.js): handed-over questions are listed;
  the coordinator replies, or writes an entry that stays pending until approved, then the assistant uses it.
"""
import json
import os
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db
from app.core.common import actor, get_student, log_event, next_id, now, require_role, words
from app.modules.assistant import engine

router = APIRouter(prefix="/api/assistant", tags=["Assistant"])

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "thinkingmachines/inkling-2-mini"
GREETING = re.compile(r"^\s*(hi|hello|hey|salam|good (morning|afternoon|evening)|thanks?|thank you)\b[\s!.?]*$", re.I)
LIMITS = {"topic": 40, "question": 150, "answer": 500}
ROOT = Path(__file__).resolve().parents[4]


def load_env() -> None:
    """Read KEY=VALUE lines from backend/.env or the repo's .env (values already set win). Never committed."""
    for path in (ROOT / "backend" / ".env", ROOT / ".env"):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()


def llm_config() -> tuple[str | None, str]:
    return os.environ.get("OPENROUTER_API_KEY") or None, os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)


SYSTEM = """You are the friendly co-op assistant inside the IPP Coop Platform, a university classroom prototype.
Students ask you about internships, matching, preparing skills such as Jira, placements, their co-op log, or anything else. Be natural, warm and genuinely helpful, like a good student advisor in a chat.

- Answer every message. Greetings and small talk get a short friendly reply.
- The APPROVED ENTRIES below are the programme's official answers. When one is relevant, base your answer on it, rephrase it naturally, and list its ID in faq_ids.
- When no entry fits, still help from general knowledge (for example how to prepare for an interview, what Jira is, how to write a good log entry). Leave faq_ids empty.
- Do not invent university-specific rules such as pay, GPA, credits, visas or deadlines. For those, give general guidance if useful, say the co-op coordinator will confirm, and set needs_coordinator to true.
- Never approve placements or share information about other students.
- Keep replies short: 1 to 5 sentences, plain English, speaking to the student as "you"."""

SCHEMA = {"name": "assistant_reply", "strict": True, "schema": {
    "type": "object", "additionalProperties": False,
    "properties": {"answer": {"type": "string"}, "faq_ids": {"type": "array", "items": {"type": "string"}},
                   "needs_coordinator": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["answer", "faq_ids", "needs_coordinator", "reason"]}}


def build_messages(question: str, entries: list[dict]) -> list[dict]:
    blocks = "\n\n".join(
        f"[{e['faq_id']}] Topic: {e['topic']}\nAnswers questions like: {e['question']}"
        + (f" / {' / '.join(e['alternatives'])}" if e.get("alternatives") else "")
        + f"\nApproved answer: {e['answer']}\nSource: {e['source']}" for e in entries)
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"APPROVED ENTRIES:\n{blocks}\n\nSTUDENT QUESTION:\n{question}"}]


def validate_reply(raw: str, sent_ids: set[str]) -> dict:
    """Keep the model's reply but drop citations of entries we did not send; an empty reply goes to a person."""
    try:
        reply = json.loads(raw)
    except (TypeError, ValueError):
        return {"answer": "", "faq_ids": [], "needs_coordinator": True, "reason": "The model did not return a readable reply."}
    text = str(reply.get("answer", "")).strip()
    if not text:
        return {"answer": "", "faq_ids": [], "needs_coordinator": True, "reason": str(reply.get("reason", ""))[:300] or "Empty reply."}
    return {"answer": text[:1500], "faq_ids": [i for i in reply.get("faq_ids", []) if i in sent_ids],
            "needs_coordinator": bool(reply.get("needs_coordinator")), "reason": str(reply.get("reason", "")).strip()[:300]}


def ask_model(question: str, entries: list[dict], key: str, model: str) -> dict:
    body = {"model": model, "messages": build_messages(question, entries), "temperature": 0.5, "max_tokens": 2500,
            "reasoning": {"effort": "low", "exclude": True},
            "response_format": {"type": "json_schema", "json_schema": SCHEMA}}
    response = httpx.post(OPENROUTER_URL, json=body, timeout=25, headers={
        "Authorization": f"Bearer {key}", "X-Title": "IPP co-op assistant (classroom prototype)"})
    response.raise_for_status()
    raw = (response.json()["choices"][0]["message"].get("content") or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
    return validate_reply(raw, {e["faq_id"] for e in entries})


def approved_entries(conn) -> list[dict]:
    extra = [{"faq_id": r["faq_id"], "topic": r["topic"], "question": r["question"], "alternatives": [],
              "keywords": [], "answer": r["answer"], "source": f"Coordinator-approved ({r['approved_by']}, "
                                                               f"{r['approved_at'][:10]})", "team": "Coordinator"}
             for r in conn.execute("SELECT * FROM assistant_entries WHERE status = 'approved' ORDER BY faq_id")]
    return engine.seed()["entries"] + extra


def normalize(question: str) -> str:
    return " ".join(sorted(set(engine.tokens(question)))) or question.strip().lower()


def hand_over(conn, question: str, role: str, student_id: str | None, reason: str) -> str:
    """Record a question for the coordinator; repeats of the same question are counted, not duplicated."""
    key = normalize(question)
    row = conn.execute("SELECT question_id FROM assistant_questions WHERE normalized = ? AND status = 'open'",
                       (key,)).fetchone()
    if row:
        conn.execute("UPDATE assistant_questions SET count = count + 1, last_asked_at = ? WHERE question_id = ?",
                     (now(), row["question_id"]))
        return row["question_id"]
    question_id = next_id(conn, "Q", ["SELECT question_id FROM assistant_questions"], 3)
    conn.execute("INSERT INTO assistant_questions (question_id, question, normalized, asked_by_role, student_id, reason, "
                 "count, first_asked_at, last_asked_at, status) VALUES (?,?,?,?,?,?,1,?,?, 'open')",
                 (question_id, question.strip()[:500], key, role, student_id, reason, now(), now()))
    log_event(conn, "P06", role, "Co-op assistant", "assistant_handoff",
              f"The assistant handed question {question_id} to the coordinator", question_id)
    return question_id


class AskIn(BaseModel):
    question: str
    role: str = "student"
    student_id: str | None = None


@router.get("/status")
def status():
    key, model = llm_config()
    with db.connect() as conn:
        return {"mode": "llm" if key else "retrieval", "model": model if key else None,
                "approved_entries": len(approved_entries(conn)),
                "note": "Answers come only from approved entries." + (
                    "" if key else " Add OPENROUTER_API_KEY to backend/.env to let a model rephrase them.")}


@router.post("/ask")
def ask(body: AskIn):
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(422, "Type a question first.")
    question = question[:500]
    with db.connect() as conn:
        student = get_student(conn, body.student_id) if body.student_id else None
        students = [get_student(conn, r["student_id"]) for r in conn.execute("SELECT student_id FROM students")]
        entries = approved_entries(conn)
        result = engine.answer(question, entries, [s for s in students if s], body.student_id)
        base = {"question": question, "guard": result["guard"], "score": result["score"], "ranked": result["ranked"],
                "reason": result["reason"], "faq_id": None, "faq_ids": [], "question_id": None}

        if result["kind"] == "refused":
            return {**base, "kind": "refused", "mode": "retrieval", "confident": False, "source": None,
                    "answer": "Please don't share personal details such as emails, phone numbers or IDs here. "
                              "Ask your question without them."}
        if GREETING.match(question):  # greetings and thanks get a short reply instead of a hand-over
            name = student["display_name"].split()[0] if student else "there"
            return {**base, "kind": "chat", "mode": "retrieval", "confident": True, "source": None,
                    "answer": f"Hi {name}! Ask me about internship matching, preparing a skill such as Jira, "
                              "your placement or your co-op log."}

        key, model = llm_config()
        if key and result["guard"] != "privacy":
            sent = engine.candidates(question, entries)
            try:
                reply = ask_model(question, sent, key, model)
            except Exception as error:  # noqa: BLE001 - any model failure falls back to the approved text
                reply = None
                base["reason"] += f" (Model unavailable: {type(error).__name__}; approved text shown.)"
            if reply and reply["answer"]:
                question_id = (hand_over(conn, question, body.role, body.student_id, reply["reason"] or "Model flagged it")
                               if reply["needs_coordinator"] else None)
                cited = [e for e in sent if e["faq_id"] in reply["faq_ids"]]
                return {**base, "kind": "handoff" if question_id else "answer", "mode": "llm", "model": model,
                        "answer": reply["answer"], "faq_ids": reply["faq_ids"],
                        "faq_id": reply["faq_ids"][0] if reply["faq_ids"] else None,
                        "source": "; ".join(f"{e['faq_id']}: {e['source']}" for e in cited) or None,
                        "approved_text": [{"faq_id": e["faq_id"], "answer": e["answer"]} for e in cited],
                        "confident": bool(cited), "question_id": question_id}

        if result["kind"] == "answer":
            entry = result["entry"]
            return {**base, "kind": "answer", "mode": "retrieval", "confident": True, "answer": entry["answer"],
                    "faq_id": entry["faq_id"], "faq_ids": [entry["faq_id"]], "source": entry["source"],
                    "topic": entry["topic"]}
        question_id = hand_over(conn, question, body.role, body.student_id, result["reason"])
        return {**base, "kind": "handoff", "mode": "retrieval", "confident": False, "source": None,
                "question_id": question_id,
                "answer": "I don't have an approved answer for that yet, so I've passed your question to the co-op "
                          f"coordinator ({question_id}). You'll see the reply here."}


@router.get("/faq")
def faq():
    with db.connect() as conn:
        return approved_entries(conn)


@router.get("/questions")
def questions(status: str = "", student_id: str = ""):
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if student_id:
        clauses.append("student_id = ?")
        params.append(student_id)
    query = "SELECT * FROM assistant_questions" + (" WHERE " + " AND ".join(clauses) if clauses else "") + \
            " ORDER BY question_id"
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(query, params)]


class ReplyIn(BaseModel):
    actor_role: str
    actor_name: str | None = None
    reply: str


class Actor(BaseModel):
    actor_role: str
    actor_name: str | None = None


class EntryIn(Actor):
    topic: str
    question: str
    answer: str
    question_id: str | None = None


def _question(conn, question_id: str):
    row = conn.execute("SELECT * FROM assistant_questions WHERE question_id = ?", (question_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Question {question_id} not found")
    return row


@router.post("/questions/{question_id}/reply", status_code=201)
def reply(question_id: str, body: ReplyIn):
    require_role(body.actor_role, "coordinator", "reply to a handed-over question")
    if words(body.reply) < 4:
        raise HTTPException(422, "Write a reply of at least four words.")
    who = actor("coordinator", body.actor_name)
    with db.connect() as conn:
        if _question(conn, question_id)["status"] != "open":
            raise HTTPException(409, f"{question_id} is already closed.")
        conn.execute("UPDATE assistant_questions SET status = 'answered', reply = ?, replied_by = ?, replied_at = ? "
                     "WHERE question_id = ?", (body.reply.strip(), who, now(), question_id))
        log_event(conn, "P06", "coordinator", who, "assistant_reply", f"{who} answered handed-over question {question_id}",
                  question_id)
        return dict(_question(conn, question_id))


@router.post("/questions/{question_id}/dismiss", status_code=201)
def dismiss(question_id: str, body: Actor):
    require_role(body.actor_role, "coordinator", "dismiss a question")
    with db.connect() as conn:
        _question(conn, question_id)
        conn.execute("UPDATE assistant_questions SET status = 'dismissed' WHERE question_id = ?", (question_id,))
        return dict(_question(conn, question_id))


@router.get("/entries")
def entries(status: str = ""):
    """Coordinator-written entries (pending ones are never used for answers)."""
    query = "SELECT * FROM assistant_entries" + (" WHERE status = ?" if status else "") + " ORDER BY faq_id"
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(query, (status,) if status else ())]


@router.post("/entries", status_code=201)
def add_entry(body: EntryIn):
    require_role(body.actor_role, "coordinator", "write an assistant answer")
    values = {"topic": body.topic.strip(), "question": body.question.strip(), "answer": body.answer.strip()}
    errors = {f: f"{f.capitalize()} is required." for f, v in values.items() if not v}
    errors.update({f: f"{f.capitalize()} must be {LIMITS[f]} characters or fewer." for f, v in values.items()
                   if f not in errors and len(v) > LIMITS[f]})
    if any(engine.detect_pii(v) for v in values.values()):
        errors["answer"] = "Entries must not contain personal information."
    who = actor("coordinator", body.actor_name)
    with db.connect() as conn:
        known = {normalize(e["question"]) for e in approved_entries(conn)} | {
            normalize(r["question"]) for r in conn.execute("SELECT question FROM assistant_entries")}
        if "question" not in errors and normalize(values["question"]) in known:
            errors["question"] = "An entry already answers this question."
        if errors:
            raise HTTPException(422, {"message": "Fix the entry before saving it.", "errors": errors})
        taken = [e["faq_id"] for e in engine.seed()["entries"]]
        faq_id = next_id(conn, "FAQ", ["SELECT faq_id FROM assistant_entries"] +
                         [f"SELECT '{i}'" for i in taken], 2)
        conn.execute("INSERT INTO assistant_entries (faq_id, topic, question, answer, status, created_by, created_at, "
                     "from_question) VALUES (?,?,?,?, 'pending', ?,?,?)",
                     (faq_id, values["topic"], values["question"], values["answer"], who, now(), body.question_id))
        log_event(conn, "P06", "coordinator", who, "assistant_entry_drafted",
                  f"{who} drafted assistant entry {faq_id} (pending approval)", faq_id)
        return dict(conn.execute("SELECT * FROM assistant_entries WHERE faq_id = ?", (faq_id,)).fetchone())


@router.post("/entries/{faq_id}/approve", status_code=201)
def approve(faq_id: str, body: Actor):
    """Approve a pending entry: from now on the assistant uses it, and open questions it answers are closed."""
    require_role(body.actor_role, "coordinator", "approve an assistant answer")
    who = actor("coordinator", body.actor_name)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM assistant_entries WHERE faq_id = ?", (faq_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Entry {faq_id} not found")
        if row["status"] == "approved":
            raise HTTPException(409, f"{faq_id} is already approved.")
        conn.execute("UPDATE assistant_entries SET status = 'approved', approved_by = ?, approved_at = ? WHERE faq_id = ?",
                     (who, now(), faq_id))
        entries_now = approved_entries(conn)
        closed = []
        for q in conn.execute("SELECT * FROM assistant_questions WHERE status = 'open'").fetchall():
            result = engine.answer(q["question"], entries_now, [], None)
            if q["question_id"] == row["from_question"] or (result["entry"] and result["entry"]["faq_id"] == faq_id):
                conn.execute("UPDATE assistant_questions SET status = 'answered', reply = ?, replied_by = ?, "
                             "replied_at = ? WHERE question_id = ?", (row["answer"], who, now(), q["question_id"]))
                closed.append(q["question_id"])
        log_event(conn, "P06", "coordinator", who, "assistant_entry_approved",
                  f"{who} approved assistant entry {faq_id}" + (f"; answered {', '.join(closed)}" if closed else ""), faq_id)
        return {**dict(conn.execute("SELECT * FROM assistant_entries WHERE faq_id = ?", (faq_id,)).fetchone()),
                "answered_questions": closed}


@router.post("/entries/{faq_id}/discard", status_code=201)
def discard(faq_id: str, body: Actor):
    require_role(body.actor_role, "coordinator", "discard an assistant answer")
    with db.connect() as conn:
        row = conn.execute("SELECT status FROM assistant_entries WHERE faq_id = ?", (faq_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Entry {faq_id} not found")
        if row["status"] != "pending":
            raise HTTPException(409, "Only a pending entry can be discarded.")
        conn.execute("DELETE FROM assistant_entries WHERE faq_id = ?", (faq_id,))
        return {"faq_id": faq_id, "discarded": True}
