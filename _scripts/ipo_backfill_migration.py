"""
_scripts/ipo_backfill_migration.py
Migrates ipo_history (333 IPOs) into ipo_intelligence with LQI pre-computed.

Usage:
  python _scripts/ipo_backfill_migration.py
  python _scripts/ipo_backfill_migration.py --dry-run
"""

import os
import sys
import json
import argparse
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true")
args = parser.parse_args()

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require",
                            cursor_factory=psycopg2.extras.RealDictCursor)

# ── Scoring functions (inline so script is self-contained) ────────────────────

def score_retail_allocation(ofs_pct):
    # ofs_pct is OFS %, higher OFS = more retail pressure
    if ofs_pct is None: return 7.5
    fresh_ratio = 1 - (float(ofs_pct) / 100)
    if fresh_ratio >= 0.75: return 15.0
    if fresh_ratio >= 0.40: return 10.0
    return 5.0

def score_qib_retail(qib_x, retail_x):
    if not qib_x or not retail_x or float(retail_x) == 0: return 5.0
    ratio = float(qib_x) / float(retail_x)
    if ratio >= 3.0: return 15.0
    if ratio >= 1.0: return 10.0
    return 0.0

def score_qib_strength(qib_x):
    if qib_x is None: return 3.0
    q = float(qib_x)
    if q >= 50: return 10.0
    if q >= 20: return 7.0
    if q >= 5:  return 4.0
    return 0.0

def score_anchor(anchor_score):
    # anchor_score is already 0-10 in ipo_history
    if anchor_score is None: return 5.0
    a = float(anchor_score)
    if a >= 8: return 15.0
    if a >= 5: return 10.0
    if a >= 3: return 5.0
    return 0.0

def score_gmp(gmp_pct):
    if gmp_pct is None: return 3.0
    g = float(gmp_pct)
    if g >= 25: return 10.0
    if g >= 10: return 7.0
    if g >= 0:  return 3.0
    return -5.0

def score_gmp_momentum(gmp_min, gmp_max):
    # If gmp rose from min to max = RISING
    if gmp_min is None or gmp_max is None: return 5.0
    diff = float(gmp_max) - float(gmp_min)
    if diff > 10:  return 15.0   # rising
    if diff > -5:  return 7.0    # stable
    if diff > -20: return -10.0  # falling
    return -20.0                  # crashing

def score_nifty_regime(market_regime):
    r = (market_regime or "").upper()
    if "BULL" in r or "ABOVE" in r: return 10.0
    if "BEAR" in r or "BELOW" in r: return 0.0
    return 7.0  # neutral/sideways

def score_sector_heat(sector, market_regime):
    # Simplified — use market regime as proxy
    r = (market_regime or "").upper()
    if "BULL" in r: return 8.0
    if "SIDE" in r: return 5.0
    return 3.0

def compute_lqi_from_history(row):
    """Compute LQI from ipo_history row structure."""
    ofs_pct = float(row.get("ofs_pct") or 0)
    fresh_ratio = 1 - (ofs_pct / 100)

    s_retail    = score_retail_allocation(ofs_pct)
    s_fresh     = (15.0 if fresh_ratio >= 0.75 else 10.0 if fresh_ratio >= 0.40 else 0.0)
    s_qib_ret   = score_qib_retail(row.get("qib_x"), row.get("retail_x"))
    s_anchor    = score_anchor(row.get("anchor_score"))
    s_qib_str   = score_qib_strength(row.get("qib_x"))
    s_val       = 5.0   # unknown valuation premium — neutral
    s_brlm      = 5.0   # unknown BRLM — neutral
    s_gmp       = score_gmp(row.get("gmp_pct_of_issue"))
    s_gmp_mom   = score_gmp_momentum(row.get("gmp_min"), row.get("gmp_max"))
    s_gmp_vol   = 3.0   # neutral
    s_nifty     = score_nifty_regime(row.get("market_regime"))
    s_sector    = score_sector_heat(row.get("sector"), row.get("market_regime"))
    s_breadth   = 3.0   # neutral

    raw = sum([s_retail, s_fresh, s_qib_ret, s_anchor, s_qib_str,
               s_val, s_brlm, s_gmp, s_gmp_mom, s_gmp_vol,
               s_nifty, s_sector, s_breadth])

    lqi_base = max(0, min(100, raw / 150 * 100))

    above_ema = "BULL" in (row.get("market_regime") or "").upper()
    regime_mult = 1.00 if above_ema else 0.80
    lqi_final = min(100, lqi_base * regime_mult)

    if lqi_final >= 80:   archetype = "MOMENTUM_CHASE"
    elif lqi_final >= 60: archetype = "VALUE_DIP"
    elif lqi_final >= 40: archetype = "TACTICAL"
    else:                 archetype = "AVOID"

    return {
        "scores": {
            "retail_alloc": s_retail, "fresh_issue": s_fresh,
            "qib_retail": s_qib_ret, "anchor": s_anchor,
            "qib_strength": s_qib_str, "valuation": s_val,
            "brlm": s_brlm, "gmp_current": s_gmp,
            "gmp_momentum": s_gmp_mom, "gmp_volatility": s_gmp_vol,
            "nifty_regime": s_nifty, "sector_heat": s_sector,
            "ipo_breadth": s_breadth,
        },
        "raw_score": raw,
        "lqi_base": round(lqi_base, 2),
        "regime_multiplier": regime_mult,
        "lqi_final": round(lqi_final, 2),
        "archetype": archetype,
        "nifty_above_ema200": above_ema,
        "fresh_issue_ratio": round(fresh_ratio, 4),
        "qib_to_retail_ratio": float(row.get("qib_x") or 0) / max(float(row.get("retail_x") or 1), 0.1),
    }

def main():
    print("═" * 55)
    print("  AACapital — IPO History Migration to ipo_intelligence")
    print("═" * 55)

    conn = get_conn()
    cur  = conn.cursor()

    # Load all ipo_history rows
    cur.execute("""
        SELECT * FROM ipo_history
        ORDER BY year, name
    """)
    rows = [dict(r) for r in cur.fetchall()]
    print(f"\n  Found {len(rows)} IPOs in ipo_history\n")

    ok = 0
    skip = 0
    failed = 0

    for row in rows:
        name = row.get("name", "Unknown")
        year = row.get("year")

        # Compute LQI
        try:
            lqi = compute_lqi_from_history(row)
        except Exception as e:
            print(f"  ✗ Score failed {name}: {e}")
            failed += 1
            continue

        # Map outcomes
        listing_gain  = row.get("listing_gain_pct")
        d1_gain       = row.get("d1_close_gain_pct")
        listing_price = row.get("listing_price")
        issue_price   = row.get("issue_price")

        r_listing = float(listing_gain) / 100 if listing_gain is not None else None
        r_day1    = float(d1_gain) / 100 if d1_gain is not None else r_listing
        achieved  = r_day1 is not None and r_day1 >= 0.10

        # Approximate listing date from year
        listing_date = f"{year}-01-01" if year else None

        # Build insert
        data = {
            "company_name":         name,
            "sector":               row.get("sector"),
            "issue_price":          row.get("issue_price"),
            "listing_price":        listing_price,
            "listing_open":         listing_price,  # approximation
            "fresh_issue_ratio":    lqi["fresh_issue_ratio"],
            "qib_subscription_x":   row.get("qib_x"),
            "nii_subscription_x":   row.get("nii_x"),
            "rii_subscription_x":   row.get("retail_x"),
            "total_subscription_x": row.get("total_x"),
            "qib_to_retail_ratio":  round(lqi["qib_to_retail_ratio"], 4),
            "anchor_quality":       "STRONG" if float(row.get("anchor_score") or 0) >= 7 else "MIXED" if float(row.get("anchor_score") or 0) >= 4 else "WEAK",
            "gmp_pct_t1":           row.get("gmp_pct_of_issue"),
            "gmp_momentum":         "RISING" if (row.get("gmp_max") or 0) > (row.get("gmp_min") or 0) else "STABLE",
            "nifty_above_ema200":   lqi["nifty_above_ema200"],
            "market_regime_str":    row.get("market_regime"),
            # LQI scores
            "score_retail_alloc":   lqi["scores"]["retail_alloc"],
            "score_fresh_issue":    lqi["scores"]["fresh_issue"],
            "score_qib_retail_ratio": lqi["scores"]["qib_retail"],
            "score_anchor":         lqi["scores"]["anchor"],
            "score_qib_strength":   lqi["scores"]["qib_strength"],
            "score_valuation":      lqi["scores"]["valuation"],
            "score_brlm":           lqi["scores"]["brlm"],
            "score_gmp_current":    lqi["scores"]["gmp_current"],
            "score_gmp_momentum":   lqi["scores"]["gmp_momentum"],
            "score_gmp_volatility": lqi["scores"]["gmp_volatility"],
            "score_nifty_regime":   lqi["scores"]["nifty_regime"],
            "score_sector_heat":    lqi["scores"]["sector_heat"],
            "score_ipo_breadth":    lqi["scores"]["ipo_breadth"],
            "raw_score":            lqi["raw_score"],
            "lqi_base":             lqi["lqi_base"],
            "regime_multiplier":    lqi["regime_multiplier"],
            "lqi_final":            lqi["lqi_final"],
            "archetype":            lqi["archetype"],
            # Outcomes
            "return_listing_open":  r_listing,
            "return_day1_close":    r_day1,
            "achieved_10pct":       achieved,
            "is_backtest":          True,
            "data_source":          "ipo_history_migration",
        }

        if args.dry_run:
            print(f"  [DRY] {name[:35]:<35} LQI={lqi['lqi_final']:5.1f}  {lqi['archetype']:<18}  D1={r_day1*100:+.1f}%" if r_day1 is not None else f"  [DRY] {name[:35]:<35} LQI={lqi['lqi_final']:5.1f}  {lqi['archetype']}")
            ok += 1
            continue

        try:
            # Filter to only columns that exist in ipo_intelligence
            valid_cols = [
                "company_name","sector","issue_price","listing_price","listing_open",
                "fresh_issue_ratio","qib_subscription_x","nii_subscription_x",
                "rii_subscription_x","total_subscription_x","qib_to_retail_ratio",
                "anchor_quality","gmp_pct_t1","gmp_momentum","nifty_above_ema200",
                "score_retail_alloc","score_fresh_issue","score_qib_retail_ratio",
                "score_anchor","score_qib_strength","score_valuation","score_brlm",
                "score_gmp_current","score_gmp_momentum","score_gmp_volatility",
                "score_nifty_regime","score_sector_heat","score_ipo_breadth",
                "raw_score","lqi_base","regime_multiplier","lqi_final","archetype",
                "return_listing_open","return_day1_close","achieved_10pct",
                "is_backtest","data_source",
            ]
            insert_data = {k: data[k] for k in valid_cols if k in data}
            cols = list(insert_data.keys())
            vals = list(insert_data.values())

            cur.execute(f"""
                INSERT INTO ipo_intelligence ({', '.join(cols)})
                VALUES ({', '.join(['%s']*len(cols))})
                ON CONFLICT DO NOTHING
            """, vals)
            ok += 1
        except Exception as e:
            print(f"  ✗ Insert failed {name}: {e}")
            failed += 1
            conn.rollback()
            continue

    if not args.dry_run:
        conn.commit()

    cur.close()
    conn.close()

    print(f"\n{'═'*55}")
    print(f"  Migrated : {ok}")
    print(f"  Failed   : {failed}")
    print(f"  Mode     : {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"\n✅ Done")

    if not args.dry_run:
        print(f"\nNext steps:")
        print(f"  python _scripts/engines/ipo_intelligence_engine.py --mode=backtest")

if __name__ == "__main__":
    main()
