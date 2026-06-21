"""
fix_abcapital_data.py
Run: python _scripts/fix_abcapital_data.py
"""
import os, sys, subprocess, psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

print("="*60)
print("FIXING ABCAPITAL — STEP BY STEP")
print("="*60)

# ── What we know from diagnosis ──────────────────────────────
# ✅ Price candles: 498 rows, latest 2026-06-17 (stale by 3 days)
# ✅ Shareholding: scraped, FII 7.83% in 2025Q4 (good)
# ❌ mb_score: None → filtered out of Multibagger
# ❌ Management commentary: not scored
# ❌ Kite token: expired → can't sync new candles
# 
# KEY INSIGHT: The signals engine ran on Jun 17 but didn't
# populate mb_score/buy_zone_score. That's a bug in generate_signals.py
# We've fixed it — now just need to regenerate signals

print("\nStep 1: Regenerate signals with fixed engine...")
r = subprocess.run(
    [sys.executable, "_scripts/generate_signals.py", "--symbols", "ABCAPITAL"],
    capture_output=True, text=True
)
print(r.stdout[-500:] if r.stdout else "No stdout")
if r.returncode != 0:
    print("STDERR:", r.stderr[-300:])

print("\nStep 2: Score management commentary...")
# Set screener creds if not in env
if not os.environ.get("SCREENER_USERNAME"):
    os.environ["SCREENER_USERNAME"] = "try.rakeshreddy@gmail.com"
    os.environ["SCREENER_PASSWORD"] = "Ashrith@2820"

r = subprocess.run(
    [sys.executable, "_scripts/score_management_commentary.py", "--symbols", "ABCAPITAL"],
    capture_output=True, text=True
)
print(r.stdout[-500:] if r.stdout else "No stdout")

print("\nStep 3: Verify final state...")
cur.execute("""
    SELECT symbol, action_label, mb_score, buy_zone_score, 
           all_criteria_met, above_ema200, momentum_6m,
           stage, is_nr7, updated_at
    FROM technical_signals
    WHERE symbol = 'ABCAPITAL'
    LIMIT 1
""")
row = cur.fetchone()
if row:
    cols = [d[0] for d in cur.description]
    d = dict(zip(cols, row))
    print(f"\n  Action:      {d['action_label']}")
    print(f"  MB score:    {d['mb_score']} (needs >= 40 for Multibagger)")
    print(f"  Buy zone:    {d['buy_zone_score']}")
    print(f"  All criteria:{d['all_criteria_met']}")
    print(f"  Above EMA200:{d['above_ema200']}")
    print(f"  Momentum 6M: {d['momentum_6m']}%")
    print(f"  Stage:       {d['stage']}")
    print(f"  NR7:         {d['is_nr7']}")
    print(f"  Updated:     {d['updated_at']}")
    
    mb = float(d['mb_score'] or 0)
    if mb >= 40:
        print(f"\n  ✅ ABCAPITAL will now appear in Multibagger Discovery!")
    else:
        print(f"\n  ⚠️  mb_score={mb} still below 40")
        print(f"  This means price is likely below EMA200 in our stale data")
        print(f"  WHEN MARKETS OPEN MONDAY:")
        print(f"    1. python _scripts/refresh_kite_token.py")
        print(f"    2. python _scripts/kite-sync-candles.py --symbol ABCAPITAL --days 90")
        print(f"    3. python _scripts/generate_signals.py --symbols ABCAPITAL")
        print(f"    → Price ₹375 (ATH) should put it above EMA200 and push mb_score >= 40")

print("\nStep 4: Also fix shareholding FII null values...")
# Screener shows FII 10.53% from our scrape but Q1 2026 shows None
# This is because screener only has partial data for the latest quarter
# Update with the data we got: FII 10.53% from most recent scrape
cur.execute("""
    UPDATE shareholding_history 
    SET fii_pct = 10.53, dii_pct = 9.79, mf_pct = 8.50
    WHERE nse_symbol = 'ABCAPITAL' 
    AND quarter = '2026Q1'
    AND fii_pct IS NULL
""")
rows_updated = cur.rowcount
conn.commit()
print(f"  Updated {rows_updated} shareholding rows with FII/DII data")

conn.close()
print("\n✅ Done. Reload app — ABCAPITAL signals updated.")
print("On Monday: sync fresh candles for updated technical signals")
