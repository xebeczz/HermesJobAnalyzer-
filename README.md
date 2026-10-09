# Internship & Job Opportunity Analyzer

> **SerpApi India Hackathon 2026 entry — Track: Knowledge & Public Interest**
> An analyzer that finds internships and entry-level developer jobs for students
> in India, matches them against the student's profile, tracks deadlines and
> duplicates, and delivers a deterministic ranked daily digest.

## What it does

```
Live job leads (SerpApi Google Jobs)
  → normalize + dedupe → opportunity database
  → profile matching (Strong / Moderate / Partial / Low)
  → verification pass ("verify before applying")
  → deterministic daily digest: ranked Top 5, why-apply reasons,
    verification notes, deadline watch
```

The digest format is fixed and deterministic — the same database always
produces the same report. No LLM is required to run the pipeline.

## SerpApi usage (meaningful use)

Live data enters through `scripts/serpapi_jobs_fetcher.py`, which queries
SerpApi's **`google_jobs`** engine with targeted queries
(`AI intern India`, `machine learning intern India`, `data science intern
India`, …):

- Every result is normalized into the opportunity database and tagged
  `source="serpapi"`.
- Every SerpApi record is stored with `status="needs-verification"`, so it
  appears in the digest **marked for verification** and can never reach the
  ranked Top 5 until the verification pass clears it.
- Dedupe is on company + role + application URL — re-runs import zero
  duplicates.
- The API key comes from the `SERPAPI_API_KEY` environment variable; it is
  never written into code, docs, or git.

Without SerpApi the pipeline has no live inlet — search data is what makes
the digest fresh every day.

## Setup (stdlib only — no `pip install`)

Requirements: Python 3.10+.

```bash
git clone https://github.com/xebeczz/HermesJobAnalyzer-.git
cd HermesJobAnalyzer-

# free signup at https://serpapi.com (250 search credits/month for building)
export SERPAPI_API_KEY="f03d798be95d8c75378051f2d67ffc97d6d43a9ed30a2e4095d7e710c018681d"
```

## Usage

```bash
# 1. Preview what SerpApi returns (no DB changes, no credits wasted on imports)
python3 scripts/serpapi_jobs_fetcher.py --dry-run

# 2. Import fresh leads as needs-verification
python3 scripts/serpapi_jobs_fetcher.py --import

# 3. Full pipeline: live fetch, then the deterministic digest
./scripts/run_pipeline_with_serpapi.sh

# 4. Digest on its own (works with or without fresh SerpApi data)
python3 scripts/job_digest.py

# 5. Inspect the opportunity DB
python3 scripts/opportunity_store.py list
python3 scripts/opportunity_store.py deadlines --within-days 14
```

## Project structure

```
├── config/
│   ├── profile.yaml            # student profile — the matching source of truth
│   ├── analyzer.yaml           # digest time, timezone, keywords, thresholds
│   └── company_watchlist.yaml  # 15 product companies with official careers URLs
├── scripts/
│   ├── serpapi_jobs_fetcher.py     # ★ SerpApi Google Jobs inlet (stdlib only)
│   ├── run_pipeline_with_serpapi.sh# fetch → digest, one command
│   ├── opportunity_store.py        # opportunity DB: add/list/get/deadlines
│   ├── job_digest.py               # deterministic 24h digest builder
│   ├── job_deadline_watch.py       # deadline watch (silent unless urgent)
│   └── telegram_send.py            # Telegram delivery (optional)
├── .hermes/skills/internship-job-analyzer/SKILL.md  # analyzer operating spec
└── README.md
```

`data/` (the live opportunity DB) and `reports/` (archived digests) are
git-ignored — they are generated at runtime.

## Disclosure

- **Existing project, extended for the hackathon.** The analyzer (profile
  matching, digest, deadline watch) was built in October 2026; the SerpApi
  Google Jobs integration was added as the live-data inlet for this entry.
- **AI tools used:** built with Muse (Meta's personal AI agent), which also
  wrote the fetcher, the pipeline script, and this README.
- **Track:** Knowledge & Public Interest — "use Google Jobs results to help
  people find their first developer role."
