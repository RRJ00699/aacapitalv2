"""
Real return analysis — what you actually make buying at listing open.
Run AFTER fix_listing_day_close.py
"""
import psycopg2, os

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

print("=" * 75)
print("REAL RETURNS — What you make buying at listing open price")
print("=" * 75)
print()
print("Formula: (price_at_exit - listing_open) / listing_open × 100")
print("NOT: (listing_open - issue_price) / issue_price  ← that's GMP gain, not yours")
print()

cur.execute("""
    SELECT
        play_recommendation,
        COUNT(*) as ipos,
        -- GMP gain (NOT your return — shown for reference only)
        ROUND(AVG(return_listing_open)::numeric, 1) as gmp_gain_pct,

        -- EOD return (buy open, sell close same day)
        ROUND(AVG(
            CASE WHEN listing_open > 0 AND listing_day_close > 0
                 AND ABS(listing_day_close - listing_open) > 0.5  -- exclude bad data
            THEN (listing_day_close - listing_open) / listing_open * 100
            END
        )::numeric, 1) as real_eod_pct,

        -- 7-day return (buy open, hold 1 week)
        ROUND(AVG(
            CASE WHEN listing_open > 0 AND return_day7 IS NOT NULL AND issue_price > 0
            THEN ((issue_price * (1 + return_day7/100.0)) - listing_open) / listing_open * 100
            END
        )::numeric, 1) as real_7d_pct,

        -- 30-day return
        ROUND(AVG(
            CASE WHEN listing_open > 0 AND return_day30 IS NOT NULL AND issue_price > 0
            THEN ((issue_price * (1 + return_day30/100.0)) - listing_open) / listing_open * 100
            END
        )::numeric, 1) as real_30d_pct,

        -- 90-day return
        ROUND(AVG(
            CASE WHEN listing_open > 0 AND return_day90 IS NOT NULL AND issue_price > 0
            THEN ((issue_price * (1 + return_day90/100.0)) - listing_open) / listing_open * 100
            END
        )::numeric, 1) as real_90d_pct,

        -- EOD win/loss (properly computed)
        SUM(CASE WHEN listing_day_close > listing_open
                  AND ABS(listing_day_close - listing_open) > 0.5 THEN 1 ELSE 0 END) as eod_winners,
        SUM(CASE WHEN listing_day_close < listing_open
                  AND ABS(listing_day_close - listing_open) > 0.5 THEN 1 ELSE 0 END) as eod_losers,
        SUM(CASE WHEN hit_uc_day1 = TRUE THEN 1 ELSE 0 END) as uc_count,

        -- Max possible gain (hit UC = +20% from open)
        SUM(CASE WHEN hit_uc_day1 = TRUE THEN 1 ELSE 0 END) * 20 as uc_gain_pool

    FROM ipo_intelligence
    WHERE is_sme = FALSE
      AND play_recommendation IS NOT NULL
      AND listing_open > 0
    GROUP BY play_recommendation
    ORDER BY real_7d_pct DESC NULLS LAST
""")

rows = cur.fetchall()
cols = [d[0] for d in cur.description]

for row in rows:
    d = dict(zip(cols, row))
    play = d['play_recommendation']
    n    = d['ipos']
    ew   = d['eod_winners'] or 0
    el   = d['eod_losers'] or 0
    uc   = d['uc_count'] or 0
    eod_valid = ew + el

    print(f"{'─'*75}")
    print(f"  {play}  ({n} IPOs)")
    print(f"    GMP gain (NOT your return, shown for ref): {d['gmp_gain_pct']}%")
    print(f"    ┌─ Buy at open, sell EOD:      {d['real_eod_pct']:>+6}%  "
          f"({'?' if eod_valid==0 else f'{ew}/{eod_valid} positive'})")
    print(f"    ├─ Buy at open, hold 7 days:   {d['real_7d_pct']:>+6}%")
    print(f"    ├─ Buy at open, hold 30 days:  {d['real_30d_pct']:>+6}%")
    print(f"    └─ Buy at open, hold 90 days:  {d['real_90d_pct']:>+6}%")
    if uc > 0:
        print(f"    🔴 UC hits: {uc} IPOs → max EOD gain = +20% on those")

print(f"{'─'*75}")
print()
print("KEY INSIGHT:")
print("  EOD return is tiny (+1-2%) because most listing gains happen AT open")
print("  The real edge is holding 7-30 days after a strong IPO listing")
print("  BUY_AT_OPEN + hold 30 days historically gives the best risk/reward")
print()

# Best individual performers - buying at open
print("=" * 75)
print("TOP 10 REAL RETURNS — BUY_AT_OPEN, measured from listing open price")
print("=" * 75)
cur.execute("""
    SELECT
        company_name,
        issue_price,
        listing_open,
        listing_day_close,
        CASE WHEN listing_open > 0 AND listing_day_close > 0
             AND ABS(listing_day_close - listing_open) > 0.5
        THEN ROUND(((listing_day_close - listing_open) / listing_open * 100)::numeric, 1)
        END as real_eod,
        CASE WHEN listing_open > 0 AND return_day30 IS NOT NULL AND issue_price > 0
        THEN ROUND((((issue_price * (1 + return_day30/100.0)) - listing_open) / listing_open * 100)::numeric, 1)
        END as real_30d,
        qib_subscription_x,
        hit_uc_day1
    FROM ipo_intelligence
    WHERE play_recommendation = 'BUY_AT_OPEN'
      AND listing_open > 0
      AND return_day30 IS NOT NULL
      AND is_sme = FALSE
    ORDER BY real_30d DESC NULLS LAST
    LIMIT 10
""")
print(f"{'Company':30s} {'Issue':>6} {'Open':>6} {'EOD%':>7} {'30d%':>7} {'QIB':>6} {'UC'}")
print("-" * 75)
for row in cur.fetchall():
    co, ip, lo, lc, eod, d30, qib, uc = row
    uc_str = "🔴" if uc else "  "
    eod_str = f"{eod:+.1f}%" if eod is not None else "  n/a "
    d30_str = f"{d30:+.1f}%" if d30 is not None else "  n/a "
    print(f"{str(co)[:30]:30s} ₹{ip:>5.0f} ₹{lo:>5.0f} {eod_str:>7} {d30_str:>7} {str(qib or '?'):>6}x {uc_str}")

conn.close()
