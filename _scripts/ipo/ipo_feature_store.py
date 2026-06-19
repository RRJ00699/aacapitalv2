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

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRES_PRISMA_URL")

if not DATABASE_URL:
    raise RuntimeError("No database URL found in .env")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ipo_feature_store (
    ipo_id BIGINT PRIMARY KEY,
    company_name TEXT,
    symbol TEXT,
    sector TEXT,
    status TEXT,
    listing_date DATE,
    has_live_feed BOOLEAN DEFAULT FALSE,
    has_gmp BOOLEAN DEFAULT FALSE,
    has_subscription BOOLEAN DEFAULT FALSE,
    has_symbol BOOLEAN DEFAULT FALSE,
    has_issue_price BOOLEAN DEFAULT FALSE,
    has_issue_size BOOLEAN DEFAULT FALSE,
    has_similarity BOOLEAN DEFAULT FALSE,
    has_sector_history BOOLEAN DEFAULT FALSE,
    gmp NUMERIC,
    gmp_pct NUMERIC,
    qib_sub NUMERIC,
    nii_sub NUMERIC,
    retail_sub NUMERIC,
    total_sub NUMERIC,
    issue_price NUMERIC,
    issue_size_cr NUMERIC,
    fresh_issue_cr NUMERIC,
    ofs_cr NUMERIC,
    fresh_ratio NUMERIC,
    ofs_ratio NUMERIC,
    avg_similarity_score NUMERIC,
    similar_avg_gain NUMERIC,
    similar_p_gain_10 NUMERIC,
    similar_p_gain_20 NUMERIC,
    similar_p_loss NUMERIC,
    similar_count INTEGER,
    sector_avg_gain NUMERIC,
    sector_p_gain_10 NUMERIC,
    sector_p_loss NUMERIC,
    sector_sample INTEGER,
    feature_quality_score NUMERIC,
    feature_quality_bucket TEXT,
    apply_eligible BOOLEAN DEFAULT FALSE,
    missing_features JSONB,
    quality_reasons JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
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


def quality_bucket(score):
    if score >= 75:
        return "HIGH"
    if score >= 55:
        return "MEDIUM"
    if score >= 35:
        return "LOW"
    return "VERY_LOW"


def load_data(conn):
    master = pd.read_sql(
        """
        SELECT id AS ipo_id, company_name, symbol, sector, status, listing_date,
               issue_price, issue_size_cr, fresh_issue_cr, ofs_cr
        FROM ipo_master
        """,
        conn,
    )

    live = pd.read_sql(
        """
        SELECT ipo_id, gmp, gmp_pct, qib_sub, nii_sub, retail_sub, total_sub,
               updated_at AS live_updated_at
        FROM ipo_live_feed
        """,
        conn,
    )

    hist = pd.read_sql(
        """
        SELECT ipo_id, sector, listing_gain_pct
        FROM ipo_historical_results
        WHERE listing_gain_pct IS NOT NULL
        """,
        conn,
    )

    sim = pd.read_sql(
        """
        SELECT ipo_id,
               AVG(similarity_score) AS avg_similarity_score,
               AVG(listing_gain_pct) AS similar_avg_gain,
               AVG(CASE WHEN listing_gain_pct >= 10 THEN 1 ELSE 0 END) * 100 AS similar_p_gain_10,
               AVG(CASE WHEN listing_gain_pct >= 20 THEN 1 ELSE 0 END) * 100 AS similar_p_gain_20,
               AVG(CASE WHEN listing_gain_pct < 0 THEN 1 ELSE 0 END) * 100 AS similar_p_loss,
               COUNT(*) AS similar_count
        FROM ipo_similarity_results
        GROUP BY ipo_id
        """,
        conn,
    )

    logging.info("Loaded master=%s live=%s historical=%s similarity=%s", len(master), len(live), len(hist), len(sim))
    return master, live, hist, sim


def build_sector_stats(hist):
    if hist.empty:
        return pd.DataFrame(columns=["sector_key", "sector_avg_gain", "sector_p_gain_10", "sector_p_loss", "sector_sample"])
    df = hist.copy()
    df["sector_key"] = df["sector"].fillna("").astype(str).str.lower().str.strip()
    df["gain"] = df["listing_gain_pct"].apply(lambda x: safe_float(x, None))
    df = df.dropna(subset=["gain"])
    return df.groupby("sector_key").agg(
        sector_avg_gain=("gain", "mean"),
        sector_p_gain_10=("gain", lambda x: (x >= 10).mean() * 100),
        sector_p_loss=("gain", lambda x: (x < 0).mean() * 100),
        sector_sample=("gain", "count"),
    ).reset_index()


def compute_feature_quality(row):
    symbol = str(row.get("symbol") or "").strip()
    has_symbol = symbol != ""
    has_live_feed = row.get("ipo_id_num") is not None and not pd.isna(row.get("ipo_id_num"))

    gmp = safe_float(row.get("gmp"), 0)
    gmp_pct = safe_float(row.get("gmp_pct"), 0)
    qib = safe_float(row.get("qib_sub"), 1)
    nii = safe_float(row.get("nii_sub"), 1)
    retail = safe_float(row.get("retail_sub"), 1)
    total = safe_float(row.get("total_sub"), 1)
    issue_price = safe_float(row.get("issue_price"), 0)
    issue_size = safe_float(row.get("issue_size_cr"), 0)
    avg_similarity_score = safe_float(row.get("avg_similarity_score"), 0)
    similar_count = int(safe_float(row.get("similar_count"), 0))
    sector_sample = int(safe_float(row.get("sector_sample"), 0))

    has_gmp = abs(gmp_pct) > 0.01 or abs(gmp) > 0.01
    has_subscription = abs(qib - 1) > 0.01 or abs(nii - 1) > 0.01 or abs(retail - 1) > 0.01 or abs(total - 1) > 0.01
    has_issue_price = issue_price > 0
    has_issue_size = issue_size > 0
    has_similarity = similar_count >= 3 and avg_similarity_score > 0
    has_sector_history = sector_sample >= 5

    components = {
        "live_feed": 15 if has_live_feed else 0,
        "gmp": 20 if has_gmp else 0,
        "subscription": 25 if has_subscription else 0,
        "similarity": 20 if has_similarity else 0,
        "sector_history": 8 if has_sector_history else 0,
        "issue_price": 5 if has_issue_price else 0,
        "issue_size": 5 if has_issue_size else 0,
        "symbol": 2 if has_symbol else 0,
    }
    score = clamp(sum(components.values()), 0, 100)

    missing = []
    for key, ok in [
        ("live_feed", has_live_feed), ("gmp", has_gmp), ("subscription", has_subscription),
        ("similarity", has_similarity), ("sector_history", has_sector_history),
        ("issue_price", has_issue_price), ("issue_size", has_issue_size), ("symbol", has_symbol)
    ]:
        if not ok:
            missing.append(key)

    apply_eligible = score >= 70 and has_gmp and has_subscription and has_similarity
    return {
        "has_live_feed": has_live_feed,
        "has_gmp": has_gmp,
        "has_subscription": has_subscription,
        "has_symbol": has_symbol,
        "has_issue_price": has_issue_price,
        "has_issue_size": has_issue_size,
        "has_similarity": has_similarity,
        "has_sector_history": has_sector_history,
        "feature_quality_score": round(score, 2),
        "feature_quality_bucket": quality_bucket(score),
        "apply_eligible": apply_eligible,
        "missing_features": missing,
        "quality_reasons": {
            "components": components,
            "apply_rules": {
                "feature_quality_score_gte": 70,
                "requires_gmp": True,
                "requires_subscription": True,
                "requires_similarity": True,
            },
        },
    }


def nullable_float(value):
    return safe_float(value, None)


def build_rows(master, live, hist, sim):
    live = live.copy()
    live["ipo_id_num"] = pd.to_numeric(live["ipo_id"], errors="coerce")
    sector_stats = build_sector_stats(hist)

    master = master.copy()
    master["sector_key"] = master["sector"].fillna("").astype(str).str.lower().str.strip()

    df = master.merge(live.drop(columns=["ipo_id"], errors="ignore"), left_on="ipo_id", right_on="ipo_id_num", how="left")
    df = df.merge(sim, on="ipo_id", how="left")
    df = df.merge(sector_stats, on="sector_key", how="left")

    rows = []
    for _, row in df.iterrows():
        issue_size = safe_float(row.get("issue_size_cr"), 0)
        fresh = safe_float(row.get("fresh_issue_cr"), 0)
        ofs = safe_float(row.get("ofs_cr"), 0)
        fresh_ratio = fresh / issue_size if issue_size > 0 else 0
        ofs_ratio = ofs / issue_size if issue_size > 0 else 0
        q = compute_feature_quality(row)

        rows.append((
            int(row["ipo_id"]), row.get("company_name"), row.get("symbol"), row.get("sector"), row.get("status"), row.get("listing_date"),
            q["has_live_feed"], q["has_gmp"], q["has_subscription"], q["has_symbol"], q["has_issue_price"], q["has_issue_size"], q["has_similarity"], q["has_sector_history"],
            nullable_float(row.get("gmp")), nullable_float(row.get("gmp_pct")), nullable_float(row.get("qib_sub")), nullable_float(row.get("nii_sub")), nullable_float(row.get("retail_sub")), nullable_float(row.get("total_sub")),
            nullable_float(row.get("issue_price")), nullable_float(row.get("issue_size_cr")), nullable_float(row.get("fresh_issue_cr")), nullable_float(row.get("ofs_cr")), round(fresh_ratio, 4), round(ofs_ratio, 4),
            nullable_float(row.get("avg_similarity_score")), nullable_float(row.get("similar_avg_gain")), nullable_float(row.get("similar_p_gain_10")), nullable_float(row.get("similar_p_gain_20")), nullable_float(row.get("similar_p_loss")), int(safe_float(row.get("similar_count"), 0)),
            nullable_float(row.get("sector_avg_gain")), nullable_float(row.get("sector_p_gain_10")), nullable_float(row.get("sector_p_loss")), int(safe_float(row.get("sector_sample"), 0)),
            q["feature_quality_score"], q["feature_quality_bucket"], q["apply_eligible"], json.dumps(q["missing_features"]), json.dumps(q["quality_reasons"]), datetime.now(timezone.utc),
        ))
    return rows


def upsert_rows(conn, rows):
    sql = """
    INSERT INTO ipo_feature_store (
        ipo_id, company_name, symbol, sector, status, listing_date,
        has_live_feed, has_gmp, has_subscription, has_symbol, has_issue_price, has_issue_size, has_similarity, has_sector_history,
        gmp, gmp_pct, qib_sub, nii_sub, retail_sub, total_sub,
        issue_price, issue_size_cr, fresh_issue_cr, ofs_cr, fresh_ratio, ofs_ratio,
        avg_similarity_score, similar_avg_gain, similar_p_gain_10, similar_p_gain_20, similar_p_loss, similar_count,
        sector_avg_gain, sector_p_gain_10, sector_p_loss, sector_sample,
        feature_quality_score, feature_quality_bucket, apply_eligible, missing_features, quality_reasons, updated_at
    ) VALUES %s
    ON CONFLICT (ipo_id) DO UPDATE SET
        company_name=EXCLUDED.company_name, symbol=EXCLUDED.symbol, sector=EXCLUDED.sector, status=EXCLUDED.status, listing_date=EXCLUDED.listing_date,
        has_live_feed=EXCLUDED.has_live_feed, has_gmp=EXCLUDED.has_gmp, has_subscription=EXCLUDED.has_subscription, has_symbol=EXCLUDED.has_symbol,
        has_issue_price=EXCLUDED.has_issue_price, has_issue_size=EXCLUDED.has_issue_size, has_similarity=EXCLUDED.has_similarity, has_sector_history=EXCLUDED.has_sector_history,
        gmp=EXCLUDED.gmp, gmp_pct=EXCLUDED.gmp_pct, qib_sub=EXCLUDED.qib_sub, nii_sub=EXCLUDED.nii_sub, retail_sub=EXCLUDED.retail_sub, total_sub=EXCLUDED.total_sub,
        issue_price=EXCLUDED.issue_price, issue_size_cr=EXCLUDED.issue_size_cr, fresh_issue_cr=EXCLUDED.fresh_issue_cr, ofs_cr=EXCLUDED.ofs_cr, fresh_ratio=EXCLUDED.fresh_ratio, ofs_ratio=EXCLUDED.ofs_ratio,
        avg_similarity_score=EXCLUDED.avg_similarity_score, similar_avg_gain=EXCLUDED.similar_avg_gain, similar_p_gain_10=EXCLUDED.similar_p_gain_10, similar_p_gain_20=EXCLUDED.similar_p_gain_20, similar_p_loss=EXCLUDED.similar_p_loss, similar_count=EXCLUDED.similar_count,
        sector_avg_gain=EXCLUDED.sector_avg_gain, sector_p_gain_10=EXCLUDED.sector_p_gain_10, sector_p_loss=EXCLUDED.sector_p_loss, sector_sample=EXCLUDED.sector_sample,
        feature_quality_score=EXCLUDED.feature_quality_score, feature_quality_bucket=EXCLUDED.feature_quality_bucket, apply_eligible=EXCLUDED.apply_eligible,
        missing_features=EXCLUDED.missing_features, quality_reasons=EXCLUDED.quality_reasons, updated_at=EXCLUDED.updated_at;
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()
    logging.info("Upserted %s feature-store rows", len(rows))


def main():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
        conn.commit()
        master, live, hist, sim = load_data(conn)
        rows = build_rows(master, live, hist, sim)
        upsert_rows(conn, rows)
        with conn.cursor() as cur:
            cur.execute("SELECT feature_quality_bucket, COUNT(*) FROM ipo_feature_store GROUP BY feature_quality_bucket ORDER BY feature_quality_bucket")
            print("\nFeature quality summary:")
            for bucket, count in cur.fetchall():
                print(bucket, count)
    logging.info("DONE")


if __name__ == "__main__":
    main()
