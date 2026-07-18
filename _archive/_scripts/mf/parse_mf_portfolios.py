import os
import re
from pathlib import Path
from datetime import datetime

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


DATABASE_URL = os.getenv("DATABASE_URL")

MF_ROOT = Path("data/mf_holdings")

# folder slug -> display names. Folders are named like "hdfc_smallcap", "nippon_midcap".
AMC_DISPLAY = {
    "sbi": "SBI", "hdfc": "HDFC", "nippon": "Nippon India", "kotak": "Kotak",
    "axis": "Axis", "dsp": "DSP", "quant": "Quant", "invesco": "Invesco",
    "tata": "Tata", "bandhan": "Bandhan",
    # added so folders you already have stop being silently skipped:
    "canara": "Canara Robeco", "ppfas": "PPFAS", "shriram": "Shriram",
    "groww": "Groww", "mahindra": "Mahindra Manulife",
}
CAP_DISPLAY = {
    "smallcap": "Small Cap Fund", "small": "Small Cap Fund",
    "midcap": "Mid Cap Fund", "mid": "Mid Cap Fund",
    "flexicap": "Flexi Cap Fund", "flexi": "Flexi Cap Fund",
}

def folder_to_names(folder_name):
    """hdfc_smallcap -> ("HDFC Mutual Fund", "HDFC Small Cap Fund")"""
    parts = re.split(r"[_\-]+", folder_name.lower())
    amc = cap = None
    for part in parts:
        if part in AMC_DISPLAY: amc = AMC_DISPLAY[part]
        if part in CAP_DISPLAY: cap = CAP_DISPLAY[part]
    if amc and cap:
        return f"{amc} Mutual Fund", f"{amc} {cap}"
    return None, None

def discover_dirs():
    out = []
    if not MF_ROOT.exists():
        return out
    for folder in sorted(MF_ROOT.iterdir()):
        if not folder.is_dir():
            continue
        amc_name, scheme_name = folder_to_names(folder.name)
        if not amc_name:
            print(f"SKIP folder (can't map name): {folder.name}")
            continue
        out.append((amc_name, scheme_name, folder))
    return out


_MON3 = {m[:3].lower(): n for n, m in {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"}.items()}
_MON3["sept"] = 9


def _parse_date_str(t):
    """First-of-month date from a text fragment, trying the formats AMC files actually use.
    Uses digit/letter lookarounds (not \\b) so underscore-prefixed dates like
    'Portfolio_30042026' and 'Portfolio_May-2026' still match."""
    if not t:
        return None
    t = str(t)
    # 31-May-2026 / 31 May 26 / 31.May.2026
    m = re.search(r"(?<!\d)(\d{1,2})[\-/.\s]+([A-Za-z]{3,9})[\-/.\s]+(\d{2,4})(?!\d)", t)
    if m and m.group(2)[:3].lower() in _MON3:
        yr = int(m.group(3)); yr += 2000 if yr < 100 else 0
        return datetime(yr, _MON3[m.group(2)[:3].lower()], 1).date()
    # May-2026 / MAY 2026 / May-24  (no day)
    m = re.search(r"(?<![A-Za-z])([A-Za-z]{3,9})[\-/.\s]+(\d{2,4})(?!\d)", t)
    if m and m.group(1)[:3].lower() in _MON3:
        yr = int(m.group(2)); yr += 2000 if yr < 100 else 0
        return datetime(yr, _MON3[m.group(1)[:3].lower()], 1).date()
    # 31/05/2026 / 31-05-2026 / 31.05.2026
    m = re.search(r"(?<!\d)(\d{1,2})[\-/.](\d{1,2})[\-/.](\d{4})(?!\d)", t)
    if m and 1 <= int(m.group(2)) <= 12:
        return datetime(int(m.group(3)), int(m.group(2)), 1).date()
    # ISO 2026-05-31
    m = re.search(r"(?<!\d)(\d{4})[\-/.](\d{2})[\-/.](\d{2})(?!\d)", t)
    if m and 1 <= int(m.group(2)) <= 12:
        return datetime(int(m.group(1)), int(m.group(2)), 1).date()
    # 8-digit: DDMMYYYY (e.g. 30042026) or YYYYMMDD
    m = re.search(r"(?<!\d)(\d{8})(?!\d)", t)
    if m:
        s = m.group(1)
        dd, mm, yy = int(s[:2]), int(s[2:4]), int(s[4:])
        if 1 <= mm <= 12 and 1 <= dd <= 31 and 2000 <= yy <= 2100:
            return datetime(yy, mm, 1).date()
        yy, mm, dd = int(s[:4]), int(s[4:6]), int(s[6:])
        if 1 <= mm <= 12 and 2000 <= yy <= 2100:
            return datetime(yy, mm, 1).date()
    return None


def parse_date_from_filename(filename):
    return _parse_date_str(filename)


def month_from_content(raw):
    """Pull the disclosure month from the header area when the filename has no date.
    Prefers an explicit 'as on/at/of <date>', then a real date cell, then any date text."""
    head = raw.head(15)
    for cells in head.values:
        line = " ".join(str(x) for x in cells if pd.notna(x))
        if re.search(r"as\s+(on|at|of)\b", line, re.I):
            d = _parse_date_str(line)
            if d:
                return d
    for val in head.values.flatten():
        if isinstance(val, (pd.Timestamp, datetime)):
            return datetime(val.year, val.month, 1).date()
    text = " ".join(str(x) for x in head.values.flatten() if pd.notna(x))
    return _parse_date_str(text)


def clean_number(value):
    if pd.isna(value):
        return None

    value = str(value).replace(",", "").replace("%", "").strip()

    try:
        return float(value)
    except Exception:
        return None


def parse_excel_file(file_path, amc_name, scheme_name):
    raw = pd.read_excel(file_path, header=None)

    holding_month = parse_date_from_filename(file_path.name) or month_from_content(raw)

    if holding_month is None:
        print(f"SKIP no month (filename+content): {file_path.name}")
        return pd.DataFrame()

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

        if ("name of instrument" in c or "name of the instrument" in c
              or "instrument name" in c or "issuer" in c
              or "company name" in c or "name of company" in c
              or "security name" in c or "name of holding" in c):
            rename_map[col] = "stock_name"
        elif "isin" in c:
            rename_map[col] = "isin"
        elif "industry" in c or "sector" in c:
            rename_map[col] = "sector"
        elif "quantity" in c:
            rename_map[col] = "quantity"
        elif "market value" in c or "fair value" in c or "market/ fair value" in c or "market value" in c.replace("/"," "):
            rename_map[col] = "market_value_lakh"
        elif ("% to nav" in c or "% of nav" in c or "% nav" in c
              or "% to net asset" in c or "% of net asset" in c
              or "% to aum" in c or "% of aum" in c or "net asset" in c
              or ("%" in c and "asset" in c)):
            rename_map[col] = "portfolio_weight_pct"

    df = df.rename(columns=rename_map)

    # Two source columns can rename to the same target (e.g. "% to NAV" and "% to AUM"
    # both -> portfolio_weight_pct). That makes df["col"] return a DataFrame, and
    # clean_number then receives a Series -> "truth value of a Series is ambiguous".
    # Collapse duplicates, keeping the first occurrence.
    df = df.loc[:, ~df.columns.duplicated()]

    # --- drop DEBT/bond rows (these files mix equity + debt) ---
    # 1) any row carrying a coupon value is a bond, not equity
    coupon_cols = [c for c in df.columns if "coupon" in c]
    for cc in coupon_cols:
        df = df[df[cc].apply(lambda v: clean_number(v) is None)]
    # 2) name-based guard for debt/cash instruments that lack a coupon cell
    DEBT_KW = ("bond", "debenture", "ncd", "t-bill", "treasury", "g-sec", "gsec",
               "govt", "government", "sdl", "commercial paper", "certificate of deposit",
               "cd ", "tri party", "trireport", "repo", "cblo", "net receivable",
               "cash", "margin", "clearing corp", "money market")
    if "stock_name" in df.columns:
        def _is_debt_name(v):
            n = str(v).lower()
            return any(k in n for k in DEBT_KW)
        df = df[~df["stock_name"].apply(_is_debt_name)]

    required_columns = [
        "stock_name",
        "isin",
        "quantity",
        "market_value_lakh",
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
            "market_value_lakh",
            "portfolio_weight_pct",
        ]
    ]

    df = df[df["isin"].astype(str).str.startswith("INE", na=False)]
    df = df[df["stock_name"].notna()]

    df["quantity"] = df["quantity"].apply(clean_number)
    df["market_value_lakh"] = df["market_value_lakh"].apply(clean_number)
    df["market_value_cr"] = df["market_value_lakh"].apply(lambda v: round(v/100.0, 2) if v is not None else None)
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
            "market_value_lakh",
            "market_value_cr",
            "portfolio_weight_pct",
        ]
    ]

    return df


DDL = """
CREATE TABLE IF NOT EXISTS mf_scheme_holdings (
    id SERIAL PRIMARY KEY,
    month DATE NOT NULL,
    amc_name TEXT NOT NULL,
    scheme_name TEXT NOT NULL,
    stock_name TEXT,
    isin TEXT,
    sector TEXT,
    nse_symbol TEXT,
    quantity DOUBLE PRECISION,
    market_value_lakh DOUBLE PRECISION,
    market_value_cr DOUBLE PRECISION,
    portfolio_weight_pct DOUBLE PRECISION,
    UNIQUE (month, amc_name, scheme_name, isin)
);
ALTER TABLE mf_scheme_holdings ADD COLUMN IF NOT EXISTS market_value_lakh DOUBLE PRECISION;
ALTER TABLE mf_scheme_holdings ADD COLUMN IF NOT EXISTS market_value_cr DOUBLE PRECISION;
"""

UPSERT = """
INSERT INTO mf_scheme_holdings
  (month, amc_name, scheme_name, stock_name, isin, sector, nse_symbol,
   quantity, market_value_lakh, market_value_cr, portfolio_weight_pct)
VALUES %s
ON CONFLICT (month, amc_name, scheme_name, isin) DO UPDATE SET
  stock_name = EXCLUDED.stock_name,
  sector = EXCLUDED.sector,
  quantity = EXCLUDED.quantity,
  market_value_lakh = EXCLUDED.market_value_lakh,
  market_value_cr = EXCLUDED.market_value_cr,
  portfolio_weight_pct = EXCLUDED.portfolio_weight_pct
"""

def main():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL is missing")

    dirs = discover_dirs()
    if not dirs:
        print(f"No mappable AMC folders under {MF_ROOT}")
        return

    all_rows = []
    for amc_name, scheme_name, folder in dirs:
        files = sorted(folder.glob("*.xlsx"))
        print(f"\n=== {scheme_name}  ({len(files)} files) ===")
        for file_path in files:
            parsed = parse_excel_file(file_path, amc_name, scheme_name)
            if not parsed.empty:
                all_rows.append(parsed)

    if not all_rows:
        print("No rows parsed")
        return

    final = pd.concat(all_rows, ignore_index=True)
    final = final.drop_duplicates(
        subset=["month", "amc_name", "scheme_name", "isin"], keep="last"
    )
    print(f"\nRows parsed: {len(final)}")
    print(final.head(10).to_string())

    rows = list(final.itertuples(index=False, name=None))
    conn = psycopg2.connect(DATABASE_URL); conn.autocommit = True
    cur = conn.cursor()
    for stmt in DDL.strip().split(";"):
        if stmt.strip():
            cur.execute(stmt)
    execute_values(cur, UPSERT, rows, page_size=500)
    cur.close(); conn.close()
    print(f"DONE: upserted {len(rows)} rows into mf_scheme_holdings (idempotent)")


if __name__ == "__main__":
    main()