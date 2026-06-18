import os
import json
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
CREATE TABLE IF NOT EXISTS ipo_similarity_results (
    id BIGSERIAL PRIMARY KEY,
    ipo_id BIGINT NOT NULL,
    similar_ipo_id BIGINT NOT NULL,
    similar_company_name TEXT,
    similar_symbol TEXT,
    similarity_score NUMERIC,
    listing_gain_pct NUMERIC,
    reasons JSONB,
    model_version TEXT DEFAULT 'ipo_similarity_v1',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (ipo_id, similar_ipo_id)
);
"""


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        return value
    except Exception:
        return default


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def score_pair(a, b):
    score = 0.0
    reasons = {}

    sector_match = str(a.get("sector") or "").lower() == str(b.get("sector") or "").lower()
    if sector_match:
        score += 25
    reasons["sector_match"] = sector_match

    for field, weight, scale in [
        ("issue_price", 15, 300),
        ("gmp_pct", 20, 50),
        ("qib_sub", 15, 100),
        ("nii_sub", 15, 100),
        ("retail_sub", 10, 50),
        ("total_sub", 15, 100),
    ]:
        av = safe_float(a.get(field), 0)
        bv = safe_float(b.get(field), 0)
        diff_score = (1 - clamp(abs(av - bv) / scale, 0, 1)) * weight
        score += diff_score
        reasons[field] = {
            "target": round(av, 2),
            "similar": round(bv, 2),
            "score": round(diff_score, 2),
        }

    return round(clamp(score, 0, 100), 2), reasons


def load_data(conn):
    master = pd.read_sql(
        """
        SELECT
            id AS ipo_id,
            company_name,
            symbol,
            sector,
            issue_price
        FROM ipo_master
        """,
        conn,
    )

    live = pd.read_sql(
        """
        SELECT
            ipo_id,
            gmp_pct,
            qib_sub,
            nii_sub,
            retail_sub,
            total_sub
        FROM ipo_live_feed
        """,
        conn,
    )

    hist = pd.read_sql(
        """
        SELECT
            ipo_id,
            company_name,
            symbol,
            sector,
            issue_price,
            listing_gain_pct,
            gmp_pct,
            qib_sub,
            nii_sub,
            retail_sub,
            total_sub
        FROM ipo_historical_results
        WHERE listing_gain_pct IS NOT NULL
        """,
        conn,
    )

    live["ipo_id_num"] = pd.to_numeric(live["ipo_id"], errors="coerce")
    current = master.merge(
    live.drop(columns=["ipo_id"], errors="ignore"),
    left_on="ipo_id",
    right_on="ipo_id_num",
    how="left",
)

    logging.info("Loaded current=%s historical=%s", len(current), len(hist))
    return current, hist


def build_similarity_rows(current, hist, top_n=7):
    rows = []

    for _, a in current.iterrows():
        candidate_scores = []

        for _, b in hist.iterrows():
            if int(a["ipo_id"]) == int(b["ipo_id"]):
                continue

            similarity_score, reasons = score_pair(a, b)

            candidate_scores.append(
                {
                    "ipo_id": int(a["ipo_id"]),
                    "similar_ipo_id": int(b["ipo_id"]),
                    "similar_company_name": b.get("company_name"),
                    "similar_symbol": b.get("symbol"),
                    "similarity_score": similarity_score,
                    "listing_gain_pct": safe_float(b.get("listing_gain_pct"), 0),
                    "reasons": reasons,
                }
            )

        candidate_scores = sorted(
            candidate_scores,
            key=lambda x: x["similarity_score"],
            reverse=True,
        )[:top_n]

        for x in candidate_scores:
            rows.append(
                (
                    x["ipo_id"],
                    x["similar_ipo_id"],
                    x["similar_company_name"],
                    x["similar_symbol"],
                    x["similarity_score"],
                    x["listing_gain_pct"],
                    json.dumps(x["reasons"]),
                    "ipo_similarity_v1",
                    datetime.now(timezone.utc),
                )
            )

    return rows


def upsert_rows(conn, rows):
    if not rows:
        logging.warning("No similarity rows prepared")
        return

    sql = """
    INSERT INTO ipo_similarity_results (
        ipo_id,
        similar_ipo_id,
        similar_company_name,
        similar_symbol,
        similarity_score,
        listing_gain_pct,
        reasons,
        model_version,
        created_at
    )
    VALUES %s
    ON CONFLICT (ipo_id, similar_ipo_id)
    DO UPDATE SET
        similar_company_name = EXCLUDED.similar_company_name,
        similar_symbol = EXCLUDED.similar_symbol,
        similarity_score = EXCLUDED.similarity_score,
        listing_gain_pct = EXCLUDED.listing_gain_pct,
        reasons = EXCLUDED.reasons,
        model_version = EXCLUDED.model_version,
        created_at = EXCLUDED.created_at;
    """

    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE ipo_similarity_results RESTART IDENTITY")
        execute_values(cur, sql, rows)

    conn.commit()
    logging.info("Upserted %s similarity rows", len(rows))


def main():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
        conn.commit()

        current, hist = load_data(conn)
        rows = build_similarity_rows(current, hist, top_n=7)
        logging.info("Prepared %s similarity rows", len(rows))
        upsert_rows(conn, rows)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ipo_similarity_results")
            count = cur.fetchone()[0]

        logging.info("DONE. ipo_similarity_results count = %s", count)


if __name__ == "__main__":
    main()
