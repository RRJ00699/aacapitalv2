import psycopg2, os, math

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# First — understand exactly what columns we have and what they mean
cur.execute("""
    SELECT 
        company_name,
        issue_price,
        listing_open,
        listing_day_close,
        return_listing_open,   -- (listing_open - issue_price) / issue_price × 100
        return_day1_close,     -- (listing_day_close - issue_price) / issue_price × 100
        -- The REAL return if you BUY at listing open:
        CASE WHEN listing_open > 0 AND listing_day_close > 0
            THEN ROUND(((listing_day_close - listing_open) / listing_open * 100)::numeric, 2)
        END as real_buy_at_open_return,
        -- Return from open to Day7
        CASE WHEN listing_open > 0 AND return_day7 IS NOT NULL
            THEN ROUND((((issue_price * (1 + return_day7/100)) - listing_open) / listing_open * 100)::numeric, 2)
        END as real_return_day7,
        play_recommendation,
        qib_subscription_x
    FROM ipo_intelligence
    WHERE listing_open > 0
      AND listing_day_close > 0
      AND is_sme = FALSE
      AND play_recommendation = 'BUY_AT_OPEN'
    ORDER BY listing_date DESC
    LIMIT 20
""")

rows = cur.fetchall()
print("SAMPLE BUY_AT_OPEN IPOs — Real return from listing open price:")
print(f"{'Company':35s} {'Issue':>6} {'Open':>6} {'D1Close':>7} {'GMP%':>6} {'REAL%':>7}")
print("-" * 75)
for r in rows:
    co, ip, lo, lc, ret_open, ret_d1, real_ret, real_d7, play, qib = r
    if ip and lo and lc:
        gmp_pct  = ret_open or 0
        real_pct = real_ret or 0
        print(f"{str(co)[:35]:35s} ₹{ip:>5.0f} ₹{lo:>5.0f} ₹{lc:>6.0f} "
              f"{gmp_pct:>+6.1f}% {real_pct:>+7.1f}%")

# Now aggregate properly
print("\n\n" + "="*70)
print("REAL RETURNS — Buying at listing open, selling EOD")
print("="*70)

cur.execute("""
    SELECT 
        play_recommendation,
        COUNT(*) as ipos,
        -- Wrong metric (what I was showing before)
        ROUND(AVG(return_listing_open)::numeric, 1) as wrong_avg_gmp_gain,
        -- Correct metric: buy at open, sell at day1 close
        ROUND(AVG(
            CASE WHEN listing_open > 0 AND listing_day_close > 0
                THEN (listing_day_close - listing_open) / listing_open * 100
            END
        )::numeric, 1) as real_avg_eod_return,
        -- Buy at open, hold 7 days
        ROUND(AVG(
            CASE WHEN listing_open > 0 AND return_day7 IS NOT NULL AND issue_price > 0
                THEN ((issue_price * (1 + return_day7/100)) - listing_open) / listing_open * 100
            END
        )::numeric, 1) as real_avg_day7_return,
        -- Buy at open, hold 30 days
        ROUND(AVG(
            CASE WHEN listing_open > 0 AND return_day30 IS NOT NULL AND issue_price > 0
                THEN ((issue_price * (1 + return_day30/100)) - listing_open) / listing_open * 100
            END
        )::numeric, 1) as real_avg_day30_return,
        -- Win rate: closed Day1 above open
        SUM(CASE WHEN listing_day_close > listing_open THEN 1 ELSE 0 END) as eod_winners,
        SUM(CASE WHEN listing_day_close < listing_open THEN 1 ELSE 0 END) as eod_losers,
        -- UC/LC stats
        SUM(CASE WHEN hit_uc_day1 THEN 1 ELSE 0 END) as hit_uc,
        SUM(CASE WHEN hit_lc_day1 THEN 1 ELSE 0 END) as hit_lc
    FROM ipo_intelligence
    WHERE listing_open > 0 AND listing_day_close > 0
      AND is_sme = FALSE AND play_recommendation IS NOT NULL
    GROUP BY play_recommendation
    ORDER BY real_avg_eod_return DESC NULLS LAST
""")

rows = cur.fetchall()
cols = [d[0] for d in cur.description]
for row in rows:
    d = dict(zip(cols, row))
    print(f"\n  {d['play_recommendation']} ({d['ipos']} IPOs)")
    print(f"    ❌ Wrong metric I used: avg GMP gain = {d['wrong_avg_gmp_gain']}%")
    print(f"    ✅ Real return (buy open, sell EOD):   {d['real_avg_eod_return']}%")
    print(f"    ✅ Real return (buy open, hold 7d):    {d['real_avg_day7_return']}%")
    print(f"    ✅ Real return (buy open, hold 30d):   {d['real_avg_day30_return']}%")
    print(f"    EOD winners: {d['eod_winners']} | EOD losers: {d['eod_losers']}")
    print(f"    Hit UC Day1: {d['hit_uc']} | Hit LC Day1: {d['hit_lc']}")

conn.close()
