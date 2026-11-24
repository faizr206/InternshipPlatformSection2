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
import math
import re
from collections import Counter
from pathlib import Path

AI_METHOD_VERSION = "ai-termmatch-v1"

_ALIASES_FILE = Path(__file__).resolve().parents[2] / "seed" / "fixtures" / "skill_aliases.json"
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


# ---------------------------------------------------------------------------
# AI recommendation insights (P05-04 extension, Sprint 2): ai-insights-v1
#
# Same bounds as term matching: offline, deterministic, labelled. Insights are
# computed beside the stored rules result and never change eligibility, score,
# gaps, unknowns or the rules ordering. Every statement is built from the
# student's own profile and the listing; nothing is invented.
# ---------------------------------------------------------------------------
INSIGHTS_VERSION = "ai-insights-v1"

_STOPWORDS = frozenset(
    "a an and are as at be by for from in into is it of on or our the their this to with will "
    "you your we day work support using use e g eg".split()
)


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z]+", text.lower())
    # Light stemming: drop a plural "s" so "dashboards" ~ "dashboard".
    return [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
            for w in words if w not in _STOPWORDS and len(w) > 1]


def _student_text(student: dict, skill_names: dict[str, str], aliases: dict[str, list[str]]) -> str:
    parts = list(student.get("interests") or [])
    for s in student.get("skills") or []:
        parts.append(skill_names.get(s["skill_id"], s["skill_id"]))
        parts.extend(aliases.get(s["skill_id"], []))
    return " ".join(parts)


def _opportunity_text(opp: dict, skill_names: dict[str, str], aliases: dict[str, list[str]]) -> str:
    parts = [str(opp.get(f) or "") for f in ("title", "description", "sector")]
    for sid in (opp.get("required_skills") or []) + (opp.get("desirable_skills") or []):
        parts.append(skill_names.get(sid, sid))
        parts.extend(aliases.get(sid, []))
    return " ".join(parts)


def relevance_scores(student: dict, opportunities: list[dict], skill_names: dict[str, str],
                     aliases: dict[str, list[str]] = ALIASES) -> dict[str, dict]:
    """TF-IDF cosine similarity (0-100) between the profile and each listing's text.

    Returns {opportunity_id: {"relevance": int, "top_terms": [...]}}; top_terms are
    the shared terms that contributed most, so the number is explainable.
    """
    docs = {o["opportunity_id"]: Counter(_tokens(_opportunity_text(o, skill_names, aliases)))
            for o in opportunities}
    query = Counter(_tokens(_student_text(student, skill_names, aliases)))
    n = len(docs) + 1
    df = Counter()
    for tf in list(docs.values()) + [query]:
        df.update(tf.keys())
    idf = {t: math.log((1 + n) / (1 + df[t])) + 1 for t in df}

    def vec(tf: Counter) -> dict[str, float]:
        return {t: c * idf[t] for t, c in tf.items()}

    qv = vec(query)
    qn = math.sqrt(sum(v * v for v in qv.values())) or 1.0
    out = {}
    for oid, tf in docs.items():
        dv = vec(tf)
        dn = math.sqrt(sum(v * v for v in dv.values())) or 1.0
        contrib = {t: qv[t] * dv[t] for t in qv.keys() & dv.keys()}
        cosine = sum(contrib.values()) / (qn * dn)
        top = [t for t, _ in sorted(contrib.items(), key=lambda kv: (-kv[1], kv[0]))[:4]]
        out[oid] = {"relevance": round(100 * cosine), "top_terms": top}
    return out


def gap_coach(student: dict, opp: dict, opportunities: list[dict], skill_names: dict[str, str],
              weights: dict) -> list[dict]:
    """Next steps that would strengthen this match, ranked by impact.

    Missing required skills: points the rules would add, and how many other open
    listings also require the skill. Self-declared required skills: getting the
    evidence reviewed (no score change; the label becomes verified).
    """
    held = {s["skill_id"]: s["evidence_status"] for s in student.get("skills") or []}
    others = [o for o in opportunities if o["opportunity_id"] != opp["opportunity_id"]]
    tips = []
    for sid in opp.get("required_skills") or []:
        name = skill_names.get(sid, sid)
        if sid not in held:
            unlocks = sorted(o["opportunity_id"] for o in others if sid in (o.get("required_skills") or []))
            tips.append({
                "kind": "learn", "skill_id": sid, "skill_name": name,
                "score_gain": weights["required_skill"], "unlocks": unlocks,
                "tip": f"Add {name} with evidence: +{weights['required_skill']} on this listing"
                       + (f" and it is required by {len(unlocks)} other open listing"
                          f"{'s' if len(unlocks) != 1 else ''}" if unlocks else ""),
            })
        elif held[sid] != "reviewed":
            tips.append({
                "kind": "verify", "skill_id": sid, "skill_name": name, "score_gain": 0, "unlocks": [],
                "tip": f"Get your {name} evidence reviewed so employers see it as verified",
            })
    for sid in opp.get("desirable_skills") or []:
        if sid not in held:
            name = skill_names.get(sid, sid)
            tips.append({
                "kind": "learn", "skill_id": sid, "skill_name": name,
                "score_gain": weights["desirable_skill"], "unlocks": [],
                "tip": f"Optional: {name} is desirable here (+{weights['desirable_skill']})",
            })
    order = {"learn": 0, "verify": 1}
    return sorted(tips, key=lambda t: (-t["score_gain"], order[t["kind"]], -len(t["unlocks"]), t["skill_id"]))


def similar_opportunities(opp: dict, opportunities: list[dict], limit: int = 2) -> list[dict]:
    """Other open listings with the most similar skill set and sector (Jaccard)."""
    def features(o):
        return set(o.get("required_skills") or []) | set(o.get("desirable_skills") or []) | {f"sector:{o.get('sector')}"}

    base = features(opp)
    scored = []
    for o in opportunities:
        if o["opportunity_id"] == opp["opportunity_id"]:
            continue
        f = features(o)
        sim = len(base & f) / len(base | f) if base | f else 0
        if sim > 0:
            scored.append((sim, o))
    scored.sort(key=lambda x: (-x[0], x[1]["opportunity_id"]))
    return [{"opportunity_id": o["opportunity_id"], "title": o["title"],
             "employer_name": o.get("employer_name"), "similarity": round(100 * s)}
            for s, o in scored[:limit]]


def summary(student: dict, opp: dict, result: dict, matches: list[dict], skill_names: dict[str, str]) -> str:
    """A short plain-language explanation of the rules result (it restates, never re-decides)."""
    first = (student.get("display_name") or "This student").split()[0]
    held = {s["skill_id"]: s["evidence_status"] for s in student.get("skills") or []}
    req = opp.get("required_skills") or []
    have = [skill_names.get(s, s) for s in req if s in held]
    lead = {
        "eligible": f"{first} is available for the full {opp['title']} period",
        "unknown": f"{first}'s eligibility for {opp['title']} still needs checking",
        "ineligible": f"{first}'s availability does not cover the {opp['title']} dates, so this is not a fit right now",
    }[result["eligibility"]]
    bits = []
    if opp.get("sector") in (student.get("interests") or []):
        bits.append(f"it matches the interest in {opp['sector']}")
    if req:
        noun = "skill is" if len(have) == 1 else "skills are"
        bits.append(f"{len(have)} of {len(req)} required {noun} on the profile"
                    + (f" ({', '.join(have)})" if have else ""))
    if matches:
        bits.append("the description mentions " + ", ".join(f"“{m['term']}”" for m in matches[:2]))
    text = lead + (" — " + "; ".join(bits) if bits and result["eligibility"] != "ineligible" else "") + "."
    if result["gaps"] and result["eligibility"] != "ineligible":
        text += f" Closing {len(result['gaps'])} skill gap{'s' if len(result['gaps']) > 1 else ''} would strengthen it."
    return text


def insights(student: dict, opp: dict, result: dict, matches: list[dict], opportunities: list[dict],
             skill_names: dict[str, str], weights: dict, relevance: dict) -> dict:
    """All AI insights for one recommendation, as stored with the run."""
    return {
        "version": INSIGHTS_VERSION,
        "relevance": relevance["relevance"],
        "top_terms": relevance["top_terms"],
        "summary": summary(student, opp, result, matches, skill_names),
        "next_steps": gap_coach(student, opp, opportunities, skill_names, weights),
        "similar": similar_opportunities(opp, opportunities),
    }


def statement_draft(student: dict, opp: dict, skill_names: dict[str, str],
                    aliases: dict[str, list[str]] = ALIASES) -> dict:
    """A starter statement the student must review and edit before submitting.

    It only cites skills and interests already on the profile (self-declared skills are
    worded as such) and is never submitted automatically.
    """
    held = {s["skill_id"]: s["evidence_status"] for s in student.get("skills") or []}
    wanted = (opp.get("required_skills") or []) + (opp.get("desirable_skills") or [])
    def plain(sid):  # "Data visualisation (e.g. Tableau)" -> "Data visualisation" in prose
        return re.sub(r"\s*\(.*?\)", "", skill_names.get(sid, sid))

    reviewed = [plain(s) for s in wanted if held.get(s) == "reviewed"]
    declared = [plain(s) for s in wanted if s in held and held[s] != "reviewed"]
    terms = [m["term"] for m in term_matches(student, opp, skill_names, aliases)]

    def join(xs):
        return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]

    sentences = []
    sector = opp.get("sector")
    if sector in (student.get("interests") or []):
        sentences.append(f"I am applying for the {opp['title']} role at {opp['employer_name']} because "
                         f"{sector} is one of my main interests.")
    else:
        sentences.append(f"I am applying for the {opp['title']} role at {opp['employer_name']}.")
    if reviewed:
        sentences.append(f"I bring reviewed evidence in {join(reviewed)}"
                         + (f", which fits the {join(terms[:2])} work described" if terms else "") + ".")
    if declared:
        sentences.append(f"I have also worked with {join(declared)} and am happy to show examples.")
    if not reviewed and not declared:
        sentences.append("I am keen to build the skills this role needs and learn quickly on the job.")
    return {
        "version": INSIGHTS_VERSION,
        "draft": " ".join(sentences),
        "cited_skills": reviewed + declared,
        "note": "AI starter text — review and edit before submitting. It only cites skills already on your profile.",
    }
