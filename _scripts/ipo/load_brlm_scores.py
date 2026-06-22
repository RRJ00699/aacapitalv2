"""
load_brlm_scores.py  —  populates brlm_scores from the Chittorgarh "Lead Managers by
No. and Performance" yearly files (2021-2026). Fixes "only 5 managers showing": loads
ALL of them (78 across these years), aggregated.

Pipeline (matches your existing flow):
    python _scripts/ipo/load_brlm_scores.py     # rebuild brlm_scores from the files
    python link_brlm_scores.py                  # your existing: recalibrate score + link to ipo_intelligence

Place the six Lead_Managers_*.xlsx in data/Ipo_reports/ (alongside your other Chittorgarh exports).
"""
import psycopg2, os, glob
import pandas as pd
from collections import defaultdict

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
REPORT_DIR = "data/Ipo_reports"

def num(x):
    v = pd.to_numeric(x, errors="coerce")
    return 0 if pd.isna(v) else float(v)

def aggregate():
    agg = defaultdict(lambda: {"issues": 0.0, "neg": 0.0, "gain_w": 0.0, "amt": 0.0})
    files = glob.glob(os.path.join(REPORT_DIR, "Lead_Managers_*.xlsx"))
    if not files:
        raise SystemExit(f"No Lead_Managers_*.xlsx found in {REPORT_DIR}")
    for f in files:
        d = pd.read_excel(f, skiprows=2, header=None).iloc[:, :8]
        d.columns = ["name", "issues", "amt", "pos", "pos_pct", "neg", "neg_pct", "avg_gain"]
        for _, r in d.iterrows():
            n = str(r["name"]).strip()
            if not n or n.lower() in ("nan", "total") or "ipomatrix" in n.lower():
                continue
            iss = num(r["issues"])
            if iss <= 0:
                continue
            a = agg[n]
            a["issues"] += iss
            a["neg"]    += num(r["neg"])
            a["gain_w"] += num(r["avg_gain"]) * iss     # issue-weighted gain
            a["amt"]    += num(r["amt"])
    out = []
    for n, a in agg.items():
        if a["issues"] <= 0:
            continue
        out.append((n,
                    int(a["issues"]),
                    round(a["gain_w"] / a["issues"], 2),     # avg_listing
                    round(a["neg"] / a["issues"] * 100, 1),  # pct_negative
                    round(a["amt"], 2)))                     # issue_amount_cr
    return sorted(out, key=lambda x: -x[1])

def main():
    if not DATABASE_URL:
        raise SystemExit("Set DATABASE_URL (or NEON_DATABASE_URL) first.")
    rows = aggregate()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()

    # Ensure table + columns exist (idempotent; won't clobber an existing table).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS brlm_scores (
            brlm_name TEXT PRIMARY KEY, ipo_count INT, avg_listing NUMERIC,
            pct_negative NUMERIC, issue_amount_cr NUMERIC, score NUMERIC,
            updated_at TIMESTAMPTZ DEFAULT now())
    """)
    for col, typ in [("ipo_count","INT"),("avg_listing","NUMERIC"),("pct_negative","NUMERIC"),
                     ("issue_amount_cr","NUMERIC"),("score","NUMERIC"),
                     ("updated_at","TIMESTAMPTZ DEFAULT now()")]:
        cur.execute(f"ALTER TABLE brlm_scores ADD COLUMN IF NOT EXISTS {col} {typ}")
    conn.commit()

    # Full rebuild from the files (brlm_scores is a derived aggregate).
    cur.execute("DELETE FROM brlm_scores")
    for name, count, avg, pctneg, amt in rows:
        cur.execute("""
            INSERT INTO brlm_scores (brlm_name, ipo_count, avg_listing, pct_negative, issue_amount_cr, updated_at)
            VALUES (%s,%s,%s,%s,%s, now())
        """, (name, count, avg, pctneg, amt))
    conn.commit()
    print(f"brlm_scores rebuilt: {len(rows)} lead managers loaded (was ~5).")
    print("Top 5 by IPO count:")
    for name, count, avg, pctneg, amt in rows[:5]:
        print(f"  {name[:34]:34s} n={count:3d}  avg_listing={avg:5.1f}%  neg={pctneg:4.1f}%")
    print("\nNext: python link_brlm_scores.py   (recalibrates score + links to ipo_intelligence)")
    conn.close()

if __name__ == "__main__":
    main()
