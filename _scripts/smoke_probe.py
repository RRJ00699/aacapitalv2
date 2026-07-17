#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smoke_probe.py — post-pipeline smoke test (audit action #2). Hits the live
API and FAILS the lean step (-> failure sink -> phone) if the command center
would render broken. Read-only; API routes are session-free (proxy gates pages).
"""
import json, sys, urllib.request

BASE = "https://aacapitalprivatelimited.com"

def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "aac-smoke"})
    return json.load(urllib.request.urlopen(req, timeout=30))

def main():
    fails = []
    try:
        d = get("/api/ipo-command")
        if d.get("degraded"): fails.append(f"command DEGRADED: {str(d['degraded'])[:120]}")
        elif not isinstance(d.get("cards"), list) or len(d["cards"]) < 100:
            fails.append(f"command cards suspicious: {len(d.get('cards') or [])}")
    except Exception as e:
        fails.append(f"command unreachable: {str(e)[:100]}")
    try:
        s = get("/api/admin/pipeline-steps")
        if not s.get("ok"): fails.append("pipeline-steps not ok")
    except Exception as e:
        fails.append(f"pipeline-steps: {str(e)[:100]}")
    if fails:
        print("SMOKE FAIL:\n  " + "\n  ".join(fails)); sys.exit(1)
    print("SMOKE PASS: command API healthy, steps endpoint healthy")

if __name__ == "__main__":
    main()
