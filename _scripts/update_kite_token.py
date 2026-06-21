import psycopg2, os

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
token = os.environ.get("KITE_ACCESS_TOKEN", "")

if not token:
    print("ERROR: KITE_ACCESS_TOKEN not set. Load .env.local first.")
    exit(1)

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("UPDATE platform_config SET value = %s WHERE key = %s", (token, "kite_access_token"))
print(f"Updated {cur.rowcount} rows with token {token[:8]}...")
conn.commit()
conn.close()
print("Done — Kite token synced to Neon")
