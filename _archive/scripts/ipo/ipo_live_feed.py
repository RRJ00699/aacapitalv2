import os
import math
import logging
from datetime import datetime, timezone

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("POSTGRES_PRISMA_URL")
)

if not DATABASE_URL:
    raise RuntimeError("No database URL found in .env")


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ipo_live_feed (
    id BIGSERIAL PRIMARY KEY,
    ipo_id TEXT NOT NULL,
    symbol TEXT,
    company_name TEXT,
    gmp NUMERIC,
    gmp_pct NUMERIC,
    qib_sub NUMERIC DEFAULT 1,
    nii_sub NUMERIC DEFAULT 1,
    retail_sub NUMERIC DEFAULT 1,
    total_sub NUMERIC DEFAULT 1,
    anchor_quality NUMERIC DEFAULT 0,
    source TEXT DEFAULT 'ipo_historical_results',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ipo_id)
);
"""


def safe_float(value, default=None):
    if value is None:
        return default

    try:
        if isinstance(value, str):
            value = (
                value.replace(",", "")
                .replace("%", "")
                .replace("₹", "")
                .replace("Rs.", "")
                .replace("x", "")
                .strip()
            )

            if value.lower() in ["", "-", "na", "n/a", "null", "none", "nan"]:
                return default

        value = float(value)

        if math.isnan(value) or math.isinf(value):
            return default

        return value
    except Exception:
        return default


def load_historical_results(conn):
    df = pd.read_sql(
        """
        SELECT
            ipo_id,
            company_name,
            symbol,
            issue_price,
            gmp,
            gmp_pct,
            qib_sub,
            nii_sub,
            retail_sub,
            total_sub
        FROM ipo_historical_results
        WHERE ipo_id IS NOT NULL
        """,
        conn,
    )

    logging.info("Loaded %s rows from ipo_historical_results", len(df))
    return df


def normalize_live_feed(df):
    rows = []

    for _, r in df.iterrows():
        ipo_id = str(r.get("ipo_id")).strip()
        symbol = str(r.get("symbol") or "").strip().upper()
        company_name = str(r.get("company_name") or "").strip()

        issue_price = safe_float(r.get("issue_price"), None)
        gmp = safe_float(r.get("gmp"), None)
        gmp_pct = safe_float(r.get("gmp_pct"), None)

        if gmp_pct is None and gmp is not None and issue_price and issue_price > 0:
            gmp_pct = round((gmp / issue_price) * 100, 2)

        qib_sub = safe_float(r.get("qib_sub"), 1.0)
        nii_sub = safe_float(r.get("nii_sub"), 1.0)
        retail_sub = safe_float(r.get("retail_sub"), 1.0)
        total_sub = safe_float(r.get("total_sub"), 1.0)

        rows.append(
            (
                ipo_id,
                symbol,
                company_name,
                gmp,
                gmp_pct,
                qib_sub,
                nii_sub,
                retail_sub,
                total_sub,
                0.0,
                "ipo_historical_results",
                datetime.now(timezone.utc),
            )
        )

    return rows


def upsert_live_feed(conn, rows):
    if not rows:
        logging.warning("No rows prepared for ipo_live_feed")
        return

    sql = """
    INSERT INTO ipo_live_feed (
        ipo_id,
        symbol,
        company_name,
        gmp,
        gmp_pct,
        qib_sub,
        nii_sub,
        retail_sub,
        total_sub,
        anchor_quality,
        source,
        updated_at
    )
    VALUES %s
    ON CONFLICT (ipo_id)
    DO UPDATE SET
        symbol = EXCLUDED.symbol,
        company_name = EXCLUDED.company_name,
        gmp = EXCLUDED.gmp,
        gmp_pct = EXCLUDED.gmp_pct,
        qib_sub = EXCLUDED.qib_sub,
        nii_sub = EXCLUDED.nii_sub,
        retail_sub = EXCLUDED.retail_sub,
        total_sub = EXCLUDED.total_sub,
        anchor_quality = EXCLUDED.anchor_quality,
        source = EXCLUDED.source,
        updated_at = EXCLUDED.updated_at;
    """

    with conn.cursor() as cur:
        execute_values(cur, sql, rows)

    conn.commit()
    logging.info("Upserted %s rows into ipo_live_feed", len(rows))


def main():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute("TRUNCATE TABLE ipo_live_feed RESTART IDENTITY")
        conn.commit()

        df = load_historical_results(conn)
        rows = normalize_live_feed(df)

        logging.info("Prepared %s live IPO feed rows", len(rows))
        upsert_live_feed(conn, rows)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ipo_live_feed")
            count = cur.fetchone()[0]

        logging.info("DONE. ipo_live_feed count = %s", count)


if __name__ == "__main__":
    main()
