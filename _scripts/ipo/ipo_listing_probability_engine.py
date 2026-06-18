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


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def create_prediction_table(conn):
    sql = """
    CREATE TABLE IF NOT EXISTS ipo_predictions (
        ipo_id BIGINT PRIMARY KEY,
        lqi_score NUMERIC,
        p_gain_10 NUMERIC,
        p_loss NUMERIC,
        expected_return NUMERIC,
        expected_drawdown NUMERIC,
        decision TEXT,
        confidence NUMERIC,
        reasons JSONB,
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        p_gain_20 NUMERIC,
        expected_drawdown_pct NUMERIC,
        feature_json JSONB,
        model_version TEXT,
        expected_return_pct NUMERIC
    );
    """

    with conn.cursor() as cur:
        cur.execute(sql)

    conn.commit()


def load_data(conn):
    master = pd.read_sql(
        """
        SELECT
            id AS ipo_id,
            company_name,
            symbol,
            sector,
            issue_price,
            price_band_high,
            issue_size_cr,
            fresh_issue_cr,
            ofs_cr,
            status,
            open_date,
            close_date,
            listing_date
        FROM ipo_master
        """,
        conn,
    )

    live = pd.read_sql(
        """
        SELECT
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
            updated_at
        FROM ipo_live_feed
        """,
        conn,
    )

    hist = pd.read_sql(
        """
        SELECT
            ipo_id,
            sector,
            issue_price,
            listing_gain_pct,
            qib_sub,
            nii_sub,
            retail_sub,
            total_sub,
            gmp_pct,
            market_regime
        FROM ipo_historical_results
        WHERE listing_gain_pct IS NOT NULL
        """,
        conn,
    )

    sim = pd.read_sql(
        """
        SELECT
            ipo_id,
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

    logging.info(
        "Loaded master=%s live=%s historical=%s similarity=%s",
        len(master),
        len(live),
        len(hist),
        len(sim),
    )

    return master, live, hist, sim


def historical_baselines(hist):
    if hist.empty:
        return {
            "avg_gain": 12.0,
            "p_gain_10": 50.0,
            "p_gain_20": 30.0,
            "p_loss": 30.0,
        }

    gains = hist["listing_gain_pct"].apply(lambda x: safe_float(x, None)).dropna()

    return {
        "avg_gain": round(float(gains.mean()), 2),
        "p_gain_10": round(float((gains >= 10).mean() * 100), 2),
        "p_gain_20": round(float((gains >= 20).mean() * 100), 2),
        "p_loss": round(float((gains < 0).mean() * 100), 2),
    }


def sector_baseline(hist, sector):
    if not sector or hist.empty:
        return None

    s = hist[hist["sector"].fillna("").str.lower() == str(sector).lower()]

    if len(s) < 5:
        return None

    gains = s["listing_gain_pct"].apply(lambda x: safe_float(x, None)).dropna()

    if gains.empty:
        return None

    return {
        "sector_avg_gain": round(float(gains.mean()), 2),
        "sector_p_gain_10": round(float((gains >= 10).mean() * 100), 2),
        "sector_p_loss": round(float((gains < 0).mean() * 100), 2),
        "sector_sample": int(len(gains)),
    }


def compute_score(row, base, sec):
    gmp_pct = safe_float(row.get("gmp_pct"), 0)
    qib = safe_float(row.get("qib_sub"), 1)
    nii = safe_float(row.get("nii_sub"), 1)
    retail = safe_float(row.get("retail_sub"), 1)
    total = safe_float(row.get("total_sub"), 1)
    anchor = safe_float(row.get("anchor_quality"), 0)

    fresh = safe_float(row.get("fresh_issue_cr"), 0)
    ofs = safe_float(row.get("ofs_cr"), 0)
    issue_size = safe_float(row.get("issue_size_cr"), 0)

    fresh_ratio = fresh / issue_size if issue_size > 0 else 0
    ofs_ratio = ofs / issue_size if issue_size > 0 else 0

    avg_similarity_score = safe_float(row.get("avg_similarity_score"), 0)
    similar_avg_gain = safe_float(row.get("similar_avg_gain"), base["avg_gain"])
    similar_p_gain_10 = safe_float(row.get("similar_p_gain_10"), base["p_gain_10"])
    similar_p_loss = safe_float(row.get("similar_p_loss"), base["p_loss"])
    similar_count = safe_float(row.get("similar_count"), 0)

    gmp_score = clamp((gmp_pct + 5) / 45, 0, 1) * 100

    sub_score = (
        clamp(math.log1p(qib) / math.log1p(100), 0, 1) * 35
        + clamp(math.log1p(nii) / math.log1p(100), 0, 1) * 30
        + clamp(math.log1p(retail) / math.log1p(50), 0, 1) * 20
        + clamp(math.log1p(total) / math.log1p(100), 0, 1) * 15
    )

    sector_score = sec["sector_p_gain_10"] if sec else base["p_gain_10"]

    structure_score = clamp(50 + fresh_ratio * 20 - ofs_ratio * 20, 0, 100)
    anchor_score = clamp(anchor, 0, 100)

    similarity_score = avg_similarity_score if similar_count > 0 else 50

    lqi = (
        similarity_score * 0.35
        + gmp_score * 0.25
        + sub_score * 0.20
        + sector_score * 0.10
        + structure_score * 0.05
        + anchor_score * 0.05
    )

    expected = (
        similar_avg_gain * 0.35
        + base["avg_gain"] * 0.20
        + gmp_pct * 0.30
        + (total - 1) * 0.10
        + (qib - 1) * 0.05
    )

    if sec:
        expected = expected * 0.80 + sec["sector_avg_gain"] * 0.20

    expected = clamp(expected, -25, 120)

    p_gain_10 = (
        similar_p_gain_10 * 0.45
        + sigmoid((lqi - 48) / 12) * 100 * 0.55
    )

    p_gain_20 = sigmoid((lqi - 62) / 12) * 100

    p_loss = (
        similar_p_loss * 0.45
        + (100 - sigmoid((lqi - 38) / 10) * 100) * 0.55
    )

    if gmp_pct < 0:
        p_loss += 15
    if total < 1:
        p_loss += 10
    if qib < 1:
        p_loss += 7

    p_loss = clamp(p_loss, 0, 95)
    expected_drawdown = -1 * clamp(8 + p_loss * 0.18, 5, 30)

    confidence = 35
    if similar_count >= 3:
        confidence += 25
    if gmp_pct != 0:
        confidence += 15
    if total > 1:
        confidence += 10
    if qib > 1:
        confidence += 10
    if sec and sec["sector_sample"] >= 5:
        confidence += 5

    confidence = clamp(confidence, 20, 95)

    # Strong live-data checks based on already-normalized numeric values.
    # This avoids Decimal('NaN') / string NaN edge cases after pandas merge.
    has_gmp = abs(gmp_pct) > 0.01
    has_subscription = abs(total - 1) > 0.01
    has_symbol = (
        row.get("symbol") is not None
        and not pd.isna(row.get("symbol"))
        and str(row.get("symbol")).strip() != ""
    )

    has_live_data = has_gmp and has_subscription

    if not has_live_data:
        confidence = min(confidence, 55)

    if not has_symbol:
        confidence = min(confidence, 60)

    if has_live_data and p_gain_10 >= 68 and p_loss <= 30 and expected >= 8:
        decision = "APPLY"
    elif p_loss >= 48 or expected < 0:
        decision = "AVOID"
    else:
        decision = "WATCH"

    reasons = {
        "gmp_pct": round(gmp_pct, 2),
        "qib_sub": round(qib, 2),
        "nii_sub": round(nii, 2),
        "retail_sub": round(retail, 2),
        "total_sub": round(total, 2),
        "fresh_ratio": round(fresh_ratio, 2),
        "ofs_ratio": round(ofs_ratio, 2),
        "similarity": {
            "avg_similarity_score": round(avg_similarity_score, 2),
            "similar_avg_gain": round(similar_avg_gain, 2),
            "similar_p_gain_10": round(similar_p_gain_10, 2),
            "similar_p_loss": round(similar_p_loss, 2),
            "similar_count": int(similar_count),
        },
        "sector_baseline": sec,
        "base_historical": base,
        "data_quality": {
            "has_gmp": bool(has_gmp),
            "has_subscription": bool(has_subscription),
            "has_symbol": bool(has_symbol),
            "has_live_data": bool(has_live_data),
        },
    }

    features = {
        "similarity_score": round(similarity_score, 2),
        "gmp_score": round(gmp_score, 2),
        "subscription_score": round(sub_score, 2),
        "sector_score": round(sector_score, 2),
        "structure_score": round(structure_score, 2),
        "anchor_score": round(anchor_score, 2),
    }

    return {
        "lqi_score": round(lqi, 2),
        "p_gain_10": round(p_gain_10, 2),
        "p_gain_20": round(p_gain_20, 2),
        "p_loss": round(p_loss, 2),
        "expected_return": round(expected, 2),
        "expected_return_pct": round(expected, 2),
        "expected_drawdown": round(expected_drawdown, 2),
        "expected_drawdown_pct": round(expected_drawdown, 2),
        "decision": decision,
        "confidence": round(confidence, 2),
        "reasons": reasons,
        "feature_json": features,
        "model_version": "ipo_listing_probability_v2_strict_live_gate",
    }


def build_predictions(master, live, hist, sim):
    live = live.copy()
    live["ipo_id_num"] = pd.to_numeric(live["ipo_id"], errors="coerce")

    df = master.merge(
        live,
        left_on="ipo_id",
        right_on="ipo_id_num",
        how="left",
        suffixes=("", "_live"),
    )

    df = df.merge(sim, on="ipo_id", how="left")

    missing_live_gmp = df["gmp_pct"].isna().sum()
    logging.info("After ipo_id merge: rows=%s missing_live_gmp=%s", len(df), missing_live_gmp)

    base = historical_baselines(hist)
    rows = []

    for _, row in df.iterrows():
        sec = sector_baseline(hist, row.get("sector"))
        result = compute_score(row, base, sec)

        rows.append(
            (
                int(row["ipo_id"]),
                result["lqi_score"],
                result["p_gain_10"],
                result["p_loss"],
                result["expected_return"],
                result["expected_drawdown"],
                result["decision"],
                result["confidence"],
                json.dumps(result["reasons"]),
                datetime.now(timezone.utc),
                result["p_gain_20"],
                result["expected_drawdown_pct"],
                json.dumps(result["feature_json"]),
                result["model_version"],
                result["expected_return_pct"],
            )
        )

    return rows


def upsert_predictions(conn, rows):
    sql = """
    INSERT INTO ipo_predictions (
        ipo_id,
        lqi_score,
        p_gain_10,
        p_loss,
        expected_return,
        expected_drawdown,
        decision,
        confidence,
        reasons,
        updated_at,
        p_gain_20,
        expected_drawdown_pct,
        feature_json,
        model_version,
        expected_return_pct
    )
    VALUES %s
    ON CONFLICT (ipo_id)
    DO UPDATE SET
        lqi_score = EXCLUDED.lqi_score,
        p_gain_10 = EXCLUDED.p_gain_10,
        p_loss = EXCLUDED.p_loss,
        expected_return = EXCLUDED.expected_return,
        expected_drawdown = EXCLUDED.expected_drawdown,
        decision = EXCLUDED.decision,
        confidence = EXCLUDED.confidence,
        reasons = EXCLUDED.reasons,
        updated_at = EXCLUDED.updated_at,
        p_gain_20 = EXCLUDED.p_gain_20,
        expected_drawdown_pct = EXCLUDED.expected_drawdown_pct,
        feature_json = EXCLUDED.feature_json,
        model_version = EXCLUDED.model_version,
        expected_return_pct = EXCLUDED.expected_return_pct;
    """

    with conn.cursor() as cur:
        execute_values(cur, sql, rows)

    conn.commit()
    logging.info("Upserted %s IPO predictions", len(rows))


def main():
    with psycopg2.connect(DATABASE_URL) as conn:
        create_prediction_table(conn)
        master, live, hist, sim = load_data(conn)
        rows = build_predictions(master, live, hist, sim)
        upsert_predictions(conn, rows)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT decision, COUNT(*)
                FROM ipo_predictions
                GROUP BY decision
                ORDER BY decision
                """
            )

            print("\nDecision summary:")
            for decision, count in cur.fetchall():
                print(decision, count)

    logging.info("DONE")


if __name__ == "__main__":
    main()
