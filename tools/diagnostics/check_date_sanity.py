#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_date_sanity.py — GUARDRAIL D: IPO dates can lie (scraped). Flag
contradictions BEFORE they reach a card (Caliber "open" when not open, SBI in
Upcoming while closed). Runs in lean after the build, before the API serves.
Writes offenders to pipeline_failures; --strict exits 1 to fail the step.
"""
import os, sys, argparse
import psycopg2

CHECKS = [
    ("open_after_close", """SELECT company_name, ipo_open_date, ipo_close_date
        FROM ipo_consolidated
        WHERE ipo_open_date IS NOT NULL AND ipo_close_date IS NOT NULL
          AND ipo_open_date > ipo_close_date"""),
    ("close_after_listing", """SELECT company_name, ipo_close_date, listing_date
        FROM ipo_consolidated
        WHERE ipo_close_date IS NOT NULL AND listing_date IS NOT NULL
          AND ipo_close_date > listing_date"""),
    ("listed_but_marked_open", """SELECT company_name, listing_date
        FROM ipo_consolidated
        WHERE listing_date < (now() AT TIME ZONE 'Asia/Kolkata')::date
          AND ipo_close_date >= (now() AT TIME ZONE 'Asia/Kolkata')::date"""),
]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    offenders = []
    for name, q in CHECKS:
        try:
            cur.execute(q)
            for row in cur.fetchall():
                offenders.append(f"{name}: {row}")
        except Exception as e:
            offenders.append(f"{name}: CHECK ERROR {str(e)[:80]}"); conn.rollback()
    if offenders:
        note = "DATE SANITY — " + " | ".join(offenders[:10])
        try:
            cur.execute("INSERT INTO pipeline_failures (step, script, stderr_tail) VALUES (%s,%s,%s)",
                        ("date sanity gate", "check_date_sanity.py", note[:490]))
            conn.commit()
        except Exception:
            pass
        print(f"DATE SANITY: {len(offenders)} contradiction(s):")
        for o in offenders: print("  " + o)
        conn.close()
        sys.exit(1 if a.strict else 0)
    print("DATE SANITY: clean — no date contradictions")
    conn.close()

if __name__ == "__main__":
    main()
