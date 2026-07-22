#!/usr/bin/env python3
"""pattern_mining.py — WHAT MAKES WINNERS STAY POSITIVE (owner ask 2026-07-22).

Cohorts: WINNERS = last close in the listing→lock30 window ABOVE issue price
(stayed positive), LOSERS = below. Every factor the golden object carries is
profiled: winners-vs-losers medians, and top-half vs bottom-half win rates
with a two-proportion z-test — the same honesty bar as rule_validation.
Categoricals (sector) get per-bucket win rates (n>=8).

Read-only. Decade-locked by default; --since 2000 for inception.
Run:  python _scripts/pattern_mining.py            (report only)
"""
import argparse
import json
import math
import os
import sys

ELIG = ("COALESCE(is_sme,false)=false AND (issue_size_cr IS NULL OR issue_size_cr>=200) "
        "AND company_name !~* '\\y(REIT|InvIT)\\y' AND candles_json IS NOT NULL "
        "AND issue_price > 0 AND listing_date >= DATE '{SINCE}-01-01'")

# factor -> (label, higher_is expectation note)
NUMERIC = [
    ("anchor_count", "Anchors (count)"),
    ("anchor_pct", "Anchor amount / issue"),
    ("final_qib", "QIB subscription x"),
    ("final_nii", "NII subscription x"),
    ("final_retail", "Retail subscription x"),
    ("final_total", "Total subscription x"),
    ("bnii_x", "bNII (>10L) x"),
    ("snii_x", "sNII (2-10L) x"),
    ("ipo_pe", "IPO P/E"),
    ("pe_vs_peers", "P/E vs peer median"),
    ("ronw", "RoNW %"),
    ("roe", "RoE %"),
    ("revenue_cagr_3y", "Revenue CAGR 3y"),
    ("profit_cagr_3y", "Profit CAGR 3y"),
    ("debt_equity", "Debt/Equity"),
    ("ebitda_margin", "EBITDA margin"),
    ("promoter_post_pct", "Promoter holding post"),
    ("ofs_pct", "OFS share of issue"),
    ("issue_size_cr", "Issue size (cr)"),
    ("listing_gap_pct", "Listing-open gap %"),
    ("price_to_book", "P/B"),
    ("quality_score", "Quality score"),
]


def z2p(z):
    return math.erfc(abs(z) / math.sqrt(2))


def prop_z(w1, n1, w2, n2):
    if min(n1, n2) < 8:
        return None
    p1, p2 = w1 / n1, w2 / n2
    p = (w1 + w2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return z2p((p1 - p2) / se) if se else None


def med(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=2016)
    a = ap.parse_args()
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=25)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET statement_timeout = '120s'")
    # INTROSPECT the view first (owner crash 2026-07-22: quality_score lives
    # on the insights table, not ipo_gold) — profile only what exists; name
    # what doesn't. View drift can never crash this again.
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name = 'ipo_gold'""")
    have = {r["column_name"] for r in cur.fetchall()}
    wanted = ["anchor_count", "anchor_amount_cr", "final_qib", "final_nii",
              "final_retail", "final_total", "bnii_x", "snii_x", "ipo_pe",
              "peer_median_pe", "ronw", "roe", "revenue_cagr_3y",
              "profit_cagr_3y", "debt_equity", "ebitda_margin",
              "promoter_post_pct", "ofs_pct", "issue_size_cr",
              "listing_gap_pct", "price_to_book", "quality_score", "industry"]
    missing = [c for c in wanted if c not in have]
    cols = ", ".join(c for c in wanted if c in have)
    if missing:
        print(f"not in ipo_gold (skipped): {', '.join(missing)}")
    cur.execute(f"""SELECT company_name, listing_date, issue_price, candles_json,
            {cols}
        FROM ipo_gold WHERE {ELIG.replace('{SINCE}', str(a.since))}""")
    rows = cur.fetchall()
    conn.close()

    data = []
    first_err = None
    skipped = 0
    for r in rows:
        try:
            candles = r["candles_json"]
            if isinstance(candles, str):
                candles = json.loads(candles)
            if not candles:
                continue
            last_close = float(candles[-1]["close"] if isinstance(candles[-1], dict)
                               else candles[-1][4])
            ip = float(r["issue_price"])
            r = dict(r)
            r["_ret"] = (last_close - ip) / ip * 100
            r["_win"] = r["_ret"] > 0
            aa, isz = r.get("anchor_amount_cr"), r.get("issue_size_cr")
            r["anchor_pct"] = float(aa) / float(isz) if aa and isz else None
            pe, ppe = r.get("ipo_pe"), r.get("peer_median_pe")
            r["pe_vs_peers"] = float(pe) / float(ppe) if pe and ppe and float(ppe) > 0 else None
            data.append(r)
        except Exception as e:
            skipped += 1
            if first_err is None:
                first_err = f"{type(e).__name__}: {e} · row={r.get('company_name')}"
            continue
    if skipped:
        print(f"! rows skipped during parse: {skipped} · first error: {first_err}")

    W = [d for d in data if d["_win"]]
    L = [d for d in data if not d["_win"]]
    print(f"PATTERN MINING · winners = last lock-window close > issue price · since {a.since}")
    wm, lm = med([d["_ret"] for d in W]), med([d["_ret"] for d in L])
    print(f"universe n={len(data)} · WINNERS {len(W)} ({len(W)/max(len(data),1)*100:.1f}%) · "
          f"LOSERS {len(L)} · winner median hold-return "
          f"{(f'{wm:+.1f}%' if wm is not None else '—')} · loser "
          f"{(f'{lm:+.1f}%' if lm is not None else '—')}")
    if not data:
        print("universe parsed to ZERO rows — the first error above is the cause; fix and rerun.")
        return 1
    print(f"{'factor':26} {'n':>4} {'win-med':>9} {'lose-med':>9} {'top½win%':>9} {'bot½win%':>9} {'p':>7}  read")
    for col, label in NUMERIC:
        vals = [(float(d[col]), d["_win"]) for d in data if d.get(col) is not None]
        if len(vals) < 30:
            print(f"{label:26} {len(vals):>4}  — coverage too thin (<30)")
            continue
        wmed = med([v for v, w in vals if w])
        lmed = med([v for v, w in vals if not w])
        vs = sorted(vals)
        half = len(vs) // 2
        bot, top = vs[:half], vs[half:]
        tw, tn = sum(1 for _, w in top if w), len(top)
        bw, bn = sum(1 for _, w in bot if w), len(bot)
        p = prop_z(tw, tn, bw, bn)
        sig = " <<" if p is not None and p < 0.05 and abs(tw/tn - bw/bn) >= 0.05 else ""
        print(f"{label:26} {len(vals):>4} {wmed:>9.2f} {lmed:>9.2f} {tw/tn*100:>8.1f}% {bw/bn*100:>8.1f}% "
              f"{(f'{p:.3f}' if p is not None else '   —'):>7}{sig}")
    # sector buckets
    print("\nSECTOR (n>=8):")
    by = {}
    for d in data:
        k = (d.get("industry") or "—").strip()[:34]
        by.setdefault(k, []).append(d["_win"])
    for k, ws in sorted(by.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]) if kv[1] else 0):
        if len(ws) >= 8:
            print(f"  {k:36} n={len(ws):>3}  win {sum(ws)/len(ws)*100:5.1f}%")
    print("\n'<<' = top-half vs bottom-half split significant at p<0.05 with a >=5pt gap.")
    print("Read-only run — nothing written. Patterns here are CANDIDATES for the")
    print("rule engine, not conclusions: promote a factor only via rule_validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
