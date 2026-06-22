import psycopg2, os
from dotenv import load_dotenv
load_dotenv(".env.local")
conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"].strip('"'))
cur = conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'ipo_intelligence' ORDER BY ordinal_position")
print("Columns in ipo_intelligence:")
for name, dtype in cur.fetchall():
    print(f"  {name:<35} {dtype}")
conn.close()
