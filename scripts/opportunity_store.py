#!/usr/bin/env python3
"""Opportunity database for the Internship & Job Opportunity Analyzer.

Stores agent-analyzed opportunities in data/opportunities.json with:

- Deduplication on normalized (company, role, application_url).
- Deadline normalization to YYYY-MM-DD ("October 15" -> 2026-10-15).
- Lifecycle status management: new, saved, deadline-approaching,
  needs-verification, ready-to-apply, rejected.

The agent performs detection/extraction/comparison/classification/verification
per SKILL.md and passes the finished analysis JSON to `add`. This module never
invents opportunity data.

Usage:
    python3 opportunity_store.py add --file analysis.json [--source TEXT] [--source-url URL]
    python3 opportunity_store.py list [--status S] [--limit N]
    python3 opportunity_store.py get --id ID
    python3 opportunity_store.py set-status --id ID --status S
    python3 opportunity_store.py deadlines [--within-days N]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
OPP_FILE = DATA_DIR / "opportunities.json"
TZ = ZoneInfo("Asia/Kolkata")

VALID_STATUSES = {
    "new",
    "saved",
    "deadline-approaching",
    "needs-verification",
    "ready-to-apply",
    "rejected",
}

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _norm_text(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _norm_url(value: object) -> str:
    url = str(value or "").strip().lower()
    if url in ("", "not specified", "n/a", "na", "none"):
        return ""
    url = url.rstrip("/")
    return url


def dedupe_key(company: str, role: str, application_url: str) -> str:
    return "|".join((_norm_text(company), _norm_text(role), _norm_url(application_url)))


def parse_deadline(raw: object) -> str | None:
    """Normalize a deadline to YYYY-MM-DD, or None when unspecified/unparseable."""
    text = str(raw or "").strip()
    if not text or text.lower() in ("not specified", "n/a", "na", "none", "unclear — verify before applying"):
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year += 2000 if year < 100 else 0
        return f"{year:04d}-{month:02d}-{day:02d}"
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?", text)
    if not m:
        m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s*,?\s*(\d{4}))?", text)
        if m:
            day, mon, year = int(m.group(1)), m.group(2).lower(), m.group(3)
        else:
            return None
    else:
        mon, day, year = m.group(1).lower(), int(m.group(2)), m.group(3)
    month = MONTHS.get(mon)
    if not month:
        return None
    today = datetime.now(TZ).date()
    y = int(year) if year else today.year
    try:
        parsed = date(y, month, day)
    except ValueError:
        return None
    if not year and parsed < today:
        parsed = date(y + 1, month, day)
    return parsed.isoformat()


def days_remaining(deadline_iso: str | None, today: date | None = None) -> int | None:
    if not deadline_iso:
        return None
    today = today or datetime.now(TZ).date()
    try:
        return (date.fromisoformat(deadline_iso) - today).days
    except ValueError:
        return None


def load_db() -> dict:
    if OPP_FILE.exists():
        return json.loads(OPP_FILE.read_text(encoding="utf-8"))
    return {"opportunities": [], "version": 1}


def save_db(db: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OPP_FILE.write_text(json.dumps(db, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def slugify(*parts: str) -> str:
    slug = "-".join(parts).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug[:60] or "opportunity"


def cmd_add(args: argparse.Namespace) -> int:
    analysis = json.loads(Path(args.file).read_text(encoding="utf-8"))
    company = str(analysis.get("company", "")).strip()
    role = str(analysis.get("role", "")).strip()
    if not company or not role:
        print("ERROR: analysis must include company and role", file=sys.stderr)
        return 2

    key = dedupe_key(company, role, str(analysis.get("application_url", "")))
    db = load_db()
    for existing in db["opportunities"]:
        if existing.get("dedupe_key") == key:
            existing["last_updated"] = datetime.now(TZ).isoformat()
            existing["duplicate_sightings"] = existing.get("duplicate_sightings", 0) + 1
            save_db(db)
            print(f"POSSIBLE DUPLICATE — updated existing record {existing['id']} "
                  f"(sightings: {existing['duplicate_sightings']})")
            return 0

    now = datetime.now(TZ)
    base_id = f"opp-{now.strftime('%Y%m%d')}-{slugify(company, role)}"
    taken = {o["id"] for o in db["opportunities"]}
    opp_id, suffix = base_id, 2
    while opp_id in taken:
        opp_id, suffix = f"{base_id}-{suffix}", suffix + 1

    deadline = parse_deadline(analysis.get("deadline"))
    record = {
        "id": opp_id,
        "dedupe_key": key,
        "company": company,
        "role": role,
        "opportunity_type": str(analysis.get("opportunity_type", "Not specified")),
        "location": str(analysis.get("location", "Not specified")),
        "work_mode": str(analysis.get("work_mode", "Not specified")),
        "duration": str(analysis.get("duration", "Not specified")),
        "stipend": str(analysis.get("stipend", "Not specified")),
        "salary": str(analysis.get("salary", "Not specified")),
        "eligibility": analysis.get("eligibility", {}),
        "skills_required": analysis.get("skills_required", {}),
        "responsibilities": str(analysis.get("responsibilities", "Not specified")),
        "deadline": deadline,
        "application_url": str(analysis.get("application_url", "Not specified")),
        "official_url": str(analysis.get("official_url", "Not specified")),
        "recruiter_info": str(analysis.get("recruiter_info", "Not specified")),
        "conditions": str(analysis.get("conditions", "Not specified")),
        "match": analysis.get("match", {}),
        "verification": analysis.get("verification", {}),
        "source": args.source or str(analysis.get("source", "manual")),
        "source_url": args.source_url or analysis.get("source_url"),
        "status": args.status or str(analysis.get("status", "new")),
        "first_seen": now.isoformat(),
        "last_updated": now.isoformat(),
        "duplicate_sightings": 1,
        "notified_in_digest": [],
        "deadline_reminded": None,
    }
    if record["status"] not in VALID_STATUSES:
        record["status"] = "new"
    db["opportunities"].append(record)
    save_db(db)
    print(f"STORED {opp_id} — {company} / {role} (deadline: {deadline or 'Not specified'})")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    db = load_db()
    opps = db["opportunities"]
    if args.status:
        opps = [o for o in opps if o.get("status") == args.status]
    opps = sorted(opps, key=lambda o: o.get("first_seen", ""), reverse=True)[: args.limit]
    if not opps:
        print("No opportunities stored.")
        return 0
    for o in opps:
        dr = days_remaining(o.get("deadline"))
        dl = f"{o.get('deadline')} ({dr}d)" if dr is not None else "Not specified"
        match = (o.get("match") or {}).get("classification", "?")
        print(f"{o['id']} | {o['company']} — {o['role']} | {o.get('opportunity_type','?')} "
              f"| {match} | deadline: {dl} | status: {o.get('status')}")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    db = load_db()
    for o in db["opportunities"]:
        if o["id"] == args.id:
            print(json.dumps(o, indent=2, ensure_ascii=False))
            return 0
    print(f"ERROR: no opportunity with id {args.id}", file=sys.stderr)
    return 1


def cmd_set_status(args: argparse.Namespace) -> int:
    if args.status not in VALID_STATUSES:
        print(f"ERROR: status must be one of {sorted(VALID_STATUSES)}", file=sys.stderr)
        return 2
    db = load_db()
    for o in db["opportunities"]:
        if o["id"] == args.id:
            o["status"] = args.status
            o["last_updated"] = datetime.now(TZ).isoformat()
            save_db(db)
            print(f"{args.id} -> {args.status}")
            return 0
    print(f"ERROR: no opportunity with id {args.id}", file=sys.stderr)
    return 1


def cmd_deadlines(args: argparse.Namespace) -> int:
    db = load_db()
    today = datetime.now(TZ).date()
    rows = []
    for o in db["opportunities"]:
        if o.get("status") == "rejected":
            continue
        dr = days_remaining(o.get("deadline"), today)
        if dr is not None and 0 <= dr <= args.within_days:
            rows.append((dr, o))
    rows.sort(key=lambda r: r[0])
    if not rows:
        print(f"No deadlines within {args.within_days} days.")
        return 0
    for dr, o in rows:
        print(f"{dr:3d}d | {o['company']} — {o['role']} | {o.get('deadline')} | {o['id']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Opportunity database CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Store a finished agent analysis")
    p_add.add_argument("--file", required=True, help="Path to analysis JSON")
    p_add.add_argument("--source", default=None)
    p_add.add_argument("--source-url", default=None)
    p_add.add_argument("--status", default=None, choices=sorted(VALID_STATUSES))
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="List stored opportunities")
    p_list.add_argument("--status", default=None, choices=sorted(VALID_STATUSES))
    p_list.add_argument("--limit", type=int, default=50)
    p_list.set_defaults(func=cmd_list)

    p_get = sub.add_parser("get", help="Show one record as JSON")
    p_get.add_argument("--id", required=True)
    p_get.set_defaults(func=cmd_get)

    p_status = sub.add_parser("set-status", help="Change lifecycle status")
    p_status.add_argument("--id", required=True)
    p_status.add_argument("--status", required=True, choices=sorted(VALID_STATUSES))
    p_status.set_defaults(func=cmd_set_status)

    p_dl = sub.add_parser("deadlines", help="Upcoming deadlines, soonest first")
    p_dl.add_argument("--within-days", type=int, default=30)
    p_dl.set_defaults(func=cmd_deadlines)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
