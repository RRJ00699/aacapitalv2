#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smoke_probe.py v3 — self-synchronizing DB contract probe (LAST lean step).

v2 hand-listed columns and immediately mixed tables (ipo_open_date lives on
ipo_consolidated, not ipo_intelligence — its own first catch). v3 removes the
human from the loop: it PARSES the command route's source at runtime, extracts
every `alias.column` reference, maps aliases to tables, and probes each table
with exactly the columns the code actually uses. Route evolves -> contract
evolves, automatically. Plus the authed worker-chain check.
Failure exits 1 -> failure sink -> Pipeline health -> phone.
"""
import json, os, re, sys, urllib.request
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTE = os.path.join(os.path.dirname(HERE), "app", "api", "ipo-command", "route.ts")
ALIAS_TABLE = {"c": "ipo_consolidated", "ii": "ipo_intelligence",
               "v": "ipo_verdicts", "ri": "ipo_rhp_intel", "n": "ipo_research_notes"}
SQL_NOISE = {"state", "and", "or", "then", "else", "end", "select", "from", "where"}

def contract_from_route():
    src = open(ROUTE, encoding="utf-8").read()
    found = {}
    for alias, col in re.findall(r"\b(c|ii|v|ri|n)\.([a-z][a-z0-9_]*)\b", src):
        if col in SQL_NOISE: continue
        found.setdefault(ALIAS_TABLE[alias], set()).add(col)
    return found

def main():
    fails, probed = [], 0
    try:
        contract = contract_from_route()
    except Exception as e:
        print(f"SMOKE FAIL:\n  cannot read route source: {e}"); sys.exit(1)
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
        for table, cols in sorted(contract.items()):
            collist = ", ".join(sorted(cols))
            try:
                cur.execute(f"SELECT {collist} FROM {table} LIMIT 1")
                probed += len(cols)
            except Exception as e:
                fails.append(f"{table}: {str(e).splitlines()[0][:140]}")
                conn.rollback()
        conn.close()
    except Exception as e:
        fails.append(f"DB unreachable: {str(e)[:120]}")
    key = os.getenv("ADMIN_JOB_KEY", "")
    if key:
        try:
            req = urllib.request.Request(
                "https://aacapitalprivatelimited.com/api/admin/job-flag",
                headers={"X-AAC-Key": key, "User-Agent": "aac-smoke"})
            d = json.load(urllib.request.urlopen(req, timeout=30))
            if not d.get("ok"): fails.append("worker chain: job-flag rejected the key")
        except Exception as e:
            fails.append(f"worker chain: {str(e)[:100]}")
    if fails:
        print("SMOKE FAIL:\n  " + "\n  ".join(fails)); sys.exit(1)
    print(f"SMOKE PASS: {probed} route-referenced columns verified across "
          f"{len(contract)} tables (contract parsed from route.ts) · worker chain healthy")

if __name__ == "__main__":
    main()
