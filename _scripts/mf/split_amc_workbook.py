#!/usr/bin/env python3
"""
split_amc_workbook.py — split a full multi-scheme AMC monthly-portfolio workbook into
single-scheme .xlsx files under data/mf_holdings/<amc>_<captype>/, which the existing
_scripts/mf/parse_mf_portfolios.py then loads (it derives the scheme from the folder
name, globs *.xlsx, and finds the holdings header by scanning for "isin"+"quantity").

Verified against the real Nippon India workbook: it is ONE SHEET PER SCHEME, with sheet 0
('Index') mapping a 2-letter sheet code -> full scheme name. We read that map, locate the
Mid Cap and Small Cap equity sheets, and write each out verbatim (so the original holdings
header survives for the downstream parser).

Add another AMC by dumping its workbook first:
    python -c "import pandas as pd,glob; f=[x for x in glob.glob('data/amfi_portfolios/*') if x.lower().endswith(('.xls','.xlsx'))][0]; xl=pd.ExcelFile(f); print(xl.sheet_names); print(pd.read_excel(f,0,header=None).head(35).to_string())"
then add a CONFIG entry below. DO NOT guess a layout you haven't seen.
"""
import os
import re
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# parse_mf_portfolios.parse_date_from_filename matches FULL month name + 4-digit year,
# so output filenames must use the full month name.
FULLMON = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
           7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"}
MONTHS_RE = "|".join(FULLMON.values())
ABBR = {m[:3].lower(): n for n, m in FULLMON.items()}
ABBR.update({"sept": 9})

# Per-AMC split recipe.
#   index_sheet      : sheet holding the code->name map (the workbook's table of contents)
#   code_col/name_col: columns within that index sheet
#   targets          : (folder_slug, include_regex, exclude_regex)
#                      folder_slug MUST be parseable by parse_mf_portfolios.folder_to_names:
#                      an AMC keyword (sbi/hdfc/nippon/kotak/axis/dsp/quant/invesco/tata/bandhan)
#                      PLUS a cap keyword (midcap/smallcap).
CONFIG = {
    "Nippon India": {
        "index_sheet": "Index",
        "code_col": 0,
        "name_col": 1,
        "targets": [
            ("nippon_midcap",   r"mid cap fund",   r"large|multi|flexi|small|nifty|etf|index|sensex"),
            ("nippon_smallcap", r"small cap fund", r"nifty|etf|index"),
        ],
    },
}


def _date_from_text(t):
    if not t:
        return None
    # 31-May-2026 / 31 May 26 / 31.May.2026
    m = re.search(r"(\d{1,2})[\-/.\s]+([A-Za-z]{3,9})[\-/.\s]+(\d{2,4})", t)
    if m and m.group(2)[:3].lower() in ABBR:
        yr = int(m.group(3)); yr += 2000 if yr < 100 else 0
        return datetime(yr, ABBR[m.group(2)[:3].lower()], 1).date()
    # 31/05/2026 / 31-05-2026 / 31.05.2026
    m = re.search(r"\b(\d{1,2})[\-/.](\d{1,2})[\-/.](\d{4})\b", t)
    if m and 1 <= int(m.group(2)) <= 12:
        return datetime(int(m.group(3)), int(m.group(2)), 1).date()
    # ISO 2026-05-31
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), 1).date()
    # May 2026
    m = re.search(r"(" + MONTHS_RE + r")[\-_ ]+(\d{4})", t, re.I)
    if m:
        return datetime(int(m.group(2)), ABBR[m.group(1)[:3].lower()], 1).date()
    return None


def detect_month(df_raw, override, source_name=""):
    """Disclosure month from --month, the source filename, a real date-cell, or top-row text."""
    if override:
        return datetime.strptime(override, "%Y-%m-%d").date()
    d = _date_from_text(source_name)            # e.g. NIMF-MONTHLY-PORTFOLIO-31-May-26.xls
    if d:
        return d
    for val in df_raw.head(40).values.flatten():  # a genuine Excel date cell
        if isinstance(val, (pd.Timestamp, datetime)):
            try:
                return datetime(val.year, val.month, 1).date()
            except Exception:
                pass
    text = " ".join(str(x) for x in df_raw.head(40).values.flatten() if pd.notna(x))
    return _date_from_text(text)


def has_holdings_header(df_raw):
    """parse_mf_portfolios looks for a row (within 60) containing both 'isin' and 'quantity'."""
    for i in range(min(60, len(df_raw))):
        row = " ".join(str(x) for x in df_raw.iloc[i].tolist()).lower()
        if "isin" in row and "quantity" in row:
            return True
    return False


def split(amc, file_path, out_root, month_override):
    cfg = CONFIG.get(amc)
    if not cfg:
        sys.exit(f"No split recipe for '{amc}'. Known: {list(CONFIG)}. Dump the workbook and add a CONFIG entry.")

    xl = pd.ExcelFile(file_path)
    idx = pd.read_excel(file_path, sheet_name=cfg["index_sheet"], header=None)
    code_to_name = {}
    for _, r in idx.iterrows():
        code = str(r[cfg["code_col"]]).strip()
        name = str(r[cfg["name_col"]]).strip()
        if code and code in xl.sheet_names and name and name.lower() != "nan":
            code_to_name[code] = name
    log.info(f"[{amc}] index maps {len(code_to_name)} scheme sheets")

    made = []
    for folder_slug, inc, exc in cfg["targets"]:
        inc_re, exc_re = re.compile(inc, re.I), re.compile(exc, re.I) if exc else None
        hits = [(c, n) for c, n in code_to_name.items()
                if inc_re.search(n) and not (exc_re and exc_re.search(n))]
        if not hits:
            log.error(f"[{amc}] {folder_slug}: no scheme matched /{inc}/ — skipped")
            continue
        if len(hits) > 1:
            log.warning(f"[{amc}] {folder_slug}: {len(hits)} schemes matched, using first. All: "
                        + "; ".join(f"{c}={n[:50]}" for c, n in hits))
        code, name = hits[0]

        raw = pd.read_excel(file_path, sheet_name=code, header=None)
        month = detect_month(raw, month_override, Path(file_path).name)
        if month is None:
            log.error(f"[{amc}] {folder_slug} ({code}={name[:40]}): could not detect month — "
                      f"pass --month YYYY-MM-DD; skipped")
            continue
        ok = has_holdings_header(raw)

        folder = Path(out_root) / folder_slug
        folder.mkdir(parents=True, exist_ok=True)
        fname = f"{folder_slug}_{FULLMON[month.month]}-{month.year}.xlsx"
        dest = folder / fname
        raw.to_excel(dest, header=False, index=False)   # verbatim → parser finds its own header
        flag = "OK" if ok else "WARN no isin+quantity header (parser will skip!)"
        log.info(f"[{amc}] {folder_slug}: sheet {code} '{name[:45]}' "
                 f"as-on {month:%b %Y} -> {dest}  [{flag}]")
        made.append(str(dest))

    return made


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--amc", required=True, help="AMC label (key in CONFIG), e.g. 'Nippon India'")
    ap.add_argument("--file", required=True, help="path to the downloaded multi-scheme workbook")
    ap.add_argument("--out", default="data/mf_holdings", help="root for per-fund folders")
    ap.add_argument("--month", help="override disclosure month as YYYY-MM-DD if auto-detect fails")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        sys.exit(f"File not found: {args.file}")
    made = split(args.amc, args.file, args.out, args.month)
    if made:
        log.info(f"Done — wrote {len(made)} single-scheme file(s). Next: python _scripts/mf/parse_mf_portfolios.py")
    else:
        log.warning("Done — wrote 0 files. See errors above.")


if __name__ == "__main__":
    main()
