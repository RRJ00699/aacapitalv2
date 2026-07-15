#!/usr/bin/env python3
"""
compute_flags.py — red-flag / green-check scanner. Writes ipo_flags
(company_name PK) with: red_flags (text[]), green_checks (text[]),
red_count, green_count. Read by the command card.

Sources (all present tables — no dead-table deps):
  - ipo_rhp_intel governance flags (the forensic moat)
  - ipo_intelligence basic thresholds (size, OFS, PE vs peer, QIB, debt)

DERIVED -> DO UPDATE (Rule 1). Does NOT touch ipo_intelligence. DRY-RUN default.
  venv/bin/python _scripts/compute_flags.py            # dry
  venv/bin/python _scripts/compute_flags.py --apply    # write
"""
import os, sys, argparse

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

def fnum(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def scan(r):
    red, green = [], []
    size = fnum(r.get("issue_size_cr")); ofs = fnum(r.get("ofs_pct"))
    pe = fnum(r.get("ipo_pe")); ppe = fnum(r.get("peer_median_pe"))
    qib = fnum(r.get("final_qib")); de = fnum(r.get("debt_equity"))
    # RHP governance red flags (hard)
    if r.get("auditor_qualified"): red.append("auditor qualified opinion")
    if r.get("sebi_action"): red.append("SEBI action on record")
    if r.get("criminal_litigation"): red.append("criminal litigation")
    if r.get("promoter_pledge_flag"): red.append("promoter shares pledged")
    if r.get("related_party_concern"): red.append("related-party concern")
    if r.get("customer_concentration_high"): red.append("customer concentration high")
    if r.get("contingent_liabilities_material"): red.append("material contingent liabilities")
    if (r.get("numbers_integrity_flag") or "") not in ("", "clean", None):
        red.append("numbers-integrity concern")
    # quantitative red flags
    if size is not None and size < 200: red.append(f"tiny issue Rs.{size:.0f}cr (<200cr junk floor)")
    if ofs is not None and ofs > 60: red.append(f"OFS-heavy {ofs:.0f}% (promoters cashing out)")
    if pe is not None and ppe and ppe > 0 and pe > ppe*2.5: red.append(f"PE {pe:.0f} vs peer {ppe:.0f} (expensive)")
    if de is not None and de > 2: red.append(f"high leverage (D/E {de:.1f})")
    # green checks
    if size is not None and size >= 2000: green.append("mega issue (>Rs.2000cr)")
    if ofs is not None and ofs < 30: green.append("fresh-issue heavy (<30% OFS)")
    if qib is not None and qib >= 10: green.append(f"strong QIB ({qib:.0f}x)")
    if pe is not None and ppe and ppe > 0 and pe < ppe*0.9: green.append("cheaper than peers")
    if de is not None and de <= 0.3: green.append("low debt (D/E <=0.3)")
    if r.get("rhp_verdict") and not red: green.append("RHP forensic clean")
    return red, green

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(DB, connect_timeout=20)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if a.apply:
        cur.execute("""CREATE TABLE IF NOT EXISTS ipo_flags (
            company_name text PRIMARY KEY, red_flags text[], green_checks text[],
            red_count int, green_count int, computed_at timestamptz DEFAULT now())""")
        conn.commit()
    # Introspect real columns first — missing ones resolve to NULL (no crash).
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    ii = {r["column_name"] for r in cur.fetchall()}
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_rhp_intel'")
    ri = {r["column_name"] for r in cur.fetchall()}
    def ic(name):
        return f"i.{name} AS {name}" if name in ii else f"NULL AS {name}"
    def rc(name, alias=None):
        a = alias or name
        return f"ri.{name} AS {a}" if name in ri else f"NULL AS {a}"
    cols = ["i.company_name",
            ic("issue_size_cr"), ic("ofs_pct"), ic("ipo_pe"), ic("peer_median_pe"),
            ic("final_qib"), ic("debt_equity"),
            rc("verdict", "rhp_verdict"), rc("auditor_qualified"), rc("sebi_action"),
            rc("criminal_litigation"), rc("promoter_pledge_flag"), rc("related_party_concern"),
            rc("customer_concentration_high"), rc("contingent_liabilities_material"),
            rc("numbers_integrity_flag")]
    cur.execute(f"""
        SELECT {", ".join(cols)}
        FROM ipo_intelligence i
        LEFT JOIN ipo_rhp_intel ri ON ri.company_name = i.company_name
        WHERE i.company_name IS NOT NULL
    """)
    wrote = 0
    for r in cur.fetchall():
        red, green = scan(r)
        if a.apply:
            cur.execute("""
                INSERT INTO ipo_flags (company_name, red_flags, green_checks,
                    red_count, green_count, computed_at)
                VALUES (%s,%s,%s,%s,%s, now())
                ON CONFLICT (company_name) DO UPDATE SET
                    red_flags=EXCLUDED.red_flags, green_checks=EXCLUDED.green_checks,
                    red_count=EXCLUDED.red_count, green_count=EXCLUDED.green_count,
                    computed_at=now()
            """, (r["company_name"], red, green, len(red), len(green)))
            wrote += 1
    if a.apply:
        conn.commit(); print(f"applied — {wrote} flag rows written.")
    else:
        print(f"dry run — would scan {cur.rowcount} IPOs.")
    conn.close()

if __name__ == "__main__":
    main()
