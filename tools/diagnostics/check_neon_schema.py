import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("SELECT table_name, COUNT(*) as cols FROM information_schema.columns WHERE table_schema='public' GROUP BY table_name ORDER BY table_name")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} columns")
conn.close()
print("Neon schema check complete")
