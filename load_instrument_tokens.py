"""
AACapital -- Load Instrument Tokens
Downloads all NSE instruments from Kite and inserts into instrument_master.
Required before running ipo_candle_backfill.py.

Run: python load_instrument_tokens.py
"""

import os
import psycopg2

DATABASE_URL      = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL", "")
KITE_API_KEY      = os.environ.get("KITE_API_KEY", "br9m41pn8nvvywnl")
KITE_ACCESS_TOKEN = os.environ.get("KITE_ACCESS_TOKEN", "")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set"); exit(1)
if not KITE_ACCESS_TOKEN:
    print("ERROR: KITE_ACCESS_TOKEN not set — run: python _scripts/kite_login.py"); exit(1)

from kiteconnect import KiteConnect
kite = KiteConnect(api_key=KITE_API_KEY)
kite.set_access_token(KITE_ACCESS_TOKEN)

print("Downloading NSE instruments from Kite...")
instruments = kite.instruments("NSE")
print(f"Got {len(instruments)} instruments")

conn = psycopg2.connect(DATABASE_URL)
cur  = conn.cursor()

# Truncate and reload cleanly — avoids all ON CONFLICT issues
cur.execute("TRUNCATE instrument_master")

ok = 0
for inst in instruments:
    try:
        cur.execute(
            "INSERT INTO instrument_master (tradingsymbol, instrument_token, name, instrument_type, segment, exchange) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                inst["tradingsymbol"],
                inst["instrument_token"],
                inst.get("name", ""),
                inst.get("instrument_type", ""),
                inst.get("segment", ""),
                "NSE",
            )
        )
        ok += 1
    except Exception:
        pass  # skip duplicates within the batch

conn.commit()

cur.execute("SELECT COUNT(*) FROM instrument_master")
total = cur.fetchone()[0]
print(f"Loaded: {total} rows")

# Verify key symbols
cur.execute("""
    SELECT tradingsymbol, instrument_token
    FROM instrument_master
    WHERE tradingsymbol IN ('KAYNES','RELIANCE','INFY','BLSE','BANSALWIRE')
""")
print("Sample tokens:")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

conn.close()
print("Done — run python _scripts/ipo_candle_backfill.py next")
