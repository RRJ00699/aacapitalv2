"""
stock_quality_flags.py  —  ADDITIVE. Does not touch any existing table.

Flags EXISTING listed NON-FINANCIAL stocks as CLEAN / FLAGGED using the validated
operator/earnings-quality screen (chronic negative operating cash flow; profit not
backed by cash; value-destroying ROCE). Financials are tagged EXCLUDED — the
accruals/ROCE test does not apply to lenders, brokers, AMCs, insurers (a growing
lender consumes operating cash by design, so the screen mislabels them).

Sector comes from stock_fundamentals.industry (100% populated in this DB).
Writes to its OWN table (stock_quality_flags), mirroring link_brlm_scores.py.
Nothing existing is altered. Run from repo root:
    $env:DATABASE_URL="postgresql://...neon..."
    python stock_quality_flags.py
"""
import psycopg2, os, glob
import pandas as pd
from statistics import median
    import csv


DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
FUND_DIR = "data/fundamental_raw"

# Substrings that mark a financial-sector industry (matched case-insensitively
# against stock_fundamentals.industry). Validated against this DB's taxonomy.
FINANCIAL_KEYWORDS = [
    "bank", "finance", "financial", "nbfc", "broking", "broker", "investment",
    "insurance", "asset management", "mutual fund", "securities", "depository",
    "stock exchange", "commodity exchange", "microfinance", "rating agenc", "capital market",
]

def is_financial(industry):
    if not industry:
        return False
    s = industry.lower()
    return any(k in s for k in FINANCIAL_KEYWORDS)

def row(df, label):
    for i in range(len(df)):
        if str(df.iloc[i, 0]).strip() == label:
            return pd.to_numeric(df.iloc[i, 1:], errors="coerce").dropna().tolist()
    return []

def classify(path):
    """Operator/quality screen for NON-financials. Returns (flag, reasons, metrics) or None."""
    try:
        d = pd.read_excel(path, sheet_name="Data Sheet", header=None)
    except Exception:
        return None
    npat = row(d, "Net profit"); ocf = row(d, "Cash from Operating Activity")
    pbt = row(d, "Profit before tax"); intr = row(d, "Interest")
    eq = row(d, "Equity Share Capital"); res = row(d, "Reserves"); bor = row(d, "Borrowings")
    if not ocf and not (pbt and eq):
        return None
    roce = []
    L = min(len(pbt), len(intr), len(eq), len(res), len(bor)) if (pbt and intr and eq and res and bor) else 0
    for k in range(L):
        ce = eq[k] + res[k] + bor[k]
        if ce > 0:
            roce.append((pbt[k] + intr[k]) / ce * 100)
    reasons = []
    neg = (sum(1 for x in ocf if x < 0) / len(ocf)) if ocf else None
    o2p = (sum(ocf) / sum(npat)) if (npat and ocf and sum(npat) > 0) else None
    mr = median(roce) if roce else None
    if neg is not None and neg > 0.5:        reasons.append("chronic negative operating cash flow")
    if o2p is not None and o2p < 0.3:         reasons.append("profit not backed by cash (accruals)")
    if mr is not None and mr < 6:             reasons.append("value-destroying ROCE (<6%)")
    flag = "FLAGGED" if reasons else "CLEAN"
    metrics = (round(neg,3) if neg is not None else None,
               round(o2p,3) if o2p is not None else None,
               round(mr,2) if mr is not None else None)
    return flag, "; ".join(reasons), metrics

def main():
    if not DATABASE_URL:
        raise SystemExit("Set DATABASE_URL (or NEON_DATABASE_URL) first.")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_quality_flags (
            nse_symbol TEXT PRIMARY KEY, quality_flag TEXT, quality_reasons TEXT,
            industry TEXT, neg_ocf_share NUMERIC, ocf_to_pat NUMERIC, median_roce NUMERIC,
            updated_at TIMESTAMPTZ DEFAULT now())
    """)
    cur.execute("ALTER TABLE stock_quality_flags ADD COLUMN IF NOT EXISTS industry TEXT")
    conn.commit()

    # sector map from the existing, fully-populated industry field
    cur.execute("SELECT nse_symbol, industry FROM stock_fundamentals")
    sector = {s: ind for s, ind in cur.fetchall()}

    clean = flagged = excluded = skipped = 0
    for f in glob.glob(os.path.join(FUND_DIR, "*.xlsx")):
        sym = os.path.basename(f).split("_")[0]
        ind = sector.get(sym)
        if is_financial(ind):
            flag, reasons, metrics = "EXCLUDED", f"financial sector ({ind}) — accruals/ROCE screen not applicable", (None,None,None)
            excluded += 1
        else:
            out = classify(f)
            if out is None:
                skipped += 1; continue
            flag, reasons, metrics = out
            if ind is None and flag == "FLAGGED":
                reasons += " [sector unverified — confirm not financial]"
            clean += flag == "CLEAN"; flagged += flag == "FLAGGED"
        neg, o2p, mr = metrics
        cur.execute("""
            INSERT INTO stock_quality_flags
              (nse_symbol, quality_flag, quality_reasons, industry, neg_ocf_share, ocf_to_pat, median_roce, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (nse_symbol) DO UPDATE SET
              quality_flag=EXCLUDED.quality_flag, quality_reasons=EXCLUDED.quality_reasons,
              industry=EXCLUDED.industry, neg_ocf_share=EXCLUDED.neg_ocf_share,
              ocf_to_pat=EXCLUDED.ocf_to_pat, median_roce=EXCLUDED.median_roce, updated_at=now()
        """, (sym, flag, reasons, ind, neg, o2p, mr))
    conn.commit()
    print(f"stock_quality_flags: CLEAN={clean}  FLAGGED={flagged}  EXCLUDED(financials)={excluded}  skipped={skipped}")
    print("\nFLAGGED sample (real operator/quality concerns, financials removed):")
    cur.execute("SELECT nse_symbol, quality_reasons FROM stock_quality_flags WHERE quality_flag='FLAGGED' ORDER BY nse_symbol LIMIT 12")
    for s, why in cur.fetchall(): print(f"  {s:14s} {why}")
    cur.execute("SELECT nse_symbol, industry, quality_flag FROM stock_quality_flags")
    with open("sector_map.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["nse_symbol", "industry", "quality_flag"])
        w.writerows(cur.fetchall())
    print("wrote sector_map.csv")
    conn.close()

if __name__ == "__main__":
    main()

