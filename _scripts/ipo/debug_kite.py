import os, sys, psycopg2
sys.path.insert(0, 'C:\\aacapital-v2')

DATABASE_URL = os.environ.get("DATABASE_URL")
API_KEY = "br9m41pn8nvvywnl"

from kiteconnect import KiteConnect

# Get token
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT value FROM platform_config WHERE key = 'kite_access_token'")
token = cur.fetchone()[0]
conn.close()

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(token)

# Load instruments
instruments = kite.instruments("NSE")
imap = {inst['tradingsymbol']: inst['instrument_token'] for inst in instruments}

# Check our symbols
test_symbols = ["UNIMECH", "VENTIVE", "SENORES", "CARRARO", "DAMCAPITAL", "BAJAJHFL", "NTPCGREEN"]
print("Symbol lookup test:")
for sym in test_symbols:
    token_val = imap.get(sym)
    print(f"  {sym}: {token_val}")

# Show similar symbols
print("\nSearching for partial matches:")
for sym in ["UNIMECH", "VENTIVE", "DAMCAP"]:
    matches = [k for k in imap.keys() if sym[:5].upper() in k.upper()]
    print(f"  {sym} -> {matches[:5]}")

# Test actual historical fetch for a known stock
print("\nTest historical for BAJAJHFL:")
try:
    import datetime
    token_val = imap.get("BAJAJHFL")
    print(f"  Token: {token_val}")
    if token_val:
        data = kite.historical_data(token_val, datetime.date(2024,9,16), datetime.date(2024,9,25), "day")
        print(f"  Candles: {len(data)}")
        if data: print(f"  First: {data[0]}")
except Exception as e:
    print(f"  Error: {e}")
