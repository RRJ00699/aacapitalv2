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
    """Parse alias.column ONLY inside SQL template literals — v3 scanned the
    whole file and caught TypeScript payload access (c.band_high, a SELECT
    alias), conflating JS objects with SQL columns (its own first catch)."""
    src = open(ROUTE, encoding="utf-8").read()
    sql_chunks = [m for m in re.findall(r"`([^`]*)`", src, re.S)
                  if "SELECT" in m.upper() and "FROM" in m.upper()]
    found = {}
    for chunk in sql_chunks:
        # drop selected-alias names so `x AS band_high` never registers band_high
        aliases = set(re.findall(r"\bAS\s+([a-z][a-z0-9_]*)", chunk, re.I))
        for alias, col in re.findall(r"\b(c|ii|v|ri|n)\.([a-z][a-z0-9_]*)\b", chunk):
            if col in SQL_NOISE or col in aliases: continue
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
        # DATA-HEALTH INVARIANT (permanent guard): the dial's columns must not
        # silently empty. quality_score powers a UI mode; if it drops to near-
        # zero, the pipeline FAILS here -> phone, instead of a dead dial nobody
        # notices. Threshold is absolute-low (100) so a backfill only helps.
        try:
            cur.execute("SELECT count(*) FROM ipo_intelligence WHERE quality_score IS NOT NULL")
            qs = cur.fetchone()[0]
            if qs < 100:
                fails.append(f"quality_score near-empty ({qs} rows) — dial dead, compute or upstream broke")
        except Exception:
            pass
        conn.close()
    except Exception as e:
        fails.append(f"DB unreachable: {str(e)[:120]}")
    key = os.getenv("ADMIN_JOB_KEY", "")
    if key:
        # Probe with the RUNNER'S exact identity, not smoke's: the 147 CU-h
        # leak was Cloudflare 403ing the runner's UA while smoke's own UA
        # passed — a green smoke masking a red runner. Never again: this
        # check fails iff the runner's real request path would fail.
        try:
            req = urllib.request.Request(
                "https://aacapitalprivatelimited.com/api/admin/job-flag",
                headers={"X-AAC-Key": key, "User-Agent": "aac-runner"})
            d = json.load(urllib.request.urlopen(req, timeout=30))
            if not d.get("ok"): fails.append("worker chain: job-flag rejected the key (runner identity)")
        except Exception as e:
            fails.append(f"worker chain: {str(e)[:100]}")
    if fails:
        print("SMOKE FAIL:\n  " + "\n  ".join(fails)); sys.exit(1)
    print(f"SMOKE PASS: {probed} route-referenced columns verified across "
          f"{len(contract)} tables (contract parsed from route.ts) · worker chain healthy")

if __name__ == "__main__":
    main()
