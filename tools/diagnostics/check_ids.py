import os,psycopg2
c=psycopg2.connect(os.environ["DATABASE_URL"]).cursor()
c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence' AND column_name LIKE '%id%'")
print("id-ish columns:",[r[0] for r in c.fetchall()])
for col in ("ipo_id","chittorgarh_id","ipomatrix_id"):
    try:
        c.execute(f"SELECT COUNT({col}) FROM ipo_intelligence"); print(col,"filled:",c.fetchone()[0])
    except Exception as e: c.execute("ROLLBACK"); print(col,"absent")
