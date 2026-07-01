#!/usr/bin/env python3
"""
parse_sbi_notes.py  (v2) — SBI IPO notes -> structured rows.
v2 fixes: read ALL pages (peer table is on p.~8), anchor OFS/fresh to '(Rs cr)' (no share-count
mis-parse), and add a table-scan fallback for peer P/S. Re-run --write-db to refresh (ON CONFLICT
DO UPDATE), which now fills peer_ps that v1 missed.

  pip install pdfplumber rapidfuzz psycopg2-binary --break-system-packages
  python _scripts\\parse_sbi_notes.py --dir data\\research_notes --debug
  python _scripts\\parse_sbi_notes.py --dir data\\research_notes --write-db
"""
import argparse, os, re, sys, glob

def num(s):
    if s is None: return None
    s = str(s).replace(",", "").strip()
    try: return float(s)
    except: return None

def parse_pdf(path):
    import pdfplumber
    text, tables = "", []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:                       # ALL pages — peer table is late
            text += (pg.extract_text() or "") + "\n"
            try: tables += (pg.extract_tables() or [])
            except Exception: pass
    T = re.sub(r"[ \t]+", " ", text)
    def g(pat, i=1, flags=re.I):
        m = re.search(pat, T, flags); return m.group(i).strip() if m else None

    company = re.sub(r"[_\-]*IPO ?Note.*$", "", os.path.basename(path), flags=re.I).replace("_", " ").strip()
    source = "Hem" if re.search(r"Hem Securities", T, re.I) else "SBI"

    rec = {
        "company": company, "source": source,
        "price_low":  num(g(r"Price Band[^0-9]*([\d.]+)\s*[–\-]")),
        "price_high": num(g(r"Price Band[^0-9]*[\d.]+\s*[–\-]\s*([\d.]+)")),
        # anchor to (Rs cr) so we never grab a share count
        "fresh_cr":   num(g(r"Fresh Issue\s*\(Rs ?[Cc]r\)\s*([\d,.]+)")) or num(g(r"Fresh Issue\s*Rs\s*([\d,.]+)\s*Cr")),
        "ofs_cr":     num(g(r"Offer for [Ss]ale\s*\(Rs ?[Cc]r\)\s*([\d,.]+)")) or num(g(r"OFS\s*\(Rs ?[Cc]r\)\s*([\d,.]+)")),
        "issue_size_cr": num(g(r"Issue Size\s*\(Rs ?[Cc]r\)\s*([\d,.]+)")) or num(g(r"Issue Size\s*Rs\s*([\d,.]+)")),
        "registrar":  g(r"Registrar[^A-Za-z]*([A-Za-z][A-Za-z .&]+?(?:Ltd|Limited|Technologies|Pvt)[A-Za-z .]*)"),
        "qib_pct":    num(g(r"QIB[^0-9]*(\d+)\s*%")),
        "nii_pct":    num(g(r"(?:NII|Non-Institutional)[^0-9]*(\d+)\s*%")),
        "retail_pct": num(g(r"Retail[^0-9]*(\d+)\s*%")),
        "note_ps":    num(g(r"P/?S of ([\d.]+)\s*x")) or num(g(r"annualized P/?S of ([\d.]+)")),
        "peer_name": None, "peer_ps": None,
        "loss_making": bool(re.search(r"yet to achieve profitability|incurred loss|loss[- ]making", T, re.I)),
        "pdf_path": path,
    }
    mr = re.search(r"\b(LONG TERM SUBSCRIBE|NEUTRAL|SUBSCRIBE|AVOID|NOT RATED)\b", T, re.I)
    rec["rating"] = mr.group(1).title() if mr else None
    mb = re.search(r"(?:BRLMs|Lead managers)\s*(.+?)\s*Registrar", T, re.I | re.S)
    rec["brlms"] = re.sub(r"\s+", " ", mb.group(1)).strip()[:300] if mb else None

    # peer P/S — 1) inline text  2) table scan for a row starting with P/S
    mp = re.search(r"P/?S(?:ales)?\s*\(x\)\s*([\d.]+)\s+([\d.]+)", T)
    if mp:
        rec["note_ps"] = rec["note_ps"] or num(mp.group(1)); rec["peer_ps"] = num(mp.group(2))
    if rec["peer_ps"] is None:
        for tbl in tables:
            for row in tbl or []:
                cells = [ (c or "").strip() for c in row ]
                if cells and re.search(r"^P/?S(?:ales)?\b", cells[0], re.I):
                    nums = [num(c) for c in cells[1:] if num(c) is not None]
                    if len(nums) >= 2:
                        rec["note_ps"] = rec["note_ps"] or nums[0]; rec["peer_ps"] = nums[-1]
    # peer name (best-effort)
    mpn = re.search(r"Peer Comparison.*?([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,3}\s+(?:Ltd|Limited))", T, re.S)
    if mpn and rec["peer_ps"] and company.split()[0].lower() not in mpn.group(1).lower():
        rec["peer_name"] = mpn.group(1).strip()
    return rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/research_notes")
    ap.add_argument("--write-db", action="store_true"); ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    try: import pdfplumber  # noqa
    except ImportError: sys.exit("pip install pdfplumber rapidfuzz psycopg2-binary --break-system-packages")
    files = sorted(glob.glob(os.path.join(a.dir, "*.pdf")))
    if not files: sys.exit(f"no PDFs in {a.dir}")
    if a.debug: files = files[:1]
    rows = []
    for f in files:
        try:
            r = parse_pdf(f); rows.append(r)
            if a.debug:
                import json; print(json.dumps(r, indent=2, default=str)); return
        except Exception as e: print("  ✗", os.path.basename(f), str(e)[:70])
    got_peer = sum(1 for r in rows if r.get("peer_ps"))
    print(f"parsed {len(rows)} notes; peer_ps found on {got_peer}")
    for r in rows[:8]:
        print(f"  {r['company'][:28]:28} PS={r.get('note_ps')} peerPS={r.get('peer_ps')} "
              f"OFS={r.get('ofs_cr')} fresh={r.get('fresh_cr')} {r.get('rating')}")
    if not a.write_db:
        print("\ndry-run — add --write-db to persist."); return

    import psycopg2; from rapidfuzz import process, fuzz
    u = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not u: sys.exit("Set DATABASE_URL")
    conn = psycopg2.connect(u); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS ipo_research_notes(
        company text, source text, rating text, price_low numeric, price_high numeric,
        fresh_cr numeric, ofs_cr numeric, issue_size_cr numeric, qib_pct numeric, nii_pct numeric,
        retail_pct numeric, brlms text, registrar text, note_ps numeric, peer_name text, peer_ps numeric,
        loss_making boolean, pdf_path text, parsed_at timestamptz default now(), nse_symbol text,
        PRIMARY KEY(company, source))""")
    cur.execute("SELECT company_name, nse_symbol FROM ipo_intelligence WHERE company_name IS NOT NULL")
    uni = cur.fetchall(); names = [c for c, _ in uni]; sym = {c: s for c, s in uni}
    for col, typ in [("sbi_rating","text"),("ofs_cr","numeric"),("fresh_cr","numeric"),("peer_ps","numeric"),("peer_name","text")]:
        cur.execute(f"ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS {col} {typ}")
    written = filled = 0
    for r in rows:
        m = process.extractOne(r["company"], names, scorer=fuzz.token_sort_ratio)
        nse = sym.get(m[0]) if m and m[1] >= 88 else None; r["nse_symbol"] = nse
        cur.execute("""INSERT INTO ipo_research_notes
          (company,source,rating,price_low,price_high,fresh_cr,ofs_cr,issue_size_cr,qib_pct,nii_pct,
           retail_pct,brlms,registrar,note_ps,peer_name,peer_ps,loss_making,pdf_path,nse_symbol)
          VALUES (%(company)s,%(source)s,%(rating)s,%(price_low)s,%(price_high)s,%(fresh_cr)s,%(ofs_cr)s,
           %(issue_size_cr)s,%(qib_pct)s,%(nii_pct)s,%(retail_pct)s,%(brlms)s,%(registrar)s,%(note_ps)s,
           %(peer_name)s,%(peer_ps)s,%(loss_making)s,%(pdf_path)s,%(nse_symbol)s)
          ON CONFLICT (company,source) DO UPDATE SET rating=EXCLUDED.rating, peer_ps=EXCLUDED.peer_ps,
           note_ps=EXCLUDED.note_ps, ofs_cr=EXCLUDED.ofs_cr, fresh_cr=EXCLUDED.fresh_cr,
           issue_size_cr=EXCLUDED.issue_size_cr, brlms=EXCLUDED.brlms, nse_symbol=EXCLUDED.nse_symbol,
           parsed_at=now()""", r)
        written += 1
        if nse:
            cur.execute("""UPDATE ipo_intelligence SET
                sbi_rating=COALESCE(sbi_rating,%s), ofs_cr=COALESCE(ofs_cr,%s), fresh_cr=COALESCE(fresh_cr,%s),
                peer_ps=COALESCE(peer_ps,%s), peer_name=COALESCE(peer_name,%s) WHERE nse_symbol=%s""",
                (r["rating"], r["ofs_cr"], r["fresh_cr"], r["peer_ps"], r["peer_name"], nse))
            filled += cur.rowcount
    conn.commit()
    print(f"✓ ipo_research_notes: {written} rows (peer_ps on {got_peer}) | ipo_intelligence fill-empty: {filled}")

if __name__ == "__main__":
    main()
