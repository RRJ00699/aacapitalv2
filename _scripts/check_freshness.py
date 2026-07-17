#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_freshness.py — PILLAR 2: alert when a domain breaches its freshness SLA.
Reads data_lineage SLAs + data_freshness snapshots. Lean step; --strict exits 1.
"""
import os, sys, argparse, psycopg2
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    stale = []
    cur.execute("""
      SELECT f.domain, f.last_write, f.row_count,
             min(l.freshness_sla_hours) AS sla
      FROM data_freshness f
      LEFT JOIN data_lineage l ON TRUE
      GROUP BY f.domain, f.last_write, f.row_count""")
    for domain, last, cnt, sla in cur.fetchall():
        if cnt == 0:
            stale.append(f"{domain}: EMPTY (0 rows)")
        elif last is not None and sla is not None:
            cur.execute("SELECT EXTRACT(EPOCH FROM (NOW()-%s))/3600", (last,))
            age = cur.fetchone()[0]
            if age and age > float(sla):
                stale.append(f"{domain}: {age:.1f}h old (SLA {sla}h)")
    if stale:
        note = "FRESHNESS — " + " | ".join(stale)
        try:
            cur.execute("INSERT INTO pipeline_failures (step, script, stderr_tail) VALUES (%s,%s,%s)",
                        ("freshness monitor", "check_freshness.py", note[:490]))
            conn.commit()
        except Exception: pass
        print("FRESHNESS ALERT:"); [print("  "+s) for s in stale]
        conn.close(); sys.exit(1 if a.strict else 0)
    print("FRESHNESS: all domains within SLA")
    conn.close()
if __name__ == "__main__":
    main()
