"""
One-time fix: update the 5 upcoming IPOs with correct data from Chittorgarh.
Also fix old IPOs that have listing_open but NULL listing_date.
"""
import psycopg2, os, datetime

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# ── 1. Fix upcoming IPOs with real data ───────────────────────────────────────
upcoming = [
    {
        "company_name":   "Aastha Spintex Ltd.",
        "open_date":      "2026-06-29",
        "close_date":     "2026-07-01",
        "issue_price":    170.0,
        "price_band_low": 170.0,
        "price_band_high":170.0,
        "issue_size_cr":  29.70,
        "is_sme":         False,
        "brlm_names":     "BOI Merchant Bankers",
    },
    {
        "company_name":   "CSM Technologies Ltd.",
        "open_date":      "2026-06-24",
        "close_date":     "2026-06-29",
        "issue_price":    113.0,
        "price_band_low": 107.0,
        "price_band_high":113.0,
        "issue_size_cr":  145.78,
        "is_sme":         False,
        "brlm_names":     "Keynote Financial",
    },
    {
        "company_name":   "Advit Jewels Ltd.",
        "open_date":      "2026-06-23",
        "close_date":     "2026-06-25",
        "issue_price":    138.0,
        "price_band_low": 130.0,
        "price_band_high":138.0,
        "issue_size_cr":  165.16,
        "is_sme":         False,
        "brlm_names":     "Holani Consultants",
    },
    {
        "company_name":   "Waterways Leisure Tourism Ltd.",
        "open_date":      "2026-06-23",
        "close_date":     "2026-06-25",
        "issue_price":    808.0,
        "price_band_low": 769.0,
        "price_band_high":808.0,
        "issue_size_cr":  585.0,
        "is_sme":         False,
        "brlm_names":     "Centrum Broking",
    },
    {
        "company_name":   "Turtlemint Fintech Solutions Ltd.",
        "open_date":      "2026-06-19",
        "close_date":     "2026-06-23",
        "issue_price":    152.0,
        "price_band_low": 144.0,
        "price_band_high":152.0,
        "issue_size_cr":  882.67,
        "is_sme":         False,
        "brlm_names":     "ICICI Securities",
    },
]

print("Updating upcoming IPOs...")
for ipo in upcoming:
    company = ipo.pop("company_name")
    fields  = list(ipo.keys())
    vals    = [ipo[f] for f in fields]
    set_clause = ", ".join([f"{f} = %s" for f in fields])
    cur.execute(f"UPDATE ipo_intelligence SET {set_clause} WHERE company_name = %s",
                vals + [company])
    print(f"  ✓ {company} → {cur.rowcount} rows updated")

conn.commit()

# ── 2. Fix old IPOs with listing_open but NULL listing_date ──────────────────
print("\nFixing IPOs with listing_open but NULL listing_date...")
# These are old IPOs from previous imports where listing_date wasn't set
# Set them to a date far in the past so they don't show as "upcoming"
cur.execute("""
    UPDATE ipo_intelligence
    SET listing_date = '2021-01-01'
    WHERE listing_date IS NULL
      AND listing_open IS NOT NULL
      AND listing_open > 0
      AND open_date < '2026-01-01'
""")
print(f"  Fixed {cur.rowcount} old IPOs")
conn.commit()

# ── 3. Show final state ───────────────────────────────────────────────────────
print("\nFinal upcoming IPO state:")
print("="*70)
cur.execute("""
    SELECT company_name, open_date, close_date, issue_price,
           price_band_low, price_band_high, issue_size_cr, brlm_names,
           play_recommendation
    FROM ipo_intelligence
    WHERE open_date >= '2026-06-19' OR listing_date IS NULL
    ORDER BY open_date ASC NULLS FIRST
    LIMIT 10
""")
for r in cur.fetchall():
    co, od, cd, ip, pbl, pbh, size, brlm, play = r
    band = f"₹{pbl}-{pbh}" if pbl else f"₹{ip}"
    print(f"  {co[:35]:35s} | {str(od):12s} → {str(cd):12s} | {band:12s} | {size}Cr | {play or 'not scored'}")

conn.close()
print("\nDone. Now run: python _scripts/ipo/ipo_play_selector.py")
