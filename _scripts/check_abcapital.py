"""check_abcapital.py - diagnose why ABCAPITAL misses multibagger"""
import psycopg2, os

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

print("="*60)
print("ABCAPITAL — ENGINE DIAGNOSIS")
print("="*60)

# 1. Technical signals - using REAL column names
cur.execute("""
    SELECT symbol, signal, buy_zone_score, mb_score, conviction,
           nr7, volume_ratio_20, rsi, monthly_rsi,
           price_above_ema30, all_criteria_met,
           updated_at
    FROM technical_signals
    WHERE symbol = 'ABCAPITAL'
    LIMIT 1
""")
row = cur.fetchone()
if row:
    cols = [d[0] for d in cur.description]
    d = dict(zip(cols, row))
    print(f"\n1. TECHNICAL SIGNALS (updated: {d['updated_at']}):")
    print(f"   Signal:          {d['signal']}")
    print(f"   Buy zone score:  {d['buy_zone_score']} / 10")
    print(f"   MB score:        {d['mb_score']}")
    print(f"   Conviction:      {d['conviction']}")
    print(f"   NR7:             {d['nr7']}")
    print(f"   Volume ratio:    {d['volume_ratio_20']}x  (today was 2.5x — is this stale?)")
    print(f"   RSI:             {d['rsi']}")
    print(f"   Monthly RSI:     {d['monthly_rsi']}")
    print(f"   Above EMA30:     {d['price_above_ema30']}")
    print(f"   All criteria:    {d['all_criteria_met']}")
    
    print(f"\n   WHY IT MISSED MULTIBAGGER:")
    if not d['all_criteria_met']:
        print(f"   → all_criteria_met = False")
    if not d['price_above_ema30']:
        print(f"   → price_above_ema30 = False (price below EMA in our data)")
    score = float(d['mb_score'] or 0)
    if score < 40:
        print(f"   → mb_score = {score} (needs >= 40 for multibagger filter)")
else:
    print("   ❌ NOT IN technical_signals")

# 2. Shareholding (just scraped)
cur.execute("""
    SELECT quarter, promoter_pct, fii_pct, dii_pct, mf_pct, public_pct, pledged_pct
    FROM shareholding_history
    WHERE nse_symbol = 'ABCAPITAL'
    ORDER BY quarter DESC LIMIT 3
""")
rows = cur.fetchall()
print(f"\n2. SHAREHOLDING:")
if rows:
    for r in rows:
        print(f"   {r[0]}: Promoter {r[1]}%  FII {r[2]}%  DII {r[3]}%  MF {r[4]}%")
    print(f"   ✅ FII {rows[0][2]}% = real institutional holding")
    print(f"   Before fix: FII showed 0% → Smart Money = Distribution (wrong!)")
else:
    print("   ❌ No shareholding data")

# 3. Price candles
cur.execute("""
    SELECT COUNT(*) as n, MAX(date) as latest, 
           MAX(CASE WHEN date = (SELECT MAX(date) FROM price_candles WHERE symbol='ABCAPITAL') THEN close END) as last_close
    FROM price_candles WHERE symbol = 'ABCAPITAL'
""")
row = cur.fetchone()
print(f"\n3. PRICE CANDLES: {row[0]} rows, latest: {row[1]}, last close: ₹{row[2]}")
if row[0] == 0:
    print("   ❌ NO CANDLE DATA — signals engine has no price to work with!")
    print("   FIX: python _scripts/kite-sync-candles.py --symbol ABCAPITAL")

# 4. Management commentary
cur.execute("""
    SELECT sentiment_score, tone, updated_at 
    FROM management_commentary_scores 
    WHERE nse_symbol = 'ABCAPITAL' OR symbol = 'ABCAPITAL'
    LIMIT 1
""")
row = cur.fetchone()
print(f"\n4. MANAGEMENT COMMENTARY:")
if row:
    print(f"   Score: {row[0]}  Tone: {row[1]}  Updated: {row[2]}")
else:
    print("   ❌ NOT SCORED → Mgmt quality shows 10/100")
    print("   FIX: set SCREENER_USERNAME/PASSWORD in .env.local then:")
    print("        python _scripts/score_management_commentary.py --symbols ABCAPITAL")

# 5. What score needs to be to appear
print(f"\n5. TO APPEAR IN MULTIBAGGER:")
print(f"   Need: mb_score >= 40 AND signal = 'above' (or price_above_ema30 = true)")
print(f"   The 65% delivery + 2.5x volume + ATH = strong setup the engine should catch")
print(f"   Main blockers: missing candle data, stale signals, missing commentary")

conn.close()
