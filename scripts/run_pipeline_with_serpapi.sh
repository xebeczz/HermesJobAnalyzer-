#!/bin/bash
# Daily pipeline with live SerpApi data (SerpApi India Hackathon 2026 entry).
#
# Step 1: pull fresh internship/job leads from SerpApi Google Jobs
#         (skipped gracefully when SERPAPI_API_KEY is not set).
# Step 2: run the deterministic digest over the merged opportunity DB.
#
# The digest script itself is untouched: SerpApi records land in the same
# opportunity DB with source="serpapi" and status="needs-verification",
# so they appear in the digest marked for verification and never in the
# ranked Top 5 until the verification pass clears them.
set -u
cd "$(dirname "$0")"

echo "=== [1/2] SerpApi live fetch ==="
if [ -z "${SERPAPI_API_KEY:-}" ]; then
  echo "SERPAPI_API_KEY not set — skipping live fetch (free signup at serpapi.com)."
else
  python3 serpapi_jobs_fetcher.py --import
fi

echo "=== [2/2] Deterministic digest ==="
python3 job_digest.py
