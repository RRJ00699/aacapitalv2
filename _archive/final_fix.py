"""
AACapital -- Final Fix Script
1. Populates symbol in ipo_intelligence by fuzzy-matching company_name -> company_master.symbol
2. Syncs Excel data using ipo_name column (correct column name)
3. Runs returns calculator once symbols are populated

Run: python final_fix.py
"""

import os, re, logging, psycopg2, psycopg2.extras
import pandas as pd

DATABASE_URL = os.environ.get("DATABASE_URL", "")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

def normalize(name):
    """Normalize company name for fuzzy matching."""
    if not name: return ""
    s = str(name).lower().strip()
    s = re.sub(r"\b(limited|ltd\.?|private|pvt\.?|india|industries|technology|technologies|solutions|services|enterprises|holdings|group|international|infra|infrastructure|finance|financial|capital|ventures|corp|corporation)\b", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def main():
    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); return
    conn = psycopg2.connect(DATABASE_URL)
    log.info("Connected to Neon")
    cur = conn.cursor()

    # ── STEP 1: Build symbol lookup from company_master ───────────────────────
    log.info("\n=== STEP 1: Building symbol lookup from company_master ===")
    cur.execute("SELECT symbol, company_name FROM company_master WHERE symbol IS NOT NULL")
    master_rows = cur.fetchall()
    log.info(f"company_master: {len(master_rows)} symbols")

    # Build lookup: normalized_name -> symbol
    lookup = {}
    for symbol, cname in master_rows:
        key = normalize(cname)
        if key:
            lookup[key] = symbol
        # Also index by symbol itself (some names match symbol)
        lookup[symbol.lower()] = symbol

    # ── STEP 2: Match ipo_intelligence names to symbols ───────────────────────
    log.info("\n=== STEP 2: Matching IPO names to symbols ===")
    cur.execute("SELECT id, company_name FROM ipo_intelligence WHERE symbol IS NULL ORDER BY company_name")
    ipos = cur.fetchall()
    log.info(f"IPOs needing symbol: {len(ipos)}")

    matched = unmatched = 0
    unmatched_list = []

    for (iid, name) in ipos:
        key = normalize(name)
        symbol = lookup.get(key)

        # If no exact match, try partial matching
        if not symbol:
            # Try first word of IPO name against all master names
            words = key.split()
            if words:
                first = words[0]
                candidates = [(k, v) for k, v in lookup.items() if first in k]
                if len(candidates) == 1:
                    symbol = candidates[0][1]
                elif len(candidates) > 1:
                    # Pick longest key match
                    best = max(candidates, key=lambda x: len(set(x[0].split()) & set(words)))
                    if len(set(best[0].split()) & set(words)) >= 2:
                        symbol = best[1]

        if symbol:
            cur.execute("UPDATE ipo_intelligence SET symbol=%s, updated_at=NOW() WHERE id=%s", [symbol, iid])
            matched += 1
        else:
            unmatched += 1
            unmatched_list.append(name)

    conn.commit()
    log.info(f"  Matched: {matched} | Unmatched: {unmatched}")
    if unmatched_list[:10]:
        log.info(f"  Unmatched samples: {unmatched_list[:10]}")

    # ── STEP 3: Sync Excel data (using ipo_name column) ───────────────────────
    excel_path = os.environ.get("IPO_EXCEL", "")
    
    # Try to find the uploaded Excel
    candidates = [
        excel_path,
        "ipo_master.xlsx",
        "aacapital_ipo_master_304.xlsx",
        r"C:\Users\Admin\Downloads\AACapital_IPO_Data_Collection_Template.xlsx",
    ]
    df = None
    for path in candidates:
        if path and os.path.exists(path):
            try:
                df = pd.read_excel(path)
                log.info(f"\n=== STEP 3: Excel from {path} ===")
                log.info(f"  Shape: {df.shape}, Columns: {df.columns.tolist()}")
                break
            except Exception as e:
                log.warning(f"  Could not read {path}: {e}")

    if df is not None:
        # Detect name column
        name_col = None
        for c in ["ipo_name", "company_name", "name", "IPO Name", "Company"]:
            if c in df.columns:
                name_col = c
                break

        if name_col:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
            intel_cols = {r[0] for r in cur.fetchall()}

            col_map = {
                "qib_x":            "qib_subscription_x",
                "nii_x":            "nii_subscription_x",
                "retail_x":         "rii_subscription_x",
                "total_x":          "total_subscription_x",
                "gmp_pct_of_issue": "gmp_percentage",
                "gmp_t1":           "gmp_pct_t1",
                "gmp_direction":    "gmp_momentum",
                "ofs_pct":          "ofs_pct",
                "ipo_pe":           "ipo_pe",
                "peer_median_pe":   "peer_median_pe",
                "fresh_issue_amt_cr": "fresh_issue_cr",
                "ofs_amt_cr":       "ofs_cr",
                "total_issue_amt_cr": "issue_size_cr",
                "issue_price":      "issue_price",
                "valuation_gap_pct": "valuation_premium_pct",
                "brlm_names":       "brlm_names",
                "anchor_quality":   "anchor_quality",
            }

            xl_updated = xl_skipped = 0
            for _, xrow in df.iterrows():
                name = str(xrow.get(name_col, "")).strip()
                if not name or name == "nan": xl_skipped += 1; continue

                data = {}
                for xcol, icol in col_map.items():
                    if xcol in xrow and icol in intel_cols:
                        v = xrow[xcol]
                        sv = str(v).strip()
                        if sv not in ("", "nan", "None", "NaN", "Not Found", "Tier-2 Neutral"):
                            # Numeric or string
                            try:
                                data[icol] = float(v)
                            except (ValueError, TypeError):
                                data[icol] = sv

                if not data: xl_skipped += 1; continue

                # COALESCE -- only fill nulls
                set_parts = ", ".join(f"{k} = COALESCE(ipo_intelligence.{k}, %s)" for k in data)
                cur.execute(
                    f"UPDATE ipo_intelligence SET {set_parts}, updated_at=NOW() WHERE company_name ILIKE %s",
                    list(data.values()) + [f"%{name[:20]}%"]
                )
                if cur.rowcount > 0: xl_updated += 1
                else: xl_skipped += 1

            conn.commit()
            log.info(f"  Excel updated={xl_updated} skipped={xl_skipped}")
        else:
            log.warning("  No name column found in Excel")
    else:
        log.warning("  No Excel file found -- skipping Step 3")

    # ── STEP 4: Calculate returns from price_candles ──────────────────────────
    log.info("\n=== STEP 4: Returns from price_candles ===")
    cur.execute("""
        SELECT i.id, i.company_name, i.symbol, i.issue_price, i.listing_date::text
        FROM ipo_intelligence i
        WHERE i.symbol IS NOT NULL AND i.issue_price IS NOT NULL
          AND i.listing_date IS NOT NULL AND i.return_day30 IS NULL
    """)
    ipos = cur.fetchall()
    log.info(f"  Eligible: {len(ipos)}")

    ret_updated = 0
    for (iid, name, symbol, issue_price, listing_date) in ipos:
        ip = float(issue_price)
        cur.execute("""
            SELECT close, high, low FROM price_candles
            WHERE symbol=%s AND date >= %s::date ORDER BY date ASC LIMIT 120
        """, [symbol, listing_date])
        candles = cur.fetchall()
        if not candles: continue

        closes = [float(c[0]) for c in candles]
        highs  = [float(c[1]) for c in candles]
        lows   = [float(c[2]) for c in candles]
        def ret(p): return round((p-ip)/ip*100, 2) if ip > 0 else None

        d1  = ret(closes[1])  if len(closes) > 1  else None
        d7  = ret(closes[4])  if len(closes) > 4  else None
        d30 = ret(closes[20]) if len(closes) > 20 else None
        d90 = ret(closes[62]) if len(closes) > 62 else None
        cmp = ret(closes[-1])
        max_up   = ret(max(highs[:21])) if highs else None
        max_down = ret(min(lows[:21]))  if lows  else None

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
                return_day1_close=COALESCE(return_day1_close,%s),
                return_day7=%s, return_day30=%s, return_day90=%s, return_cmp=%s,
                max_upside_pct=%s, max_drawdown_day30=%s,
                achieved_10pct=%s,
                archetype=COALESCE(archetype,%s),
                updated_at=NOW()
            WHERE id=%s
        """, [d1,d7,d30,d90,cmp,max_up,max_down,
              bool(max_up and max_up>=10), bucket, iid])
        ret_updated += 1
        if ret_updated % 20 == 0:
            conn.commit()
            log.info(f"    Returns: {ret_updated} done")

    conn.commit()
    log.info(f"  Returns calculated: {ret_updated}")

    # ── FINAL REPORT ──────────────────────────────────────────────────────────
    log.info("\n=== FINAL COVERAGE REPORT ===")
    cur.execute("""
        SELECT
            COUNT(*)                                                     AS total,
            COUNT(symbol)                                                AS has_symbol,
            COUNT(issue_price)                                           AS has_price,
            COUNT(listing_gap_pct)                                       AS has_gap,
            COUNT(sector)                                                AS has_sector,
            COUNT(qib_subscription_x)                                    AS has_qib,
            COUNT(gmp_percentage)                                        AS has_gmp,
            COUNT(ipo_pe)                                                AS has_pe,
            COUNT(return_day30)                                          AS has_d30,
            COUNT(archetype) FILTER (WHERE archetype NOT IN ('UNKNOWN','')) AS has_archetype,
            COUNT(*) FILTER (
                WHERE listing_gap_pct IS NOT NULL
                  AND qib_subscription_x IS NOT NULL
                  AND issue_price IS NOT NULL
            )                                                            AS engine_ready
        FROM ipo_intelligence
    """)
    r = cur.fetchone()
    labels = ["Total","symbol","issue_price","listing_gap","sector","qib_x","gmp","ipo_pe","d30_return","archetype","ENGINE_READY"]
    for label, val in zip(labels, r):
        pct = int((val or 0) * 40 // (r[0] or 1))
        log.info(f"  {label:<18}: {str(val or 0):>4}  |{'=' * pct}")

    conn.close()
    log.info("\nAll done!")

if __name__ == "__main__":
    main()
