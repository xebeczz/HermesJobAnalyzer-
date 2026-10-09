#!/usr/bin/env python3
"""Send a text file to the user's Telegram chat via the Hermes bot token.

Reads TELEGRAM_BOT_TOKEN from ~/.hermes/.env (never prints it).
Splits messages longer than 4000 chars into sequential chunks.

Usage: telegram_send.py <text-file> [--chat-id ID]
Exit 0 when every chunk is accepted, 1 otherwise (error on stderr).
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ENV_FILE = Path("/home/hatch/.hermes/.env")
DEFAULT_CHAT_ID = "7349985252"
CHUNK = 4000


def get_token() -> str:
    m = re.search(r"^TELEGRAM_BOT_TOKEN=(.+)$", ENV_FILE.read_text(), re.M)
    if not m:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not found in ~/.hermes/.env")
    return m.group(1).strip().strip('"').strip("'")


def send_chunk(token: str, chat_id: str, text: str) -> None:
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.load(resp)
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected the send: {result}")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--chat-id")]
    chat_id = DEFAULT_CHAT_ID
    for i, a in enumerate(argv):
        if a == "--chat-id" and i + 1 < len(argv):
            chat_id = argv[i + 1]
        elif a.startswith("--chat-id="):
            chat_id = a.split("=", 1)[1]
    if not args:
        print("usage: telegram_send.py <text-file> [--chat-id ID]", file=sys.stderr)
        return 2
    text = Path(args[0]).read_text(encoding="utf-8").rstrip()
    if not text:
        print("nothing to send (empty input)", file=sys.stderr)
        return 0
    token = get_token()
    chunks = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)]
    try:
        for n, chunk in enumerate(chunks, 1):
            send_chunk(token, chat_id, chunk)
            print(f"sent chunk {n}/{len(chunks)} ({len(chunk)} chars)")
    except Exception as e:  # noqa: BLE001 - report and exit non-zero
        print(f"SEND FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
