import os, psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("""
    SELECT symbol, company_name, issue_price, listing_open, listing_date, is_sme
    FROM ipo_intelligence
    WHERE symbol = 'TURTLEMINT'
""")
row = cur.fetchone()
print("symbol, company, issue_price, listing_open, listing_date, is_sme")
print(row)
cur.close()
conn.close()
