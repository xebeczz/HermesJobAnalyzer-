# Hermes Job Analyzer

**Find opportunities. Verify the evidence. Understand your fit. Never miss a deadline.**

A full-stack MVP for the SerpApi India Hackathon 2026. It combines live Google Jobs discovery (when a SerpApi key is configured), explainable profile matching, field-level evidence checks, persistent application tracking, deadline reminders, and a deterministic digest.

> **Honest scope note:** This is a competition-ready MVP foundation, not a security-audited production service. The implementation includes working core flows and clearly documents limitations. It does not claim an employer or job is legitimate merely because it appears on Google Jobs. Demo records are explicitly marked as demo data.

## Features

- React + TypeScript + Vite responsive dark dashboard.
- FastAPI REST API with Swagger docs at `/docs`.
- Registration, login, JWT authentication, hashed passwords, protected endpoints.
- Persistent SQLAlchemy database; SQLite by default for easiest local setup, PostgreSQL supported through `DATABASE_URL`.
- Career profile editing.
- SerpApi `google_jobs` search through the backend only; API key never sent to the browser.
- Job normalization, canonical URL/source ID deduplication, search history metadata, deterministic matching.
- Opportunity evidence view with explicit unknown/missing/not-checked states and cautious URL checks.
- Saved jobs and application tracker with private notes/statuses/deadlines.
- Dashboard metrics, deadline center, deterministic digest, JSON export.
- Seeded demo mode when no SerpApi key is configured.
- Backend tests for matching, normalization, and API basics.

## Requirements

- Python 3.11+
- Node.js 20+ and npm
- A SerpApi account/API key for live job search (optional for demo mode)
- PostgreSQL optional; SQLite is the default

## Quick start (Windows PowerShell)

1. Extract the ZIP and open a terminal in the `HermesJobAnalyzer` folder.
2. Backend:

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

3. In a second terminal, frontend:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

4. Open the URL printed by Vite (normally `http://localhost:5173`). Backend docs: `http://localhost:8000/docs`.

### macOS/Linux

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Configure live SerpApi search

1. Create an account at https://serpapi.com/ and copy your API key from your dashboard.
2. Put it only in `backend/.env` as `SERPAPI_API_KEY=your_real_key_here`.
3. Restart the backend. The UI will report whether live search is configured.
4. Search requests are sent to Hermes (`POST /api/search`); only the backend contacts SerpApi.

Never commit `.env` or paste the key into frontend variables. Vite variables are public in browser bundles. The `.env.example` contains placeholders only.

## Demo mode

Without a key, search returns a small set of clearly marked synthetic demonstration opportunities. They are not real job leads. Use this mode to explore the workflow at a hackathon venue with unreliable internet or before configuring SerpApi.

## Environment variables

See `backend/.env.example`. The backend loads this file automatically from its working directory. Important values:

- `DATABASE_URL`: defaults to local SQLite (`sqlite:///./hermes.db`). PostgreSQL example: `postgresql+psycopg://hermes:password@localhost:5432/hermes`.
- `SECRET_KEY`: change to a long random secret outside local demos.
- `SERPAPI_API_KEY`: optional for demo, required for live search.
- `CORS_ORIGINS`: comma-separated frontend origins.
- `DEMO_MODE`: demo fallback flag.

## Tests

```bash
cd backend
pytest -q
```
Tests use synthetic/mocked data and do not consume SerpApi credits.

## API overview

- `POST /api/auth/register`, `/api/auth/login`; `GET /api/auth/me`
- `GET/PUT /api/profile`
- `POST /api/search`, `GET /api/search/history`
- `GET /api/opportunities`, `GET /api/opportunities/{id}`, `POST/DELETE /api/opportunities/{id}/save`
- `GET/POST/PATCH/DELETE /api/applications`
- `GET /api/dashboard`, `GET /api/reminders`, `GET /api/digests/latest`
- `GET /api/verification/summary`, `POST /api/opportunities/{id}/verify`
- `GET /api/export`, `DELETE /api/account`

FastAPI's `/docs` is the interactive API reference. Responses use standard HTTP status codes and Pydantic validation.

## Architecture

```text
frontend (React / TypeScript)
        | JSON REST requests + Bearer token
        v
backend/app/main.py (FastAPI routing + validation)
        | SQLAlchemy ORM
        v
SQLite local DB / PostgreSQL configured DB
        |
        +-- matching service (deterministic score and reasons)
        +-- normalization + deduplication
        +-- verification checks (cautious, field-level)
        +-- digest/deadline calculations
        +-- SerpApi client (server-side only)
```

The MVP keeps business rules in backend helpers, not duplicated in the UI. The frontend is a presentation layer that consumes API responses. The initial implementation uses a compact module layout to make the first setup approachable; it can be split into the fuller module structure in `docs/ARCHITECTURE.md` as the project grows.

## Important limitations (be transparent in the competition)

- Google Jobs results do not always include deadlines, salaries, direct application URLs, or stable IDs. Unknown fields remain unknown.
- The verification endpoint performs conservative syntactic and DNS/IP safety checks; it does **not** prove that an employer or listing is genuine. It intentionally avoids unrestricted server-side page fetching to reduce SSRF risk.
- The MVP includes in-app deadline calculations but not a continuously running scheduler, email delivery, password reset, resume upload/parsing, or full audit-log UI.
- JWT bearer tokens are stored in browser local storage for this local demo, which is simpler but weaker than production-grade HttpOnly cookie sessions. Do not use this configuration as-is for sensitive production data.
- Rate limiting, CSRF hardening, managed secrets, migrations, observability, and deployment hardening should be added before a public production launch.
- Demo data is synthetic and visually labelled. Never cite it as real market data.

## Three-minute demo script

1. **0:00–0:25 — Problem and dashboard:** Explain that job discovery, trust, fit, and deadlines are fragmented. Show live/demo mode label and the real dashboard metrics.
2. **0:25–0:55 — Search:** Search “Python developer internship” and show the source label. Explain that the frontend calls Hermes and the backend calls SerpApi only when configured.
3. **0:55–1:25 — Explainable fit:** Open a job, inspect matched/missing skills and why the score was assigned. Stress that a score is compatibility, not hiring probability.
4. **1:25–1:55 — Evidence & Trust:** Show supported, missing, and not-checked fields. Explain why unknown deadlines are never fabricated and Google Jobs is not an employer verification service.
5. **1:55–2:30 — Application pipeline:** Save a role, add an application, set a user-entered follow-up/deadline, and change its status.
6. **2:30–3:00 — Digest and differentiation:** Show deadline summary and deterministic digest. Close with evidence-based trust, freshness awareness, explainable matching, and persistent workflow.

## Competition and AI-use disclosure

This codebase was generated with AI assistance from the requirements supplied by the project owner. Review, test, understand, and adapt it before submission. Follow the competition's current AI-use disclosure and originality rules. Do not claim code, research, verification, or live API results that you have not personally checked.
