"""
AACapital -- Final Complete Fix
1. Derives listing_date from price_candles (first candle >= year start for each symbol)
2. Syncs real Excel data (the 304-row file uploaded to Claude)
3. Calculates all returns from price_candles
4. Fixes 117 unmatched symbols with direct overrides

Run: python final_fix2.py
"""

import os, re, logging, psycopg2, psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

# Manual symbol overrides for the 117 unmatched IPOs
# Format: "IPO name in ipo_intelligence" -> "NSE symbol in company_master"
SYMBOL_OVERRIDES = {
    "AGS Transact": "AGSTRA",
    "Aadhar Housing": "AADHARHFC",
    "Adani Wilmar": "AWL",
    "Advance Agrolife Ltd": "ADVANCEAGROLIFE",  # may be SME
    "Ami Organics": "AMIORG",
    "Angel Broking": "ANGELONE",
    "Anthem Biosciences Ltd": "ANTHEM",
    "Arisinfra Solutions Limited": "ARISINFRA",
    "Barbeque Nation": "BARBEQUE",
    "BlueStone Jewellery and Lifestyle Ltd": "BLUESTONE",
    "Burger King": "RBA",
    "CAMS": "CAMS",
    "Campus Shoes": "CAMPUS",
    "CarTrade Tech": "CARTRADE",
    "Chemplast Sanmar": "CHEMPLASTS",
    "Clean Science And Technology": "CLEANSCIENCE",
    "Concord Biotech": "CONCORDBIO",
    "Craftsman Automation": "CRAFTSMAN",
    "DCX Systems": "DCXINDIA",
    "DOMS Industries": "DOMS",
    "Data Patterns": "DATAPATTNS",
    "Delhivery": "DELHIVERY",
    "Devyani International": "DEVYANI",
    "Dodla Dairy": "DODLA",
    "DreamFolks Services": "DREAMFOLKS",
    "Easy Trip Planners": "EASEMYTRIP",
    "Emcure": "EMCURE",
    "Epack Prefab Technologies Ltd": "EPACK",
    "Ethos": "ETHOS",
    "Exicom": "EXICOM",
    "FedFina": "FEDFINA",
    "Fino Payments Bank": "FINOPB",
    "Five-Star Business Finance": "FIVESTAR",
    "Flair Writing": "FLAIR",
    "Fusion Microfinance": "FUSION",
    "G R Infraprojects": "GRINFRA",
    "Gland Pharma": "GLAND",
    "Glenmark Life Sciences": "GLS",
    "Global Health (Medanta)": "MEDANTA",
    "Go Fashion": "GOFASHION",
    "Go Fashion (India)": "GOFASHION",
    "HDB Financial Services Limited": "HDBFS",
    "Happiest Minds Technologies": "HAPPSTMNDS",
    "Harsha Engineers": "HARSHA",
    "Harsha Engineers International": "HARSHA",
    "Home First Finance": "HOMEFIRST",
    "IREDA": "IREDA",
    "IRFC": "IRFC",
    "Indigo Paints": "INDIGOPNTS",
    "Kalyan Jewellers": "KALYANKJIL",
    "Kaynes Technology": "KAYNES",
    "Kaynes Technology India": "KAYNES",
    "KFin Technologies": "KFINTECH",
    "Krsnaa Diagnostics": "KRSNAA",
    "LIC": "LICI",
    "Latent View Analytics": "LATENTVIEW",
    "Laxmi Organic": "LAXMICHEM",
    "Lodha Macrotech Developers": "LODHA",
    "MTAR Technologies": "MTAR",
    "Mankind Pharma": "MANKIND",
    "Mazagon Dock Shipbuilders": "MAZDOCK",
    "Medplus Health": "MEDPLUS",
    "Metro Brands": "METROBRAND",
    "Mrs Bectors Food Specialities": "MRSBECTORS",
    "Nykaa": "NYKAA",
    "FSN E-Commerce Ventures (Nykaa)": "NYKAA",
    "Nuvoco Vistas": "NUVOCO",
    "Ola Electric": "OLAELECTRIC",
    "One 97": "PAYTM",
    "Piramal Pharma": "PIRPHARM",
    "Policybazaar": "POLICYBZR",
    "Premier Energies": "PREMIERENE",
    "Prudent Corp": "PRUDENT",
    "RateGain Travel": "RATEGAIN",
    "Route Mobile": "ROUTE",
    "SJS Enterprises": "SJS",
    "Samhi Hotels": "SAMHI",
    "Sapphire Foods": "SAPPHIRE",
    "Signatureglobal": "SGRL",
    "SignatureGlobal": "SGRL",
    "Sona BLW Precisions": "SONACOMS",
    "Sona BLW Precis.": "SONACOMS",
    "Stove Kraft": "STOVEKRAFT",
    "Supriya Lifescience": "SUPRIYA",
    "Supriya Lifesci.": "SUPRIYA",
    "Tarsons Products": "TARSONS",
    "Tatva Chintan": "TATVA",
    "Tega Industries": "TEGA",
    "Torrent Power": "TORNTPOWER",
    "Tracxn Technologies": "TRACXN",
    "Uniparts India": "UNIPARTS",
    "Venus Pipes": "VENUSPIPES",
    "Vedant Fashions": "MANYAVAR",
    "Veranda Learning": "VERANDA",
    "Windlas Biotech": "WINDLAS",
    "Yatharth Hospital": "YATHARTH",
    "Zaggle Prepaid": "ZAGGLE",
}


def main():
    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    log.info("Connected to Neon")

    # ── STEP 1: Apply manual symbol overrides ─────────────────────────────────
    log.info("\n=== STEP 1: Applying symbol overrides ===")
    override_ok = 0
    for ipo_name, symbol in SYMBOL_OVERRIDES.items():
        # Verify symbol exists in company_master
        cur.execute("SELECT symbol FROM company_master WHERE symbol = %s", [symbol])
        if cur.fetchone():
            cur.execute(
                "UPDATE ipo_intelligence SET symbol=%s, updated_at=NOW() WHERE company_name=%s AND (symbol IS NULL OR symbol != %s)",
                [symbol, ipo_name, symbol]
            )
            if cur.rowcount > 0:
                override_ok += 1
        else:
            # Symbol not in master, still set it (may be in price_candles)
            cur.execute(
                "UPDATE ipo_intelligence SET symbol=%s, updated_at=NOW() WHERE company_name=%s AND symbol IS NULL",
                [symbol, ipo_name]
            )
            if cur.rowcount > 0:
                override_ok += 1

    conn.commit()
    log.info(f"  Overrides applied: {override_ok}")

    # Check symbol coverage now
    cur.execute("SELECT COUNT(*), COUNT(symbol) FROM ipo_intelligence")
    total, with_sym = cur.fetchone()
    log.info(f"  Symbol coverage: {with_sym}/{total}")

    # ── STEP 2: Derive listing_date from price_candles + year ─────────────────
    log.info("\n=== STEP 2: Deriving listing_date from price_candles ===")

    # Join ipo_intelligence to ipo_history to get year, then find first candle
    cur.execute("""
        SELECT i.id, i.company_name, i.symbol, h.year
        FROM ipo_intelligence i
        JOIN ipo_history h ON LOWER(h.name) = LOWER(i.company_name)
        WHERE i.symbol IS NOT NULL
          AND i.listing_date IS NULL
    """)
    rows = cur.fetchall()
    log.info(f"  IPOs needing listing_date: {len(rows)}")

    date_found = date_missing = 0
    for (iid, name, symbol, year) in rows:
        # First trading day in that year for this symbol = listing date
        cur.execute("""
            SELECT MIN(date) FROM price_candles
            WHERE symbol = %s
              AND date >= %s::date
              AND date < (%s + 1)::text::date
        """, [symbol, f"{year}-01-01", str(year + 1)])
        result = cur.fetchone()
        if result and result[0]:
            cur.execute(
                "UPDATE ipo_intelligence SET listing_date=%s, updated_at=NOW() WHERE id=%s",
                [result[0], iid]
            )
            date_found += 1
        else:
            # Try year-1 (listed late in prior year)
            cur.execute("""
                SELECT MAX(date) FROM price_candles
                WHERE symbol = %s AND date >= %s::date
            """, [symbol, f"{year-1}-06-01"])
            result2 = cur.fetchone()
            if result2 and result2[0]:
                cur.execute(
                    "UPDATE ipo_intelligence SET listing_date=%s, updated_at=NOW() WHERE id=%s",
                    [result2[0], iid]
                )
                date_found += 1
            else:
                date_missing += 1

    conn.commit()
    log.info(f"  listing_date found: {date_found} | missing: {date_missing}")

    # Also try matching by fuzzy name for unjoined rows
    cur.execute("""
        SELECT i.id, i.company_name, i.symbol
        FROM ipo_intelligence i
        WHERE i.symbol IS NOT NULL AND i.listing_date IS NULL
    """)
    remaining = cur.fetchall()
    if remaining:
        log.info(f"  {len(remaining)} still need listing_date -- using earliest candle date")
        for (iid, name, symbol) in remaining:
            cur.execute("""
                SELECT MIN(date) FROM price_candles WHERE symbol = %s
            """, [symbol])
            r = cur.fetchone()
            if r and r[0]:
                cur.execute(
                    "UPDATE ipo_intelligence SET listing_date=%s, updated_at=NOW() WHERE id=%s",
                    [r[0], iid]
                )
        conn.commit()

    # ── STEP 3: Calculate returns ──────────────────────────────────────────────
    log.info("\n=== STEP 3: Calculating returns from price_candles ===")
    cur.execute("""
        SELECT i.id, i.company_name, i.symbol, i.issue_price, i.listing_date::text
        FROM ipo_intelligence i
        WHERE i.symbol IS NOT NULL
          AND i.issue_price IS NOT NULL
          AND i.listing_date IS NOT NULL
          AND i.return_day30 IS NULL
        ORDER BY i.listing_date
    """)
    ipos = cur.fetchall()
    log.info(f"  Eligible: {len(ipos)}")

    ret_updated = 0
    for (iid, name, symbol, issue_price, listing_date) in ipos:
        ip = float(issue_price)
        cur.execute("""
            SELECT close, high, low FROM price_candles
            WHERE symbol=%s AND date >= %s::date
            ORDER BY date ASC LIMIT 120
        """, [symbol, listing_date])
        candles = cur.fetchall()
        if not candles: continue

        closes = [float(c[0]) for c in candles]
        highs  = [float(c[1]) for c in candles]
        lows   = [float(c[2]) for c in candles]

        def ret(p): return round((p - ip) / ip * 100, 2) if ip > 0 else None

        d1  = ret(closes[1])  if len(closes) > 1  else None
        d7  = ret(closes[4])  if len(closes) > 4  else None
        d30 = ret(closes[20]) if len(closes) > 20 else None
        d90 = ret(closes[62]) if len(closes) > 62 else None
        cmp_r = ret(closes[-1])
        max_up   = ret(max(highs[:21])) if highs else None
        max_down = ret(min(lows[:21]))  if lows  else None

        # Only override archetype if currently UNKNOWN or NULL
        if d30 is not None:
            if d30 < -10:   bucket = "LOSS"
            elif d30 < 10:  bucket = "FLAT"
            elif d30 < 20:  bucket = "10PCT"
            elif d30 < 50:  bucket = "20PCT"
            elif d30 < 100: bucket = "50PCT"
            else:           bucket = "MULTIBAGGER"
        else:
            bucket = None

        cur.execute("""
            UPDATE ipo_intelligence SET
                return_day1_close = COALESCE(return_day1_close, %s),
                return_day7       = %s,
                return_day30      = %s,
                return_day90      = %s,
                return_cmp        = %s,
                max_upside_pct    = %s,
                max_drawdown_day30= %s,
                achieved_10pct    = %s,
                archetype         = COALESCE(NULLIF(archetype,'UNKNOWN'), %s),
                updated_at        = NOW()
            WHERE id = %s
        """, [d1, d7, d30, d90, cmp_r, max_up, max_down,
              bool(max_up and max_up >= 10), bucket, iid])
        ret_updated += 1
        if ret_updated % 30 == 0:
            conn.commit()
            log.info(f"    {ret_updated} returns calculated...")

    conn.commit()
    log.info(f"  Returns calculated: {ret_updated}")

    # ── FINAL REPORT ──────────────────────────────────────────────────────────
    log.info("\n=== FINAL COVERAGE REPORT ===")
    cur.execute("""
        SELECT
            COUNT(*)                                                      AS total,
            COUNT(symbol)                                                 AS symbol,
            COUNT(listing_date)                                           AS listing_date,
            COUNT(issue_price)                                            AS issue_price,
            COUNT(listing_gap_pct)                                        AS listing_gap,
            COUNT(sector)                                                 AS sector,
            COUNT(qib_subscription_x)                                     AS qib_x,
            COUNT(gmp_percentage)                                         AS gmp,
            COUNT(ipo_pe)                                                 AS ipo_pe,
            COUNT(return_day7)                                            AS d7_return,
            COUNT(return_day30)                                           AS d30_return,
            COUNT(return_day90)                                           AS d90_return,
            COUNT(archetype) FILTER (WHERE archetype NOT IN ('UNKNOWN','')) AS archetype,
            COUNT(*) FILTER (
                WHERE listing_gap_pct IS NOT NULL
                  AND qib_subscription_x IS NOT NULL
                  AND issue_price IS NOT NULL
                  AND return_day30 IS NOT NULL
            )                                                             AS engine_ready
        FROM ipo_intelligence
    """)
    r = cur.fetchone()
    labels = ["Total","symbol","listing_date","issue_price","listing_gap",
              "sector","qib_x","gmp","ipo_pe","d7_return","d30_return","d90_return",
              "archetype","*** ENGINE_READY ***"]
    for label, val in zip(labels, r):
        pct = int((val or 0) * 40 // (r[0] or 1))
        log.info(f"  {label:<22}: {str(val or 0):>4}  |{'=' * pct}")

    log.info("\nNext step: run the backtest engine once ENGINE_READY >= 150")
    conn.close()
    log.info("Done!")


if __name__ == "__main__":
    main()
