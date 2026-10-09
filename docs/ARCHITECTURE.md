# Architecture and database notes

## Runtime flow

1. The React app sends JSON requests to the FastAPI base URL configured by `VITE_API_BASE_URL`.
2. Registration/login returns a signed access token. Protected requests send it as `Authorization: Bearer ...`.
3. FastAPI validates request bodies with Pydantic, identifies the user, and uses SQLAlchemy for persistence.
4. Search calls SerpApi's `google_jobs` engine from the server. It maps only fields available in the response and treats deadlines as unknown unless provided.
5. A normalization helper standardizes text and URLs. Deduplication prefers source job IDs, then URLs, then exact title/company/location comparison. Empty later fields do not erase existing values.
6. Matching is deterministic. Skills, role, location, and remote preference contribute to a documented score; the response includes reasons and missing skills.
7. Application rows are always scoped by authenticated user ID. Opportunity records are a shared catalogue; private notes and status belong to a user's application row.
8. Evidence fields report source metadata and missing values. URL verification intentionally avoids fetching arbitrary URLs and is not a legitimacy certification.

## Entities

- `users`: email, display name, password hash, creation time.
- `profiles`: one-to-one user preferences, skills, roles, location, and education.
- `opportunities`: normalized shared opportunity catalogue, source metadata, source IDs, lifecycle timestamps, raw source data.
- `applications`: user-owned tracker record referencing an opportunity, status, notes, user-entered dates and contacts.
- `search_runs`: user-owned query history and result count/mode.

Foreign keys and ORM cascades remove a user's profile/application/search history when the account is deleted. Shared opportunity catalogue records remain because they may have been discovered by other accounts; user-specific notes are deleted with the application row.

## Match score (0–100)

- Skill overlap: up to 50 points. `matched skills / detected skills`.
- Role relevance: 25 points when aligned (6.25 when not aligned/unknown).
- Location preference: 12 points when compatible (4.2 when not compatible/unknown).
- Remote preference: 8 points when compatible (3.2 otherwise).
- Profile education presence: up to 5 points.

Categories: Strong >=75; Moderate >=55; Partial >=35; Low below 35. This is a compatibility heuristic, not a hiring probability. The skill detector is a transparent keyword list, not semantic parsing. Missing data limits confidence and should be improved in future versions.

## Evidence states

- `supported`: source explicitly supplied the field.
- `missing_information`: source did not provide the field.
- `partially_checked`: a basic check was performed, but identity/content is not confirmed.
- `potentially_stale`: last observed beyond the configured conceptual freshness window.
- `not_checked` / `unsupported_or_invalid`: check could not safely establish a result.

No single blanket verified badge is used. A URL's presence or public DNS resolution does not establish that the job exists or that the employer is genuine.

## SerpApi mapping

Request parameters used: `engine=google_jobs`, `q`, `location`, `api_key`, `hl`, `gl`, `start`. Parsed fields include `jobs_results`, `job_id`, `title`, `company_name`, `location`, `description`, `detected_extensions`, `apply_options`, `share_link`, and `related_links`. API responses vary; missing fields are handled. A deadline is not inferred from a posting date. Consult current SerpApi docs before relying on fields in a future release.

## Planned production modules

As the project grows, split the compact MVP into `api/routes`, `services/serpapi_client.py`, `services/matching_engine.py`, `services/verification_engine.py`, `repositories`, `schemas`, and `workers`. Add Alembic migrations, persistent caching, server-side rate limiting, scheduler/idempotent reminder jobs, notification delivery, HttpOnly cookie sessions, audit events, observability, and a security review before public deployment.
