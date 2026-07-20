#!/usr/bin/env python3
"""_scripts/lib/notify.py — push alerts to the phone via ntfy.sh (Phase 3).

Design rules:
  * ZERO dependencies (urllib only) — safe to import from any pipeline script.
  * NEVER raises — a broken notifier must never break a pipeline step.
  * Silently no-ops when NTFY_TOPIC is unset (dev machines, CI, sandbox).
  * Every message carries the event time in BOTH IST (market/app) and
    US Central (Rakesh) so no mental timezone math at 3am.

Env:
  NTFY_TOPIC   required to send (e.g. "aacapital-alerts-x7q2")  — keep it
               unguessable; ntfy topics are the auth.
  NTFY_SERVER  optional, defaults to https://ntfy.sh

Usage:
  from lib.notify import notify
  notify("Kite token FAILED", "TOTP login failed: ...", priority="urgent",
         tags=["rotating_light"])
"""
from __future__ import annotations

import os
import urllib.request

_PRIORITY = {"urgent": "5", "high": "4", "default": "3", "low": "2", "min": "1"}


def _stamp() -> str:
    """Event time as 'IST HH:MM · US-Central HH:MM' (zoneinfo, fixed-offset fallback)."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        ist = now.astimezone(ZoneInfo("Asia/Kolkata"))
        cst = now.astimezone(ZoneInfo("America/Chicago"))
    except Exception:  # no tzdata — fixed offsets (IST never shifts; Central approx)
        ist = now.astimezone(timezone(timedelta(hours=5, minutes=30)))
        cst = now.astimezone(timezone(timedelta(hours=-5)))
    return f"IST {ist:%H:%M} · US-Central {cst:%H:%M}"


def notify(title: str, message: str, priority: str = "default",
           tags: list[str] | None = None, timeout: float = 8.0) -> bool:
    """Send a push. Returns True on 2xx, False otherwise. Never raises."""
    try:
        topic = os.environ.get("NTFY_TOPIC", "").strip()
        if not topic:
            return False  # not configured — silent no-op by design
        server = (os.environ.get("NTFY_SERVER", "").strip() or "https://ntfy.sh").rstrip("/")
        body = f"{message}\n\n{_stamp()}".encode("utf-8", errors="replace")
        req = urllib.request.Request(
            f"{server}/{topic}", data=body, method="POST",
            headers={
                "Title": title.encode("ascii", errors="replace").decode(),
                "Priority": _PRIORITY.get(priority, "3"),
                "Tags": ",".join(tags or []),
                "User-Agent": "aacapital-notify",
            })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False  # never let the notifier take down a pipeline


if __name__ == "__main__":
    import sys
    ok = notify(sys.argv[1] if len(sys.argv) > 1 else "aacapital test",
                sys.argv[2] if len(sys.argv) > 2 else "notify.py smoke test",
                priority=sys.argv[3] if len(sys.argv) > 3 else "default")
    print("sent" if ok else "not sent (NTFY_TOPIC unset or send failed)")
