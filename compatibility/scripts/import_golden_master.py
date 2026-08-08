#!/usr/bin/env python3
"""
import_golden_master.py — one-time harvest of the pre-DB manual project
(Golden_IPO_Master_CLEANED_v3.xlsx, 999 IPOs 2010-2021) into ipo_intelligence.

Rule 1 strictly: fills EMPTY cells only, never overwrites. Matches on
normalized company name + IPO year (+/-1). Prints before/after coverage
diff and writes unmatched rows to golden_unmatched.txt.

  python import_golden_master.py --file Golden_IPO_Master_CLEANED_v3.xlsx          # dry run
  python import_golden_master.py --file Golden_IPO_Master_CLEANED_v3.xlsx --apply  # write
"""
import os, re, sys, argparse

def norm(name):
    s = (name or "").lower()
    s = re.sub(r"\b(ltd|limited|pvt|private|india|co|corp|corporation|company)\b\.?", " ", s)
    s = re.sub(r"[&]", " and ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def parse_band(s):
    m = re.search(r"(\d[\d,\.]*)\s*(?:to|-|–)\s*(?:rs\.?\s*)?(\d[\d,\.]*)", str(s or ""), re.I)
    if not m: return None, None
    lo = float(m.group(1).replace(",", "")); hi = float(m.group(2).replace(",", ""))
    return (lo, hi) if 0 < lo <= hi < 100000 else (None, None)

def parse_ofs(s, issue_size):
    t = str(s or "")
    fm = re.search(r"fresh[^\d]{0,10}([\d,\.]+)\s*cr", t, re.I)
    om = re.search(r"ofs[^\d]{0,10}([\d,\.]+)\s*cr", t, re.I)
    fresh = float(fm.group(1).replace(",", "")) if fm else None
    ofs = float(om.group(1).replace(",", "")) if om else None
    if re.search(r"ofs\s*\(100%\)", t, re.I) and issue_size:
        ofs, fresh = float(issue_size), 0.0
    if re.search(r"fresh\s*\(100%\)|100%\s*fresh", t, re.I) and issue_size:
        fresh, ofs = float(issue_size), 0.0
    return fresh, ofs

# excel column -> (db column, transform tag)
MAP = [
    ("qib_x",        "qib_subscription_x",   "num"),
    ("nii_x",        "nii_subscription_x",   "num"),
    ("retail_x",     "rii_subscription_x",   "num"),
    ("total_x",      "total_subscription_x", "num"),
    ("listing_open", "listing_open",         "num"),
    ("listing_close","listing_day_close",    "num"),
    ("Issue Price",  "issue_price",          "num"),
    ("Price Band",   "price_band_low",       "band_lo"),
    ("Price Band",   "price_band_high",      "band_hi"),
    ("ofs_or_fresh", "fresh_cr",             "ofs_f"),
    ("ofs_or_fresh", "ofs_cr",               "ofs_o"),
    ("brlm_names",   "brlm_names",           "str"),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import openpyxl, psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    dbcols = {r[0] for r in cur.fetchall()}
    targets = sorted({db for _, db, _ in MAP if db in dbcols})
    print("target columns present in DB:", targets)

    def coverage():
        q = ", ".join(f"COUNT({c})" for c in targets)
        cur.execute(f"SELECT COUNT(*), {q} FROM ipo_intelligence WHERE listing_date < '2022-01-01'")
        r = cur.fetchone()
        return dict(zip(["rows"] + targets, r))

    before = coverage()

    cur.execute("""SELECT id, company_name, EXTRACT(YEAR FROM COALESCE(listing_date, open_date))::int
                   FROM ipo_intelligence WHERE COALESCE(listing_date, open_date) < '2022-06-01'""")
    db_index = {}
    for pid, nm, yr in cur.fetchall():
        db_index.setdefault(norm(nm), []).append((pid, yr))

    wb = openpyxl.load_workbook(a.file, read_only=True)
    ws = wb["Master_Enriched"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = {h: i for i, h in enumerate(rows[0])}
    matched = updated_cells = 0
    unmatched = []
    for r in rows[1:]:
        name = r[hdr.get("company_name_clean")] or r[hdr.get("Company Name")]
        yr = r[hdr.get("IPO Year")]
        if not name or not yr: continue
        cands = db_index.get(norm(name), [])
        pick = next((pid for pid, dy in cands if dy and abs(dy - int(yr)) <= 1), None)
        if not pick:
            unmatched.append(f"{name} ({int(yr)})"); continue
        matched += 1
        band = parse_band(r[hdr.get("Price Band")]) if "Price Band" in hdr else (None, None)
        fo = parse_ofs(r[hdr.get("ofs_or_fresh")], r[hdr.get("Issue Size (Cr)")]) if "ofs_or_fresh" in hdr else (None, None)
        for xl, db, kind in MAP:
            if db not in dbcols or xl not in hdr: continue
            v = r[hdr[xl]]
            if kind == "num":
                try: v = float(v) if v not in (None, "", "NA") else None
                except (TypeError, ValueError): v = None
            elif kind == "str":
                v = str(v).strip() if v not in (None, "") else None
            elif kind == "band_lo": v = band[0]
            elif kind == "band_hi": v = band[1]
            elif kind == "ofs_f": v = fo[0]
            elif kind == "ofs_o": v = fo[1]
            if v is None: continue
            if a.apply:
                cur.execute(f"UPDATE ipo_intelligence SET {db}=%s WHERE id=%s AND {db} IS NULL", (v, pick))
                updated_cells += cur.rowcount
            else:
                cur.execute(f"SELECT 1 FROM ipo_intelligence WHERE id=%s AND {db} IS NULL", (pick,))
                if cur.fetchone(): updated_cells += 1
    if a.apply: conn.commit()
    after = coverage() if a.apply else None
    wb.close()

    with open("golden_unmatched.txt", "w") as f:
        f.write("\n".join(unmatched))
    print(f"\nexcel rows matched to DB: {matched} | unmatched: {len(unmatched)} (golden_unmatched.txt)")
    print(f"cells {'written' if a.apply else 'WOULD be written (dry run)'}: {updated_cells}")
    print(f"\npre-2022 coverage ({before['rows']} rows):")
    for c in targets:
        b = before[c]
        line = f"  {c:22} {b:>4}"
        if after: line += f" -> {after[c]:>4}  (+{after[c]-b})"
        print(line)
    if not a.apply:
        print("\nDRY RUN — rerun with --apply to write (fill-empty only, Rule 1).")

if __name__ == "__main__":
    main()
