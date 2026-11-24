"""Public discovery feed. External applications stay on the provider's website."""
import hashlib
from html import unescape
import json
import logging
import re
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app import db

FEED_URL = "https://remotive.com/api/remote-jobs?limit=100"
CACHE_SECONDS = 6 * 60 * 60
_lock = threading.Lock()
log = logging.getLogger(__name__)
SENIOR = re.compile(r"\b(senior|sr\.?|principal|staff|lead|director|head|manager)\b", re.I)
ENGINEERING = re.compile(
    r"\b(machine learning|artificial intelligence|deep learning|mlops|llm|nlp|"
    r"computer vision|applied scientist|data scien\w*|data engineer\w*|"
    r"(?:ai|ml)[ /-](?:engineer\w*|research\w*|scientist|developer|safety|systems)|"
    r"research (?:engineer|scientist))\b", re.I
)
BUSINESS = re.compile(r"\b(product|business|strategy|strategic|consult\w*|economics|policy|governance|responsible|analyst)\b", re.I)
AI_CONTEXT = re.compile(r"\b(ai|ml|artificial intelligence|machine learning|llm)\b", re.I)
EARLY_CAREER = re.compile(r"\b(intern(?:ship)?s?|graduate|junior|entry[ -]level|fellows?(?:hip)?s?|resident|residency|university)\b", re.I)


def career_area(title: str, company: str = "") -> str | None:
    """A title must describe AI/data work, not merely carry an AI-related tag."""
    if BUSINESS.search(title) and (AI_CONTEXT.search(title) or (company == "Anthropic" and EARLY_CAREER.search(title))):
        return "AI business & policy"
    if ENGINEERING.search(title) or (EARLY_CAREER.search(title) and AI_CONTEXT.search(title)):
        return "AI engineering & research"
    return None


def plain_text(value: str) -> str:
    value = unescape(value)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def safe_link(value: str, source: str = "Remotive") -> bool:
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if source in ("Canonical", "Anthropic"):
        return parsed.scheme == "https" and host == "job-boards.greenhouse.io" and parsed.path.startswith("/" + source.lower() + "/jobs/")
    return parsed.scheme == "https" and host == "remotive.com"


def normalize(job: dict, source: str = "Remotive") -> dict | None:
    title, company, url = (str(job.get(key) or "").strip() for key in ("title", "company_name", "url"))
    if not title or not company or not safe_link(url, source) or not job.get("id"):
        return None
    area = career_area(title, company)
    if not area or SENIOR.search(title):
        return None
    if source in ("Canonical", "Anthropic") and not EARLY_CAREER.search(title):
        return None
    description = plain_text(str(job.get("description") or ""))
    kind = {"full_time": "full-time", "part_time": "part-time", "internship": "internship",
            "contract": "contract", "freelance": "freelance"}.get(job.get("job_type"), "unknown")
    skills = {"SK-PY": r"\bpython\b", "SK-SQL": r"\bsql\b", "SK-EXCEL": r"\bexcel\b"}
    mentions = [skill for skill, pattern in skills.items() if re.search(pattern, description, re.I)]
    return {
        "opportunity_id": f"{ {'Canonical': 'CAN', 'Anthropic': 'ANT'}.get(source, 'REM') }-{job['id']}", "version": 1,
        "employer_name": company, "title": title,
        "sector": area, "career_area": area,
        "experience_label": "Student / early career" if EARLY_CAREER.search(title) else "Check experience requirements",
        "location": str(job.get("candidate_required_location") or "Location not specified"),
        "country_code": None, "work_mode": job.get("_work_mode", "remote"), "job_type": kind,
        "degree_levels": [], "description": description[:5000],
        "required_skills": [], "desirable_skills": [], "mentioned_skills": mentions,
        "start_date": None, "end_date": None, "publication_status": "published",
        "listing_status": "open", "external": True, "source": source,
        "source_url": url, "published_at": job.get("publication_date"), "salary": str(job.get("salary") or ""),
        "content_hash": hashlib.sha256(description.encode()).hexdigest()[:16],
    }


def provider_catalogue(source: str, feed_url: str) -> dict:
    """At most one refresh per six hours, including failed attempts. Last good data survives outages."""
    with _lock:
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM external_job_cache WHERE cache_key = ?", (source,)).fetchone()
        current = datetime.now(timezone.utc)
        checked = datetime.fromisoformat(row["checked_at"]) if row else None
        if row and (current - checked).total_seconds() < CACHE_SECONDS:
            payload = json.loads(row["payload"])
            return filter_catalogue(payload)
        previous = json.loads(row["payload"]) if row else None
        try:
            response = httpx.get(feed_url, timeout=12, follow_redirects=False)
            response.raise_for_status()
            jobs = response.json()["jobs"]
            if not isinstance(jobs, list):
                raise ValueError("Provider returned an invalid jobs list")
            normalized = {}
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                if source in ("Canonical", "Anthropic"):
                    location = str((job.get("location") or {}).get("name") or "")
                    job = {**job, "company_name": source, "url": job.get("absolute_url"),
                           "candidate_required_location": location,
                           "description": unescape(str(job.get("content") or "")),
                           "category": "Software engineering",
                           "_work_mode": "remote" if re.search("home based|remote", location, re.I) else "unknown",
                           "publication_date": job.get("updated_at")}
                if result := normalize(job, source):
                    normalized[result["opportunity_id"]] = result
            payload = {"jobs": list(normalized.values()), "source": source, "status": "current",
                       "fetched_at": current.isoformat(), "message": None}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            log.warning("%s refresh failed; preserving the last successful catalogue", source)
            payload = {**(previous or {"jobs": [], "source": source, "fetched_at": None}),
                       "status": "stale" if previous and previous.get("fetched_at") else "unavailable",
                       "message": "The live feed is temporarily unavailable. Try again later."}
        with db.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO external_job_cache VALUES (?, ?, ?)",
                         (source, current.isoformat(), json.dumps(payload)))
        return filter_catalogue(payload)


def filter_catalogue(payload: dict) -> dict:
    # Apply today's discovery rules to cached rows without increasing provider requests.
    jobs = []
    for job in payload["jobs"]:
        area = career_area(job["title"], job["employer_name"])
        if area and not SENIOR.search(job["title"]):
            if job.get("source") in ("Canonical", "Anthropic") and not EARLY_CAREER.search(job["title"]):
                continue
            jobs.append({**job, "career_area": area, "sector": area,
                         "experience_label": "Student / early career" if EARLY_CAREER.search(job["title"])
                         else "Check experience requirements"})
    return {**payload, "jobs": jobs}


def catalogue() -> dict:
    feeds = [
        provider_catalogue("Anthropic", "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true"),
        provider_catalogue("Canonical", "https://boards-api.greenhouse.io/v1/boards/canonical/jobs?content=true"),
        provider_catalogue("Remotive", FEED_URL),
    ]
    dates = [feed["fetched_at"] for feed in feeds if feed.get("fetched_at")]
    jobs = [job for feed in feeds for job in feed["jobs"]]
    jobs.sort(key=lambda job: (not EARLY_CAREER.search(job["title"]), job["employer_name"], job["title"]))
    return {
        "jobs": jobs, "source": "Anthropic + Canonical + Remotive",
        "status": "current" if all(feed["status"] == "current" for feed in feeds) else "stale" if dates else "unavailable",
        "fetched_at": min(dates) if dates else None,
        "sources": [{key: feed.get(key) for key in ("source", "status", "fetched_at")} for feed in feeds],
    }
