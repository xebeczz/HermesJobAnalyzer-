# User guide: what happens inside Hermes

## 1. Create an account

Registration sends your email, display name, and password to FastAPI. The backend hashes the password using Argon2 via `pwdlib`; it does not store plaintext passwords. Login returns a signed access token. The browser sends the token to protected endpoints. The current MVP stores this token in local storage for demo convenience; this is not the recommended production session pattern.

## 2. Complete your profile

Your education, skills, target roles, locations, and remote preference are stored in `profiles`. Update the profile from **Career profile**. Matching is calculated by the backend when search results are returned and uses the saved profile.

## 3. Search for opportunities

The frontend posts the query to `/api/search`. With `SERPAPI_API_KEY` configured, FastAPI calls SerpApi Google Jobs and normalizes the results. Without a key, the app uses synthetic demo records if `DEMO_MODE=true`. The response clearly says whether results are demo or live. Demo jobs are not real vacancies.

## 4. Understand match results

Hermes compares detected skills with the skills listed in your profile, checks role title relevance, and considers location/remote preferences. It displays a category, numeric score, matching skills, missing skills, and reasons. The score is a heuristic, not a probability of getting hired. Keyword extraction can miss synonyms and context.

## 5. Review evidence

Open a job and inspect **Evidence & Trust**. Missing deadline means unknown, not “no deadline.” The URL check is deliberately limited to syntax and public-DNS safety checks. It does not fetch page content, bypass anti-bot controls, or certify an employer. Visit official company career pages yourself before submitting sensitive information.

## 6. Save and track

Saving creates a user-owned application record. Change its status, add notes, or record a user-entered deadline/follow-up/interview date. The tracker belongs to the signed-in account; the backend scopes read and update queries by user ID.

## 7. Dashboard, reminders, digest, analytics

Dashboard metrics are derived from the stored opportunity/application records. The reminder endpoint only includes dates explicitly provided by a source or entered by the user. The digest ranks stored opportunities deterministically against your profile. Analytics count tracker records and do not claim hiring success rates.

## 8. Export and deletion

Use **Export JSON** to download the profile and application history. The account-delete endpoint removes the user, profile, applications, and search history according to database relationships. The shared opportunity catalogue remains. In this MVP, account deletion is available via the API and not yet surfaced as a confirmation UI.
