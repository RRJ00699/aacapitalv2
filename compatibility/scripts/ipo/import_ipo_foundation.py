import os
import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found. Add DATABASE_URL to .env or environment.")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

IPO_MASTER_FILE = DATA_DIR / "ipo_seed_304.csv"
IPO_INTEL_FILE = DATA_DIR / "ipo_intelligence.xlsx"

print("PROJECT_ROOT:", PROJECT_ROOT)
print("DATA_DIR:", DATA_DIR)
print("IPO_MASTER_FILE:", IPO_MASTER_FILE, IPO_MASTER_FILE.exists())
print("IPO_INTEL_FILE:", IPO_INTEL_FILE, IPO_INTEL_FILE.exists())

if not IPO_MASTER_FILE.exists():
    raise FileNotFoundError(f"Missing file: {IPO_MASTER_FILE}")
if not IPO_INTEL_FILE.exists():
    raise FileNotFoundError(f"Missing file: {IPO_INTEL_FILE}")


def clean(v: Any) -> Optional[Any]:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, str):
        v = v.strip()
        if v == "" or v.lower() in {"nan", "none", "null", "na", "n/a"}:
            return None
    return v


def safe_json(row: pd.Series) -> str:
    d = {}
    for k, v in row.to_dict().items():
        cv = clean(v)
        d[k] = cv
    return json.dumps(d, default=str, allow_nan=False)


def first_value(row: pd.Series, *keys: str) -> Optional[Any]:
    for key in keys:
        value = clean(row.get(key))
        if value is not None:
            return value
    return None


def normalize_company_name(name: Any) -> Optional[str]:
    name = clean(name)
    if name is None:
        return None
    return " ".join(str(name).strip().lower().split())


def to_float_or_none(v: Any) -> Optional[float]:
    v = clean(v)
    if v is None:
        return None
    if isinstance(v, str):
        v = v.replace("%", "").replace("₹", "").replace(",", "").strip()
        if v.endswith("x") or v.endswith("X"):
            v = v[:-1]
    try:
        return float(v)
    except Exception:
        return None


def read_best_excel_sheet(path: Path) -> pd.DataFrame:
    xlsx = pd.ExcelFile(path)
    print("IPO Intelligence sheets:", xlsx.sheet_names)

    best_sheet = None
    best_score = -1
    best_shape = None

    for sheet in xlsx.sheet_names:
        tmp = pd.read_excel(path, sheet_name=sheet)
        tmp.columns = [str(c).lower().strip() for c in tmp.columns]
        cols = set(tmp.columns)
        score = tmp.shape[0]
        if "company_name" in cols or "ipo_name" in cols:
            score += 10000
        if "lqi_final" in cols or "prob_10pct_profit" in cols or "expected_return" in cols:
            score += 5000
        print(f"Sheet {sheet}: {tmp.shape[0]} rows, {tmp.shape[1]} cols, score={score}")
        if score > best_score:
            best_score = score
            best_sheet = sheet
            best_shape = tmp.shape

    print("Using sheet:", best_sheet, best_shape)
    df = pd.read_excel(path, sheet_name=best_sheet)
    df.columns = [str(c).lower().strip() for c in df.columns]
    df = df.where(pd.notnull(df), None)
    return df


def get_or_create_ipo_id(cur, mapping: dict, company: str, row: pd.Series, source: str) -> int:
    key = normalize_company_name(company)
    if key in mapping:
        return mapping[key]

    cur.execute(
        """
        INSERT INTO ipo_master(company_name, symbol, sector, source, raw_json)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            company,
            first_value(row, "symbol"),
            first_value(row, "sector"),
            source,
            safe_json(row),
        ),
    )
    ipo_id = cur.fetchone()[0]
    mapping[key] = ipo_id
    return ipo_id


def main() -> None:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("\nLoading IPO Master...")
        master = pd.read_csv(IPO_MASTER_FILE)
        master.columns = [str(c).lower().strip() for c in master.columns]
        master = master.where(pd.notnull(master), None)
        print("IPO Master shape:", master.shape)
        print(master.columns.tolist())

        master_rows = []
        skipped_master = 0

        for _, r in master.iterrows():
            company = first_value(r, "ipo_name", "company_name", "company", "name", "symbol")
            if company is None:
                skipped_master += 1
                continue

            master_rows.append(
                (
                    company,
                    first_value(r, "symbol"),
                    first_value(r, "isin"),
                    first_value(r, "ipo_type"),
                    first_value(r, "sector"),
                    first_value(r, "status", "ipo_status"),
                    first_value(r, "open_date", "issue_open_date"),
                    first_value(r, "close_date", "issue_close_date"),
                    first_value(r, "listing_date"),
                    to_float_or_none(first_value(r, "price_band_low")),
                    to_float_or_none(first_value(r, "price_band_high")),
                    to_float_or_none(first_value(r, "issue_price")),
                    first_value(r, "lot_size"),
                    to_float_or_none(first_value(r, "total_issue_amt_cr", "issue_size_cr")),
                    to_float_or_none(first_value(r, "fresh_issue_amt_cr", "fresh_issue_cr")),
                    to_float_or_none(first_value(r, "ofs_amt_cr", "ofs_cr")),
                    to_float_or_none(first_value(r, "face_value")),
                    first_value(r, "registrar"),
                    first_value(r, "brlm_names", "brlm"),
                    "seed",
                    safe_json(r),
                )
            )

        if master_rows:
            execute_values(
                cur,
                """
                INSERT INTO ipo_master(
                    company_name, symbol, isin, ipo_type, sector, status,
                    open_date, close_date, listing_date,
                    price_band_low, price_band_high, issue_price, lot_size,
                    issue_size_cr, fresh_issue_cr, ofs_cr, face_value,
                    registrar, brlm, source, raw_json
                )
                VALUES %s
                ON CONFLICT DO NOTHING
                """,
                master_rows,
            )

        print(f"Prepared {len(master_rows)} ipo_master rows, skipped {skipped_master}")

        cur.execute("SELECT id, company_name FROM ipo_master WHERE company_name IS NOT NULL")
        mapping = {normalize_company_name(name): ipo_id for ipo_id, name in cur.fetchall() if normalize_company_name(name)}

        print("\nLoading IPO Intelligence...")
        intel = read_best_excel_sheet(IPO_INTEL_FILE)
        print("IPO Intelligence shape:", intel.shape)
        print(intel.columns.tolist())

        hist_rows = []
        pred_rows = []
        skipped_intel = 0

        for _, r in intel.iterrows():
            company = first_value(r, "company_name", "ipo_name", "company", "name", "symbol")
            if company is None:
                skipped_intel += 1
                continue

            ipo_id = get_or_create_ipo_id(cur, mapping, str(company), r, "ipo_intelligence")

            hist_rows.append(
                (
                    ipo_id,
                    company,
                    first_value(r, "symbol"),
                    first_value(r, "listing_date"),
                    first_value(r, "ipo_type"),
                    first_value(r, "sector"),
                    to_float_or_none(first_value(r, "issue_price")),
                    to_float_or_none(first_value(r, "listing_price", "listing_open")),
                    to_float_or_none(first_value(r, "listing_gain_pct", "return_listing_open")),
                    to_float_or_none(first_value(r, "day_high", "listing_high")),
                    to_float_or_none(first_value(r, "day_low", "listing_low")),
                    to_float_or_none(first_value(r, "day_close")),
                    to_float_or_none(first_value(r, "day1_return_pct", "return_day1_close")),
                    to_float_or_none(first_value(r, "qib_sub", "qib_subscription", "qib_subscription_x")),
                    to_float_or_none(first_value(r, "nii_sub", "nii_subscription", "nii_subscription_x")),
                    to_float_or_none(first_value(r, "retail_sub", "retail_subscription", "rii_subscription_x")),
                    to_float_or_none(first_value(r, "total_sub", "total_subscription", "total_subscription_x")),
                    to_float_or_none(first_value(r, "gmp", "gmp_value")),
                    to_float_or_none(first_value(r, "gmp_pct", "gmp_percentage", "gmp_pct_t1")),
                    first_value(r, "market_regime", "market_regime_score"),
                    safe_json(r),
                )
            )

            pred_rows.append(
                (
                    ipo_id,
                    to_float_or_none(first_value(r, "lqi_score", "lqi_final", "ipo_score")),
                    to_float_or_none(first_value(r, "p_gain_10", "prob_10pct_profit")),
                    to_float_or_none(first_value(r, "p_gain_20", "prob_gain_20_50", "prob_gain_gt50")),
                    to_float_or_none(first_value(r, "p_loss", "prob_loss_gt10")),
                    to_float_or_none(first_value(r, "expected_return_pct", "expected_return")),
                    to_float_or_none(first_value(r, "expected_drawdown_pct", "max_drawdown_day1", "max_drawdown_day30")),
                    first_value(r, "decision", "suggested_action"),
                    to_float_or_none(first_value(r, "confidence", "confidence_level")),
                    "foundation-v1",
                    safe_json(r),
                )
            )

        if hist_rows:
            execute_values(
                cur,
                """
                INSERT INTO ipo_historical_results(
                    ipo_id, company_name, symbol, listing_date, ipo_type, sector,
                    issue_price, listing_price, listing_gain_pct,
                    day_high, day_low, day_close, day1_return_pct,
                    qib_sub, nii_sub, retail_sub, total_sub,
                    gmp, gmp_pct, market_regime, raw_json
                )
                VALUES %s
                """,
                hist_rows,
            )

        print(f"Prepared {len(hist_rows)} historical rows, skipped {skipped_intel}")

        if pred_rows:
            execute_values(
                cur,
                """
                INSERT INTO ipo_predictions(
                    ipo_id, lqi_score, p_gain_10, p_gain_20, p_loss,
                    expected_return_pct, expected_drawdown_pct,
                    decision, confidence, model_version, feature_json
                )
                VALUES %s
                ON CONFLICT (ipo_id)
                DO UPDATE SET
                    lqi_score = excluded.lqi_score,
                    p_gain_10 = excluded.p_gain_10,
                    p_gain_20 = excluded.p_gain_20,
                    p_loss = excluded.p_loss,
                    expected_return_pct = excluded.expected_return_pct,
                    expected_drawdown_pct = excluded.expected_drawdown_pct,
                    decision = excluded.decision,
                    confidence = excluded.confidence,
                    model_version = excluded.model_version,
                    feature_json = excluded.feature_json,
                    updated_at = now()
                """,
                pred_rows,
            )

        print(f"Prepared {len(pred_rows)} prediction rows")

        conn.commit()
        print("\nDONE")

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
