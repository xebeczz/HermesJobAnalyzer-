# Competition readiness checklist

- [ ] Confirm the competition's current rules for AI-generated code and include required disclosure.
- [ ] Run the full setup from a fresh extraction on the presentation machine.
- [ ] Configure your own SerpApi key privately in `backend/.env`.
- [ ] Run backend tests with `pytest -q`.
- [ ] Run frontend production build with `npm run build`.
- [ ] Test registration, logout/login, profile persistence, search, save, tracker, evidence, digest, and export.
- [ ] Verify that live search labels differ from demo mode.
- [ ] Do not call a listing “verified” unless the relevant check actually ran and evidence is stored.
- [ ] Capture genuine screenshots of the working app; do not use demo data as market evidence.
- [ ] Document limitations and what you personally implemented/reviewed.
- [ ] Do not commit `.env`, credentials, personal user data, or real resumes.
