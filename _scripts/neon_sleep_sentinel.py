#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""neon_sleep_sentinel.py — CERTAINTY that the DB sleeps (Rakesh 2026-07-18:
"make sure we are certain this time").

The 147 CU-h leak taught the lesson: unit tests validate logic; only a
production-loop alarm validates the INVARIANT. This sentinel asks Neon's
MANAGEMENT API (api.neon.tech — never the database itself, so the check can
never wake what it watches) whether the compute endpoint is idle during the
dead of night. Active at 03:33 IST, when nothing is scheduled and no human is
awake, means a leak — and your phone finds out within the minute.

Requires in .env:  NEON_API_KEY (console -> Account -> API keys)
                   NEON_PROJECT_ID (console -> Project settings -> General)
Cron (IST server):  33 3 * * * cd /root/aac && set -a && . ./.env && set +a && venv/bin/python _scripts/neon_sleep_sentinel.py >> logs/sentinel.log 2>&1
Alerting: ntfy push (NTFY_TOPIC) + logfile. NEVER touches the DB.
"""
import datetime as dt
import json, os, sys, urllib.request

def alert(msg):
    print(msg)
    topic = os.getenv("NTFY_TOPIC")
    if topic:
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"https://ntfy.sh/{topic}", data=msg.encode(),
                headers={"Title": "Neon sleep sentinel", "Priority": "high",
                         "User-Agent": "aac-sentinel"}), timeout=10)
        except Exception as e:
            print(f"(ntfy failed: {e})")

def main():
    key, proj = os.getenv("NEON_API_KEY"), os.getenv("NEON_PROJECT_ID")
    if not key or not proj:
        alert("SENTINEL MISCONFIGURED: NEON_API_KEY / NEON_PROJECT_ID missing in .env")
        sys.exit(1)
    req = urllib.request.Request(
        f"https://console.neon.tech/api/v2/projects/{proj}/endpoints",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                 "User-Agent": "aac-sentinel"})
    try:
        eps = json.load(urllib.request.urlopen(req, timeout=20)).get("endpoints", [])
    except Exception as e:
        alert(f"SENTINEL: Neon API unreachable ({str(e)[:80]}) — cannot verify sleep")
        sys.exit(1)
    now = dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)
    bad = [e for e in eps if e.get("current_state") != "idle"]
    if bad:
        names = ", ".join(f"{e.get('id','?')}={e.get('current_state')}" for e in bad)
        alert(f"DB NOT SLEEPING at {now:%H:%M} IST — {names}. "
              f"Something is polling Neon off-hours; run pg_stat_activity to name it.")
        sys.exit(2)
    print(f"{now:%Y-%m-%d %H:%M} IST — all endpoints idle. The DB sleeps. ✓")

if __name__ == "__main__":
    main()
