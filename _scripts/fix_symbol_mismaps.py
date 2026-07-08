#!/usr/bin/env python3
"""
fix_symbol_mismaps.py — audit + repair the 8 IPOs whose price_candles history
starts 900–2300 days BEFORE their listing_date (caught by the reconciler's
400d guard, 2026-07-08). Pre-listing candles mean the mapped ticker's history
belongs to a DIFFERENT company, so listing-day fields, d10/cir, daily levels,
and any backtest row touching these IPOs were computed off the wrong stock.

Two causes, decided per-IPO at runtime against the curated EXPECTED map:
  REMAP  current nse_symbol != correct one (e.g. Glenmark Life mapped to
         GLENMARK, the pharma). Fix the mapping; DO NOT touch the old
         symbol's candles — they are legit data for that other company.
  PURGE  symbol is already correct but the ticker was REUSED from a dead
         company (e.g. RAINBOW = Rainbow Papers before Rainbow Children's).
         Delete that symbol's candles dated before listing_date only.

In both cases the IPO's candle-derived fields are NULLed (they were wrong)
and its ipo_daily_levels rows deleted, so the nightly recomputes them from
clean candles. GOLDEN-RULE note: we null KNOWN-WRONG values only, and only
on rows that exhibit the anomaly (first candle > ANOMALY_DAYS before
listing) — already-fixed rows are untouched, so --apply is idempotent.

AFTER --apply (in order):
  1. python _scripts/ipo_candle_backfill.py     # fetch correct symbols' windows (Kite)
  2. full pipeline (or Admin -> Sync + nightly)  # refill listing fields, d10, cir,
                                                 # levels, consolidated
  3. rerun reconcile_listing_dates.py dry-run    # the 8 should now pass the guard

  python _scripts/fix_symbol_mismaps.py             # dry-run audit (read-only)
  python _scripts/fix_symbol_mismaps.py --apply     # write the fixes
  python _scripts/fix_symbol_mismaps.py --selftest  # no DB: verify the logic
Env: DATABASE_URL (or NEON_DATABASE_URL)
"""
import os, sys, argparse

ANOMALY_DAYS = 60   # first candle earlier than listing_date - this => wrong history

# company_name pattern (ILIKE) -> correct NSE symbol. Curated 2026-07-08 from the
# reconciler SKIP list; all are 2020-22 mainboard listings, symbols verified.
EXPECTED = [
    ("%glenmark life%",     "GLS"),
    ("%indigo paints%",     "INDIGOPNTS"),
    ("%latent%",            "LATENTVIEW"),
    ("%electronics mart%",  "EMIL"),
    ("%global health%",     "MEDANTA"),
    ("%paras defence%",     "PARAS"),
    ("%home first%",        "HOMEFIRST"),
    ("%rainbow child%",     "RAINBOW"),
]

# candle-derived master fields that must be recomputed from correct candles.
# Nulled only where the column exists (schema is 208 cols post-prune).
DERIVED = ["listing_open", "listing_gap_pct", "listing_price", "listing_high",
           "listing_low", "listing_close_price", "listing_day_high", "listing_day_low",
           "listing_day_close", "listing_volume_val", "listing_vs_gmp_pct",
           "return_listing_open", "return_day7", "return_day30", "return_day90",
           "d10_best_pct", "listing_cir", "cir_3d_avg",
           "days_to_break_issue", "days_to_new_high", "archetype"]
# delivery pct is symbol-keyed: wrong for REMAP cases (fetched under the wrong
# ticker), fine for PURGE cases (ticker traded as the new company on listing day).
DERIVED_REMAP_ONLY = ["listing_delivery_pct"]

def gapband(g):
    if g is None: return "?"
    g = float(g)
    return "LOW" if g < 4 else ("MID" if g <= 15 else "HIGH")

def decide(current_symbol, correct_symbol):
    cur = (current_symbol or "").strip().upper()
    return "REMAP" if cur != correct_symbol.upper() else "PURGE"

def run(conn, apply=False):
    cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    cols = {r[0] for r in cur.fetchall()}
    null_base = [c for c in DERIVED if c in cols]
    null_remap = null_base + [c for c in DERIVED_REMAP_ONLY if c in cols]

    print(f"{'APPLY' if apply else 'DRY-RUN'} — symbol-mismap audit "
          f"(anomaly = first candle > {ANOMALY_DAYS}d before listing)\n")
    fixed = skipped = 0
    for pattern, correct in EXPECTED:
        cur.execute("""
            SELECT i.id, i.company_name, COALESCE(NULLIF(i.nse_symbol,''), i.symbol),
                   i.listing_date, i.listing_gap_pct,
                   MIN(p.date), MAX(p.date), COUNT(p.date),
                   COUNT(p.date) FILTER (WHERE p.date < i.listing_date)
            FROM ipo_intelligence i
            LEFT JOIN price_candles p ON UPPER(p.symbol) = UPPER(COALESCE(NULLIF(i.nse_symbol,''), i.symbol))
            WHERE i.company_name ILIKE %s AND i.listing_date IS NOT NULL
            GROUP BY 1,2,3,4,5""", (pattern,))
        rows = cur.fetchall()
        if not rows:
            print(f"  ?? pattern {pattern!r}: 0 master rows — SKIPPED")
            skipped += 1
            continue
        if len(rows) > 1:
            # duplicate master rows (dedupe stragglers) — fix each; the anomaly
            # gate keeps this safe and idempotent per row. Dedupe separately.
            print(f"  !! pattern {pattern!r}: {len(rows)} master rows (dupes?) — fixing each")
        for row in rows:
            pid, name, sym, ldate, gap, dmin, dmax, ncand, npre = row
            action = decide(sym, correct)
            lead = (ldate - dmin).days if dmin else None
            anomalous = lead is not None and lead > ANOMALY_DAYS
            print(f"  {name[:34]:34} {str(sym):11} listed {ldate}  candles "
                  f"{ncand} ({npre} pre-listing, first {dmin}, lead {lead}d)  "
                  f"gap={gap} [{gapband(gap)}]")
            if not anomalous:
                print(f"     -> clean (no anomaly) — nothing to do")
                continue
            if action == "REMAP":
                print(f"     -> REMAP {sym} -> {correct}; null {len(null_remap)} derived; drop levels rows")
            else:
                print(f"     -> PURGE {npre} pre-listing candles of {correct}; null {len(null_base)} derived; drop levels rows")
            if not apply:
                fixed += 1
                continue

            if action == "REMAP":
                cur.execute("UPDATE ipo_intelligence SET nse_symbol=%s, symbol=%s WHERE id=%s",
                            (correct, correct, pid))
                nulls = null_remap
                # levels rows sit under the WRONG (other company's) symbol
                cur.execute("DELETE FROM ipo_daily_levels WHERE UPPER(symbol)=UPPER(%s)", (sym,))
            else:
                cur.execute("""DELETE FROM price_candles
                               WHERE UPPER(symbol)=UPPER(%s) AND date < %s""", (correct, ldate))
                print(f"     purged {cur.rowcount} pre-listing candles")
                nulls = null_base
                cur.execute("DELETE FROM ipo_daily_levels WHERE UPPER(symbol)=UPPER(%s)", (correct,))
            if nulls:
                cur.execute(f"UPDATE ipo_intelligence SET {', '.join(c + '=NULL' for c in nulls)} "
                            f"WHERE id=%s", (pid,))
            fixed += 1

    if apply:
        conn.commit()
        print(f"\nAPPLIED: {fixed} IPOs fixed, {skipped} skipped.")
        print("NOW RUN: ipo_candle_backfill.py (Kite) -> full pipeline -> reconcile dry-run.")
    else:
        print(f"\nDRY-RUN: {fixed} IPOs would be fixed, {skipped} skipped. Re-run with --apply.")
    print("Backtest note: any of the 8 that sat in the MID bucket polluted prior MID stats")
    print("with wrong-company returns — re-run real_return_analysis after candles refill.")

def selftest():
    assert decide("GLENMARK", "GLS") == "REMAP"
    assert decide("gls", "GLS") == "PURGE"          # case-insensitive match
    assert decide(None, "RAINBOW") == "REMAP"
    assert decide("  RAINBOW ", "RAINBOW") == "PURGE"
    assert gapband(12) == "MID" and gapband(None) == "?"
    assert len(EXPECTED) == 8 and len({s for _, s in EXPECTED}) == 8
    print("SELFTEST OK")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20)
    run(conn, apply=a.apply)
    conn.close()

if __name__ == "__main__":
    main()
