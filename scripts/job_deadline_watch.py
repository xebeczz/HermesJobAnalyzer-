#!/usr/bin/env python3
"""Morning deadline-watch entry point for Hermes cron.

`hermes cron create --no-agent --script job_deadline_watch.py --deliver telegram '0 9 * * *'`
stays silent (empty stdout) unless a deadline is within 48h and unreminded.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from job_digest import build_deadline_watch  # noqa: E402

if __name__ == "__main__":
    no_mark = "--no-mark" in sys.argv
    message = build_deadline_watch(mark=not no_mark)
    if message:
        sys.stdout.write(message)
