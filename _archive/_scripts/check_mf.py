import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='mf_stock_summary' ORDER BY ordinal_position")
for r in cur.fetchall():
    print(r[0])
conn.close()