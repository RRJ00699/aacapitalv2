"""
check_abcapital.py — uses real column names from DB
"""
import psycopg2, os

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

print("="*60)
print("ABCAPITAL — ENGINE DIAGNOSIS")
print("="*60)

# 1. Technical signals - real columns
cur.execute("""
    SELECT symbol, action_label, conviction, probability_score,
           buy_zone_score, mb_score, all_criteria_met,
           above_ema200, price_above_ema30, momentum_6m,
           vol_compression, is_nr7, daily_nr7,
           volume_ratio_20, stage, stage_label, pct_below_high,
           convergence_score, signal_date, updated_at
    FROM technical_signals
    WHERE symbol = 'ABCAPITAL'
    LIMIT 1
""")
row = cur.fetchone()
if row:
    d = dict(zip([c[0] for c in cur.description], row))
    print(f"\n1. TECHNICAL SIGNALS (as of {d['signal_date']}, updated {d['updated_at']}):")
    print(f"   Action label:    {d['action_label']}")
    print(f"   Conviction:      {d['conviction']}")
    print(f"   Probability:     {d['probability_score']}")
    print(f"   MB score:        {d['mb_score']} ← multibagger filter needs >= 40")
    print(f"   Buy zone score:  {d['buy_zone_score']}")
    print(f"   All criteria:    {d['all_criteria_met']}")
    print(f"   Above EMA200:    {d['above_ema200']}")
    print(f"   Above EMA30:     {d['price_above_ema30']}")
    print(f"   Is NR7:          {d['is_nr7']} / {d['daily_nr7']}")
    print(f"   Volume ratio:    {d['volume_ratio_20']}x")
    print(f"   Momentum 6M:     {d['momentum_6m']}%")
    print(f"   Stage:           {d['stage']} — {d['stage_label']}")
    print(f"   Vol compression: {d['vol_compression']}")
    print(f"   % below 52W hi:  {d['pct_below_high']}%")
    print(f"   Convergence:     {d['convergence_score']}")
    
    print(f"\n   VERDICT:")
    mb = float(d['mb_score'] or 0)
    if mb >= 40:
        print(f"   ✅ mb_score {mb} >= 40 — SHOULD appear in Multibagger")
        print(f"   ⚠️  Signal date {d['signal_date']} — may be stale (3 days old)")
        print(f"   → Re-run: python _scripts/generate_signals.py --symbols ABCAPITAL")
    else:
        print(f"   ❌ mb_score {mb} < 40 — filtered out of Multibagger")
        print(f"   Root cause: signals computed on {d['signal_date']} when data was missing")
else:
    print("   ❌ NOT IN technical_signals")

# 2. Shareholding
cur.execute("""
    SELECT quarter, promoter_pct, fii_pct, dii_pct, mf_pct
    FROM shareholding_history
    WHERE nse_symbol = 'ABCAPITAL'
    ORDER BY quarter DESC LIMIT 3
""")
rows = cur.fetchall()
print(f"\n2. SHAREHOLDING:")
if rows:
    for r in rows:
        print(f"   {r[0]}: Promoter {r[1]}%  FII {r[2]}%  DII {r[3]}%  MF {r[4]}%")
else:
    print("   ❌ No data")

# 3. Price candles
cur.execute("SELECT COUNT(*), MAX(date), MAX(close) FROM price_candles WHERE symbol='ABCAPITAL'")
r = cur.fetchone()
print(f"\n3. PRICE CANDLES: {r[0]} rows, latest {r[1]}, close ₹{r[2]}")
if r[0] == 0:
    print("   ❌ No candle data — Kite token needs refresh before sync")

# 4. Management commentary
cur.execute("""
    SELECT total_score, commentary_status, fiscal_quarter, updated_at
    FROM management_commentary_scores
    WHERE symbol = 'ABCAPITAL' LIMIT 1
""")
r = cur.fetchone()
print(f"\n4. MANAGEMENT COMMENTARY: {r if r else '❌ Not scored'}")

# 5. What needs to happen
print(f"\n5. ACTION PLAN:")
print(f"   a) Refresh Kite token: python _scripts/refresh_kite_token.py")
print(f"   b) Sync candles: python _scripts/kite-sync-candles.py --symbol ABCAPITAL --days 90")
print(f"   c) Regen signals: python _scripts/generate_signals.py --symbols ABCAPITAL")
print(f"   d) Score commentary: set SCREENER_USERNAME/PASSWORD in .env.local, then")
print(f"      python _scripts/score_management_commentary.py --symbols ABCAPITAL")

conn.close()
