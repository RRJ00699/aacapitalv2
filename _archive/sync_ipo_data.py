"""
AACapital -- IPO Data Sync V2
Sources:
  1. ipo_history (Neon) -- 333 rows: listing_gain, issue_price, sector, sub data
  2. Excel (304 rows)  -- qib_x, nii_x, gmp, brlm, anchor_quality, ipo_pe
  3. price_candles     -- day7/30/90 returns for IPOs with symbol

Run: python sync_ipo_data.py
"""

import os, json, logging, psycopg2, psycopg2.extras
import pandas as pd

DATABASE_URL = os.environ.get("DATABASE_URL", "")
EXCEL_PATH   = os.environ.get("IPO_EXCEL", "ipo_master.xlsx")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()


def safe_float(v):
    try: return float(v) if v is not None and str(v).strip() not in ("", "nan", "None") else None
    except: return None


def main():
    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); return

    conn = psycopg2.connect(DATABASE_URL)
    log.info("Connected to Neon")

    # ── Discover actual ipo_intelligence columns ──────────────────────────────
    cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    intel_cols = {r[0] for r in cur.fetchall()}
    log.info(f"ipo_intelligence has {len(intel_cols)} columns")

    # ── STEP 1: Sync from ipo_history ────────────────────────────────────────
    log.info("\n=== STEP 1: Syncing from ipo_history ===")
    cur.execute("SELECT * FROM ipo_history ORDER BY year DESC, name")
    rows = cur.fetchall()
    col_names = [d[0] for d in cur.description]
    log.info(f"ipo_history: {len(rows)} rows")

    updated = inserted = skipped = 0

    for row in rows:
        h = dict(zip(col_names, row))
        name = h.get("name")
        if not name:
            skipped += 1; continue

        data = {}

        # Direct field mappings (only if column exists in ipo_intelligence)
        def add(intel_col, value):
            if intel_col in intel_cols and value is not None:
                data[intel_col] = value

        add("issue_price",         safe_float(h.get("issue_price")))
        add("listing_price",       safe_float(h.get("listing_price")))
        add("listing_gap_pct",     safe_float(h.get("listing_gain_pct")))
        add("return_listing_open", safe_float(h.get("listing_gain_pct")))
        add("return_day1_close",   safe_float(h.get("d1_close_gain_pct")))
        add("sector",              h.get("sector"))
        add("qib_subscription_x",  safe_float(h.get("qib_x")))
        add("nii_subscription_x",  safe_float(h.get("nii_x")))
        add("rii_subscription_x",  safe_float(h.get("retail_x")))
        add("total_subscription_x",safe_float(h.get("total_x")))
        add("ofs_pct",             safe_float(h.get("ofs_pct")))
        add("gmp_percentage",      safe_float(h.get("gmp_pct_of_issue")))
        add("ipo_score",           safe_float(h.get("ipo_score")))

        # anchor_investors is JSON in DB -- wrap as JSON array string
        anchor_raw = h.get("anchor_examples")
        if anchor_raw and "anchor_investors" in intel_cols:
            if isinstance(anchor_raw, list):
                data["anchor_investors"] = json.dumps(anchor_raw)
            else:
                # It's a plain string -- store as JSON array with one element
                data["anchor_investors"] = json.dumps([str(anchor_raw)])

        # archetype from listing_gain_bucket
        bucket = h.get("listing_gain_bucket")
        if bucket and "archetype" in intel_cols:
            data["archetype"] = str(bucket)

        # Calculate archetype from listing_gain_pct if not set
        if "archetype" not in data or not data.get("archetype"):
            gain = safe_float(h.get("listing_gain_pct"))
            if gain is not None and "archetype" in intel_cols:
                if gain < -10:   data["archetype"] = "LOSS"
                elif gain < 10:  data["archetype"] = "FLAT"
                elif gain < 20:  data["archetype"] = "10PCT"
                elif gain < 50:  data["archetype"] = "20PCT"
                elif gain < 100: data["archetype"] = "50PCT"
                else:            data["archetype"] = "MULTIBAGGER"

        if not data:
            skipped += 1; continue

        cur.execute("SELECT id FROM ipo_intelligence WHERE company_name = %s", [name])
        existing = cur.fetchone()

        if existing:
            set_parts = ", ".join(f"{k} = %s" for k in data)
            cur.execute(
                f"UPDATE ipo_intelligence SET {set_parts}, updated_at = NOW() WHERE company_name = %s",
                list(data.values()) + [name]
            )
            updated += 1
        else:
            cols = ["company_name"] + list(data.keys())
            vals = [name] + list(data.values())
            cur.execute(
                f"INSERT INTO ipo_intelligence ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(vals))})",
                vals
            )
            inserted += 1

        if (updated + inserted) % 50 == 0:
            conn.commit()
            log.info(f"  Progress: updated={updated} inserted={inserted}")

    conn.commit()
    log.info(f"Step 1 done -- updated={updated} inserted={inserted} skipped={skipped}")

    # ── STEP 2: Sync from Excel ───────────────────────────────────────────────
    log.info(f"\n=== STEP 2: Syncing from Excel ({EXCEL_PATH}) ===")

    if not os.path.exists(EXCEL_PATH):
        log.warning(f"Excel not found at {EXCEL_PATH} -- skipping")
    else:
        df = pd.read_excel(EXCEL_PATH)
        log.info(f"Excel: {df.shape[0]} rows, columns: {df.columns.tolist()}")

        xl_updated = xl_skipped = 0
        for _, xrow in df.iterrows():
            name = xrow.get("company_name")
            if not name or str(name).strip() in ("", "nan"):
                xl_skipped += 1; continue

            data = {}

            def xadd(intel_col, excel_col):
                if intel_col in intel_cols and excel_col in xrow:
                    v = safe_float(xrow[excel_col]) if intel_col not in ("anchor_quality","gmp_momentum","brlm_names") else xrow.get(excel_col)
                    if v is not None and str(v).strip() not in ("", "nan", "None", "Not Found", "Tier-2 Neutral"):
                        data[intel_col] = v

            xadd("qib_subscription_x",  "qib_x")
            xadd("nii_subscription_x",  "nii_x")
            xadd("rii_subscription_x",  "retail_x")
            xadd("total_subscription_x","total_x")
            xadd("gmp_percentage",       "gmp_pct_of_issue")
            xadd("gmp_momentum",         "gmp_momentum")
            xadd("ofs_pct",              "ofs_pct")
            xadd("ipo_pe",               "ipo_pe")
            xadd("peer_median_pe",       "peer_median_pe")
            xadd("brlm_names",           "brlm_names")
            xadd("anchor_quality",       "anchor_quality")

            # BRLM tier
            brlm = str(xrow.get("brlm_names","")).lower()
            if brlm and brlm != "not found" and "brlm_tier" in intel_cols:
                tier1 = ["kotak","axis","icici","goldman","morgan","jm financial","sbi","dsp","hsbc","ubs","nomura"]
                data["brlm_tier"] = "TIER_1" if any(b in brlm for b in tier1) else "TIER_2"

            if not data:
                xl_skipped += 1; continue

            set_parts = ", ".join(f"{k} = COALESCE(ipo_intelligence.{k}, %s)" for k in data)
            cur.execute(
                f"UPDATE ipo_intelligence SET {set_parts}, updated_at = NOW() WHERE company_name = %s",
                list(data.values()) + [str(name)]
            )
            if cur.rowcount > 0:
                xl_updated += 1
            else:
                xl_skipped += 1

        conn.commit()
        log.info(f"Step 2 done -- Excel updated={xl_updated} skipped={xl_skipped}")

    # ── STEP 3: Calculate returns from price_candles ──────────────────────────
    log.info("\n=== STEP 3: Returns from price_candles ===")
    cur.execute("""
        SELECT i.id, i.company_name, i.symbol, i.issue_price, i.listing_date::text
        FROM ipo_intelligence i
        WHERE i.symbol IS NOT NULL AND i.issue_price IS NOT NULL
          AND i.listing_date IS NOT NULL AND i.return_day30 IS NULL
    """)
    ipos = cur.fetchall()
    log.info(f"  IPOs eligible for return calc: {len(ipos)}")

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

        bucket = "UNKNOWN"
        if d30 is not None:
            if d30 < -10:   bucket = "LOSS"
            elif d30 < 10:  bucket = "FLAT"
            elif d30 < 20:  bucket = "10PCT"
            elif d30 < 50:  bucket = "20PCT"
            elif d30 < 100: bucket = "50PCT"
            else:           bucket = "MULTIBAGGER"

        cur.execute("""
            UPDATE ipo_intelligence SET
                return_day1_close=COALESCE(return_day1_close,%s),
                return_day7=%s, return_day30=%s, return_day90=%s, return_cmp=%s,
                max_upside_pct=%s, max_drawdown_day30=%s,
                achieved_10pct=%s, archetype=COALESCE(archetype,%s), updated_at=NOW()
            WHERE id=%s
        """, [d1,d7,d30,d90,cmp,max_up,max_down,bool(max_up and max_up>=10),bucket,iid])
        ret_updated += 1

    conn.commit()
    log.info(f"  Returns calculated: {ret_updated}")

    # ── FINAL REPORT ──────────────────────────────────────────────────────────
    log.info("\n=== FINAL COVERAGE REPORT ===")
    cur.execute("""
        SELECT
            COUNT(*)                                                    AS total,
            COUNT(issue_price)                                          AS has_price,
            COUNT(listing_gap_pct)                                      AS has_gap,
            COUNT(sector)                                               AS has_sector,
            COUNT(qib_subscription_x)                                   AS has_qib,
            COUNT(gmp_percentage)                                       AS has_gmp,
            COUNT(ipo_pe)                                               AS has_pe,
            COUNT(return_day30)                                         AS has_d30,
            COUNT(return_day90)                                         AS has_d90,
            COUNT(archetype) FILTER (WHERE archetype NOT IN ('UNKNOWN','')) AS has_archetype,
            COUNT(*) FILTER (
                WHERE listing_gap_pct IS NOT NULL
                  AND qib_subscription_x IS NOT NULL
                  AND issue_price IS NOT NULL
            )                                                           AS engine_ready
        FROM ipo_intelligence
    """)
    r = cur.fetchone()
    labels = ["Total","issue_price","listing_gap","sector","qib_x","gmp","ipo_pe","d30_return","d90_return","archetype","ENGINE_READY"]
    for label, val in zip(labels, r):
        bar = "=" * int((val or 0) * 30 // (r[0] or 1))
        log.info(f"  {label:<18}: {str(val):>4}  |{bar}")

    conn.close()
    log.info("\nDone! Run check_coverage.sql in Neon console for full breakdown.")

if __name__ == "__main__":
    main()
