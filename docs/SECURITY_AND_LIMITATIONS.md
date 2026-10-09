# Security, privacy, and limitations

## Included safeguards

- Argon2 password hashing.
- Signed JWT tokens with expiration.
- Protected endpoints and per-user ownership filters for application records.
- Pydantic input validation and SQLAlchemy ORM queries.
- CORS origin allowlist configuration.
- API key only read on the backend from environment configuration.
- HTTP timeouts for SerpApi; no automatic redirects in the SerpApi request.
- Conservative verification that does not fetch user-controlled destination URLs.
- Export and account deletion endpoints.

## Not yet production-grade

- JWT is held in local storage; use secure HttpOnly/SameSite cookies or a mature session design for production.
- Add rate limiting to auth, search, and verification routes; configure proxy-aware limits and abuse monitoring.
- Add Alembic migrations rather than relying on `create_all`.
- Add robust DNS rebinding protections and isolated egress controls if page fetching is ever introduced.
- Add structured request IDs, centralized error logging, security headers, dependency scanning, backups, retention policy, and penetration testing.
- Add CSRF defenses if cookie authentication is introduced.
- Add email verification/password reset only when delivery is configured and tested.
- Resume upload/parsing and external email reminders are not implemented.
- Digest currently calculates when requested; it is not a scheduled background task.
- `SearchRun` stores query metadata; no persistent API response cache is implemented yet despite the cache setting reserved in the environment examples/specification.
- Opportunity fields are shared catalogue data. Keep user-specific notes and statuses only in the application table.

## Privacy principles

Collect only information needed for career matching. Do not upload resumes in this MVP. Do not place API keys in frontend variables. Do not claim a listing is legitimate based only on its presence in a search provider. Before public deployment, publish a privacy policy explaining retention, deletion, and third-party data flows.
