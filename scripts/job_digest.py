#!/usr/bin/env python3
"""Deterministic 24-hour digest for the Internship & Job Opportunity Analyzer.

Designed for `hermes cron create --no-agent --script job_digest.py
--deliver telegram '0 20 * * *'`: stdout is delivered verbatim to Telegram.

- Always prints a digest (heartbeat variant when nothing is new), so the user
  can tell the automation is alive.
- Never repeats an opportunity unless it is new, changed, deadline-approaching,
  needs verification, or was explicitly requested.
- Stdlib only. No secrets, no network access.

Modes:
    python3 job_digest.py            # full daily digest
    python3 job_digest.py --watch    # deadline watch: silent unless a deadline
                                     # is within 48h and not yet reminded
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from opportunity_store import (  # noqa: E402
    DATA_DIR,
    PROJECT_DIR,
    VALID_STATUSES,
    days_remaining,
    load_db,
    save_db,
)

TZ = ZoneInfo("Asia/Kolkata")
REPORTS_DIR = PROJECT_DIR / "reports"
STATE_FILE = DATA_DIR / "digest_state.json"
WATCH_DAYS = 2
DEADLINE_LIST_DAYS = 14
APPROACHING_DAYS = 7


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_digest_at": None, "last_digest_date": None, "last_deadline_watch_at": None}


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _first_seen_dt(value: object) -> datetime | None:
    """Parse a record's first_seen into a TZ-aware datetime.

    Some older records store a date-only string (e.g. "2026-10-05");
    fromisoformat() returns those as naive, which cannot be compared
    with the aware cutoff. Normalize naive values to Asia/Kolkata.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt


def fmt_deadline(opp: dict, today: date) -> str:
    dl = opp.get("deadline")
    if not dl:
        return "Not specified"
    dr = days_remaining(dl, today)
    if dr is None:
        return dl
    if dr < 0:
        return f"{dl} (passed {-dr}d ago)"
    if dr == 0:
        return f"{dl} (today!)"
    return f"{dl} ({dr} days remaining)"


# ---------------------------------------------------------------------------
# DIGEST FORMAT — USER-SPECIFIED (2026-10-05), DO NOT "IMPROVE" OR REVERT.
# The user pasted this exact report spec and said "this is a new one".
# It intentionally includes a ranked top-5, "best company today", and
# "best opportunity to apply first". A background job reverted this once
# (2026-10-05 night) citing the old "never rank companies" rule — that rule
# was superseded by the user's explicit format spec. If the format needs to
# change, ask the user first; never silently rewrite it.
# ---------------------------------------------------------------------------
MATCH_RANK = {"Strong match": 0, "Moderate match": 1, "Partial match": 2, "Low match": 3}
VERIF_RANK = {"verified": 0, "needs-verification": 1}

# Keywords that mark an opportunity as Data Science / Data Analytics / BI.
DS_PATTERNS = [
    r"\bdata scien\w*\b", r"\bdata analy\w*\b", r"\banalytics\b",
    r"\bbusiness intelligence\b", r"\bmachine learning\b", r"\bdeep learning\b",
    r"\bartificial intelligence\b", r"\bdata engineer\w*\b", r"\bstatistics\b",
    r"\bnlp\b", r"(?<![a-z])ai(?![a-z])", r"\bml\b",
]
DS_PATTERNS = [re.compile(p) for p in DS_PATTERNS]


def ds_relevant(opp: dict) -> bool:
    skills = " ".join(((opp.get("skills_required") or {}).get("technical") or []))
    text = f"{opp.get('role', '')} {skills}".lower()
    return any(p.search(text) for p in DS_PATTERNS)


def valid_url(value: object) -> bool:
    return str(value or "").strip().startswith(("http://", "https://"))


def direct_link(opp: dict) -> str:
    """Direct application link when one exists; official page next; never invented."""
    for key in ("application_url", "official_url"):
        if valid_url(opp.get(key)):
            return str(opp[key]).strip()
    src = opp.get("source_url")
    if valid_url(src):
        return str(src).strip()
    return "Not specified"


def why_apply(opp: dict) -> str:
    """Deterministic 1-2 sentence recommendation reason from stored analysis.

    Never invents: built only from match.classification, match.reason,
    match.unclear, and verification.status.
    """
    match = opp.get("match") or {}
    cls = match.get("classification") or "Not classified"
    reason = (match.get("reason") or "").strip()
    verif = opp.get("verification") or {}
    vstat = (verif.get("status") or "").lower()

    caution = None
    if vstat != "verified":
        caution = "Verify the live opening on the official page before applying."
    elif match.get("unclear"):
        caution = "Unclear before applying: " + ", ".join(match["unclear"][:3]) + "."

    base = f"{cls}: {reason}" if reason else cls
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", base) if s.strip()]
    out = parts[:1]
    if caution:
        out.append(caution)
    else:
        out.extend(parts[1:2])
    return " ".join(out)


def rank_key(opp: dict, now: datetime) -> tuple:
    """Deterministic ranking across the user's published criteria.

    Order: match strength (relevance + fresher fit from the stored analysis),
    then authenticity (verified first), then AI/DS relevance, then recency.
    Company reputation and resume value flow from the stored company/match
    analysis — this sort never invents new facts.
    """
    cls = (opp.get("match") or {}).get("classification", "")
    vstat = ((opp.get("verification") or {}).get("status") or "").lower()
    try:
        age_hours = (now - datetime.fromisoformat(opp.get("first_seen") or "")).total_seconds() / 3600
    except (ValueError, TypeError):
        age_hours = 1e9
    return (MATCH_RANK.get(cls, 4), VERIF_RANK.get(vstat, 2),
            0 if ds_relevant(opp) else 1, age_hours)


def is_internship(opp: dict) -> bool:
    return "intern" in (opp.get("opportunity_type") or "").lower()


def is_job(opp: dict) -> bool:
    t = (opp.get("opportunity_type") or "").lower()
    return "job" in t or "full-time" in t or "full time" in t


def is_verified(opp: dict) -> bool:
    return ((opp.get("verification") or {}).get("status") or "").lower() == "verified"


def no_payment_stated(opp: dict) -> bool:
    text = " ".join([
        str(opp.get("conditions") or ""),
        str((opp.get("verification") or {}).get("notes") or ""),
    ]).lower()
    return "no application fee" in text or "no fee" in text or "no payment" in text


def india_eligible(opp: dict) -> bool:
    return "india" in (opp.get("location") or "").lower()


def fresher_eligible(opp: dict) -> bool:
    elig = opp.get("eligibility") or {}
    text = " ".join(str(elig.get(k) or "") for k in
                    ("experience", "degree", "other")).lower()
    return any(w in text for w in ("fresher", "freshers", "student", "undergraduate",
                                   "pursuing", "b.tech"))


def check_mark(passing: int, total: int) -> str:
    if total == 0 or passing == total:
        return "✅"
    if passing == 0:
        return "❌"
    return "⚠️"


def build_daily_digest(mark: bool = True) -> tuple[str, list[str]]:
    """Return (message, ids_marked_notified).

    User-specified format (2026-10-05): DS/Data-Analytics/BI slice, ranked
    top-5 recommendations with 1-2 sentence reasons, verification notes,
    daily summary, and a final quality checklist. Deterministic — stdlib
    only. See the banner above: do not change this format without asking
    the user.

    With mark=False the digest is generated without consuming the "new"
    state — for delivering the same digest to a second channel.
    """
    now = datetime.now(TZ)
    today = now.date()
    cutoff = now - timedelta(hours=24)
    db = load_db()
    opps = [o for o in db["opportunities"] if o.get("status") != "rejected"]

    candidates = [
        o for o in opps
        if (_first_seen_dt(o.get("first_seen")) or datetime.min.replace(tzinfo=TZ)) >= cutoff
        and today.isoformat() not in (o.get("notified_in_digest") or [])
    ]

    date_str = now.strftime("%d %b %Y")
    lines = [
        "📊 SCIENCE / DATA ANALYTICS OPPORTUNITIES",
        "",
        f"Date: {date_str}",
        f"Reporting period: last 24h (IST)",
        "",
    ]

    if not candidates:
        lines.append("No additional verified opportunities meeting the criteria were found today.")
        lines.append("")
    else:
        ds_opps = [o for o in candidates if ds_relevant(o)]
        lines.append("SCIENCE / DATA ANALYTICS OPPORTUNITIES")
        lines.append("")
        if ds_opps:
            for o in ds_opps:
                match = (o.get("match") or {}).get("classification", "Not classified")
                lines.append(f"• {o['company']} — {o['role']} ({match})")
                lines.append(f"  Deadline: {fmt_deadline(o, today)}")
                lines.append("")
        else:
            lines.append("No dedicated Data Science / Data Analytics / BI postings were found today.")
            lines.append("")

        ranked = sorted(candidates, key=lambda o: rank_key(o, now))
        top5 = ranked[:5]

        lines.append("🏆 TOP 5 RECOMMENDATIONS FOR ME")
        lines.append("")
        for i, o in enumerate(top5, 1):
            match = (o.get("match") or {}).get("classification", "Not classified")
            lines.append(f"{i}. {o['company']} — {o['role']} ({match})")
            lines.append(f"   Why apply: {why_apply(o)}")
            lines.append(f"   Deadline: {fmt_deadline(o, today)}")
            lines.append(f"   Link: {direct_link(o)}")
            lines.append("")

        # --- verification notes ---
        lines.append("⚠️ IMPORTANT VERIFICATION NOTES")
        lines.append("")

        rejected_today = [
            o for o in db["opportunities"]
            if o.get("status") == "rejected"
            and (_first_seen_dt(o.get("first_seen")) or datetime.min.replace(tzinfo=TZ)) >= cutoff
        ]
        if rejected_today:
            names = ", ".join(f"{o['company']} — {o['role']}" for o in rejected_today)
            lines.append(f"• Excluded (did not meet requirements): {names}")
        else:
            lines.append("• Excluded / suspicious listings: none today.")

        cert_unver = [
            o for o in candidates
            if "certificate" in " ".join([
                str(o.get("conditions") or ""),
                str((o.get("verification") or {}).get("notes") or ""),
            ]).lower() and not is_verified(o)
        ]
        if cert_unver:
            names = ", ".join(f"{o['company']} — {o['role']}" for o in cert_unver)
            lines.append(f"• Certificate status NOT verified: {names}")
        else:
            lines.append("• Certificate status: no certificate claims were made by today's listings.")

        no_deadline = [o for o in candidates if not o.get("deadline")]
        if no_deadline:
            names = ", ".join(f"{o['company']} — {o['role']}" for o in no_deadline)
            lines.append(f"• Deadline not available: {names} — apply early; roles may close without notice.")
        else:
            lines.append("• Deadlines: available for all today's listings.")

        unver_src = [o for o in candidates if not is_verified(o)]
        if unver_src:
            lines.append(f"• Official source not fully verified ({len(unver_src)}): " +
                         ", ".join(f"{o['company']} — {o['role']}" for o in unver_src))
        else:
            lines.append("• Official sources: all verified.")

        elig_limits = []
        for o in candidates:
            unclear = (o.get("match") or {}).get("unclear") or []
            if unclear:
                elig_limits.append(f"{o['company']} — {o['role']}: {', '.join(unclear)}")
        if elig_limits:
            lines.append("• Eligibility limitations:")
            for item in elig_limits:
                lines.append(f"  – {item}")
        else:
            lines.append("• Eligibility limitations: none reported.")
        lines.append("")

        # --- daily summary ---
        verified_jobs = sum(1 for o in candidates if is_job(o) and is_verified(o))
        verified_interns = sum(1 for o in candidates if is_internship(o) and is_verified(o))
        no_payment_interns = sum(1 for o in candidates if is_internship(o) and no_payment_stated(o))

        best = top5[0]
        interns_ranked = [o for o in ranked if is_internship(o)]
        best_intern = interns_ranked[0] if interns_ranked else None

        with_dl = [(days_remaining(o.get("deadline"), today), o) for o in candidates
                   if days_remaining(o.get("deadline"), today) is not None
                   and days_remaining(o.get("deadline"), today) >= 0]
        urgent = min(with_dl, key=lambda r: r[0]) if with_dl else (None, None)

        lines.append("📌 DAILY SUMMARY")
        lines.append("")
        lines.append(f"Total verified jobs found: {verified_jobs}")
        lines.append(f"Total verified internships found: {verified_interns}")
        lines.append(f"Total no-payment internships found: {no_payment_interns}")
        lines.append(f"Best company today: {best['company']}")
        lines.append(f"Best role today: {best['role']}")
        if best_intern:
            lines.append(f"Best internship today: {best_intern['company']} — {best_intern['role']}")
        else:
            lines.append("Best internship today: none today")
        if urgent[1] is not None:
            dr, uo = urgent
            lines.append(f"Most urgent deadline: {uo['company']} — {uo['role']} "
                         f"({uo.get('deadline')}, {dr} day{'s' if dr != 1 else ''} remaining)")
        else:
            lines.append("Most urgent deadline: none with a published deadline")
        lines.append(f"Best opportunity to apply first: {best['company']} — {best['role']}")
        lines.append(f"Apply: {direct_link(best)}")
        lines.append("")

        # --- final quality check ---
        n = len(top5)
        counts = {
            "active": sum(1 for o in top5 if o.get("status") != "rejected"),
            "aids": sum(1 for o in top5 if ds_relevant(o) or (o.get("match") or {})
                         .get("classification") in ("Strong match", "Moderate match")),
            "fresher": sum(1 for o in top5 if fresher_eligible(o)),
            "official": sum(1 for o in top5 if valid_url(o.get("official_url"))),
            "link": sum(1 for o in top5 if valid_url(o.get("application_url"))),
            "nodup": sum(1 for o in top5
                         if sum(1 for x in db["opportunities"]
                                if x.get("dedupe_key") == o.get("dedupe_key")) <= 1),
            "nopay": sum(1 for o in top5 if no_payment_stated(o)),
            "india": sum(1 for o in top5 if india_eligible(o)),
        }
        cert_claims = [o for o in top5 if "certificate" in " ".join([
            str(o.get("conditions") or ""),
            str((o.get("verification") or {}).get("notes") or "")]).lower()]
        cert_ok = all(is_verified(o) for o in cert_claims) if cert_claims else True
        if cert_claims and cert_ok:
            cert_label = "✅ Certificate claim verified or clearly marked"
        elif cert_claims:
            cert_label = "⚠️ Certificate claim not verified — marked as such"
        else:
            cert_label = "✅ No certificate claims made"
        lines.append("✅ FINAL QUALITY CHECK")
        lines.append("")
        lines.append(f"{check_mark(counts['active'], n)} Active opportunity ({counts['active']}/{n})")
        lines.append(f"{check_mark(counts['aids'], n)} Relevant to AI/DS ({counts['aids']}/{n})")
        lines.append(f"{check_mark(counts['fresher'], n)} Fresher/student eligible ({counts['fresher']}/{n})")
        lines.append(f"{check_mark(counts['official'], n)} Official source checked ({counts['official']}/{n})")
        lines.append(f"{check_mark(counts['link'], n)} Direct application link ({counts['link']}/{n})")
        lines.append(f"{check_mark(counts['nodup'], n)} No duplicate ({counts['nodup']}/{n})")
        if counts["nopay"] == n:
            lines.append(f"✅ No mandatory payment ({counts['nopay']}/{n} state no fee)")
        elif counts["nopay"] == 0:
            lines.append("⚠️ No mandatory payment: fee status not stated — confirm before paying anything")
        else:
            lines.append(f"⚠️ No mandatory payment ({counts['nopay']}/{n} state no fee; rest unstated)")
        lines.append(cert_label)
        lines.append(f"{check_mark(counts['india'], n)} India eligibility checked ({counts['india']}/{n})")
        lines.append("")

    message = "\n".join(lines).rstrip() + "\n"

    # Archive a copy of every digest.
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y-%m-%d-%H%M")
    (REPORTS_DIR / f"digest-{stamp}.md").write_text(message, encoding="utf-8")

    # Mark newly reported opportunities so they are not repeated tomorrow.
    # Skipped with --no-mark (second-channel delivery of the same digest).
    notified_ids = [o["id"] for o in candidates]
    if mark:
        if notified_ids:
            for o in db["opportunities"]:
                if o["id"] in notified_ids:
                    seen = o.get("notified_in_digest") or []
                    if today.isoformat() not in seen:
                        seen.append(today.isoformat())
                    o["notified_in_digest"] = seen
                    o["last_updated"] = now.isoformat()
            save_db(db)

        state = load_state()
        state["last_digest_at"] = now.isoformat()
        state["last_digest_date"] = today.isoformat()
        save_state(state)
    return message, notified_ids

def build_deadline_watch(mark: bool = True) -> str:
    """Morning watch: print only when a deadline is within 48h and unreminded.

    With mark=False the reminder is generated without consuming the
    reminded state — for delivering the same reminder to a second channel.
    """
    now = datetime.now(TZ)
    today = now.date()
    db = load_db()
    urgent = []
    for o in db["opportunities"]:
        if o.get("status") == "rejected":
            continue
        dr = days_remaining(o.get("deadline"), today)
        if dr is not None and 0 <= dr <= WATCH_DAYS and o.get("deadline_reminded") != o.get("deadline"):
            urgent.append((dr, o))
    if not urgent:
        return ""
    urgent.sort(key=lambda r: r[0])
    lines = ["⏰ DEADLINE REMINDER", ""]
    for dr, o in urgent:
        when = "today" if dr == 0 else f"in {dr} day{'s' if dr != 1 else ''}"
        lines.append(f"{o['company']} — {o['role']}: deadline {when} ({o.get('deadline')}).")
        link = o.get("application_url") or "Not specified"
        lines.append(f"Apply: {link}")
        lines.append("")
        if mark:
            o["deadline_reminded"] = o.get("deadline")
            o["last_updated"] = now.isoformat()
    if mark:
        save_db(db)
        state = load_state()
        state["last_deadline_watch_at"] = now.isoformat()
        save_state(state)
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the opportunity digest")
    parser.add_argument("--watch", action="store_true", help="Deadline-watch mode (silent when nothing urgent)")
    parser.add_argument("--no-mark", action="store_true",
                        help="Do not consume new/reminded state (second-channel delivery)")
    args = parser.parse_args(argv)
    if args.watch:
        message = build_deadline_watch(mark=not args.no_mark)
    else:
        message, _ = build_daily_digest(mark=not args.no_mark)
    if message:
        sys.stdout.write(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
