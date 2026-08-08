#!/usr/bin/env python3
"""
cir_forward_test.py — leakage-free re-test of the close-in-range (CIR) finding.

Last session: MID gap + STRONG listing_cir showed 100% win / +14.6 med (n=14)
against d10_best_pct. Problem: d10_best_pct = max(closes d1..d10) vs listing
open — day 1's OWN close sits inside that max, and CIR is measured off the same
day-1 bar. A strong close mechanically inflates the outcome. Circular.

This test removes the overlap entirely:
  SIGNAL : day-1 CIR from day-1 OHLC only. (close-low)/(high-low), clamped 0..1.
  OUTCOME: strictly forward. Entry = day-1 CLOSE; exit = fixed-horizon closes
           at d2, d3, d5 (sessions 2/3/5 of the stock's life). No max/best.

Two framings of the SAME forward numbers (Rakesh picks the label):
  hold-extension     you already own it (MID rule); skip the D1-close sell and
                     exit at dK instead. Compare the FULL-TRADE table
                     (listing open -> dK close) against the sell-at-D1-close
                     baseline printed beside it.
  entry-confirmation flat at 15:25; CIR STRONG -> buy the close, exit at dK.
                     Read the INCREMENTAL table (d1 close -> dK close) alone.

Primary read: within MID gap (+4..15 open), STRONG (>=0.67) vs not-STRONG,
per horizon, with Welch t on the mean gap. n>=30 in both cells = SIGNAL bar;
smaller cells (incl. the tercile detail) are printed as INDICATIVE only.
Guard: MID split by day-1 open->close direction crossed with STRONG/not —
if STRONG only wins on green days, CIR is momentum in disguise.

Read-only: no writes, no ALTERs, safe anywhere.
  python _scripts/cir_forward_test.py             # run against DB
  python _scripts/cir_forward_test.py --selftest  # no DB: check the math
Env: DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, argparse

HORIZONS = ((1, "d2"), (2, "d3"), (4, "d5"))   # index into candle arrays (0 = listing day)
SIGNAL_N = 30

def cir(o, h, l, c):
    try:
        h, l, c = float(h), float(l), float(c)
    except (TypeError, ValueError):
        return None
    if h <= l: return None
    return max(0.0, min(1.0, (c - l) / (h - l)))

def pct(a, b):
    """return a vs b in %, None on bad input."""
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

def tercile(v):
    return "WEAK <0.33" if v < 0.33 else ("MID 0.33-0.66" if v < 0.67 else "STRONG >=0.67")

def line(tag, st, extra=""):
    if not st:
        print(f"  {tag:22} n<5 — not printable"); return
    sig = "" if st[0] >= SIGNAL_N else "  (indicative, n<30)"
    print(f"  {tag:22} n={st[0]:<4} win={st[1]:5.1f}% med={st[2]:+6.1f} mean={st[3]:+6.1f}{extra}{sig}")

def run(recs):
    """recs: list of dicts with keys cir, gap, d1ret, fwd{k}, full{k} (per horizon)."""
    mid = [r for r in recs if gapband(r["gap"]) == "MID"]
    print(f"usable IPOs: {len(recs)} pooled, {len(mid)} in MID gap (+4..15)\n")

    print("=" * 62)
    print("A) ENTRY-CONFIRMATION read — incremental, d1 close -> dK close")
    print("   (MID gap only; STRONG >=0.67 vs not-STRONG)")
    print("=" * 62)
    for k, name in HORIZONS:
        strong = [r["fwd"][k] for r in mid if r["cir"] >= 0.67 and r["fwd"].get(k) is not None]
        rest   = [r["fwd"][k] for r in mid if r["cir"] <  0.67 and r["fwd"].get(k) is not None]
        print(f"\n  -- exit {name} --")
        line("STRONG", stats(strong))
        line("not-STRONG", stats(rest))
        t = welch_t(strong, rest)
        both30 = len(strong) >= SIGNAL_N and len(rest) >= SIGNAL_N
        if t is not None:
            print(f"  Δmean t≈{t:+.2f}   {'SIGNAL bar met' if both30 else 'below n>=30 bar'}")

    print("\n" + "=" * 62)
    print("B) HOLD-EXTENSION read — full trade, listing open -> dK close")
    print("   baseline = same names sold at D1 close (the validated rule)")
    print("=" * 62)
    for k, name in HORIZONS:
        for tag, cond in (("STRONG", lambda r: r["cir"] >= 0.67),
                          ("not-STRONG", lambda r: r["cir"] < 0.67)):
            sub = [r for r in mid if cond(r) and r["full"].get(k) is not None]
            base = stats([r["d1ret"] for r in sub])
            held = stats([r["full"][k] for r in sub])
            print(f"\n  -- {tag}, exit {name} --")
            line("sell D1 close (base)", base)
            line(f"hold to {name}", held)

    print("\n" + "=" * 62)
    print("C) GUARD — is STRONG just 'the day was green'? (MID gap, exit d3)")
    print("=" * 62)
    for dtag, dcond in (("green d1 (c>o)", lambda r: r["d1ret"] > 0),
                        ("red d1   (c<=o)", lambda r: r["d1ret"] <= 0)):
        for ctag, ccond in (("STRONG", lambda r: r["cir"] >= 0.67),
                            ("not-STRONG", lambda r: r["cir"] < 0.67)):
            sub = [r["fwd"][2] for r in mid
                   if dcond(r) and ccond(r) and r["fwd"].get(2) is not None]
            line(f"{dtag} + {ctag}", stats(sub))
    print("  Read: STRONG must add something on BOTH rows, else it's momentum.")

    print("\n" + "=" * 62)
    print("D) DETAIL — terciles within MID (indicative) + pooled reference (d3)")
    print("=" * 62)
    for k in ("WEAK <0.33", "MID 0.33-0.66", "STRONG >=0.67"):
        line(f"MID gap, {k}", stats([r["fwd"][2] for r in mid
                                     if tercile(r["cir"]) == k and r["fwd"].get(2) is not None]))
    print()
    for k in ("WEAK <0.33", "MID 0.33-0.66", "STRONG >=0.67"):
        line(f"pooled, {k}", stats([r["fwd"][2] for r in recs
                                    if tercile(r["cir"]) == k and r["fwd"].get(2) is not None]))
    print("\nDecision: STRONG beats not-STRONG at d2/d3 with n>=30 and a real margin")
    print("-> cockpit confirmation card. Flat/inverted -> circular artifact, closed.")

def fetch():
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("""
        SELECT i.id, i.listing_gap_pct,
               ARRAY_AGG(p.open ORDER BY p.date), ARRAY_AGG(p.high ORDER BY p.date),
               ARRAY_AGG(p.low ORDER BY p.date),  ARRAY_AGG(p.close ORDER BY p.date)
        FROM ipo_intelligence i
        JOIN price_candles p
          ON UPPER(p.symbol)=UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol))
         AND p.date >= i.listing_date
        WHERE i.listing_date IS NOT NULL
        GROUP BY 1,2 HAVING COUNT(*) >= 2""")
    recs = []
    for _pid, gap, o, h, l, c in cur.fetchall():
        d1 = cir(o[0], h[0], l[0], c[0])
        d1ret = pct(c[0], o[0])
        if d1 is None or d1ret is None: continue
        fwd, full = {}, {}
        for k, _ in HORIZONS:
            if len(c) > k and c[k] is not None:
                fwd[k] = pct(c[k], c[0])
                full[k] = pct(c[k], o[0])
        if not fwd: continue
        recs.append({"cir": d1, "gap": float(gap) if gap is not None else None,
                     "d1ret": d1ret, "fwd": fwd, "full": full})
    conn.close()
    return recs

def selftest():
    assert cir(100, 110, 100, 110) == 1.0          # closed at high
    assert cir(100, 110, 100, 100) == 0.0          # closed at low
    assert cir(100, 110, 100, 105) == 0.5
    assert cir(100, 100, 100, 100) is None          # flat bar
    assert cir(100, 105, 100, 95) == 0.0            # Knack case: close below low -> clamp
    assert abs(pct(103.3, 100) - 3.3) < 1e-9
    assert pct(100, 0) is None
    n, win, med, mean = stats([1, -1, 2, 3, -2])
    assert n == 5 and win == 60.0 and med == 1
    t = welch_t([1, 2, 3, 4], [1, 2, 3, 4]); assert t == 0 or t is None
    assert gapband(3.9) == "LOW" and gapband(4) == "MID" and gapband(15) == "MID" and gapband(15.1) == "HIGH"
    assert tercile(0.67) == "STRONG >=0.67" and tercile(0.329) == "WEAK <0.33"
    # end-to-end on synthetic recs: STRONG names drift up, weak drift down
    recs = []
    for i in range(40):
        recs.append({"cir": 0.8, "gap": 8.0, "d1ret": 2.0,
                     "fwd": {1: 1.0, 2: 2.0, 4: 3.0}, "full": {1: 3.0, 2: 4.0, 4: 5.0}})
        recs.append({"cir": 0.2, "gap": 8.0, "d1ret": -1.0,
                     "fwd": {1: -1.0, 2: -2.0, 4: -3.0}, "full": {1: -2.0, 2: -3.0, 4: -4.0}})
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
