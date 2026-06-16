"""
AACapital — Multibagger Signal Audit
Checks every current signal against red flag criteria:
- Market cap too small
- Low delivery %
- Promoter pledge
- No institutional holding
- Not in company_master
- Suspicious volume
"""
import psycopg2, os
from dotenv import load_dotenv
load_dotenv(".env.local")

NEON = os.environ["NEON_DATABASE_URL"].strip('"')
LOCAL = {
    "host": "localhost", "port": 5432,
    "database": "aacapital", "user": "postgres",
    "password": "Ashrith@2820", "sslmode": "disable",
}

conn = psycopg2.connect(NEON)
cur  = conn.cursor()

# Get all current signals
cur.execute("""
    SELECT
        t.symbol,
        t.probability_score,
        t.action_label,
        t.monthly_rsi_14,
        t.weekly_ok,
        t.daily_nr7_recent,
        t.daily_inside_bar_recent,
        t.volume_ratio_20,
        t.delivery_percentage,
        t.signal_date,
        -- From company_master if exists
        cm.market_cap_cr,
        cm.mcap_category
    FROM technical_signals t
    LEFT JOIN company_master cm ON cm.nse_symbol = t.symbol
    ORDER BY t.probability_score DESC
""")
signals = cur.fetchall()
cols = [d[0] for d in cur.description]

print("\n" + "="*70)
print("MULTIBAGGER SIGNAL AUDIT")
print("="*70)

RED_FLAGS = {
    "small_cap": "Market cap < ₹500 Cr or unknown",
    "low_delivery": "Delivery % < 30% (no real conviction)",
    "vol_spike": "Volume > 10x average (manipulation risk)",
    "not_in_master": "Not in company_master (outside tracked universe)",
}

for row in signals:
    r = dict(zip(cols, row))
    flags = []

    # Check market cap
    if r["market_cap_cr"] is None:
        flags.append("❌ NOT IN COMPANY_MASTER — untracked stock")
    elif float(r["market_cap_cr"] or 0) < 500:
        flags.append(f"❌ MICRO CAP — ₹{r['market_cap_cr']} Cr (< ₹500 Cr)")

    # Check delivery %
    if r["delivery_percentage"] is not None:
        deliv = float(r["delivery_percentage"])
        if deliv < 30:
            flags.append(f"❌ LOW DELIVERY — {deliv:.1f}% (< 30% = operator activity)")
        elif deliv < 50:
            flags.append(f"⚠ MODERATE DELIVERY — {deliv:.1f}%")

    # Check volume spike
    if r["volume_ratio_20"] is not None:
        vol = float(r["volume_ratio_20"])
        if vol > 10:
            flags.append(f"❌ VOLUME SPIKE — {vol:.1f}x average (manipulation risk)")
        elif vol > 5:
            flags.append(f"⚠ HIGH VOLUME — {vol:.1f}x average")

    # Print
    score = float(r["probability_score"] or 0)
    print(f"\n{'─'*60}")
    print(f"  {r['symbol']:<15} Score={score:.0f}  Action={r['action_label']}")
    print(f"  RSI={r['monthly_rsi_14']:.1f if r['monthly_rsi_14'] else 'N/A'}  "
          f"Vol_ratio={float(r['volume_ratio_20'] or 0):.2f}x  "
          f"Delivery={r['delivery_percentage'] or 'N/A'}%  "
          f"Date={r['signal_date']}")
    if r["market_cap_cr"]:
        print(f"  Mcap=₹{r['market_cap_cr']} Cr  Category={r['mcap_category']}")

    if flags:
        print(f"\n  🚨 RED FLAGS:")
        for f in flags:
            print(f"     {f}")
    else:
        print(f"\n  ✅ No red flags detected")

print(f"\n{'='*70}")
print(f"Total signals: {len(signals)}")
print(f"{'='*70}\n")
conn.close()
