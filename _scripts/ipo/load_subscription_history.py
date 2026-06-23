"""
load_subscription_history.py — ingest Chittorgarh/IPOMatrix "Issue Subscription"
exports into the ipo_subscription_history table.

Stores, per NSE symbol: category-wise subscription multiples (Anchor / QIB /
QIB-ex-anchor / NII / bNII / sNII / Retail / Employee / Total), the back-out
allocation % (QIB/NII/Retail share of the issue), and the inferred structure
(75/15/10 = Reg 6(2) institutional-heavy, vs 50/15/35 = normal).

Full rebuild: drop the data, re-ingest everything, dedup by NSE symbol keeping
the most-complete row. Re-run any time you drop a new Issue_Subscription_*.xlsx
into data/Ipo_reports/.

Usage:
    python _scripts/ipo/load_subscription_history.py
(uses DATABASE_URL / NEON_DATABASE_URL from env)
"""
import os, glob, sys, re
import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values

# Look in the standard reports dir first, then a couple of fallbacks.
SEARCH_DIRS = [
    "data/Ipo_reports",
    "data",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "Ipo_reports"),
]


def num(v):
    if v is None:
        return None
    s = re.sub(r"[,%]", "", str(v)).strip()
    if s == "" or s.lower() == "nan":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def find_header(path):
    """Header row = the one containing 'Company' and a QIB column."""
    raw = pd.read_excel(path, header=None, nrows=15)
    for i, row in raw.iterrows():
        vals = [str(v).strip().lower() for v in row]
        if any(v == "company" for v in vals) and any("qib" in v for v in vals):
            return i
    return 0


def col(df, *substrings, exclude=()):
    """First column whose lowercased name contains ALL substrings and none of exclude."""
    for c in df.columns:
        cl = str(c).lower()
        if all(s in cl for s in substrings) and not any(e in cl for e in exclude):
            return c
    return None


def parse_date(v):
    if v is None or str(v).strip().lower() in ("", "nan"):
        return None
    try:
        return pd.to_datetime(v, errors="coerce").date()
    except Exception:
        return None


def load_files():
    files = []
    for d in SEARCH_DIRS:
        files += glob.glob(os.path.join(d, "Issue_Subscription_*.xlsx"))
    files = sorted(set(os.path.abspath(f) for f in files))
    if not files:
        print("No Issue_Subscription_*.xlsx found in", SEARCH_DIRS)
        sys.exit(1)
    return files


def build_rows(files):
    rows = {}
    for f in files:
        d = pd.read_excel(f, skiprows=find_header(f))
        m = {
            "company":     col(d, "company"),
            "isin":        col(d, "isin"),
            "category":    col(d, "issue category"),
            "nse":         col(d, "nse symbol"),
            "opening":     col(d, "opening date"),
            "closing":     col(d, "closing date"),
            "listing":     col(d, "listing date"),
            "issue_amt":   col(d, "issue amount"),
            "anchor_x":    col(d, "anchor", "(x)"),
            "qib_x":       col(d, "qib", "(x)", exclude=("ex anchor", "ex-anchor")),
            "qib_ex_x":    col(d, "qib", "ex", "(x)"),
            "nii_x":       col(d, "nii", "(x)", exclude=("bnii", "snii")),
            "bnii_x":      col(d, "bnii", "(x)"),
            "snii_x":      col(d, "snii", "(x)"),
            "retail_x":    col(d, "retail", "(x)"),
            "employee_x":  col(d, "employee", "(x)"),
            "total_x":     col(d, "total"),
            # shares-applied (value) columns — used to back out allocation %
            "qib_app":     col(d, "qib", "applied"),
            "nii_app":     col(d, "nii", "applied", exclude=("bnii", "snii")),
            "retail_app":  col(d, "retail", "applied"),
        }
        for _, r in d.iterrows():
            sym = r[m["nse"]] if m["nse"] else None
            sym = str(sym).strip().upper() if sym is not None else ""
            if not sym or sym == "NAN":
                continue
            qx, nx, rx = num(r[m["qib_x"]]) if m["qib_x"] else None, \
                         num(r[m["nii_x"]]) if m["nii_x"] else None, \
                         num(r[m["retail_x"]]) if m["retail_x"] else None
            # allocation % via offered = applied / times
            qa = num(r[m["qib_app"]])    if m["qib_app"]    else None
            na = num(r[m["nii_app"]])    if m["nii_app"]    else None
            ra = num(r[m["retail_app"]]) if m["retail_app"] else None
            q_off = (qa / qx) if (qa and qx) else None
            n_off = (na / nx) if (na and nx) else None
            r_off = (ra / rx) if (ra and rx) else None
            tot   = sum(x for x in (q_off, n_off, r_off) if x) or None
            q_pct = round(q_off / tot * 100, 2) if (q_off and tot) else None
            n_pct = round(n_off / tot * 100, 2) if (n_off and tot) else None
            r_pct = round(r_off / tot * 100, 2) if (r_off and tot) else None
            structure = None
            if r_pct is not None:
                structure = "75/15/10" if r_pct <= 12 else "50/15/35" if r_pct >= 28 else "other"

            rec = dict(
                nse_symbol=sym,
                company=(str(r[m["company"]]).strip() if m["company"] and pd.notna(r[m["company"]]) else None),
                isin=(str(r[m["isin"]]).strip() if m["isin"] and pd.notna(r[m["isin"]]) else None),
                issue_category=(str(r[m["category"]]).strip() if m["category"] and pd.notna(r[m["category"]]) else None),
                opening_date=parse_date(r[m["opening"]]) if m["opening"] else None,
                closing_date=parse_date(r[m["closing"]]) if m["closing"] else None,
                listing_date=parse_date(r[m["listing"]]) if m["listing"] else None,
                issue_amount_cr=num(r[m["issue_amt"]]) if m["issue_amt"] else None,
                anchor_x=num(r[m["anchor_x"]]) if m["anchor_x"] else None,
                qib_x=qx,
                qib_ex_anchor_x=num(r[m["qib_ex_x"]]) if m["qib_ex_x"] else None,
                nii_x=nx,
                bnii_x=num(r[m["bnii_x"]]) if m["bnii_x"] else None,
                snii_x=num(r[m["snii_x"]]) if m["snii_x"] else None,
                retail_x=rx,
                employee_x=num(r[m["employee_x"]]) if m["employee_x"] else None,
                total_x=num(r[m["total_x"]]) if m["total_x"] else None,
                qib_alloc_pct=q_pct, nii_alloc_pct=n_pct, retail_alloc_pct=r_pct,
                structure_type=structure,
            )
            # dedup: keep the most-complete record per symbol
            score = sum(1 for v in rec.values() if v is not None)
            if sym not in rows or score > rows[sym][0]:
                rows[sym] = (score, rec)
    return [v[1] for v in rows.values()]


DDL = """
CREATE TABLE IF NOT EXISTS ipo_subscription_history (
    nse_symbol        TEXT PRIMARY KEY,
    company           TEXT,
    isin              TEXT,
    issue_category    TEXT,
    opening_date      DATE,
    closing_date      DATE,
    listing_date      DATE,
    issue_amount_cr   NUMERIC(14,2),
    anchor_x          NUMERIC(12,3),
    qib_x             NUMERIC(12,3),
    qib_ex_anchor_x   NUMERIC(12,3),
    nii_x             NUMERIC(12,3),
    bnii_x            NUMERIC(12,3),
    snii_x            NUMERIC(12,3),
    retail_x          NUMERIC(12,3),
    employee_x        NUMERIC(12,3),
    total_x           NUMERIC(12,3),
    qib_alloc_pct     NUMERIC(6,2),
    nii_alloc_pct     NUMERIC(6,2),
    retail_alloc_pct  NUMERIC(6,2),
    structure_type    TEXT,
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ish_listing   ON ipo_subscription_history (listing_date DESC);
CREATE INDEX IF NOT EXISTS idx_ish_structure ON ipo_subscription_history (structure_type);
"""

COLS = ["nse_symbol","company","isin","issue_category","opening_date","closing_date",
        "listing_date","issue_amount_cr","anchor_x","qib_x","qib_ex_anchor_x","nii_x",
        "bnii_x","snii_x","retail_x","employee_x","total_x","qib_alloc_pct",
        "nii_alloc_pct","retail_alloc_pct","structure_type"]


def write_db(rows):
    db = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not db:
        print("DATABASE_URL not set"); sys.exit(1)
    conn = psycopg2.connect(db); cur = conn.cursor()
    for stmt in DDL.strip().split(";"):
        if stmt.strip():
            cur.execute(stmt)
    cur.execute("TRUNCATE ipo_subscription_history")   # full rebuild
    vals = [tuple(r.get(c) for c in COLS) for r in rows]
    execute_values(cur,
        f"INSERT INTO ipo_subscription_history ({','.join(COLS)}) VALUES %s", vals)
    conn.commit()
    cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE structure_type='75/15/10') FROM ipo_subscription_history")
    n, n75 = cur.fetchone()
    cur.close(); conn.close()
    print(f"ipo_subscription_history rebuilt: {n} rows  ({n75} are 75/15/10 institutional-heavy)")


def main():
    files = load_files()
    print(f"Reading {len(files)} subscription file(s)")
    rows = build_rows(files)
    print(f"Parsed {len(rows)} unique IPOs by NSE symbol")
    write_db(rows)


if __name__ == "__main__":
    main()
