"""Public discovery feed. External applications stay on the provider's website."""
import hashlib
from html import unescape
import json
import logging
import re
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx

from app import db
from app.modules.applications.job_feeds import FEEDS, HOSTS, PREFIXES, adapt, feed_rows

FEED_URL = "https://remotive.com/api/remote-jobs?limit=100"
CACHE_SECONDS = 6 * 60 * 60
_locks = {source: threading.Lock() for source, _ in FEEDS}
log = logging.getLogger(__name__)
TOPICS = re.compile(r"\b(ai|ml|machine learning|data|python|research|software|nlp|vision|cloud|engineer|analyst)\b", re.I)
SENIOR = re.compile(r"\b(senior|sr\.?|principal|staff|lead|director|head|manager)\b", re.I)


def plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", unescape(value)))).strip()


def safe_link(value: str, source: str = "Remotive") -> bool:
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if source == "Canonical":
        return parsed.scheme == "https" and host == "job-boards.greenhouse.io" and parsed.path.startswith("/canonical/jobs/")
    return parsed.scheme == "https" and host in HOSTS.get(source, set())


def normalize(job: dict, source: str = "Remotive") -> dict | None:
    title, company, url = (str(job.get(key) or "").strip() for key in ("title", "company_name", "url"))
    tags = [str(tag) for tag in job.get("tags") or []]
    if not title or not company or not safe_link(url, source) or not job.get("id"):
        return None
    if not TOPICS.search(" ".join([title, *tags])) or SENIOR.search(title):
        return None
    if source == "Canonical" and not re.search(r"\b(graduate|junior|intern)\b", title, re.I):
        return None
    description = plain_text(str(job.get("description") or ""))
    kind = {"full_time": "full-time", "part_time": "part-time", "internship": "internship",
            "contract": "contract", "freelance": "freelance"}.get(job.get("job_type"), "unknown")
    skills = {"SK-PY": r"\bpython\b", "SK-SQL": r"\bsql\b", "SK-EXCEL": r"\bexcel\b"}
    mentions = [skill for skill, pattern in skills.items() if re.search(pattern, description, re.I)]
    return {
        "opportunity_id": f"{PREFIXES[source]}-{job['id']}", "version": 1,
        "employer_name": company, "title": title,
        "sector": str(job.get("category") or "Technology"),
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
    with _locks[source]:
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM external_job_cache WHERE cache_key = ?", (source,)).fetchone()
        current = datetime.now(timezone.utc)
        checked = datetime.fromisoformat(row["checked_at"]) if row else None
        if row and (current - checked).total_seconds() < CACHE_SECONDS:
            return json.loads(row["payload"])
        previous = json.loads(row["payload"]) if row else None
        try:
            response = httpx.get(feed_url, timeout=12, follow_redirects=True,
                                 headers={"User-Agent": "Coop-Career-Discovery/1.0"})
            response.raise_for_status()
            jobs = feed_rows(source, response.json())
            normalized = {}
            for job in jobs:
                if not isinstance(job, dict):
                    continue
                try:
                    job = adapt(source, job)
                except (ValueError, TypeError, OverflowError, OSError):
                    continue
                if source == "Canonical":
                    location = str((job.get("location") or {}).get("name") or "")
                    job = {**job, "company_name": "Canonical", "url": job.get("absolute_url"),
                           "candidate_required_location": location,
                           "description": unescape(str(job.get("content") or "")),
                           "category": "Software engineering",
                           "_work_mode": "remote" if re.search("home based", location, re.I) else "unknown",
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
        return payload


def catalogue() -> dict:
    with ThreadPoolExecutor(max_workers=len(FEEDS)) as executor:
        feeds = list(executor.map(lambda feed: provider_catalogue(*feed), FEEDS))
    dates = [feed["fetched_at"] for feed in feeds if feed.get("fetched_at")]
    return {
        "jobs": [job for feed in feeds for job in feed["jobs"]],
        "source": " + ".join(source for source, _ in FEEDS),
        "status": "current" if all(feed["status"] == "current" for feed in feeds) else "stale" if dates else "unavailable",
        "fetched_at": min(dates) if dates else None,
        "sources": [{**{key: feed.get(key) for key in ("source", "status", "fetched_at")},
                     "job_count": len(feed["jobs"])} for feed in feeds],
    }
