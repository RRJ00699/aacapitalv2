import psycopg2, os

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

companies = [
    "Aastha Spintex",
    "CSM Technologies",
    "Advit Jewels",
    "Waterways Leisure Tourism",
    "Turtlemint Fintech",
    "Hexagon Nutrition",
    "CMR Green Technologies",
]

print("="*80)
print("CHECKING UPCOMING IPOs IN NEON")
print("="*80)

for co in companies:
    cur.execute("""
        SELECT company_name, open_date, close_date, listing_date,
               listing_open, listing_day_close, issue_price,
               qib_subscription_x, play_recommendation, nse_symbol
        FROM ipo_intelligence
        WHERE company_name ILIKE %s
        LIMIT 1
    """, (f"%{co}%",))
    row = cur.fetchone()
    if row:
        co_name, open_d, close_d, list_d, l_open, l_close, ip, qib, play, sym = row
        has_listing = "✅ HAS listing data" if l_open else "❌ No listing data"
        print(f"\n✅ FOUND: {co_name}")
        print(f"   Symbol: {sym} | Issue: ₹{ip}")
        print(f"   Open: {open_d} | Close: {close_d} | Listing: {list_d}")
        print(f"   {has_listing} | Open px: {l_open} | Close px: {l_close}")
        print(f"   QIB: {qib}x | Play: {play}")
    else:
        print(f"\n❌ NOT IN DB: {co}")

# Also show what upcoming IPOs we DO have
print("\n" + "="*80)
print("ALL UPCOMING / RECENT IPOs IN NEON (listing date >= Jun 2026)")
print("="*80)
cur.execute("""
    SELECT company_name, open_date, close_date, listing_date,
           issue_price, qib_subscription_x, play_recommendation, listing_open
    FROM ipo_intelligence
    WHERE listing_date >= '2026-06-01' OR listing_date IS NULL
    ORDER BY listing_date ASC NULLS FIRST
    LIMIT 20
""")
rows = cur.fetchall()
for r in rows:
    co, od, cd, ld, ip, qib, play, lo = r
    listed = f"Listed {ld} @ ₹{lo}" if lo else (f"Listing {ld}" if ld else "UPCOMING")
    print(f"  {co[:35]:35s} | {listed:25s} | QIB:{str(qib or '?'):6s} | {play or 'not scored'}")

conn.close()
