#!/usr/bin/env python3
"""
check_data_contract.py — the guardrail that ends the circular rework.

Reads ipo_data_contract.csv (the single source of truth for the IPO data model),
queries the live DB for the ACTUAL coverage of every field, and compares it to the
recorded baseline. It FAILS LOUD (exit 1) the moment:
  - a LIVE field regresses below its baseline, OR
  - a LIVE field's column/table has vanished (an ALTER broke the schema).

Run it after every build / in the daily pipeline. This is what was missing: the VIX
bug survived for weeks because nothing checked. Now something checks.

Usage:
    export DATABASE_URL=...        # or NEON_DATABASE_URL
    python check_data_contract.py                 # looks for ipo_data_contract.csv nearby
    python check_data_contract.py path/to/contract.csv
    python check_data_contract.py --update-baselines   # rewrite coverage_now from reality

The contract CSV is the source of truth. To onboard a new column: add a row FIRST
(source_table, source_column, populator_script, consumer), then ship the ALTER + populator.
No row -> the field isn't real.
"""
import os, sys, csv, re

try:
    import psycopg2
except ImportError:
    sys.exit("psycopg2 not installed:  pip install psycopg2-binary --break-system-packages")

# ---- locate the contract CSV ---------------------------------------------------
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
FLAGS = {a for a in sys.argv[1:] if a.startswith("--")}
CANDIDATES = ([ARGS[0]] if ARGS else []) + [
    os.getenv("CONTRACT_CSV", ""),
    "ipo_data_contract.csv",
    os.path.join(os.path.dirname(__file__), "ipo_data_contract.csv"),
    os.path.join(os.path.dirname(__file__), "..", "ipo_data_contract.csv"),
]
CONTRACT = next((p for p in CANDIDATES if p and os.path.exists(p)), None)
if not CONTRACT:
    sys.exit("Could not find ipo_data_contract.csv. Pass its path or set CONTRACT_CSV.")

DB = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
if not DB:
    sys.exit("Set DATABASE_URL (or NEON_DATABASE_URL) first.")

# statuses that have nothing queryable yet (forward-only / unstructured / no source)
NON_QUERYABLE = {"NOT_CAPTURED", "NO_HISTORY", "NOT_STRUCTURED"}
LIVE = {"LIVE"}

def baseline_num(s):
    """Pull the leading integer out of coverage_now ('310/432'->310, '25 days'->25)."""
    m = re.match(r"\s*~?(\d+)", str(s or ""))
    return int(m.group(1)) if m else None

def colset(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    return {r[0] for r in cur.fetchall()}

def main():
    rows = list(csv.DictReader(open(CONTRACT, encoding="utf-8")))
    conn = psycopg2.connect(DB); conn.autocommit = True
    cur = conn.cursor()

    # cache columns per table so we can detect schema breaks (vanished columns)
    tbl_cols = {}
    results = []          # (field, table.col, baseline, current, status, verdict)
    regressions = 0

    for r in rows:
        field  = (r.get("field") or "").strip()
        table  = (r.get("source_table") or "").strip()
        col    = (r.get("source_column") or "").strip()
        status = (r.get("status") or "").strip().upper()
        base   = baseline_num(r.get("coverage_now"))

        # nothing to query (forward-only / unstructured / placeholder source)
        if status in NON_QUERYABLE or table.startswith("(") or col.startswith("(") or not table or not col:
            results.append((field, f"{table}.{col}", base, None, status, "—  (no source yet)"))
            continue

        if table not in tbl_cols:
            try:
                tbl_cols[table] = colset(cur, table)
            except Exception:
                tbl_cols[table] = set()

        # SCHEMA BREAK: column the contract names no longer exists
        if col not in tbl_cols[table]:
            verdict = "❌ SCHEMA BREAK (column/table gone)"
            if status in LIVE:
                regressions += 1
            results.append((field, f"{table}.{col}", base, "MISSING", status, verdict))
            continue

        # count populated rows ( >0 for the tier-1 count field, else NOT NULL )
        pred = f"{col} > 0" if "tier1" in field or "tier1" in col else f"{col} IS NOT NULL"
        try:
            cur.execute(f"SELECT count(*) FILTER (WHERE {pred}) FROM {table}")
            current = cur.fetchone()[0]
        except Exception as e:
            results.append((field, f"{table}.{col}", base, "ERR", status, f"⚠️ query error: {str(e)[:40]}"))
            continue

        if status in LIVE:
            # LIVE must not regress below 95% of its recorded baseline
            if base is not None and current < base * 0.95:
                verdict = f"❌ REGRESSED  ({current} < baseline {base})"
                regressions += 1
            else:
                verdict = "✅ ok"
        else:
            # broken/in-progress field: just watch it climb as we fix it
            delta = "" if base is None else f"  (baseline {base})"
            verdict = f"… watch [{status}]{delta}"
        results.append((field, f"{table}.{col}", base, current, status, verdict))

    # optional: rewrite baselines from reality
    if "--update-baselines" in FLAGS:
        for r in rows:
            for f, src, base, cur_n, st, v in results:
                if r.get("field","").strip()==f and isinstance(cur_n,int):
                    r["coverage_now"] = str(cur_n)
        with open(CONTRACT,"w",newline="",encoding="utf-8") as fh:
            w=csv.DictWriter(fh,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
        print(f"baselines rewritten from live coverage -> {CONTRACT}\n")

    # ---- report ----
    print(f"\nDATA CONTRACT HEALTH-CHECK  ({CONTRACT})\n" + "="*78)
    print(f"{'FIELD':24}{'SOURCE':34}{'base':>6}{'now':>7}  VERDICT")
    print("-"*78)
    for f, src, base, cur_n, st, v in results:
        b = "" if base is None else str(base)
        n = "" if cur_n is None else str(cur_n)
        print(f"{f[:23]:24}{src[:33]:34}{b:>6}{n:>7}  {v}")
    live = sum(1 for *_,st,_ in results if st in LIVE)
    print("-"*78)
    print(f"{live} LIVE fields checked | {regressions} regression(s)/schema-break(s)")
    if regressions:
        print("\n❌ FAIL — a LIVE field regressed or its column vanished. Fix before shipping.")
        sys.exit(1)
    print("\n✅ PASS — no LIVE field regressed.")
    sys.exit(0)

if __name__ == "__main__":
    main()
