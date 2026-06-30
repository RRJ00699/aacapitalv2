#!/usr/bin/env python3
"""
import_golden_master.py — ingest Golden_IPO_Master_CLEANED_v3.xlsx into ipo_intelligence,
extending the universe back to 2010 (kills the survivorship / short-history gap).

The Excel has no ticker column, so RESOLVE matches Company Name -> NSE symbol against the
Kite instruments dump + your live DB, conservatively, and writes a self-contained REVIEW
CSV (every field apply needs is in it). APPLY reads ONLY that CSV — no Excel, no paths.

GOLDEN RULE: inserts only genuinely-new company_names; never touches existing live rows.
Leaves listing_open + financials NULL on purpose (Zerodha candles + screener fill them).

WORKFLOW:
  1) python _scripts\\import_golden_master.py --xlsx "<path>\\Golden_IPO_Master_CLEANED_v3.xlsx"
  2) eyeball golden_symbol_review.csv (fix REVIEW rows, clear/delete to skip), save
  3) python _scripts\\import_golden_master.py --reviewed golden_symbol_review.csv --apply
  4) backfill_ipo_ohlc.py -> import_screener_financials.py -> build_ipo_consolidated_v2.py -> check_data_contract.py

Needs: pip install rapidfuzz openpyxl --break-system-packages ; Kite token in platform_config.
"""
import os, sys, re, argparse
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
try:
    import pandas as pd, psycopg2
except ImportError:
    sys.exit("pip install pandas psycopg2-binary openpyxl --break-system-packages")

REVIEW_DEFAULT = "golden_symbol_review.csv"
AUTO, REVIEW_HI = 92, 80
# review-CSV column -> ipo_intelligence column (identity/listing/subscription; NOT listing_open/financials)
FIELDS = {
    "issue_price": "issue_price", "issue_size_cr": "issue_size_cr",
    "open_date": "open_date", "close_date": "close_date", "listing_date": "listing_date",
    "qib_subscription_x": "qib_subscription_x", "nii_subscription_x": "nii_subscription_x",
    "rii_subscription_x": "rii_subscription_x", "total_subscription_x": "total_subscription_x",
    "brlm_names": "brlm_names",
}

def norm(s):
    s = str(s or "").lower()
    s = re.sub(r"\b(limited|ltd|private|pvt|india|indian|the|company|co)\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)

def db():
    u = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not u: sys.exit("Set DATABASE_URL.")
    return psycopg2.connect(u)

def resolve(xlsx):
    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        sys.exit("pip install rapidfuzz --break-system-packages")
    from kite_connect import get_kite

    m = pd.read_excel(xlsx, sheet_name="Master_Enriched")
    m = m[m["Include Mainboard"].astype(str).str.lower() == "yes"].copy()
    print(f"mainboard rows in Excel: {len(m)}")

    conn = db(); cur = conn.cursor()
    cur.execute("SELECT company_name, nse_symbol FROM ipo_intelligence WHERE company_name IS NOT NULL")
    live = {norm(c): (c, s) for c, s in cur.fetchall()}

    kite = get_kite()
    eq = [i for i in kite.instruments("NSE") if i.get("instrument_type") == "EQ" and i.get("name")]
    inst_names = {norm(i["name"]): i["tradingsymbol"] for i in eq}
    name_keys = list(inst_names.keys())
    print(f"live DB names: {len(live)} | NSE EQ instruments: {len(eq)}")

    # Excel source columns -> our review-CSV field names
    XL = {"issue_price": "Issue Price", "issue_size_cr": "Issue Size (Cr)",
          "open_date": "Open Date", "close_date": "Close Date", "listing_date": "Listing Date",
          "qib_subscription_x": "qib_x", "nii_subscription_x": "nii_x",
          "rii_subscription_x": "retail_x", "total_subscription_x": "total_x",
          "brlm_names": "brlm_names"}
    rows = []
    for _, r in m.iterrows():
        name = r.get("company_name_clean") or r.get("Company Name")
        k = norm(name)
        if k in live:
            sym, conf, status = live[k][1], 100, "IN_DB"
        else:
            best = process.extractOne(k, name_keys, scorer=fuzz.token_sort_ratio)
            if best and best[1] >= AUTO:      sym, conf, status = inst_names[best[0]], best[1], "AUTO"
            elif best and best[1] >= REVIEW_HI: sym, conf, status = inst_names[best[0]], best[1], "REVIEW"
            else:                               sym, conf, status = "", (best[1] if best else 0), "UNRESOLVED"
        row = dict(company=name, approved_symbol=sym, confidence=round(conf), status=status,
                   year=r.get("IPO Year"))
        for fld, xlcol in XL.items():
            v = r.get(xlcol)
            row[fld] = "" if pd.isna(v) else v
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(REVIEW_DEFAULT, index=False)
    vc = out["status"].value_counts().to_dict()
    print("status:", " | ".join(f"{k}={v}" for k, v in vc.items()))
    print(f"-> wrote {REVIEW_DEFAULT} (self-contained — apply needs only this file)")
    print("Eyeball REVIEW/UNRESOLVED rows, set/clear 'approved_symbol', then --apply.")

def apply(reviewed):
    rev = pd.read_csv(reviewed, dtype=str, keep_default_na=False)   # every cell a string; empties = ""
    rev["approved_symbol"] = rev["approved_symbol"].str.strip()
    rev = rev[(rev["status"] != "IN_DB") & (rev["approved_symbol"] != "")]
    if rev.empty: sys.exit("nothing approved to insert (all IN_DB or empty symbol).")
    print("approved by status:", rev["status"].value_counts().to_dict())

    conn = db(); cur = conn.cursor(); inserted = 0
    for _, r in rev.iterrows():
        name = str(r["company"]).strip()
        cur.execute("SELECT 1 FROM ipo_intelligence WHERE company_name = %s", (name,))
        if cur.fetchone():            # GOLDEN RULE: never touch an existing row
            continue
        data = {"nse_symbol": r["approved_symbol"].upper(), "is_sme": False, "company_name": name}
        for fld, dbcol in FIELDS.items():
            v = str(r.get(fld, "")).strip()
            if v != "":
                data[dbcol] = v       # Postgres casts text -> date/numeric on insert
        cols = list(data.keys())
        cur.execute(f"INSERT INTO ipo_intelligence ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(cols))})",
                    [data[c] for c in cols])
        inserted += 1
    conn.commit()
    print(f"\n✓ inserted {inserted} new IPOs (listing_open + financials left NULL).")
    print("NEXT: backfill_ipo_ohlc.py -> import_screener_financials.py -> build_ipo_consolidated_v2.py -> check_data_contract.py")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx")
    ap.add_argument("--reviewed")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.apply:
        if not a.reviewed: sys.exit("--apply needs --reviewed <csv>")
        apply(a.reviewed)
    elif a.xlsx:
        resolve(a.xlsx)
    else:
        sys.exit("give --xlsx <file> to resolve, or --reviewed <csv> --apply to insert.")

if __name__ == "__main__":
    main()
