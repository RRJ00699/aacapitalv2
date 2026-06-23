#!/usr/bin/env python3
"""
backfill_brlm_names.py — fills ipo_intelligence.brlm_names from Chittorgarh "Issue Details"
exports (and the older "Mainboard IPOs in India" reports). These are the only sources with
real per-IPO lead managers; without them brlm_names is "nan" and link_brlm_scores.py can't link.

Handles the messy export format: auto-detects the header row (it differs per file), reads the
"Lead Manager(s)" column, and matches to ipo_intelligence by NSE Symbol first, then company name.

Place the files in data/Ipo_reports/ then:
    python _scripts/ipo/backfill_brlm_names.py
    python link_brlm_scores.py
"""
import os, re, glob, sys, psycopg2
import pandas as pd
from difflib import SequenceMatcher

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")

STOP = {"ltd", "limited", "pvt", "private", "the", "co", "company", "india"}
BAD  = {"", "nan", "not found", "none", "-"}

def norm(name):
    s = re.sub(r"\[.*?\]", " ", str(name).lower())
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(t for t in s.split() if t not in STOP)

def find_header(f):
    raw = pd.read_excel(f, header=None, nrows=15)
    for i, row in raw.iterrows():
        vals = [str(v).strip() for v in row.tolist()]
        if "Company" in vals and any("Lead Manager" in v for v in vals):
            return i
    return None

by_sym, by_comp = {}, {}
patterns = ["Issue_Details_*.xlsx", "Mainboard_IPOs_in_India_*.xlsx"]
files = [f for p in patterns for f in glob.glob(os.path.join("data/Ipo_reports", p))]
if not files:
    sys.exit("No Issue_Details_*.xlsx or Mainboard_IPOs_in_India_*.xlsx in data/Ipo_reports/")

for f in files:
    h = find_header(f)
    if h is None:
        print(f"  (skip {os.path.basename(f)}: no header found)"); continue
    d = pd.read_excel(f, skiprows=h)
    lm_col   = next((c for c in d.columns if "Lead Manager" in str(c)), None)
    comp_col = next((c for c in d.columns if str(c).strip() == "Company"), None)
    sym_col  = next((c for c in d.columns if "NSE Symbol" in str(c)), None)
    if not lm_col or not comp_col:
        continue
    for _, r in d.iterrows():
        lead = str(r[lm_col]).strip()
        if lead.lower() in BAD:
            continue
        if sym_col and pd.notna(r[sym_col]):
            sym = str(r[sym_col]).strip().upper()
            if sym and sym.lower() not in BAD:
                by_sym[sym] = lead
        cn = norm(r[comp_col])
        if cn:
            by_comp[cn] = lead
print(f"loaded {len(by_sym)} symbol and {len(by_comp)} company -> lead-manager mappings from {len(files)} file(s)")

conn = psycopg2.connect(URL); conn.autocommit = True; cur = conn.cursor()
cur.execute("SELECT id, company_name, symbol FROM ipo_intelligence")
rows = cur.fetchall()

by_symbol_hits = by_company_hits = fuzzy_hits = 0
samples = []
for ipo_id, company, symbol in rows:
    lead = None
    if symbol:
        lead = by_sym.get(str(symbol).strip().upper())
        if lead: by_symbol_hits += 1
    if not lead and company:
        cn = norm(company)
        lead = by_comp.get(cn)
        if lead:
            by_company_hits += 1
        else:
            best, br = None, 0.0
            for k, v in by_comp.items():
                r = SequenceMatcher(None, cn, k).ratio()
                if r > br:
                    br, best = r, v
            if br >= 0.88:
                lead, fuzzy_hits = best, fuzzy_hits + 1
    if lead:
        cur.execute("UPDATE ipo_intelligence SET brlm_names = %s WHERE id = %s", (lead, ipo_id))
        if len(samples) < 8:
            samples.append((company, lead))

total = by_symbol_hits + by_company_hits + fuzzy_hits
print(f"backfilled brlm_names on {total} IPOs  "
      f"(by NSE symbol: {by_symbol_hits}, by company: {by_company_hits}, fuzzy: {fuzzy_hits})")
for c, l in samples:
    print(f"  {str(c)[:38]:38s} -> {l}")
print("\nNext: python link_brlm_scores.py")
conn.close()
