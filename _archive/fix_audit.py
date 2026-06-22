"""
AACapital — Fix All + Audit
Checks schemas and fixes everything in one run
"""
import psycopg2, os
from dotenv import load_dotenv
load_dotenv(".env.local")

NEON = os.environ["NEON_DATABASE_URL"].strip('"')
conn = psycopg2.connect(NEON)
cur  = conn.cursor()

# 1. Check actual company_master columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='company_master' ORDER BY ordinal_position")
cm_cols = [r[0] for r in cur.fetchall()]
print("company_master columns:", cm_cols[:10])

# 2. Check actual market_regimes columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='market_regimes' ORDER BY ordinal_position")
mr_cols = [r[0] for r in cur.fetchall()]
print("market_regimes columns:", mr_cols)

# 3. Audit ANTELOPUS specifically
print("\n=== ANTELOPUS AUDIT ===")
cur.execute("SELECT * FROM technical_signals WHERE symbol = 'ANTELOPUS'")
row = cur.fetchone()
if row:
    cols = [d[0] for d in cur.description]
    data = dict(zip(cols, row))
    print(f"  probability_score:    {data.get('probability_score')}")
    print(f"  volume_ratio_20:      {data.get('volume_ratio_20')}")
    print(f"  delivery_percentage:  {data.get('delivery_percentage')}")
    print(f"  monthly_rsi_14:       {data.get('monthly_rsi_14')}")
    print(f"  weekly_close:         {data.get('weekly_close')}")
    print(f"  weekly_ema_30:        {data.get('weekly_ema_30')}")
    vol = float(data.get('volume_ratio_20') or 0)
    deliv = data.get('delivery_percentage')
    print(f"\n  Volume ratio: {vol:.2f}x average")
    if vol > 5:
        print(f"  🚨 HIGH VOLUME RATIO — classic operator signal")
    if deliv is not None and float(deliv) < 30:
        print(f"  🚨 LOW DELIVERY {deliv}% — no real conviction")
    elif deliv is None:
        print(f"  ⚠ No delivery data available")

# 4. Check if ANTELOPUS is in company_master
mcap_col = "mcap_cr" if "mcap_cr" in cm_cols else ("market_cap_cr" if "market_cap_cr" in cm_cols else cm_cols[2] if len(cm_cols) > 2 else None)
sym_col  = "nse_symbol" if "nse_symbol" in cm_cols else "symbol"
print(f"\n  Using company_master cols: sym={sym_col}, mcap={mcap_col}")

cur.execute(f"SELECT * FROM company_master WHERE {sym_col} = 'ANTELOPUS'")
cm_row = cur.fetchone()
if cm_row:
    cm_data = dict(zip(cm_cols, cm_row))
    print(f"  In company_master: YES")
    if mcap_col:
        print(f"  Market cap: ₹{cm_data.get(mcap_col)} Cr")
else:
    print(f"  🚨 NOT IN COMPANY_MASTER — untracked/operator stock")
    # Check all columns to find any match
    cur.execute(f"SELECT COUNT(*) FROM company_master")
    total = cur.fetchone()[0]
    print(f"  company_master has {total} stocks total")

conn.close()
print("\nDone.")
