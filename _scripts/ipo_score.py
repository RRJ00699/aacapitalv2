#!/usr/bin/env python3
"""
ipo_score.py — Score v0: evidence-weighted buy-at-open setup score.

Every weight traces to a SIGNAL line (n>=30, era-consistent) from factor_backtest
runs of 2026-07-05 on n=370, baseline 72%/+5.9%, hold=10 sessions:

  +2  size >2000cr       (81.8%/+9.2,  n=77,  eras 72/88/85)
  -2  size 150-500cr     (58.9%/+1.5,  n=73;  LOW x 150-500 = 50.0%/+0.4, n=40)
  +1  peer-PE <0.6x      (76.7%/+7.6,  n=30)
  +1  PE > 60            (78.9%/+8.2,  n=38)
  -1  PE 30-60           (66.2%/+3.4,  n=136)
  -1  gap HIGH           (64.0%/+5.4,  n=89; 2025+ decayed to 50%)
Zero-weighted by evidence: OFS mix, GMP level, final QIB, ROE (all ~baseline);
anchors & regime & QIB-backloading & GMP-trajectory (insufficient data — listed
as PENDING factors so the card can say what the score does NOT yet know).

Modes:
  --backtest   READ-ONLY validation: scores all history, prints win%/median by
               score band + era consistency. Bands must be monotonic or v0 is
               rejected — this printout is the acceptance test.
  --apply      Writes ipo_score, score_band, score_expected_win, score_expected_med,
               score_evidence (text) into ipo_intelligence. DERIVED -> DO UPDATE
               (Rule 1). Adds columns IF NOT EXISTS. No raw fact touched.

  python _scripts/ipo_score.py --backtest
  venv/bin/python _scripts/ipo_score.py --apply     (VM, after backtest approves)
"""
import os, sys, argparse
DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
HOLD = 10

BANDS = [(-99, -2, "AVOID"), (-1, 0, "NEUTRAL"), (1, 2, "FAVORABLE"), (3, 99, "STRONG")]

def band_of(s):
    for lo, hi, name in BANDS:
        if lo <= s <= hi:
            return name
    return "NEUTRAL"

def score_row(r):
    s, why = 0, []
    gb = (r.get("gap_bucket") or "").upper()
    # MID GAP REMOVED 2026-07-18. IPO_BUSINESS_REQUIREMENTS.md §5 lists MID gap
    # as DEAD: the original +2 (84.1% win, n=69) was measured on POLLUTED data
    # and COLLAPSED to a coin-flip once the data was rebuilt. Scoring it inflated
    # the band on every MID-gap IPO — the single highest-value correctness fix in
    # ARCHITECTURE_TARGET.md §6. HIGH gap -1 stays (still evidenced, decayed but
    # not dead). Do not reinstate without a new leakage-free backtest.
    if gb == "HIGH":   s -= 1; why.append("HIGH gap -1")
    sz = r.get("issue_size_cr")
    if sz is not None:
        sz = float(sz)
        if sz >= 2000:          s += 2; why.append(">2000cr +2")
        elif 150 <= sz < 500:   s -= 2; why.append("150-500cr -2")
    pe, pm = r.get("ipo_pe"), r.get("peer_median_pe")
    if pe and pm and float(pm) > 0 and float(pe) / float(pm) < 0.6:
        s += 1; why.append("peer-cheap +1")
    if pe:
        pe = float(pe)
        if pe > 60:          s += 1; why.append("PE>60 +1")
        elif 30 <= pe <= 60: s -= 1; why.append("PE30-60 -1")
    pending = []
    if not r.get("anchor_count"):     pending.append("anchors")
    if r.get("peer_median_pe") is None: pending.append("peerPE")
    return s, why, pending

def era_of(d):
    # Era buckets widened for the 2006 IPOMatrix backfill: deep history gets its
    # own buckets so the backtest reveals if 2006-15 behaves differently rather
    # than hiding it all in one <=2021 lump (Rakesh 2026-07-18).
    if d is None: return "?"
    y = d.year
    return ("<=2010" if y <= 2010 else "2011-15" if y <= 2015 else
            "2016-20" if y <= 2020 else "2021" if y == 2021 else
            "2022-24" if y <= 2024 else "2025+")

def load(cur):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_consolidated'")
    cols = {r[0] for r in cur.fetchall()}
    sym = "symbol_final" if "symbol_final" in cols else "nse_symbol"
    open_col = next((c for c in ("listing_open", "listing_open_price") if c in cols), None)
    sel = [sym, "company_name", "listing_date", "gap_bucket", "issue_size_cr", "ipo_pe",
           "peer_median_pe", "anchor_count"] + ([open_col] if open_col else [])
    sel = [c for c in sel if c in cols]
    cur.execute(f"SELECT {', '.join(sel)} FROM ipo_consolidated WHERE listing_date IS NOT NULL")
    names = [d[0] for d in cur.description]
    rows = [dict(zip(names, r)) for r in cur.fetchall()]
    cur.execute(f"""SELECT UPPER(REGEXP_REPLACE(c.{sym},'\\.NS$','')) s, p.date, p.open, p.close
                    FROM ipo_consolidated c JOIN price_candles p
                      ON UPPER(p.symbol)=UPPER(REGEXP_REPLACE(c.{sym},'\\.NS$',''))
                     AND p.date>=c.listing_date AND p.date<=c.listing_date+30
                    WHERE c.listing_date IS NOT NULL ORDER BY s, p.date""")
    cnd = {}
    for s, d, o, cl in cur.fetchall():
        cnd.setdefault(s, []).append((o, cl))
    return rows, cnd, sym, open_col

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--backtest", action="store_true"); g.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not DB: sys.exit("DATABASE_URL not set")
    import psycopg2
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()

    if a.backtest:
        rows, cnd, sym, open_col = load(cur); conn.close()
        bands = {}
        for r in rows:
            cs = cnd.get((r.get(sym) or "").upper().replace(".NS", "")) or []
            if not cs: continue
            entry = float(r[open_col]) if open_col and r.get(open_col) else float(cs[0][0] or 0)
            closes = [float(c) for _, c in cs[:HOLD] if c]
            if entry <= 0 or len(closes) < 3: continue
            ret = (max(closes) - entry) / entry * 100
            s, _, _ = score_row(r)
            bands.setdefault(band_of(s), []).append((ret, max(closes) > entry, era_of(r["listing_date"]), s))
        n_all = sum(len(v) for v in bands.values())
        print(f"SCORE v0 BACKTEST — n={n_all}, hold={HOLD} sessions, baseline 72%/+5.9%")
        print(f"{'band':10} {'score-range':12} {'n':>4} {'win%':>6} {'med%':>7}  eras")
        prev = None; monotonic = True
        for lo, hi, name in BANDS:
            g = bands.get(name, [])
            if not g:
                print(f"{name:10} {f'{lo}..{hi}':12}    0"); continue
            gn = len(g); w = sum(1 for _, win, _, _ in g if win) / gn * 100
            m = sorted(x for x, _, _, _ in g)[gn // 2]
            eras = []
            for e in ("<=2010", "2011-15", "2016-20", "2021", "2022-24", "2025+"):
                ge = [x for x in g if x[2] == e]
                eras.append(f"{e}:{sum(1 for _, win, _, _ in ge if win)/len(ge)*100:.0f}%({len(ge)})" if len(ge) >= 8 else f"{e}:-")
            print(f"{name:10} {f'{lo}..{hi}':12} {gn:>4} {w:>6.1f} {m:>+7.1f}  {' '.join(eras)}")
            if prev is not None and w < prev - 2:      # allow 2pt noise
                monotonic = False
            prev = w
        print("\nACCEPTANCE:", "PASS — bands are monotonic; v0 approved for --apply"
              if monotonic else "FAIL — bands not monotonic; do NOT apply, weights need revisit")
        return

    # --apply
    for col, typ in [("ipo_score", "INT"), ("score_band", "TEXT"),
                     ("score_evidence", "TEXT"),
                     ("score_expected_win", "NUMERIC"),
                     ("score_expected_med", "NUMERIC")]:
        cur.execute(f"ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS {col} {typ}")
    rows, _, sym, _ = load(cur)
    upd = 0
    for r in rows:
        s, why, pending = score_row(r)
        ev = "; ".join(why) or "no scored factors"
        if pending:
            ev += f" | pending-data: {','.join(pending)}"
        # BAND_STATS: verbatim from the approved --backtest printout,
        # 2026-07-17 (n=390, hold=10, baseline 72%/+5.9%, bands monotonic,
        # ACCEPTANCE PASS). Change ONLY by rerunning --backtest and pasting.
        BAND_STATS = {"AVOID": (60.6, 1.9), "NEUTRAL": (73.7, 6.3),
                      "FAVORABLE": (80.2, 7.4), "STRONG": (81.4, 9.2)}
        band = band_of(s)
        ew, em = BAND_STATS.get(band, (None, None))
        cur.execute("""UPDATE ipo_intelligence
                       SET ipo_score=%s, score_band=%s, score_evidence=%s,
                           score_expected_win=%s, score_expected_med=%s
                       WHERE UPPER(COALESCE(NULLIF(nse_symbol,''), symbol)) = %s""",
                    (s, band, ev, ew, em, (r.get(sym) or "").upper().replace(".NS", "")))
        upd += cur.rowcount
        if cur.rowcount == 0 and r.get("company_name"):
            cur.execute("""UPDATE ipo_intelligence SET ipo_score=%s, score_band=%s, score_evidence=%s,
                               score_expected_win=%s, score_expected_med=%s
                           WHERE company_name = %s""", (s, band, ev, ew, em, r["company_name"]))
            upd += cur.rowcount
    conn.commit(); conn.close()
    print(f"APPLIED: ipo_score/score_band/score_evidence/score_expected_win/med written on {upd} rows (derived, DO UPDATE).")

if __name__ == "__main__":
    main()
