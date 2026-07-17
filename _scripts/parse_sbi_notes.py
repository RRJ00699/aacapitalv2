#!/usr/bin/env python3
"""
parse_sbi_notes.py  (v3) — SBI IPO notes -> structured rows.
Robust cross-company peer-comparison parse: pulls subject + peer-MEDIAN P/E (and P/S
where present) + peer names from the "Peer Comparison" matrix, and fills
ipo_intelligence.peer_median_pe / peer_ps / peer_name fill-empty-only with value sanity.

  pip install pdfplumber psycopg2-binary --break-system-packages
  python _scripts/parse_sbi_notes.py --dir data/research_notes --debug
  python _scripts/parse_sbi_notes.py --dir data/research_notes --write-db
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
        "fresh_cr":   num(g(r"Fresh Issue\s*\(Rs ?[Cc]r\)\s*([\d,.]+)")) or num(g(r"Fresh Issue\s*Rs\s*([\d,.]+)\s*Cr")),
        "ofs_cr":     num(g(r"Offer for [Ss]ale\s*\(Rs ?[Cc]r\)\s*([\d,.]+)")) or num(g(r"OFS\s*\(Rs ?[Cc]r\)\s*([\d,.]+)")),
        "issue_size_cr": num(g(r"Issue Size\s*\(Rs ?[Cc]r\)\s*([\d,.]+)")) or num(g(r"Issue Size\s*Rs\s*([\d,.]+)")),
        "registrar":  g(r"Registrar[^A-Za-z]*([A-Za-z][A-Za-z .&]+?(?:Ltd|Limited|Technologies|Pvt)[A-Za-z .]*)"),
        "qib_pct":    num(g(r"QIB[^0-9]*(\d+)\s*%")),
        "nii_pct":    num(g(r"(?:NII|Non-Institutional)[^0-9]*(\d+)\s*%")),
        "retail_pct": num(g(r"Retail[^0-9]*(\d+)\s*%")),
        "note_ps":    num(g(r"P/?S of ([\d.]+)\s*x")) or num(g(r"annualized P/?S of ([\d.]+)")),
        "peer_name": None, "peer_ps": None, "note_pe": None, "peer_pe": None,
        "loss_making": bool(re.search(r"yet to achieve profitability|incurred loss|loss[- ]making", T, re.I)),
        "pdf_path": path,
    }
    mr = re.search(r"\b(LONG TERM SUBSCRIBE|NEUTRAL|SUBSCRIBE|AVOID|NOT RATED)\b", T, re.I)
    rec["rating"] = mr.group(1).title() if mr else None
    mb = re.search(r"(?:BRLMs|Lead managers)\s*(.+?)\s*Registrar", T, re.I | re.S)
    rec["brlms"] = re.sub(r"\s+", " ", mb.group(1)).strip()[:300] if mb else None

    # ---- peer comparison (cross-company matrix): [metric, SUBJECT, peer1, peer2, ...] ----
    # Identify the RIGHT table by the subject company appearing in its header row, so the
    # subject's own multi-YEAR ratio table can't be mistaken for peers. Peer median =
    # median of the PEER columns (positive values only), robust to one loss-making peer.
    def _peer_metric(rowvals):
        vals = [num(c) for c in rowvals]; vals = [v for v in vals if v is not None]
        if len(vals) < 2: return None, None
        subject = vals[0]
        peers = sorted(v for v in vals[1:] if v and v > 0)
        if not peers: return subject, None
        m = len(peers)//2
        med = peers[m] if len(peers) % 2 else (peers[m-1] + peers[m]) / 2
        return subject, round(med, 2)

    subj_key = (company.split()[0].lower() if company else "")
    for tbl in tables or []:
        if not tbl or len(tbl) < 2: continue
        header = [ (c or "").strip() for c in tbl[0] ]
        if subj_key and subj_key not in " ".join(header).lower():
            continue
        rowmap = {}
        for row in tbl:
            cells = [ (c or "").strip() for c in row ]
            if cells and cells[0]: rowmap[cells[0].lower()] = cells[1:]
        pe_key = next((k for k in rowmap if re.match(r"^p\s*/?\s*e\b", k)), None)
        if not pe_key: continue
        subj_pe, peer_pe = _peer_metric(rowmap[pe_key])
        if peer_pe is None: continue
        rec["note_pe"] = subj_pe; rec["peer_pe"] = peer_pe
        ps_key = next((k for k in rowmap if re.match(r"^p\s*/?\s*s\b", k) or "p/s" in k), None)
        if ps_key:
            subj_ps, peer_ps = _peer_metric(rowmap[ps_key])
            rec["note_ps"] = rec["note_ps"] or subj_ps; rec["peer_ps"] = peer_ps
        peers = [h for h in header[2:] if h and h not in ("-",)]
        if peers: rec["peer_name"] = ", ".join(peers[:3])
        break
    if rec["peer_ps"] is None:
        mp = re.search(r"P/?S(?:ales)?\s*\(x\)\s*([\d.]+)\s+([\d.]+)", T)
        if mp:
            rec["note_ps"] = rec["note_ps"] or num(mp.group(1)); rec["peer_ps"] = num(mp.group(2))
    return rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/research_notes")
    ap.add_argument("--write-db", action="store_true"); ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    try: import pdfplumber  # noqa
    except ImportError: sys.exit("pip install pdfplumber psycopg2-binary --break-system-packages")
    files = sorted(glob.glob(os.path.join(a.dir, "*.pdf")))
    if not files: sys.exit(f"no PDFs in {a.dir}")
    if a.debug: files = files[:1]
    rows = []
    for f in files:
        try:
            r = parse_pdf(f); rows.append(r)
            if a.debug:
                import json; print(json.dumps(r, indent=2, default=str)); return
        except Exception as e: print("  x", os.path.basename(f), str(e)[:70])
    got_peer = sum(1 for r in rows if r.get("peer_pe"))
    print(f"parsed {len(rows)} notes; peer_pe found on {got_peer}")
    for r in rows[:8]:
        print(f"  {r['company'][:28]:28} PE={r.get('note_pe')} peerPE={r.get('peer_pe')} "
              f"peerPS={r.get('peer_ps')} {r.get('peer_name')}")
    if not a.write_db:
        print("\ndry-run — add --write-db to persist."); return

    import psycopg2
    from schema_sync import _canon  # ledger #9 fix: THE canon from #210 —
    # imported, not copied, so this join can never drift from the dedup/unique
    # canon. Replaces the rapidfuzz>=88 fuzzy match (RULE 2 violation) which
    # also MISSED 'Ltd' vs 'Limited' (scored 85.7).
    u = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not u: sys.exit("Set DATABASE_URL")
    conn = psycopg2.connect(u); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS ipo_research_notes(
        company text, source text, rating text, price_low numeric, price_high numeric,
        fresh_cr numeric, ofs_cr numeric, issue_size_cr numeric, qib_pct numeric, nii_pct numeric,
        retail_pct numeric, brlms text, registrar text, note_ps numeric, peer_name text, peer_ps numeric,
        loss_making boolean, pdf_path text, parsed_at timestamptz default now(), nse_symbol text,
        PRIMARY KEY(company, source))""")
    for col, typ in [("sbi_rating","text"),("ofs_cr","numeric"),("fresh_cr","numeric"),("peer_ps","numeric"),("peer_name","text")]:
        cur.execute(f"ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS {col} {typ}")
    written = filled = 0
    for r in rows:
        cur.execute(f"""SELECT nse_symbol FROM ipo_intelligence
                        WHERE {_canon('company_name')} = {_canon('%s')}
                          AND company_name IS NOT NULL LIMIT 1""", (r["company"],))
        m = cur.fetchone()
        nse = m[0] if m else None; r["nse_symbol"] = nse
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
            # value-sanity BEFORE commit: a real peer P/E is >0 and not an absurd artifact
            pe_ok = r["peer_pe"] if (r["peer_pe"] and 0 < r["peer_pe"] <= 500) else None
            cur.execute("""UPDATE ipo_intelligence SET
                sbi_rating=COALESCE(sbi_rating,%s), ofs_cr=COALESCE(ofs_cr,%s), fresh_cr=COALESCE(fresh_cr,%s),
                peer_ps=COALESCE(peer_ps,%s), peer_name=COALESCE(peer_name,%s),
                peer_median_pe=COALESCE(peer_median_pe,%s) WHERE nse_symbol=%s""",
                (r["rating"], r["ofs_cr"], r["fresh_cr"], r["peer_ps"], r["peer_name"], pe_ok, nse))
            filled += cur.rowcount
    conn.commit()
    print(f"ipo_research_notes: {written} rows | ipo_intelligence peer/sbi fill-empty: {filled}")

if __name__ == "__main__":
    main()
