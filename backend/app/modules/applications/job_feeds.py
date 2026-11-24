"""Adapters for public feeds. Preserve provider locations and application URLs."""
from datetime import datetime, timezone

FEEDS = [
    ("Canonical", "https://boards-api.greenhouse.io/v1/boards/canonical/jobs?content=true"),
    ("Remotive", "https://remotive.com/api/remote-jobs?limit=100"),
    ("Arbeitnow", "https://www.arbeitnow.com/api/job-board-api?page=1"),
    ("Remote OK", "https://remoteok.com/api"),
    ("Jobicy", "https://jobicy.com/api/jobs?count=200"),
]
PREFIXES = {"Canonical": "CAN", "Remotive": "REM", "Arbeitnow": "ARB", "Remote OK": "ROK", "Jobicy": "JOB"}
HOSTS = {"Remotive": {"remotive.com"},
         "Arbeitnow": {"www.arbeitnow.com", "arbeitnow.com"},
         "Remote OK": {"remoteok.com", "www.remoteok.com"},
         "Jobicy": {"jobicy.com", "www.jobicy.com"}}


def feed_rows(source: str, data) -> list:
    if source == "Remote OK":
        rows = data
    else:
        rows = data["data" if source == "Arbeitnow" else "jobs"]
    if not isinstance(rows, list):
        raise ValueError("Invalid job list")
    return rows


def job_type(values) -> str:
    values = [values] if isinstance(values, str) else values or []
    mapping = {"fulltime": "full_time", "parttime": "part_time",
               "internship": "internship", "intern": "internship",
               "contract": "contract", "freelance": "freelance"}
    for value in values:
        key = str(value).lower().replace("-", "").replace("_", "").replace(" ", "")
        if key in mapping:
            return mapping[key]
    return "unknown"


def adapt(source: str, job: dict) -> dict:
    if source == "Arbeitnow":
        created = job.get("created_at")
        published = datetime.fromtimestamp(int(created), timezone.utc).isoformat() if created else None
        return {**job, "id": job.get("slug"), "candidate_required_location": job.get("location"),
                "publication_date": published, "job_type": job_type(job.get("job_types")),
                "_work_mode": "remote" if job.get("remote") is True else "unknown",
                "category": "Technology"}
    if source == "Remote OK":
        return {**job, "title": job.get("position"), "company_name": job.get("company"),
                "candidate_required_location": job.get("location"), "publication_date": job.get("date"),
                "category": "Technology", "job_type": "unknown", "_work_mode": "remote"}
    if source == "Jobicy":
        return {**job, "title": job.get("jobTitle"), "company_name": job.get("companyName"),
                "description": job.get("jobDescription") or job.get("jobExcerpt"),
                "candidate_required_location": job.get("jobGeo"), "publication_date": job.get("pubDate"),
                "category": ", ".join(job.get("jobIndustry") or []),
                "job_type": job_type(job.get("jobType")), "_work_mode": "remote"}
    return job
