"""
What predicts "should I hold this BUY_AT_OPEN for 7 days?"

From 340 historical IPOs with real Kite data, let's find which 
LISTING DAY signals (available by 10:30 AM) predict 7-day returns.

Signals to test:
1. Float Turnover Ratio (FTR) at 10:30 AM — volume / day1 float
   FTR > 0.8 = weak hands flushed = HOLD
   FTR < 0.4 = still selling = EXIT EOD

2. Price vs VWAP at 10:30 AM
   Price > VWAP = institutional accumulation = HOLD
   Price < VWAP = distribution = EXIT EOD

3. Opening premium vs GMP
   Listed BELOW GMP = panic selling = institutions buy = HOLD
   Listed ABOVE GMP by >20% = euphoria = institutions sell = EXIT

4. QIB subscription velocity
   QIB > 50x = institutions want stock = they buy dips = HOLD
   QIB < 10x = weak = EXIT EOD

5. UC on Day 1
   Hit UC = momentum = gap up Day 2 = HOLD
   Hit LC = trapped = EXIT immediately
"""
import psycopg2, os

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

print("=" * 75)
print("WHAT PREDICTS 7-DAY HOLD SUCCESS?")
print("Signals available on listing morning by 10:30 AM")
print("=" * 75)

# Signal 1: QIB subscription tier
print("\n1. QIB SUBSCRIPTION vs 7-DAY REAL RETURN")
print("   (buy at open, sell after 7 trading days)")
cur.execute("""
    SELECT
        CASE
            WHEN qib_subscription_x >= 100 THEN 'QIB 100x+  (ultra)'
            WHEN qib_subscription_x >= 50  THEN 'QIB 50-100x (high)'
            WHEN qib_subscription_x >= 20  THEN 'QIB 20-50x  (med)'
            WHEN qib_subscription_x >= 5   THEN 'QIB 5-20x   (low)'
            ELSE                                 'QIB < 5x    (weak)'
        END as qib_tier,
        COUNT(*) as ipos,
        ROUND(AVG(
            CASE WHEN listing_open > 0 AND return_day7 IS NOT NULL AND issue_price > 0
            THEN ((issue_price * (1 + return_day7/100.0)) - listing_open) / listing_open * 100
            END
        )::numeric, 1) as real_7d,
        ROUND(AVG(
            CASE WHEN listing_open > 0 AND return_day30 IS NOT NULL AND issue_price > 0
            THEN ((issue_price * (1 + return_day30/100.0)) - listing_open) / listing_open * 100
            END
        )::numeric, 1) as real_30d,
        SUM(CASE WHEN hit_uc_day1 THEN 1 ELSE 0 END) as uc_hits
    FROM ipo_intelligence
    WHERE listing_open > 0 AND is_sme = FALSE
      AND return_day7 IS NOT NULL
    GROUP BY 1
    ORDER BY real_7d DESC NULLS LAST
""")
print(f"   {'QIB Tier':22s} {'IPOs':>5} {'7d%':>7} {'30d%':>7} {'UC hits':>8}")
print("   " + "-"*55)
for row in cur.fetchall():
    tier, n, d7, d30, uc = row
    hold = "✅ HOLD" if (d7 or 0) > 5 else "⚠️ CAUTION"
    print(f"   {tier:22s} {n:>5} {str(d7 or 'n/a'):>7} {str(d30 or 'n/a'):>7} "
          f"{uc:>5} {hold}")

# Signal 2: UC/LC Day 1
print("\n2. UC/LC DAY 1 vs NEXT 7 DAYS")
cur.execute("""
    SELECT
        CASE
            WHEN hit_uc_day1 = TRUE  THEN 'Hit UC Day 1 🔴'
            WHEN hit_lc_day1 = TRUE  THEN 'Hit LC Day 1 🔵'
            ELSE                          'Normal close'
        END as circuit,
        COUNT(*) as ipos,
        ROUND(AVG(
            CASE WHEN listing_open > 0 AND return_day7 IS NOT NULL AND issue_price > 0
            THEN ((issue_price * (1 + return_day7/100.0)) - listing_open) / listing_open * 100
            END
        )::numeric, 1) as real_7d,
        ROUND(AVG(
            CASE WHEN listing_open > 0 AND return_day30 IS NOT NULL AND issue_price > 0
            THEN ((issue_price * (1 + return_day30/100.0)) - listing_open) / listing_open * 100
            END
        )::numeric, 1) as real_30d
    FROM ipo_intelligence
    WHERE listing_open > 0 AND is_sme = FALSE
      AND return_day7 IS NOT NULL
    GROUP BY 1
    ORDER BY real_7d DESC NULLS LAST
""")
print(f"   {'Day 1 outcome':20s} {'IPOs':>5} {'7d%':>7} {'30d%':>7}")
print("   " + "-"*45)
for row in cur.fetchall():
    circuit, n, d7, d30 = row
    action = "HOLD 7d ✅" if (d7 or 0) > 5 else ("EXIT NOW 🚨" if (d7 or 0) < -3 else "HOLD with caution")
    print(f"   {circuit:20s} {n:>5} {str(d7 or 'n/a'):>7} {str(d30 or 'n/a'):>7}  → {action}")

# Signal 3: Listing premium vs issue price (proxy for GMP vs actual)
print("\n3. HOW MUCH ABOVE ISSUE PRICE DID IT LIST?")
print("   (listing_open / issue_price - 1)")
cur.execute("""
    WITH base AS (
        SELECT
            CASE
                WHEN listing_open >= issue_price * 1.50 THEN '1_Listed 50%+ above issue (very hot)'
                WHEN listing_open >= issue_price * 1.25 THEN '2_Listed 25-50% above issue (hot)'
                WHEN listing_open >= issue_price * 1.10 THEN '3_Listed 10-25% above issue (good)'
                WHEN listing_open >= issue_price * 1.00 THEN '4_Listed 0-10% above issue (flat)'
                ELSE                                         '5_Listed below issue price (negative)'
            END as listing_tier,
            CASE WHEN listing_open > 0 AND return_day7 IS NOT NULL AND issue_price > 0
                 THEN ((issue_price * (1 + return_day7/100.0)) - listing_open) / listing_open * 100
            END as r7,
            CASE WHEN listing_open > 0 AND return_day30 IS NOT NULL AND issue_price > 0
                 THEN ((issue_price * (1 + return_day30/100.0)) - listing_open) / listing_open * 100
            END as r30
        FROM ipo_intelligence
        WHERE listing_open > 0 AND issue_price > 0
          AND is_sme = FALSE AND return_day7 IS NOT NULL
    )
    SELECT
        SUBSTRING(listing_tier, 3) as listing_tier,
        COUNT(*) as ipos,
        ROUND(AVG(r7)::numeric, 1) as real_7d,
        ROUND(AVG(r30)::numeric, 1) as real_30d
    FROM base
    GROUP BY listing_tier
    ORDER BY listing_tier
""")
print(f"   {'Listing tier':42s} {'IPOs':>5} {'7d%':>7} {'30d%':>7}")
print("   " + "-"*65)
for row in cur.fetchall():
    tier, n, d7, d30 = row
    if (d7 or 0) > 8:
        action = "HOLD ✅"
    elif (d7 or 0) > 0:
        action = "hold cautiously"
    else:
        action = "EXIT or avoid ❌"
    print(f"   {tier:42s} {n:>5} {str(d7 or 'n/a'):>7} {str(d30 or 'n/a'):>7}  {action}")

print()
print("=" * 75)
print("THE HOLD DECISION FRAMEWORK (by 10:30 AM)")
print("=" * 75)
print("""
  HOLD 7 DAYS if ALL of:
  ✅ QIB > 50x  (institutions really wanted this stock)
  ✅ Listed 10-50% above issue (healthy demand, not euphoria)
  ✅ Day 1 close > open OR hit UC (buying continues)
  ✅ Issue size > ₹500 Cr (liquidity to exit)

  EXIT EOD if ANY of:
  ❌ QIB < 10x  (weak institutional conviction)
  ❌ Listed > 50% above issue (euphoria, sell-the-news)
  ❌ Price falling below open by 10:30 AM (distribution)
  ❌ Hit LC Day 1 (trapped, run)
  ❌ Issue size < ₹300 Cr (liquidity risk)

  KITE SIGNALS to watch 10:00-10:30 AM:
  → VWAP: if price > VWAP at 10:30 → institutional accumulation → HOLD
  → Volume: if 50%+ of day1 float traded by 10:30 → weak hands flushed → HOLD  
  → Bid/Ask: deep bid side → buying pressure → HOLD
  → Price momentum: still rising at 10:15 → HOLD
  → Price falling from open: selling pressure → EXIT
""")
conn.close()
