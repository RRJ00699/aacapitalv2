"""
analyze_qib_pattern.py  —  Does "high QIB + weak HNI + good anchor" actually list well?

Runs against YOUR Neon ipo_intelligence table (has the subscription numbers + returns).
Tests the Turtlemint-style thesis honestly: shows the FULL distribution, not the winners.

Run locally:
    python analyze_qib_pattern.py
(uses DATABASE_URL / NEON_DATABASE_URL from your env)
"""
import os, numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

DB = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
if not DB:
    raise SystemExit("Set DATABASE_URL (or NEON_DATABASE_URL) first.")

conn = psycopg2.connect(DB)
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("""
    SELECT company_name, symbol,
           qib_subscription_x  AS qib,
           nii_subscription_x  AS nii,
           rii_subscription_x  AS rii,
           anchor_tier1_count  AS atc,
           return_day1_close   AS r1,
           return_day7         AS r7,
           return_day30        AS r30
    FROM ipo_intelligence
    WHERE COALESCE(is_sme,false) = false
      AND return_day1_close IS NOT NULL
""")
rows = cur.fetchall()
cur.close(); conn.close()

def col(rows, k):
    return np.array([float(r[k]) for r in rows if r[k] is not None], dtype=float)

# auto-detect whether returns are stored as fraction (0.4) or percent (40)
_all = col(rows, "r1")
SCALE = 100.0 if np.nanmedian(np.abs(_all)) > 2 else 1.0   # -> express as fraction
def rets(subset, k):
    a = np.array([float(r[k]) for r in subset if r[k] is not None], dtype=float) / SCALE
    return a

def show(subset, label):
    if not subset:
        print(f"  {label}: n=0"); return
    print(f"  {label}  (n={len(subset)})")
    for k, lbl in [("r1","listing day"), ("r7","~1 week"), ("r30","~1 month")]:
        a = rets(subset, k)
        if len(a) == 0:
            print(f"     {lbl:11s} n=0"); continue
        print(f"     {lbl:11s} n={len(a):3d}  avg={a.mean()*100:6.1f}%  median={np.median(a)*100:6.1f}%"
              f"  win={(a>0).mean()*100:3.0f}%  >=40%={(a>=0.40).mean()*100:4.1f}%"
              f"  lost={(a<0).mean()*100:3.0f}%  <-20%={(a<-0.20).mean()*100:4.1f}%")
    print()

print(f"Mainboard IPOs with subscription + returns: {len(rows)}  (returns scale auto = /{SCALE:g})\n")

show(rows, "BASELINE — all mainboard IPOs")

# Your thesis: QIB-heavy, HNI(NII)-weak
patt = [r for r in rows if r["qib"] is not None and r["nii"] is not None
        and float(r["qib"]) >= 50 and float(r["nii"]) <= 15]
show(patt, "QIB>=50x  AND  NII<=15x")

# Closer to Turtlemint's shape (QIB ~200x, NII ~7x)
strict = [r for r in rows if r["qib"] is not None and r["nii"] is not None
          and float(r["qib"]) >= 100 and float(r["nii"]) <= 10]
show(strict, "QIB>=100x AND NII<=10x  (Turtlemint-like)")

# Add the anchor-quality condition on top
anch = [r for r in strict if r["atc"] is not None and float(r["atc"]) >= 2]
show(anch, "  + Tier-1 anchors >= 2")

# Honest reference: how does the SAME-period baseline compare? If the pattern's
# numbers look like the baseline, the pattern adds nothing.
print("READ IT HONESTLY:")
print(" - Compare each pattern row to BASELINE. If win% / avg / >=40% are ~the same,")
print("   the subscription shape is NOT separating winners — it's just bull-market drift.")
print(" - 'lost%' and '<-20%' are your real downside base rates. That's the risk you take.")
print(" - High QIB is the NORM for hyped IPOs, so it rarely differentiates. Let the n and")
print("   the spread decide — not the few 40-50% pops you remember.")
