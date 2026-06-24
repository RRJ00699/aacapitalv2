import re
from pathlib import Path
from datetime import datetime

import pandas as pd


INPUT_DIRS = [
    Path.home() / "Downloads" / "MFDATA",
    Path("data/mf_holdings"),
]

OUTPUT_CSV = Path("data/mf_holdings/mf_holdings_ready.csv")

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def clean_number(x):
    if pd.isna(x):
        return None
    s = str(x).replace(",", "").replace("%", "").replace("₹", "").strip()
    if s in ("", "-", "nan", "None"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def infer_amc(path):
    text = str(path).lower()
    if "canara" in text:
        return "Canara Robeco Mutual Fund"
    if "ppfas" in text or "parag" in text or "ppfcf" in text:
        return "PPFAS Mutual Fund"
    if "quant" in text or "monthly_portfolio" in text or "mfdata" in text or path.name.lower().startswith("md-"):
        return "quant Mutual Fund"
    if "sbi" in text:
        return "SBI Mutual Fund"
    return "Unknown AMC"


def infer_month(path, raw):
    text = path.name + " "
    for i in range(min(15, len(raw))):
        text += " ".join(str(x) for x in raw.iloc[i].tolist()) + " "

    patterns = [
        r"(\d{1,2})[\s\-_]+([A-Za-z]+)[\s,\-_]+(\d{4})",
        r"([A-Za-z]+)[\s\-_]+(\d{1,2})[\s,\-_]+(\d{4})",
        r"([A-Za-z]+)[\s\-_]+(\d{4})",
        r"([A-Za-z]+)(\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue

        g = match.groups()

        if len(g) == 3:
            if g[0].isdigit():
                day = int(g[0])
                mon = g[1].lower()
                year = int(g[2])
            else:
                mon = g[0].lower()
                day = int(g[1])
                year = int(g[2])

            if mon in MONTHS:
                return datetime(year, MONTHS[mon], day).date()

        if len(g) == 2:
            mon = g[0].lower()
            year = int(g[1])
            if year < 100:
                year = 2000 + year

            if mon in MONTHS:
                return datetime(year, MONTHS[mon], 1).date()

    return None


def infer_scheme(path, sheet_name, raw):
    quant_map = {
        "qSCF": "quant Small Cap Fund",
        "qMCF": "quant Mid Cap Fund",
        "qFLEXI": "quant Flexi Cap Fund",
        "qActive": "quant Active Fund",
        "qIF": "quant Infrastructure Fund",
        "qVF": "quant Value Fund",
        "qMLC": "quant Large and Mid Cap Fund",
        "qMOM": "quant Momentum Fund",
    }

    sheet = str(sheet_name).strip()
    if sheet in quant_map:
        return quant_map[sheet]

    for i in range(min(10, len(raw))):
        for value in raw.iloc[i].tolist():
            if pd.isna(value):
                continue
            s = str(value).strip()
            if "fund" in s.lower() and len(s) < 150:
                return s

    if sheet and "sheet" not in sheet.lower():
        return sheet

    return path.stem.replace("_", " ").replace("-", " ")


def find_header_row(raw):
    for i in range(min(120, len(raw))):
        row_text = " ".join(str(x) for x in raw.iloc[i].tolist()).lower()
        if (
            "isin" in row_text
            and ("quantity" in row_text or "qty" in row_text)
            and "market" in row_text
            and "value" in row_text
        ):
            return i
    return None


def normalize_columns(columns):
    mapping = {}

    for col in columns:
        c = str(col).strip().lower().replace("\n", " ")

        if "name of instrument" in c or "name of the instrument" in c or "issuer" in c:
            mapping[col] = "stock_name"
        elif "isin" in c:
            mapping[col] = "isin"
        elif "industry" in c or "sector" in c:
            mapping[col] = "sector"
        elif "quantity" in c or "qty" in c:
            mapping[col] = "quantity"
        elif "market/fair value" in c or "market value" in c or "mkt value" in c:
            mapping[col] = "market_value_cr"
        elif "% to net" in c or "% to nav" in c or "% of nav" in c or "% nav" in c:
            mapping[col] = "portfolio_weight_pct"

    return mapping


def safe_get_column(df, name):
    value = df[name]
    if isinstance(value, pd.DataFrame):
        return value.iloc[:, 0]
    return value


def parse_sheet(path, sheet_name):
    try:
        raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    except Exception:
        return pd.DataFrame()

    header_row = find_header_row(raw)
    if header_row is None:
        return pd.DataFrame()

    month = infer_month(path, raw)
    if month is None:
        return pd.DataFrame()

    try:
        df = pd.read_excel(path, sheet_name=sheet_name, header=header_row)
    except Exception:
        return pd.DataFrame()

    df = df.rename(columns=normalize_columns(df.columns))

    required = ["stock_name", "isin", "quantity", "market_value_cr"]
    for col in required:
        if col not in df.columns:
            return pd.DataFrame()

    out = pd.DataFrame()
    out["stock_name"] = safe_get_column(df, "stock_name")
    out["isin"] = safe_get_column(df, "isin")
    out["quantity"] = safe_get_column(df, "quantity")
    out["market_value_cr"] = safe_get_column(df, "market_value_cr")

    if "sector" in df.columns:
        out["sector"] = safe_get_column(df, "sector")
    else:
        out["sector"] = None

    if "portfolio_weight_pct" in df.columns:
        out["portfolio_weight_pct"] = safe_get_column(df, "portfolio_weight_pct")
    else:
        out["portfolio_weight_pct"] = None

    out = out[out["isin"].astype(str).str.startswith("INE", na=False)]
    out = out[out["stock_name"].notna()]

    if out.empty:
        return pd.DataFrame()

    out["quantity"] = out["quantity"].apply(clean_number)
    out["market_value_cr"] = out["market_value_cr"].apply(clean_number)
    out["portfolio_weight_pct"] = out["portfolio_weight_pct"].apply(clean_number)

    out["month"] = month
    out["amc_name"] = infer_amc(path)
    out["scheme_name"] = infer_scheme(path, sheet_name, raw)
    out["nse_symbol"] = None
    out["market_value_lakh"] = out["market_value_cr"] * 100

    return out[
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
            "market_value_lakh",
        ]
    ]


def parse_workbook(path):
    try:
        xls = pd.ExcelFile(path)
    except Exception as e:
        print(f"SKIP unreadable: {path.name} | {e}")
        return pd.DataFrame()

    rows = []

    for sheet in xls.sheet_names:
        parsed = parse_sheet(path, sheet)
        if not parsed.empty:
            print(f"OK {path.name} / {sheet}: {len(parsed)} rows")
            rows.append(parsed)

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True)


def find_files():
    files = []
    for folder in INPUT_DIRS:
        if folder.exists():
            files.extend(folder.rglob("*.xlsx"))
            files.extend(folder.rglob("*.xls"))
    return sorted(set(files))


def main():
    files = find_files()
    print(f"Found Excel files: {len(files)}")

    all_rows = []

    for path in files:
        print(f"Parsing workbook: {path}")
        parsed = parse_workbook(path)
        if not parsed.empty:
            all_rows.append(parsed)

    if not all_rows:
        print("No rows parsed")
        return

    final = pd.concat(all_rows, ignore_index=True)

    final = final.drop_duplicates(
        subset=["month", "amc_name", "scheme_name", "isin", "stock_name"],
        keep="last",
    )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    final.to_csv(OUTPUT_CSV, index=False)

    print(f"DONE wrote CSV: {OUTPUT_CSV}")
    print(f"Rows written: {len(final)}")


if __name__ == "__main__":
    main()