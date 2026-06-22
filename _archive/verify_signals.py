import psycopg2, os
from dotenv import load_dotenv
load_dotenv(".env.local")
conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"].strip('"'))
cur = conn.cursor()

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='technical_signals' ORDER BY ordinal_position")
cols = [r[0] for r in cur.fetchall()]
print("Columns:", cols)

cur.execute("SELECT * FROM technical_signals LIMIT 3")
rows = cur.fetchall()
print(f"\nRows: {len(rows)}")
for r in rows:
    print(dict(zip(cols, r)))

conn.close()
