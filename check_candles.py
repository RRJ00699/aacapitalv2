import psycopg2, os

neon  = os.environ.get("DATABASE_URL", "")
local = os.environ.get("CANDLES_DATABASE_URL", "")

print("=== NEON ===")
conn = psycopg2.connect(neon)
cur  = conn.cursor()

cur.execute("SELECT COUNT(*) FROM instrument_master")
print(f"instrument_master rows: {cur.fetchone()[0]}")

cur.execute("SELECT COUNT(*) FROM price_candles")
print(f"price_candles rows: {cur.fetchone()[0]}")

cur.execute("SELECT symbol, date, close FROM price_candles LIMIT 3")
print(f"price_candles sample: {cur.fetchall()}")

cur.execute("SELECT COUNT(*) FROM price_candles_weekly")
print(f"price_candles_weekly rows: {cur.fetchone()[0]}")

conn.close()

print("\n=== LOCAL POSTGRES ===")
try:
    conn2 = psycopg2.connect(local)
    cur2  = conn2.cursor()
    cur2.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    tables = [r[0] for r in cur2.fetchall()]
    print(f"Tables: {tables}")
    if "instrument_master" in tables:
        cur2.execute("SELECT COUNT(*) FROM instrument_master")
        print(f"local instrument_master: {cur2.fetchone()[0]}")
        cur2.execute("SELECT tradingsymbol, instrument_token FROM instrument_master LIMIT 3")
        print(f"sample: {cur2.fetchall()}")
    if "price_candles" in tables:
        cur2.execute("SELECT COUNT(*) FROM price_candles")
        print(f"local price_candles: {cur2.fetchone()[0]}")
    conn2.close()
except Exception as e:
    print(f"Local DB error: {e}")
