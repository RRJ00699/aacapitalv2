import os
import re
from pathlib import Path
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine


DATABASE_URL = os.getenv("DATABASE_URL")

BASE_DIRS = [
    ("SBI Mutual Fund", "SBI Small Cap Fund", Path("data/mf_holdings/sbi_smallcap")),
    ("SBI Mutual Fund", "SBI Magnum Midcap Fund", Path("data/mf_holdings/sbi_midcap")),
]


def parse_date_from_filename(filename):
    match = re.search(
        r"(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)[-_ ]+(\d{4})",
        filename.upper(),
    )
    if not match:
        return None

    return datetime.strptime(
        f"01 {match.group(1)} {match.group(2)}",
        "%d %B %Y",
    ).date()


def clean_number(value):
    if pd.isna(value):
        return None

    value = str(value).replace(",", "").replace("%", "").strip()

    try:
        return float(value)
    except Exception:
        return None


def parse_excel_file(file_path, amc_name, scheme_name):
    holding_month = parse_date_from_filename(file_path.name)

    if holding_month is None:
        print(f"SKIP no month: {file_path.name}")
        return pd.DataFrame()

    raw = pd.read_excel(file_path, header=None)

    header_row = None

    for i in range(min(60, len(raw))):
        row_text = " ".join(str(x) for x in raw.iloc[i].tolist()).lower()

        if "isin" in row_text and "quantity" in row_text:
            header_row = i
            break

    if header_row is None:
        print(f"SKIP no header: {file_path.name}")
        return pd.DataFrame()

    df = pd.read_excel(file_path, header=header_row)

    df.columns = [
        str(col).strip().lower().replace("\n", " ")
        for col in df.columns
    ]

    rename_map = {}

    for col in df.columns:
        c = col.lower()

        if "name of instrument" in c or "issuer" in c:
            rename_map[col] = "stock_name"
        elif "isin" in c:
            rename_map[col] = "isin"
        elif "industry" in c or "sector" in c:
            rename_map[col] = "sector"
        elif "quantity" in c:
            rename_map[col] = "quantity"
        elif "market value" in c:
            rename_map[col] = "market_value_cr"
        elif "% to nav" in c or "% of nav" in c or "% nav" in c:
            rename_map[col] = "portfolio_weight_pct"

    df = df.rename(columns=rename_map)

    required_columns = [
        "stock_name",
        "isin",
        "quantity",
        "market_value_cr",
    ]

    for col in required_columns:
        if col not in df.columns:
            print(f"SKIP missing {col}: {file_path.name}")
            print(df.columns.tolist())
            return pd.DataFrame()

    if "sector" not in df.columns:
        df["sector"] = None

    if "portfolio_weight_pct" not in df.columns:
        df["portfolio_weight_pct"] = None

    df = df[
        [
            "stock_name",
            "isin",
            "sector",
            "quantity",
            "market_value_cr",
            "portfolio_weight_pct",
        ]
    ]

    df = df[df["isin"].astype(str).str.startswith("INE", na=False)]
    df = df[df["stock_name"].notna()]

    df["quantity"] = df["quantity"].apply(clean_number)
    df["market_value_cr"] = df["market_value_cr"].apply(clean_number)
    df["portfolio_weight_pct"] = df["portfolio_weight_pct"].apply(clean_number)

    df["month"] = holding_month
    df["amc_name"] = amc_name
    df["scheme_name"] = scheme_name
    df["nse_symbol"] = None

    df = df[
        [
            "month",
            "amc_name",
            "scheme_name",
            "stock_name",
            "isin",
            "sector",
            "nse_symbol",
            "quantity",
            "market_value_cr",
            "portfolio_weight_pct",
        ]
    ]

    return df


def main():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL is missing")

    all_rows = []

    for amc_name, scheme_name, folder in BASE_DIRS:
        if not folder.exists():
            print(f"Folder missing: {folder}")
            continue

        for file_path in sorted(folder.glob("*.xlsx")):
            print(f"Parsing {file_path}")
            parsed = parse_excel_file(file_path, amc_name, scheme_name)

            if not parsed.empty:
                all_rows.append(parsed)

    if not all_rows:
        print("No rows parsed")
        return

    final = pd.concat(all_rows, ignore_index=True)

    final = final.drop_duplicates(
        subset=[
            "month",
            "amc_name",
            "scheme_name",
            "isin",
            "stock_name",
        ],
        keep="last",
    )

    print(f"Rows parsed: {len(final)}")
    print(final.head(10))

    engine = create_engine(DATABASE_URL)

    final.to_sql(
        name="mf_scheme_holdings",
        con=engine,
        if_exists="append",
        index=False,
        chunksize=500,
    )

    print("DONE: Loaded into mf_scheme_holdings")


if __name__ == "__main__":
    main()