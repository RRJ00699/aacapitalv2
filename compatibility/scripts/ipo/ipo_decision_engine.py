import os
import json
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


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        value = float(value)
        if pd.isna(value):
            return default
        return value
    except Exception:
        return default


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def ensure_prediction_columns(conn):
    sql = """
    ALTER TABLE ipo_predictions
    ADD COLUMN IF NOT EXISTS final_decision TEXT,
    ADD COLUMN IF NOT EXISTS final_confidence NUMERIC,
    ADD COLUMN IF NOT EXISTS feature_quality_score NUMERIC,
    ADD COLUMN IF NOT EXISTS feature_quality_bucket TEXT,
    ADD COLUMN IF NOT EXISTS apply_eligible BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS decision_reasons JSONB;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def load_data(conn):
    df = pd.read_sql(
        """
        SELECT
            p.ipo_id,
            p.lqi_score,
            p.p_gain_10,
            p.p_gain_20,
            p.p_loss,
            p.expected_return_pct,
            p.expected_drawdown_pct,
            p.confidence AS probability_confidence,
            p.reasons AS probability_reasons,
            p.feature_json AS probability_features,
            f.company_name,
            f.symbol,
            f.sector,
            f.status,
            f.gmp_pct,
            f.qib_sub,
            f.nii_sub,
            f.retail_sub,
            f.total_sub,
            f.avg_similarity_score,
            f.similar_avg_gain,
            f.similar_count,
            f.feature_quality_score,
            f.feature_quality_bucket,
            f.apply_eligible,
            f.missing_features,
            f.quality_reasons
        FROM ipo_predictions p
        JOIN ipo_feature_store f ON f.ipo_id = p.ipo_id
        """,
        conn,
    )
    logging.info("Loaded %s prediction + feature rows", len(df))
    return df


def parse_json(value, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def final_decision(row):
    p_gain_10 = safe_float(row.get("p_gain_10"), 0)
    p_loss = safe_float(row.get("p_loss"), 100)
    expected = safe_float(row.get("expected_return_pct"), 0)
    lqi = safe_float(row.get("lqi_score"), 0)
    probability_confidence = safe_float(row.get("probability_confidence"), 0)
    feature_quality_score = safe_float(row.get("feature_quality_score"), 0)
    apply_eligible = bool(row.get("apply_eligible"))

    missing_features = parse_json(row.get("missing_features"), [])
    quality_reasons = parse_json(row.get("quality_reasons"), {})
    probability_reasons = parse_json(row.get("probability_reasons"), {})
    probability_features = parse_json(row.get("probability_features"), {})

    hard_blocks = []
    caution_flags = []

    if feature_quality_score < 70:
        hard_blocks.append("feature_quality_below_apply_threshold")
    if not apply_eligible:
        hard_blocks.append("apply_not_eligible_due_to_missing_core_features")
    if "gmp" in missing_features:
        hard_blocks.append("missing_gmp")
    if "subscription" in missing_features:
        hard_blocks.append("missing_subscription")
    if p_loss >= 45:
        hard_blocks.append("high_loss_probability")
    if expected < 0:
        hard_blocks.append("negative_expected_return")

    if p_gain_10 < 45:
        caution_flags.append("low_probability_of_10pct_gain")
    if lqi < 55:
        caution_flags.append("low_lqi_score")
    if probability_confidence < 60:
        caution_flags.append("low_probability_confidence")

    if hard_blocks:
        if p_loss >= 48 or expected < 0 or p_gain_10 < 40:
            decision = "AVOID"
        else:
            decision = "WATCH"
    else:
        if p_gain_10 >= 68 and p_loss <= 30 and expected >= 8 and lqi >= 65:
            decision = "APPLY"
        elif p_gain_10 >= 50 and expected >= 3 and p_loss < 45:
            decision = "WATCH"
        else:
            decision = "AVOID"

    final_confidence = probability_confidence
    if feature_quality_score < 70:
        final_confidence = min(final_confidence, 65)
    if feature_quality_score < 50:
        final_confidence = min(final_confidence, 50)
    if decision == "APPLY":
        final_confidence = min(95, max(final_confidence, 70))
    final_confidence = clamp(final_confidence, 20, 95)

    reasons = {
        "final_decision": decision,
        "decision_summary": {
            "p_gain_10": round(p_gain_10, 2),
            "p_loss": round(p_loss, 2),
            "expected_return_pct": round(expected, 2),
            "lqi_score": round(lqi, 2),
            "feature_quality_score": round(feature_quality_score, 2),
            "apply_eligible": apply_eligible,
        },
        "hard_blocks": hard_blocks,
        "caution_flags": caution_flags,
        "missing_features": missing_features,
        "feature_quality": quality_reasons,
        "probability_features": probability_features,
        "probability_reasons": probability_reasons,
        "rules": {
            "apply_requires_feature_quality_gte": 70,
            "apply_requires_apply_eligible": True,
            "apply_requires_p_gain_10_gte": 68,
            "apply_requires_p_loss_lte": 30,
            "apply_requires_expected_return_gte": 8,
            "apply_requires_lqi_gte": 65,
        },
        "model_version": "ipo_decision_engine_v1",
    }
    return decision, round(final_confidence, 2), reasons


def build_rows(df):
    rows = []
    for _, row in df.iterrows():
        decision, final_confidence, reasons = final_decision(row)
        rows.append((
            decision,
            final_confidence,
            safe_float(row.get("feature_quality_score"), 0),
            row.get("feature_quality_bucket"),
            bool(row.get("apply_eligible")),
            json.dumps(reasons),
            decision,
            final_confidence,
            json.dumps(reasons),
            datetime.now(timezone.utc),
            int(row["ipo_id"]),
        ))
    return rows


def update_predictions(conn, rows):
    sql = """
    UPDATE ipo_predictions
    SET
        final_decision = data.final_decision,
        final_confidence = data.final_confidence,
        feature_quality_score = data.feature_quality_score,
        feature_quality_bucket = data.feature_quality_bucket,
        apply_eligible = data.apply_eligible,
        decision_reasons = data.decision_reasons::jsonb,
        decision = data.legacy_decision,
        confidence = data.legacy_confidence,
        reasons = data.legacy_reasons::jsonb,
        updated_at = data.updated_at
    FROM (VALUES %s) AS data (
        final_decision, final_confidence, feature_quality_score, feature_quality_bucket,
        apply_eligible, decision_reasons, legacy_decision, legacy_confidence,
        legacy_reasons, updated_at, ipo_id
    )
    WHERE ipo_predictions.ipo_id = data.ipo_id;
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()
    logging.info("Updated %s IPO final decisions", len(rows))


def print_validation(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT final_decision, COUNT(*) FROM ipo_predictions GROUP BY final_decision ORDER BY final_decision")
        print("\nFinal decision summary:")
        for decision, count in cur.fetchall():
            print(decision, count)

        for decision in ["APPLY", "WATCH", "AVOID"]:
            print("\n" + "=" * 100)
            print(f"TOP 25 {decision}")
            print("=" * 100)
            cur.execute(
                """
                SELECT m.company_name, m.symbol, p.final_decision, p.lqi_score, p.p_gain_10,
                       p.p_loss, p.expected_return_pct, p.feature_quality_score, p.final_confidence
                FROM ipo_predictions p
                JOIN ipo_master m ON m.id = p.ipo_id
                WHERE p.final_decision = %s
                ORDER BY CASE WHEN %s = 'AVOID' THEN p.p_loss ELSE p.lqi_score END DESC
                LIMIT 25
                """,
                (decision, decision),
            )
            for row in cur.fetchall():
                print(row)


def main():
    with psycopg2.connect(DATABASE_URL) as conn:
        ensure_prediction_columns(conn)
        df = load_data(conn)
        rows = build_rows(df)
        update_predictions(conn, rows)
        print_validation(conn)
    logging.info("DONE")


if __name__ == "__main__":
    main()
