#!/usr/bin/env python3
"""
test_untested_theses.py — once SBI notes are parsed, test the 3 theses the data now unlocks,
using the VALIDATED outcome metric: buy-at-open -> best close within first 10 sessions (%).

  A. OFS-vs-fresh   : does a high insider-cash-out (OFS %) predict a WORSE post-listing trade?
  B. Book-manager   : do certain BRLMs cluster with better/worse outcomes?
  C. Peer valuation : does cheaper-than-peer (note P/S < peer P/S) predict a BETTER trade?

Outcome comes from price_candles; note fields from ipo_research_notes; join on nse_symbol.

  pip install psycopg2-binary numpy --break-system-packages
  python _scripts\\test_untested_theses.py               # prints report
  python _scripts\\test_untested_theses.py --md out.md    # also writes markdown
"""
import argparse, os, sys, statistics as st

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--md", default=""); a = ap.parse_args()
    import psycopg2
    u = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not u: sys.exit("Set DATABASE_URL")
    conn = psycopg2.connect(u); cur = conn.cursor()

    # outcome per IPO: buy day-0 open -> best close in first 10 sessions
    cur.execute("""
      WITH firsts AS (
        SELECT n.nse_symbol AS symbol, n.company, n.ofs_cr, n.fresh_cr, n.note_ps, n.peer_ps,
               n.brlms, i.listing_date
        FROM ipo_research_notes n
        JOIN ipo_intelligence i ON i.nse_symbol = n.nse_symbol
        WHERE n.nse_symbol IS NOT NULL AND i.listing_date IS NOT NULL
      )
      SELECT f.symbol, f.company, f.ofs_cr, f.fresh_cr, f.note_ps, f.peer_ps, f.brlms,
             (SELECT c.open FROM price_candles c WHERE c.symbol=f.symbol AND c.date>=f.listing_date
              ORDER BY c.date LIMIT 1) AS open0,
             (SELECT MAX(c.close) FROM (SELECT close FROM price_candles c WHERE c.symbol=f.symbol
              AND c.date>=f.listing_date ORDER BY c.date LIMIT 10) c) AS best10
      FROM firsts f
    """)
    rows = []
    for sym, comp, ofs, fresh, nps, pps, brlms, o0, b10 in cur.fetchall():
        if not o0 or not b10 or o0 == 0: continue
        ret = (float(b10) - float(o0)) / float(o0) * 100.0
        rows.append(dict(symbol=sym, company=comp, ofs=ofs, fresh=fresh, note_ps=nps,
                         peer_ps=pps, brlms=brlms or "", ret=ret))
    n = len(rows)
    out = [f"# Untested theses — N={n} IPOs with SBI note + price data\n",
           "Outcome = buy day-0 open → best close within 10 sessions (%).\n"]
    if n < 10:
        out.append(f"\n⚠️ Only {n} matched — parse more notes / backfill candles before trusting these.\n")

    def summ(g):
        r = [x["ret"] for x in g]
        return (len(r), round(st.median(r), 1), round(sum(1 for x in r if x > 0) / len(r) * 100)) if r else (0, None, None)

    # A. OFS %
    A = [x for x in rows if x["ofs"] and x["fresh"] and (x["ofs"] + x["fresh"]) > 0]
    out.append("\n## A. OFS-vs-fresh")
    if len(A) >= 8:
        for x in A: x["ofs_pct"] = x["ofs"] / (x["ofs"] + x["fresh"]) * 100
        med = st.median([x["ofs_pct"] for x in A])
        hi = [x for x in A if x["ofs_pct"] >= med]; lo = [x for x in A if x["ofs_pct"] < med]
        out.append(f"- split at OFS%={med:.0f}%")
        out.append(f"- HIGH OFS% (insiders cashing out): n={summ(hi)[0]} median={summ(hi)[1]}% win={summ(hi)[2]}%")
        out.append(f"- LOW  OFS% : n={summ(lo)[0]} median={summ(lo)[1]}% win={summ(lo)[2]}%")
    else:
        out.append(f"- not enough data (n={len(A)})")

    # B. BRLM (lead = first manager mentioned)
    out.append("\n## B. Book-manager (BRLM)")
    from collections import defaultdict
    buckets = defaultdict(list)
    for x in rows:
        lead = (x["brlms"].split(",")[0].split(" Ltd")[0].strip() if x["brlms"] else "")[:24]
        if lead: buckets[lead].append(x)
    shown = 0
    for lead, g in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        c, m, w = summ(g)
        if c >= 4: out.append(f"- {lead:24} n={c} median={m}% win={w}%"); shown += 1
    if not shown: out.append("- no BRLM with n≥4 yet")

    # C. Peer valuation
    C = [x for x in rows if x["note_ps"] and x["peer_ps"]]
    out.append("\n## C. Peer valuation (note P/S vs peer P/S)")
    if len(C) >= 8:
        cheap = [x for x in C if x["note_ps"] < x["peer_ps"]]
        exp = [x for x in C if x["note_ps"] >= x["peer_ps"]]
        out.append(f"- CHEAPER than peer: n={summ(cheap)[0]} median={summ(cheap)[1]}% win={summ(cheap)[2]}%")
        out.append(f"- PRICIER than peer: n={summ(exp)[0]} median={summ(exp)[1]}% win={summ(exp)[2]}%")
    else:
        out.append(f"- not enough data (n={len(C)})")

    report = "\n".join(out)
    print(report)
    if a.md:
        open(a.md, "w", encoding="utf-8").write(report)
        print(f"\n✓ wrote {a.md}")

if __name__ == "__main__":
    main()
