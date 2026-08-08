#!/usr/bin/env python3
"""
_scripts/ipo/enrich_from_reports.py
-----------------------------------------------------------------------------
Loads REAL IPO data from data/Ipo_reports/*.xlsx (the IPOMatrix / Chittorgarh
exports already in the repo) into ipo_intelligence, overwriting the
placeholder / fabricated values the scoring run exposed.

Fixes, in order of impact:
  - real QIB / NII / Retail / Total subscription  (kills the fake 28x/65x rows)
  - issue_size_cr                                 (was NULL on most rows -> pt1)
  - open_date / listing_date                      (status classification)
  - listing_open / listing_day_close / open gain  (clean outcomes)
  - ipo_pe (P/E post-IPO)                          (valuation -> pt3/5)

Sources:
  Mainboard_IPOs_IPO_Subscription_Listing_Details_*  -> subscription/issue/dates/listing
  Mainboard_IPOs_Key_Performance_Indicator_KPI_*      -> P/E

Matching: normalized company name, with token-subset fallback so
"NTPC Green" matches "NTPC Green Energy Ltd.". Only columns that EXIST in the
table and have a real value are written, so this never errors on schema drift
and never nulls good data.

Usage:
  python _scripts/ipo/enrich_from_reports.py            # dry-run (no writes)
  python _scripts/ipo/enrich_from_reports.py --apply    # write to ipo_intelligence
  python _scripts/ipo/enrich_from_reports.py --test-xlsx data/ipo_intelligence.xlsx  # offline match test

After --apply, run score_ipos_live.py to re-score on the real data.
Install: pip install psycopg2-binary python-dotenv pandas openpyxl
"""

import os
import re
import sys
import glob
import argparse
from pathlib import Path

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv(".env.local" if Path(".env.local").exists() else ".env")
except ImportError:
    pass

REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "data" / "Ipo_reports"
DB_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

_STOP = {"ltd", "limited", "pvt", "private", "the", "india", "co", "corp",
         "corporation", "inc", "of", "and"}


def toks(name):
    s = re.sub(r"[.,&'()/\-]", " ", str(name).lower())
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return frozenset(t for t in s.split() if t and t not in _STOP)


def num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().replace(",", "").replace("%", "")
    if s.lower() in ("", "nan", "-", "na", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def isodate(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return pd.to_datetime(v).date().isoformat()
    except Exception:
        return None


# ── load real data from the report spreadsheets ───────────────────────────────
def load_subscription():
    out = {}
    for f in glob.glob(str(REPORTS / "Mainboard_IPOs_IPO_Subscription_Listing_Details_*.xlsx")):
        d = pd.read_excel(f, skiprows=2, header=None).iloc[:, :15]
        for _, r in d.iterrows():
            co = str(r[0]).strip()
            if len(co) < 3 or co.lower() == "nan":
                continue
            out[co] = {
                "issue_price":          num(r[2]),
                "issue_size_cr":        num(r[3]),
                "open_date":            isodate(r[1]),
                "qib_subscription_x":   num(r[4]),
                "nii_subscription_x":   num(r[5]),
                "rii_subscription_x":   num(r[6]),
                "total_subscription_x": num(r[10]),
                "listing_date":         isodate(r[11]),
                "listing_open":         num(r[12]),
                "listing_day_close":    num(r[13]),
                "return_listing_open":  num(r[14]),
            }
    return out


def load_kpi():
    out = {}
    for f in glob.glob(str(REPORTS / "Mainboard_IPOs_Key_Performance_Indicator_KPI_*.xlsx")):
        d = pd.read_excel(f, skiprows=2, header=None).iloc[:, :18]
        for _, r in d.iterrows():
            co = str(r[0]).strip()
            if len(co) < 3 or co.lower() == "nan":
                continue
            out[co] = {"ipo_pe": num(r[14])}
    return out


def build_enriched():
    sub = load_subscription()
    kpi = load_kpi()
    enriched = {}
    for co, rec in sub.items():
        enriched[co] = dict(rec)
    for co, rec in kpi.items():
        enriched.setdefault(co, {}).update({k: v for k, v in rec.items() if v is not None})
    # index by token set for matching
    index = [(toks(co), {k: v for k, v in rec.items() if v is not None}) for co, rec in enriched.items()]
    return enriched, [(t, rec) for t, rec in index if t]


def match(db_name, index):
    """Return the best enriched record for a DB company name, or None."""
    t = toks(db_name)
    if not t:
        return None
    best, best_score = None, 0.0
    for et, rec in index:
        if t == et:
            return rec
        if t <= et or et <= t:           # one is a subset of the other (variant)
            j = len(t & et) / len(t | et)
            if j > best_score:
                best, best_score = rec, j
    return best if best_score >= 0.6 else None


# ── offline test against a local xlsx snapshot ────────────────────────────────
def test_xlsx(path):
    _, index = build_enriched()
    db = pd.read_excel(path)
    namecol = "company_name" if "company_name" in db.columns else db.columns[0]
    hit = 0
    samples = ["NTPC Green", "Ola Electric", "Meesho", "Netweb", "Bharat Coking",
               "Tata Capital", "Vikram Solar"]
    shown = []
    for _, row in db.iterrows():
        rec = match(row[namecol], index)
        if rec:
            hit += 1
            nm = str(row[namecol])
            if any(s.lower() in nm.lower() for s in samples) and nm not in [s[0] for s in shown]:
                old_qib = row.get("qib_subscription_x")
                shown.append((nm, old_qib, rec.get("qib_subscription_x"),
                              rec.get("issue_size_cr"), rec.get("ipo_pe")))
    print(f"\nMatched {hit}/{len(db)} rows ({100*hit/len(db):.0f}%) to real report data.\n")
    print(f"{'company':34s}{'old QIB':>10s}{'REAL QIB':>10s}{'size_cr':>10s}{'PE':>8s}")
    for nm, oq, nq, sz, pe in shown:
        print(f"{nm[:34]:34s}{str(oq):>10s}{str(nq):>10s}{str(sz):>10s}{str(pe):>8s}")


# ── live DB upsert ────────────────────────────────────────────────────────────
def apply_to_db(dry):
    import psycopg2
    import psycopg2.extras
    if not DB_URL:
        print("ERROR: set DATABASE_URL", file=sys.stderr)
        sys.exit(1)
    _, index = build_enriched()
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    existing = {r["column_name"] for r in cur.fetchall()}
    cur.execute("SELECT id, company_name FROM ipo_intelligence")
    rows = cur.fetchall()

    matched, written = 0, 0
    for row in rows:
        rec = match(row["company_name"], index)
        if not rec:
            continue
        matched += 1
        fields = {k: v for k, v in rec.items() if k in existing and v is not None}
        if not fields:
            continue
        if dry:
            continue
        sets = ", ".join(f"{k} = %s" for k in fields)
        with conn.cursor() as uc:
            uc.execute(f"UPDATE ipo_intelligence SET {sets} WHERE id = %s",
                       list(fields.values()) + [row["id"]])
        written += 1
        if written % 50 == 0:
            conn.commit()
    if not dry:
        conn.commit()
    conn.close()
    cols_written = sorted({k for _, rec in index for k in rec} & existing)
    print(f"\nMatched {matched}/{len(rows)} ipo_intelligence rows to real report data.")
    print(f"Columns enriched: {cols_written}")
    if dry:
        print(f"\nDRY-RUN - nothing written. Re-run with --apply.")
    else:
        print(f"Updated {written} rows. Now run: python _scripts/ipo/score_ipos_live.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--test-xlsx", help="offline: test matching against a local xlsx snapshot")
    args = ap.parse_args()
    if args.test_xlsx:
        test_xlsx(args.test_xlsx)
    else:
        apply_to_db(dry=not args.apply)


if __name__ == "__main__":
    main()
