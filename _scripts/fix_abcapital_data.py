"""
fix_abcapital_data.py
=====================
Fixes the 3 data gaps that caused ABCAPITAL to miss multibagger recommendations:
  1. Runs shareholding scraper for ABCAPITAL
  2. Scores management commentary
  3. Updates smart money signal from real shareholding data
  4. Re-runs intelligence engine for ABCAPITAL

Run once:
  python fix_abcapital_data.py
"""
import os, sys, subprocess, psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

print("="*60)
print("FIXING ABCAPITAL DATA GAPS")
print("="*60)

# Step 1: Shareholding
print("\nStep 1: Scraping shareholding for ABCAPITAL...")
r = subprocess.run([sys.executable, "_scripts/scrape_shareholding.py", "--symbols", "ABCAPITAL"], 
                   capture_output=True, text=True)
print(r.stdout[-500:] if r.stdout else "No output")
if r.returncode != 0: print("Error:", r.stderr[-200:])

# Step 2: Management commentary  
print("\nStep 2: Scoring management commentary...")
r = subprocess.run([sys.executable, "_scripts/score_management_commentary.py", "--symbols", "ABCAPITAL"],
                   capture_output=True, text=True)
print(r.stdout[-500:] if r.stdout else "No output")

# Step 3: Candle sync for ABCAPITAL
print("\nStep 3: Syncing price candles...")
r = subprocess.run([sys.executable, "_scripts/sync_candles_to_neon.py", "--symbol", "ABCAPITAL"],
                   capture_output=True, text=True)
print(r.stdout[-300:] if r.stdout else "No output")

# Step 4: Check what we have now
print("\nStep 4: Verifying data...")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("SELECT quarter, promoter_pct, fii_pct, dii_pct FROM shareholding_history WHERE symbol='ABCAPITAL' ORDER BY quarter DESC LIMIT 2")
rows = cur.fetchall()
print(f"  Shareholding rows: {len(rows)}")
for r in rows: print(f"    {r[0]}: Promoter {r[1]}% FII {r[2]}% DII {r[3]}%")

cur.execute("SELECT sentiment_score, tone FROM management_commentary_scores WHERE symbol='ABCAPITAL' LIMIT 1")
row = cur.fetchone()
print(f"  Commentary: {row if row else '❌ still missing'}")

cur.execute("SELECT COUNT(*) FROM price_candles WHERE symbol='ABCAPITAL'")
n = cur.fetchone()[0]
print(f"  Price candles: {n} rows")

conn.close()

print("\n✅ Done. Now run:")
print("  python _scripts/generate_signals.py --symbol ABCAPITAL")
print("  Then reload the app — ABCAPITAL should appear in Multibagger")
