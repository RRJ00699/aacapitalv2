"""
fix_abcapital_data.py
======================
Fixes ABCAPITAL data gaps and re-runs signals engine.
Run from project root: python _scripts/fix_abcapital_data.py

What this does:
  1. Syncs Kite candles for ABCAPITAL (price data, volume)
  2. Scores management commentary via Screener
  3. Re-generates technical signals with correct volume data
  4. Shows final state
"""
import os, sys, subprocess, psycopg2, psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

def run(cmd, label):
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")
    r = subprocess.run(cmd, capture_output=False, text=True)
    return r.returncode == 0

print("FIXING ABCAPITAL — DATA PIPELINE")
print("="*50)

# Step 1: Sync candles from Kite (needs KITE_ACCESS_TOKEN)
run([sys.executable, "_scripts/kite-sync-candles.py", "--symbol", "ABCAPITAL", "--days", "90"],
    "Step 1: Kite candle sync (90 days for ABCAPITAL)")

# Step 2: Score management commentary from Screener
run([sys.executable, "_scripts/score_management_commentary.py", "--symbols", "ABCAPITAL"],
    "Step 2: Score management commentary from Screener.in")

# Step 3: Re-generate technical signals
run([sys.executable, "_scripts/generate_signals.py", "--symbols", "ABCAPITAL"],
    "Step 3: Re-generate technical signals")

# Step 4: Check final state
print("\n" + "="*50)
print("  FINAL STATE CHECK")
print("="*50)

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Check actual columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='technical_signals'")
ts_cols = [r[0] for r in cur.fetchall()]
score_col = 'conviction_score' if 'conviction_score' in ts_cols else 'buy_zone_score'
name_col  = 'company_name' if 'company_name' in ts_cols else 'symbol'

cur.execute(f"""
    SELECT symbol, buy_zone_score, {score_col}, technical_signal, 
           volume_ratio, is_nr7, stage, updated_at
    FROM technical_signals WHERE symbol = 'ABCAPITAL'
""")
row = cur.fetchone()
if row:
    cols = [d[0] for d in cur.description]
    d = dict(zip(cols, row))
    print(f"\nABCAPITAL technical_signals:")
    print(f"  Buy zone score:  {d.get('buy_zone_score')}")
    print(f"  Conviction:      {d.get(score_col)}")
    print(f"  Signal:          {d.get('technical_signal')} ← needs 'above' to appear in Multibagger")
    print(f"  Volume ratio:    {d.get('volume_ratio')} ← should be ~2.5 now")
    print(f"  Is NR7:          {d.get('is_nr7')}")
    print(f"  Stage:           {d.get('stage')}")
    print(f"  Updated at:      {d.get('updated_at')}")
    
    score = float(d.get(score_col) or 0)
    signal = d.get('technical_signal', '')
    if score >= 40 and signal == 'above':
        print(f"\n  ✅ ABCAPITAL should now appear in Multibagger Discovery!")
    else:
        print(f"\n  ⚠️  Still may not show — score {score:.0f} (needs 40+), signal '{signal}' (needs 'above')")
        if signal != 'above':
            print(f"  → Price may be below 200 EMA in our data — run candle sync again after market close")
else:
    print("  ❌ Still not in technical_signals")

# Check price candles
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='price_candles'")
pc_cols = [r[0] for r in cur.fetchall()]
sym_col = 'symbol' if 'symbol' in pc_cols else 'tradingsymbol'
cur.execute(f"SELECT COUNT(*), MAX(date), MAX(close) FROM price_candles WHERE {sym_col}='ABCAPITAL'")
row = cur.fetchone()
print(f"\nPrice candles: {row[0]} rows, latest: {row[1]}, last close: ₹{row[2]}")

# Commentary
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='management_commentary_scores'")
mc_cols = [r[0] for r in cur.fetchall()]
sym_mc = 'nse_symbol' if 'nse_symbol' in mc_cols else 'symbol'
cur.execute(f"SELECT sentiment_score, tone FROM management_commentary_scores WHERE {sym_mc}='ABCAPITAL' LIMIT 1")
row = cur.fetchone()
print(f"Commentary: {row if row else '❌ still missing — SCREENER_USERNAME/PASSWORD needed'}")

conn.close()
print("\n✅ Done. Reload aacapital-v2.vercel.app to see updated signals.")
