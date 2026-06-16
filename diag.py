import psycopg2, os, glob

print("=== 1. Excel location ===")
hits = glob.glob("C:\\\\**\\\\aacapital_ipo_master_304.xlsx", recursive=True)
print("Found:", hits if hits else "NOT FOUND anywhere")
hits2 = glob.glob("**\\aacapital_ipo_master_304.xlsx", recursive=True)
print("In project:", hits2 if hits2 else "NOT FOUND in project folder")

print("\n=== 2. Neon ipo_intelligence coverage ===")
db = os.environ.get("DATABASE_URL","")
if not db:
    print("DATABASE_URL not set!")
else:
    conn = psycopg2.connect(db)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(symbol) as has_symbol,
            COUNT(listing_date) as has_date,
            COUNT(issue_price) as has_price,
            COUNT(listing_gap_pct) as has_gap,
            COUNT(return_day30) as has_d30,
            COUNT(return_day90) as has_d90
        FROM ipo_intelligence
    """)
    r = cur.fetchone()
    print(f"  Total rows   : {r[0]}")
    print(f"  Has symbol   : {r[1]}")
    print(f"  Has list date: {r[2]}")
    print(f"  Has issue px : {r[3]}")
    print(f"  Has list gap : {r[4]}")
    print(f"  Has d30 rtn  : {r[5]}")
    print(f"  Has d90 rtn  : {r[6]}")

    print("\n=== 3. Sample rows ===")
    cur.execute("""
        SELECT company_name, symbol, listing_date, issue_price,
               listing_gap_pct, return_day30, archetype
        FROM ipo_intelligence LIMIT 10
    """)
    for row in cur.fetchall():
        print(" ", row)

    print("\n=== 4. ipo_history table (backup source) ===")
    try:
        cur.execute("""
            SELECT COUNT(*), COUNT(listing_price), COUNT(listing_gain_pct),
                   COUNT(issue_price), COUNT(sector)
            FROM ipo_history
        """)
        h = cur.fetchone()
        print(f"  ipo_history rows:{h[0]} listing_price:{h[1]} gain:{h[2]} issue_px:{h[3]} sector:{h[4]}")
        cur.execute("SELECT name, issue_price, listing_price, listing_gain_pct, sector FROM ipo_history LIMIT 5")
        for row in cur.fetchall():
            print(" ", row)
    except Exception as e:
        print(f"  ipo_history error: {e}")

    print("\n=== 5. price_candles sample ===")
    cur.execute("SELECT symbol, date, close FROM price_candles LIMIT 5")
    for row in cur.fetchall():
        print(" ", row)

    conn.close()
print("\nDone.")
