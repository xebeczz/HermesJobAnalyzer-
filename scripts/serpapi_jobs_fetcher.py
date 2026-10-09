#!/usr/bin/env python3
"""SerpApi Google Jobs fetcher for the Internship & Job Opportunity Analyzer.

Draft prepared 2026-10-08 as the "meaningful SerpApi use" leg of the
SerpApi India Hackathon 2026 entry. Stdlib only. No secrets in code or
files: the API key comes from the SERPAPI_API_KEY environment variable.

Usage:
    SERPAPI_API_KEY=... python3 serpapi_jobs_fetcher.py --dry-run
    SERPAPI_API_KEY=... python3 serpapi_jobs_fetcher.py --import   # adds as needs-verification
    SERPAPI_API_KEY=... python3 serpapi_jobs_fetcher.py --import --queries "AI intern" "data science intern"

Every imported record is marked source="serpapi" and status="needs-verification",
so nothing reaches the ranked Top 5 digest before the verification pass.
The digest script itself stays deterministic and stdlib-only; this fetcher is
the live-data inlet for it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from opportunity_store import (  # noqa: E402
    dedupe_key,
    load_db,
    save_db,
    slugify,
)

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
ENGINE = "google_jobs"
DEFAULT_QUERIES = [
    "AI intern India",
    "machine learning intern India",
    "data science intern India",
    "software engineer intern India",
    "python developer intern India",
]
DEFAULT_LOCATION = "India"


def serpapi_search(api_key: str, query: str, location: str) -> dict:
    """One SerpApi google_jobs search. Raises on HTTP/API error."""
    params = {
        "engine": ENGINE,
        "q": query,
        "location": location,
        "api_key": api_key,
    }
    url = SERPAPI_ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "HermesJobAnalyzer/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if "error" in payload:
        raise RuntimeError(f"SerpApi error: {payload['error']}")
    return payload


def _as_dict(value) -> dict:
    """SerpApi fields like `extensions` may be a list in live responses."""
    return value if isinstance(value, dict) else {}


def normalize_job(job: dict, fetched_on: str) -> dict:
    """Convert one SerpApi google_jobs result into the opportunity DB shape."""
    company = job.get("company_name") or "Unknown"
    title = job.get("title") or "Untitled"
    location = job.get("location") or "India"
    job_id = str(job.get("job_id") or slugify(company, title, fetched_on))
    extensions = _as_dict(job.get("extensions"))
    detected = _as_dict(job.get("detected_extensions"))
    related = job.get("related_links") or [{}]
    first_link = related[0] if isinstance(related, list) and related else {}
    app_url = first_link.get("link", "") if isinstance(first_link, dict) else ""
    record = {
        "id": f"opp-serpapi-{job_id}",
        "dedupe_key": dedupe_key(company, title, app_url),
        "company": company,
        "role": title,
        "opportunity_type": "Internship" if "intern" in title.lower() else "Job",
        "location": location,
        "work_mode": "Not specified",
        "duration": "Not specified",
        "stipend": extensions.get("salary") or "Not specified",
        "salary": "Not specified",
        "eligibility": {
            "academic_year": "Not specified",
            "branch": "Not specified",
            "cgpa": "Not specified",
            "degree": "Not specified",
            "experience": "Not specified",
            "other": "Not specified",
        },
        "skills_required": {"technical": [], "other": ["Not specified"]},
        "responsibilities": "Not specified",
        "deadline": None,
        "application_url": app_url,
        "official_url": "",
        "recruiter_info": job.get("via") or "Not specified",
        "conditions": "Not specified",
        "match": {
            "classification": "Partial match",
            "matching": ["Fetched live from SerpApi Google Jobs; classification pending verification pass."],
            "gaps": ["Eligibility, stipend, deadline, official posting all need verification."],
        },
        "verification": {
            "status": "needs-verification",
            "notes": "Third-party aggregation (SerpApi Google Jobs). Verify the live opening on the official page before applying.",
        },
        "source": "serpapi",
        "fetched_on": fetched_on,
        "status": "needs-verification",
        "serpapi_raw": {
            "job_id": job.get("job_id"),
            "posted_at": detected.get("posted_at") or extensions.get("posted"),
            "schedule_type": detected.get("schedule_type"),
            "work_from_home": detected.get("work_from_home"),
            "thumbnail": job.get("thumbnail"),
            "description_snippet": (job.get("description") or "")[:600],
        },
    }
    return record


def run(api_key: str, queries: list[str], location: str, do_import: bool) -> dict:
    fetched_on = date.today().isoformat()
    all_jobs: list[dict] = []
    for query in queries:
        payload = serpapi_search(api_key, query, location)
        jobs = payload.get("jobs_results") or []
        for job in jobs:
            all_jobs.append(normalize_job(job, fetched_on))
        time.sleep(1)  # be gentle with the API

    result = {"queries": queries, "fetched": len(all_jobs), "imported": 0, "skipped_duplicates": 0}
    if not do_import:
        result["preview"] = [
            {"id": j["id"], "company": j["company"], "role": j["role"], "location": j["location"]}
            for j in all_jobs[:20]
        ]
        return result

    db = load_db()
    opps = db.setdefault("opportunities", [])
    existing_keys = {o.get("dedupe_key") for o in opps}
    for job in all_jobs:
        if job["dedupe_key"] in existing_keys:
            result["skipped_duplicates"] += 1
            continue
        opps.append(job)
        existing_keys.add(job["dedupe_key"])
        result["imported"] += 1
    save_db(db)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch live internship/job leads via SerpApi Google Jobs.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="fetch and print a preview only")
    mode.add_argument("--import", dest="do_import", action="store_true", help="fetch and add to the DB")
    ap.add_argument("--queries", nargs="*", default=DEFAULT_QUERIES, help="search queries")
    ap.add_argument("--location", default=DEFAULT_LOCATION, help="Google Jobs location")
    args = ap.parse_args(argv)

    api_key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: set the SERPAPI_API_KEY environment variable (free signup at serpapi.com).", file=sys.stderr)
        return 2
    try:
        result = run(api_key, args.queries, args.location, args.do_import)
    except Exception as exc:  # network/API failure: report, never crash the pipeline
        print(f"ERROR: SerpApi fetch failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
