"""Rules-based matching baseline (P05-02). Pure functions, no I/O.

Mandatory condition: the student's availability covers the opportunity dates.
Preferences (scored): sector in interests, required skills held, desirable skills held.
Missing information is reported as unknown, never treated as satisfied.
"""

RULES = {
    "version": "rules-v1",
    "weights": {"interest": 3, "required_skill": 2, "desirable_skill": 1},
}


def is_eligible_listing(opp: dict) -> bool:
    return opp.get("publication_status") == "published" and opp.get("listing_status") == "open"


def match(student: dict, opp: dict, skill_names: dict[str, str], rules: dict = RULES) -> dict:
    w = rules["weights"]
    score = 0
    compatible = True
    reasons, gaps, unknowns = [], [], []

    # Mandatory: availability
    s_start, s_end = student.get("availability_start"), student.get("availability_end")
    o_start, o_end = opp.get("start_date"), opp.get("end_date")
    if None in (s_start, s_end, o_start, o_end):
        unknowns.append("Availability: Needs checking (dates missing)")
    elif s_start <= o_start and s_end >= o_end:
        reasons.append(f"Availability {s_start}..{s_end} covers {o_start}..{o_end}")
    else:
        compatible = False
        reasons.append(f"Mandatory conflict: availability {s_start}..{s_end} does not cover {o_start}..{o_end}")

    # Preference: interests
    interests = student.get("interests") or []
    if not interests:
        unknowns.append("Interests: not provided")
    elif opp.get("sector") in interests:
        score += w["interest"]
        reasons.append(f"Interest '{opp['sector']}' matches opportunity sector")

    # Preference: skills
    held = {s["skill_id"]: s["evidence_status"] for s in student.get("skills") or []}

    def label(skill_id: str) -> str:
        name = skill_names.get(skill_id, skill_id)
        status = held.get(skill_id)
        return f"{name} ({skill_id}, {'reviewed' if status == 'reviewed' else 'self-declared'})"

    for skill_id in opp.get("required_skills") or []:
        if skill_id in held:
            score += w["required_skill"]
            reasons.append(f"Has required skill {label(skill_id)}")
        else:
            gaps.append(f"Missing required skill {skill_names.get(skill_id, skill_id)} ({skill_id})")
    for skill_id in opp.get("desirable_skills") or []:
        if skill_id in held:
            score += w["desirable_skill"]
            reasons.append(f"Has desirable skill {label(skill_id)}")

    return {
        "student_id": student["student_id"],
        "profile_version": student["profile_version"],
        "opportunity_id": opp["opportunity_id"],
        "opportunity_version": opp["version"],
        "method_version": rules["version"],
        "score": score,
        "compatible": compatible,
        "reasons": reasons,
        "gaps": gaps,
        "unknowns": unknowns,
    }


def recommend(student: dict, opportunities: list[dict], skill_names: dict[str, str],
              rules: dict = RULES) -> list[dict]:
    results = [match(student, o, skill_names, rules) for o in opportunities if is_eligible_listing(o)]
    # Compatible first, then highest score, then id for a stable order.
    return sorted(results, key=lambda r: (not r["compatible"], -r["score"], r["opportunity_id"]))
