#!/usr/bin/env python3
"""
regime_mid_backtest.py — do red-Nifty listing days worsen the MID-gap trade?

The trade under test is the validated one: MID gap (+4..15% open vs issue),
buy listing open, sell D1 close. Outcome = D1 open->close return. No forward
horizon, so no leakage surface on the outcome side.

The look-ahead trap lives on the SIGNAL side: the listing day's Nifty close is
NOT knowable when you enter at the open. So two clearly-separated reads:

  A) ACTIONABLE FILTER — prior trading day's state (knowable pre-open):
       A1  prev-day Nifty red vs green (its own daily close-over-close return)
       A2  prev-day above_ema200 true/false
       A3  prev-day India VIX band  <14 / 14-20 / >20
     If red-prev-day MID trades are materially worse, that's a real skip-rule.

  B) DIAGNOSTIC — same-day Nifty red vs green (close vs prev close):
     Not an entry filter (look-ahead). Measures how much of the MID trade is
     market beta vs IPO-specific. If same-day red barely dents the win rate,
     the edge is idiosyncratic.

Pre-declared bar: MID n=~49 splits into ~25-per-cell — likely under the n>=30
SIGNAL bar. Standard for a cockpit skip-rule: MID and POOLED must agree in
direction, with the pooled split clearing n>=30 and a real margin (Welch t).
MID alone will not be called SIGNAL.

Regime source: market_regimes (nifty_close, above_ema200, india_vix), one row
per trading day, backfilled to ~2018. Prev-day = last regime row strictly
before listing_date (staleness cap 7 calendar days).

Read-only. No writes, no ALTERs.
  python _scripts/regime_mid_backtest.py             # run against DB
  python _scripts/regime_mid_backtest.py --selftest  # no DB: verify the math
Env: DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, argparse, datetime

SIGNAL_N = 30
STALE_DAYS = 7

def pct(a, b):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return None
    if b <= 0: return None
    return (a / b - 1.0) * 100.0

def stats(rets):
    n = len(rets)
    if n < 5: return None
    s = sorted(rets)
    med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return n, sum(1 for r in rets if r > 0) / n * 100, med, sum(rets) / n

def welch_t(a, b):
    na, nb = len(a), len(b)
    if na < 2 or nb < 2: return None
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = (va / na + vb / nb) ** 0.5
    return (ma - mb) / se if se > 0 else None

def gapband(g):
    if g is None: return "?"
    return "LOW" if g < 4 else ("MID" if g <= 15 else "HIGH")

def vixband(v):
    if v is None: return None
    return "VIX <14" if v < 14 else ("VIX 14-20" if v <= 20 else "VIX >20")

def line(tag, st):
    if not st:
        print(f"  {tag:26} n<5 — not printable"); return
    sig = "" if st[0] >= SIGNAL_N else "  (n<30)"
    print(f"  {tag:26} n={st[0]:<4} win={st[1]:5.1f}% med={st[2]:+6.1f} mean={st[3]:+6.1f}{sig}")

def pair(title, universe, key, aval, bval, alab, blab):
    """print a two-cell split + Welch t; returns (a_vals, b_vals)."""
    a = [r["ret"] for r in universe if r.get(key) == aval]
    b = [r["ret"] for r in universe if r.get(key) == bval]
    print(f"\n  -- {title} --")
    line(alab, stats(a)); line(blab, stats(b))
    t = welch_t(a, b)
    if t is not None:
        bar = "n>=30 both cells" if len(a) >= SIGNAL_N and len(b) >= SIGNAL_N else "below n>=30 bar"
        print(f"  Δmean t≈{t:+.2f}   ({bar})")
    return a, b

def run(recs):
    """recs: dicts with ret (D1 open->close %), gap, prev_red, prev_above_ema,
    prev_vix_band, same_red (each may be None if regime row missing)."""
    mid = [r for r in recs if gapband(r["gap"]) == "MID"]
    cov = sum(1 for r in recs if r.get("prev_red") is not None)
    print(f"usable IPOs: {len(recs)} pooled, {len(mid)} MID gap; "
          f"regime coverage {cov}/{len(recs)}\n")

    for label, uni in (("MID gap (the trade)", mid), ("POOLED (direction check)", recs)):
        print("=" * 64)
        print(f"A) ACTIONABLE — prior-day state, {label}")
        print("=" * 64)
        pair("A1 prev-day Nifty", uni, "prev_red", True, False,
             "prev-day RED", "prev-day GREEN")
        pair("A2 prev-day trend", uni, "prev_above_ema", False, True,
             "below 200EMA", "above 200EMA")
        print(f"\n  -- A3 prev-day VIX --")
        for band in ("VIX <14", "VIX 14-20", "VIX >20"):
            line(band, stats([r["ret"] for r in uni if r.get("prev_vix_band") == band]))
        print("=" * 64)
        print(f"B) DIAGNOSTIC (look-ahead — NOT a filter), {label}")
        print("=" * 64)
        pair("B1 same-day Nifty", uni, "same_red", True, False,
             "same-day RED", "same-day GREEN")
        print()

    print("Decision: prev-day-red materially worse in MID AND same direction")
    print("pooled (pooled cells n>=30, real t) -> 'skip red-open days' soft filter")
    print("on the cockpit card. No difference -> regime doesn't matter for the")
    print("D1-close exit; thread closed.")

def fetch():
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()

    # regimes with each day's own daily return (close over prev close)
    cur.execute("""SELECT evaluation_date, nifty_close, above_ema200, india_vix
                   FROM market_regimes WHERE nifty_close IS NOT NULL
                   ORDER BY evaluation_date""")
    days = []   # (date, red_today, above_ema, vix)
    prev_close = None
    for d, nc, ab, vix in cur.fetchall():
        nc = float(nc)
        red = (nc < prev_close) if prev_close is not None else None
        days.append((d, red, ab, float(vix) if vix is not None else None))
        prev_close = nc
    idx = {d: i for i, (d, *_ ) in enumerate(days)}

    def prev_row(ldate):
        """last regime row strictly before ldate, within staleness cap."""
        lo, hi = 0, len(days) - 1
        best = None
        while lo <= hi:
            m = (lo + hi) // 2
            if days[m][0] < ldate: best = m; lo = m + 1
            else: hi = m - 1
        if best is None: return None
        if (ldate - days[best][0]).days > STALE_DAYS: return None
        return days[best]

    cur.execute("""
        SELECT i.id, i.listing_gap_pct, i.listing_date,
               ARRAY_AGG(p.open ORDER BY p.date), ARRAY_AGG(p.close ORDER BY p.date)
        FROM ipo_intelligence i
        JOIN price_candles p
          ON UPPER(p.symbol)=UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol))
         AND p.date >= i.listing_date
        WHERE i.listing_date IS NOT NULL
        GROUP BY 1,2,3 HAVING COUNT(*) >= 1""")
    recs = []
    for _pid, gap, ldate, o, c in cur.fetchall():
        ret = pct(c[0], o[0])
        if ret is None: continue
        r = {"ret": ret, "gap": float(gap) if gap is not None else None,
             "prev_red": None, "prev_above_ema": None, "prev_vix_band": None,
             "same_red": None}
        p = prev_row(ldate)
        if p:
            r["prev_red"], r["prev_above_ema"] = p[1], p[2]
            r["prev_vix_band"] = vixband(p[3])
        i = idx.get(ldate)
        if i is not None:
            r["same_red"] = days[i][1]
        recs.append(r)
    conn.close()
    return recs

def selftest():
    assert abs(pct(103.3, 100) - 3.3) < 1e-9 and pct(100, 0) is None
    assert gapband(3.9) == "LOW" and gapband(4) == "MID" and gapband(15) == "MID" and gapband(15.1) == "HIGH"
    assert vixband(13.9) == "VIX <14" and vixband(14) == "VIX 14-20" and vixband(20) == "VIX 14-20" and vixband(20.1) == "VIX >20"
    assert vixband(None) is None
    n, win, med, mean = stats([1, -1, 2, 3, -2])
    assert n == 5 and win == 60.0 and med == 1
    # synthetic: red prev-days hurt, green help; same-day diagnostic mirrors it
    recs = []
    for i in range(40):
        recs.append({"ret": -2.0, "gap": 8.0, "prev_red": True, "prev_above_ema": False,
                     "prev_vix_band": "VIX >20", "same_red": True})
        recs.append({"ret": +4.0, "gap": 8.0, "prev_red": False, "prev_above_ema": True,
                     "prev_vix_band": "VIX <14", "same_red": False})
        recs.append({"ret": +1.0, "gap": 20.0, "prev_red": False, "prev_above_ema": True,
                     "prev_vix_band": "VIX 14-20", "same_red": False})
    run(recs)
    print("\nSELFTEST OK")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="no DB; verify the math")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    run(fetch())

if __name__ == "__main__":
    main()
