"""Co-op assistant retrieval engine (P06-owned; one assistant for the whole platform).

Python port of Team P6/P7's engine (legacy/p06-p07-waypoint/source/src/ai_engine.js) with the P01-P03 privacy
guard (legacy/p01-p03-ipp/src/faq.js detectPii). It answers ONLY with approved entries and never writes policy:
- personal information in the question (email, phone, IDs, "my name is") -> refused, nothing stored;
- a question about another named student -> the privacy answer (FAQ-10), no data shown;
- a policy topic no approved entry covers (pay, GPA, visas, ...) -> handed to the coordinator;
- best match below 0.45, or fewer than two shared terms -> handed to the coordinator;
- otherwise the closest approved entry, quoted with its source.
"""
import json
import math
import re
from functools import lru_cache
from pathlib import Path

FAQ_FILE = Path(__file__).resolve().parents[2] / "seed" / "assistant" / "faq.json"
THRESHOLD = 0.45
PRIVACY_FAQ = "FAQ-10"

STOP = set(("a an the i me my mine we our you your it its is are am be been was were do does did doing have has had "
            "to of in on at for from by with about as into than then so if or and but not no can could should would will "
            "shall may might must what which who whom whose when where why how this that these those there here please tell "
            "know want need get got any some there's i'm it's what's").split())
SYN = {
    "recommend": "match", "recommended": "match", "recommendation": "match", "recommendations": "match",
    "suggest": "match", "suggested": "match", "matching": "match", "matches": "match", "fit": "match", "fits": "match",
    "suitable": "match", "good": "match",
    "internship": "placement", "internships": "placement", "coop": "placement", "co-op": "placement", "job": "placement",
    "position": "placement", "opportunity": "placement", "opportunities": "placement", "placements": "placement",
    "role": "placement",
    "approves": "approve", "approved": "approve", "approval": "approve", "confirm": "approve", "confirms": "approve",
    "confirmation": "approve", "authorise": "approve", "authorize": "approve", "official": "approve", "signs": "sign",
    "sign-off": "sign",
    "finish": "complete", "finished": "complete", "completing": "complete", "completed": "complete", "done": "complete",
    "read": "reading", "proof": "evidence", "logbook": "log", "journal": "log", "diary": "log", "weekly": "week",
    "grades": "grade", "graded": "grade", "grading": "grade", "marks": "grade", "assessed": "assess",
    "assessment": "assess", "evaluate": "assess",
    "revise": "revision", "resubmit": "revision", "redo": "revision",
    "classmate": "other", "classmates": "other", "someone": "other", "another": "other",
    "available": "availability", "dates": "availability",
    "disagree": "challenge", "wrong": "challenge", "appeal": "challenge", "dispute": "challenge",
    "gaps": "gap", "missing": "gap", "lack": "gap",
    "course": "module", "lesson": "module", "training": "module", "modules": "module",
    "skills": "skill", "goals": "goal", "outcomes": "outcome", "students": "student",
}
PII_PATTERNS = [
    ("email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("phone number", re.compile(r"(?:\+?\d[\s().-]?){9,}\d")),
    ("ID or long number", re.compile(r"\d{6,}")),
    ("student ID", re.compile(r"\b(?:coop-?[a-z]?\d{2,}|stu-?\d{2,})\b", re.I)),
    ("self-introduction", re.compile(r"\b(?:my name is|my name's|i am called|i'm called|call me|my (?:e-?mail|phone|"
                                     r"mobile|number|address|id|student id|passport|birthday))\b", re.I)),
    ("sensitive identifier", re.compile(r"\b(?:passport|emirates id|national id|ssn|social security|credit card|"
                                        r"date of birth|dob)\b", re.I)),
]


def stem(word: str) -> str:
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokens(text: str) -> list[str]:
    text = re.sub(r"[’']s\b", "", str(text or "").lower())
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return [stem(SYN.get(w, w)) for w in text.split() if w and w not in STOP]


@lru_cache
def seed() -> dict:
    return json.loads(FAQ_FILE.read_text())


def detect_pii(text: str) -> list[str]:
    return [kind for kind, pattern in PII_PATTERNS if pattern.search(text or "")]


def sensitive_term(text: str) -> str | None:
    padded = " " + re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()) + " "
    return next((t for t in seed()["sensitive_terms"] if f" {t} " in padded), None)


def other_person(text: str, students: list[dict], self_id: str | None) -> dict | None:
    lowered = (text or "").lower()
    for s in students:
        if s["student_id"] == self_id:
            continue
        name = s["display_name"].lower()
        first = name.split()[0]
        if name in lowered or f"{first}'s" in lowered or f"{first}’s" in lowered:
            return s
    return None


class Index:
    """IDF index over approved entries (question + phrasings + keywords; answers are quoted, not indexed)."""

    def __init__(self, entries: list[dict]):
        self.entries = entries
        self.docs = []
        for e in entries:
            all_tokens = tokens(" ".join([e["question"], *e.get("alternatives", []), " ".join(e.get("keywords", []))]))
            tf: dict[str, int] = {}
            for t in all_tokens:
                tf[t] = tf.get(t, 0) + 1
            self.docs.append((e, set(all_tokens), tf))
        self.df: dict[str, int] = {}
        for _, toks, _ in self.docs:
            for t in toks:
                self.df[t] = self.df.get(t, 0) + 1

    def idf(self, term: str) -> float:
        # Words no approved entry uses (names, small talk) count at a capped weight.
        return math.log((len(self.docs) + 1) / (self.df[term] + 0.5)) if term in self.df else 1.0

    def rank(self, question: str) -> list[dict]:
        unique = list(dict.fromkeys(tokens(question)))
        total = sum(self.idf(t) for t in unique) or 1.0
        ranked = []
        for e, toks, tf in self.docs:
            hit = [t for t in unique if t in toks]
            ranked.append({"entry": e, "faq_id": e["faq_id"], "matched": hit,
                           "score": sum(self.idf(t) for t in hit) / total,
                           "weight": sum(self.idf(t) * min(tf[t], 4) for t in hit)})
        # Highest score first; near-ties (within 0.05) are broken by how central the shared terms are to
        # each entry (weight), then by ID, as in waypoint's comparator.
        ranked.sort(key=lambda r: (-r["score"], r["faq_id"]))
        out, i = [], 0
        while i < len(ranked):
            group = [ranked[i]]
            while i + len(group) < len(ranked) and abs(ranked[i]["score"] - ranked[i + len(group)]["score"]) <= 0.05:
                group.append(ranked[i + len(group)])
            out.extend(sorted(group, key=lambda r: (-r["weight"], r["faq_id"])))
            i += len(group)
        return out


def answer(question: str, entries: list[dict], students: list[dict], self_id: str | None = None) -> dict:
    """Returns {kind: answer|handoff|refused, guard, entry?, score, matched, ranked, reason}."""
    pii = detect_pii(question)
    if pii:
        return {"kind": "refused", "guard": "pii", "entry": None, "score": 0, "matched": [], "ranked": [],
                "reason": f"The question contains personal information ({', '.join(pii)}). It was not stored."}
    index = Index(entries)
    ranked = index.rank(question)
    best = ranked[0] if ranked else {"score": 0, "matched": [], "faq_id": None, "entry": None}
    top = [{"faq_id": r["faq_id"], "score": round(r["score"], 2)} for r in ranked[:3]]
    person = other_person(question, students, self_id)
    if person:
        entry = next((e for e in entries if e["faq_id"] == PRIVACY_FAQ), None)
        return {"kind": "answer", "guard": "privacy", "entry": entry, "score": 1, "matched": ["other person named"],
                "ranked": top, "reason": f"Asked about another student ({person['student_id']}); privacy answer given, "
                                         "no data shown."}
    term = sensitive_term(question)
    if term:
        return {"kind": "handoff", "guard": "policy", "entry": None, "score": round(best["score"], 2),
                "matched": best["matched"], "ranked": top,
                "reason": f"“{term}” is a policy topic that no approved source covers."}
    if not tokens(question) or best["score"] < THRESHOLD or len(best["matched"]) < 2:
        return {"kind": "handoff", "guard": "confidence", "entry": None, "score": round(best["score"], 2),
                "matched": best["matched"], "ranked": top,
                "reason": f"Best approved match {best['faq_id']} scored {best['score']:.2f} (needs {THRESHOLD} and two "
                          "shared terms)."}
    return {"kind": "answer", "guard": None, "entry": best["entry"], "score": round(best["score"], 2),
            "matched": best["matched"], "ranked": top, "reason": f"Retrieved {best['faq_id']} (score {best['score']:.2f})."}


def candidates(question: str, entries: list[dict], n: int = 4) -> list[dict]:
    """The closest approved entries: the only sources the optional LLM may use."""
    return [r["entry"] for r in Index(entries).rank(question)[:n]]
