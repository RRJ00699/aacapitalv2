#!/usr/bin/env python3
"""
load_issue_details.py — creates and fills ipo_issue_details from Chittorgarh
"Issue Details" exports (data/Ipo_reports/Issue_Details_*.xlsx).

Captures the per-IPO data retail ignores but matters for quality screening:
financials at listing (ROE, ROCE, D/E, EPS, P/E pre/post, PAT margin, promoter
holding, revenue, net worth, borrowings, EBITDA) + structure (registrar,
market makers, ISIN, scrip codes, lead managers).

Additive: its own table, keyed by ISIN. Nothing existing is touched. Full rebuild
each run, so re-export the report and re-run to pick up new listings.

Run:  python _scripts/ipo/load_issue_details.py
"""
import os, re, glob, sys, psycopg2
import pandas as pd

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

# canonical db column -> substrings to find in the (messy) report header
CANON = {
    "company": ["company"], "isin": ["isin"], "nse_symbol": ["nse symbol"],
    "bse_scrip_code": ["bse scrip"], "issue_category": ["issue category"],
    "issue_type": ["issue type"], "pricing_method": ["pricing method"],
    "sale_type": ["sale type"], "stock_exchange": ["stock exchange"],
    "opening_date": ["opening date"], "closing_date": ["closing date"],
    "listing_date": ["listing date"], "face_value": ["face value"],
    "issue_price": ["issue price"], "fresh_issue_cr": ["fresh issue"],
    "ofs_cr": ["offer for sale"], "issue_amount_cr": ["issue amount"],
    "industry": ["industry"], "roe_pct": ["roe"], "roce_pct": ["roce"],
    "debt_equity": ["debt/equity", "debt equity"], "eps_pre": ["eps (pre"],
    "eps_post": ["eps (post"], "ronw_pct": ["ronw"], "pbv": ["p/bv"],
    "pe_pre": ["p/e (x) pre"], "pe_post": ["p/e (x) post"],
    "pat_margin_pct": ["pat margin"], "promoter_pre_pct": ["pre-issue promoter"],
    "promoter_post_pct": ["post-issue promoter"], "period_ended": ["period ended"],
    "revenue_cr": ["revenue"], "pat_cr": ["profit after tax"], "assets_cr": ["assets"],
    "net_worth_cr": ["net worth"], "total_borrowing_cr": ["total borrowing"],
    "ebitda_cr": ["ebitda"], "reserves_cr": ["reserves and surplus"],
    "lead_managers": ["lead manager"], "registrar": ["registrar"],
    "market_makers": ["market maker"],
}
NUMERIC = {"face_value","issue_price","fresh_issue_cr","ofs_cr","issue_amount_cr","roe_pct",
           "roce_pct","debt_equity","eps_pre","eps_post","ronw_pct","pbv","pe_pre","pe_post",
           "pat_margin_pct","promoter_pre_pct","promoter_post_pct","revenue_cr","pat_cr",
           "assets_cr","net_worth_cr","total_borrowing_cr","ebitda_cr","reserves_cr"}
DATES = {"opening_date","closing_date","listing_date"}
COLS = list(CANON.keys())

def find_header(f):
    raw = pd.read_excel(f, header=None, nrows=15)
    for i, row in raw.iterrows():
        vals = [str(v).strip() for v in row.tolist()]
        if "Company" in vals and any("Lead Manager" in v for v in vals):
            return i
    return None

def resolve(df_cols):
    """map canonical -> actual column name in this file"""
    out = {}
    low = {str(c).lower(): c for c in df_cols}
    for canon, subs in CANON.items():
        for c_low, c_orig in low.items():
            if any(s in c_low for s in subs):
                out[canon] = c_orig
                break
    return out

def num(v):
    if v is None: return None
    s = re.sub(r"[,%]", "", str(v)).strip()
    if s.lower() in ("", "nan", "-", "none", "not found"): return None
    try: return float(s)
    except ValueError: return None

def dt(v):
    try:
        d = pd.to_datetime(v, errors="coerce")
        return None if pd.isna(d) else d.date()
    except Exception: return None

def txt(v):
    s = str(v).strip()
    return None if s.lower() in ("", "nan", "none") else s

# ── read all report files, dedup by ISIN (last wins) ──────────────────────────
files = glob.glob("data/Ipo_reports/Issue_Details_*.xlsx")
if not files:
    sys.exit("No Issue_Details_*.xlsx in data/Ipo_reports/")

records = {}
for f in files:
    h = find_header(f)
    if h is None: continue
    df = pd.read_excel(f, skiprows=h)
    cmap = resolve(df.columns)
    if "isin" not in cmap and "nse_symbol" not in cmap:
        continue
    for _, r in df.iterrows():
        rec = {}
        for canon, src in cmap.items():
            v = r[src]
            rec[canon] = num(v) if canon in NUMERIC else dt(v) if canon in DATES else txt(v)
        key = rec.get("isin") or rec.get("nse_symbol") or (f"C:{rec.get('company')}" if rec.get("company") else None)
        if not key: continue
        rec.setdefault("isin", key if key.startswith("INE") else None) or None
        if not rec.get("isin"):
            rec["isin"] = key  # pseudo-key for the few without an ISIN
        records[key] = rec
print(f"parsed {len(records)} unique IPOs from {len(files)} file(s)")

# ── (re)build table ───────────────────────────────────────────────────────────
conn = psycopg2.connect(URL); conn.autocommit = True; cur = conn.cursor()
coldefs = ",\n  ".join(
    f"{c} " + ("DATE" if c in DATES else "NUMERIC" if c in NUMERIC else "TEXT")
    for c in COLS)
cur.execute(f"""
    CREATE TABLE IF NOT EXISTS ipo_issue_details (
      {coldefs},
      updated_at TIMESTAMPTZ DEFAULT now(),
      PRIMARY KEY (isin)
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS idx_iid_symbol ON ipo_issue_details (nse_symbol)")
cur.execute("DELETE FROM ipo_issue_details")

placeholders = ",".join(["%s"] * len(COLS))
inserted = 0
for rec in records.values():
    vals = [rec.get(c) for c in COLS]
    cur.execute(f"INSERT INTO ipo_issue_details ({','.join(COLS)}) VALUES ({placeholders}) "
                f"ON CONFLICT (isin) DO NOTHING", vals)
    inserted += 1

cur.execute("SELECT count(*), count(nse_symbol), count(roce_pct), count(pe_post) FROM ipo_issue_details")
n, nsym, nroce, npe = cur.fetchone()
print(f"ipo_issue_details rebuilt: {n} rows  (NSE symbol: {nsym}, ROCE: {nroce}, post P/E: {npe})")
print("\nSample (newest listings):")
cur.execute("""SELECT company, nse_symbol, roce_pct, pe_post, lead_managers
               FROM ipo_issue_details WHERE listing_date IS NOT NULL
               ORDER BY listing_date DESC LIMIT 5""")
for c, s, roce, pe, lm in cur.fetchall():
    print(f"  {str(c)[:26]:26s} {str(s or '-'):10s} ROCE={roce} P/E={pe}  {str(lm)[:30]}")
conn.close()
