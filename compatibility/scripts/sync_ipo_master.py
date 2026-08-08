"""
AACapital -- Sync IPO Master Data
Reads aacapital_ipo_master_304.xlsx and upserts QIB, NII, GMP, OFS,
anchor_quality, ipo_pe, brlm_names into ipo_intelligence.

This file has 304 IPOs with real subscription data — critical for engine accuracy.

Run: python _scripts/sync_ipo_master.py
"""

import os, logging
import pandas as pd
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL", "")

# Path to the Excel — try multiple locations
EXCEL_PATHS = [
    "aacapital_ipo_master_304.xlsx",
    "data/ipo_alpha_engine_v3.xlsx",
    "_scripts/ipo_real_data.xlsx",
    "ipo_master.xlsx",
]


def find_excel():
    for p in EXCEL_PATHS:
        if os.path.exists(p):
            return p
    return None


def safe_float(val):
    try:
        v = float(val)
        return v if v == v else None  # nan check
    except Exception:
        return None


def main():
    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); return

    excel_path = find_excel()
    if not excel_path:
        log.error(f"Excel not found. Place aacapital_ipo_master_304.xlsx in project root.")
        return

    log.info(f"Reading: {excel_path}")
    df = pd.read_excel(excel_path)
    log.info(f"Rows: {len(df)}  Columns: {df.columns.tolist()}")

    # Normalize column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Map expected column names (flexible)
    col_map = {
        "company_name":    ["company_name", "name", "ipo_name", "company"],
        "qib_x":           ["qib_x", "qib", "qib_subscription_x"],
        "nii_x":           ["nii_x", "nii", "nii_subscription_x"],
        "retail_x":        ["retail_x", "retail", "rii_x"],
        "total_x":         ["total_x", "total", "total_subscription_x"],
        "gmp_pct":         ["gmp_pct_of_issue", "gmp_percentage", "gmp_pct", "gmp"],
        "gmp_momentum":    ["gmp_momentum", "gmp_direction"],
        "ofs_pct":         ["ofs_pct", "ofs"],
        "brlm_names":      ["brlm_names", "brlm", "lead_manager"],
        "anchor_quality":  ["anchor_quality", "anchor"],
        "ipo_pe":          ["ipo_pe", "pe", "p/e"],
        "peer_median_pe":  ["peer_median_pe", "peer_pe"],
    }

    def get_col(key):
        for c in col_map.get(key, [key]):
            if c in df.columns:
                return c
        return None

    name_col = get_col("company_name")
    if not name_col:
        log.error("No company_name column found"); return

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    # Load existing company names from ipo_intelligence for fuzzy matching
    cur.execute("SELECT id, company_name FROM ipo_intelligence")
    db_rows = cur.fetchall()
    db_map  = {r[1].lower().strip(): r[0] for r in db_rows}

    updated = skipped = 0

    for _, row in df.iterrows():
        company = str(row.get(name_col, "")).strip()
        if not company or company.lower() == "nan":
            continue

        # Find matching row in DB (exact then fuzzy)
        db_id = db_map.get(company.lower())
        if not db_id:
            # Try partial match
            for db_name, db_id_try in db_map.items():
                if company.lower()[:10] in db_name or db_name[:10] in company.lower():
                    db_id = db_id_try
                    break

        if not db_id:
            log.warning(f"  No match: {company}")
            skipped += 1
            continue

        # Build update dict — only set non-null values
        updates = {}
        def maybe(key, col_key):
            c = get_col(col_key)
            if c:
                v = safe_float(row.get(c))
                if v is not None:
                    updates[key] = v

        def maybe_str(key, col_key):
            c = get_col(col_key)
            if c:
                v = str(row.get(c, "")).strip()
                if v and v.lower() not in ("nan", "none", "not found", ""):
                    updates[key] = v

        maybe("qib_subscription_x",  "qib_x")
        maybe("nii_subscription_x",  "nii_x")
        maybe("rii_subscription_x",  "retail_x")
        maybe("total_subscription_x","total_x")
        maybe("gmp_percentage",       "gmp_pct")
        maybe("ofs_pct",              "ofs_pct")
        maybe("ipo_pe",               "ipo_pe")
        maybe("peer_median_pe",       "peer_median_pe")
        maybe_str("brlm_names",       "brlm_names")
        maybe_str("anchor_quality",   "anchor_quality")
        maybe_str("gmp_momentum",     "gmp_momentum")

        if not updates:
            skipped += 1
            continue

        set_clause = ", ".join(f"{k} = %s" for k in updates)
        vals       = list(updates.values()) + [db_id]

        try:
            cur.execute(
                f"UPDATE ipo_intelligence SET {set_clause}, updated_at=NOW() WHERE id=%s",
                vals
            )
            updated += 1
        except Exception as e:
            conn.rollback()
            log.error(f"  DB error for {company}: {e}")
            continue

    conn.commit()
    log.info(f"\nDone — updated={updated}  skipped={skipped}")

    # Coverage report
    cur.execute("""
        SELECT COUNT(*), COUNT(qib_subscription_x), COUNT(nii_subscription_x),
               COUNT(gmp_percentage), COUNT(ofs_pct), COUNT(ipo_pe), COUNT(brlm_names)
        FROM ipo_intelligence
    """)
    r = cur.fetchone()
    log.info(f"Coverage — total={r[0]} qib={r[1]} nii={r[2]} gmp={r[3]} ofs={r[4]} pe={r[5]} brlm={r[6]}")
    conn.close()


if __name__ == "__main__":
    main()
