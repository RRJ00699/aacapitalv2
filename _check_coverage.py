import os, psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM ipo_intelligence")
total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM ipo_intelligence WHERE issue_price IS NULL")
no_price = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM ipo_intelligence WHERE listing_date IS NULL")
no_date = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM ipo_intelligence WHERE listing_open IS NULL")
no_open = cur.fetchone()[0]

cur.execute("""
    SELECT COUNT(*) FROM ipo_intelligence
    WHERE COALESCE(is_sme,false)=false AND issue_price IS NOT NULL AND issue_price >= 200
      AND listing_date IS NOT NULL
""")
auto_eligible = cur.fetchone()[0]

print(f"total rows in ipo_intelligence : {total}")
print(f"  missing issue_price          : {no_price}")
print(f"  missing listing_date         : {no_date}")
print(f"  missing listing_open         : {no_open}")
print(f"  mainboard, >=200, dated (auto-today eligible EVER): {auto_eligible}")

# show a few recent-ish rows so we see what IS populated
print("\nsample of 8 mainboard rows (symbol, issue_price, listing_open, listing_date):")
cur.execute("""
    SELECT symbol, issue_price, listing_open, listing_date
    FROM ipo_intelligence
    WHERE COALESCE(is_sme,false)=false AND symbol IS NOT NULL
    ORDER BY listing_date DESC NULLS LAST
    LIMIT 8
""")
for r in cur.fetchall():
    print("  ", r)

cur.close()
conn.close()
