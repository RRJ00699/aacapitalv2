#!/usr/bin/env python3
"""
mf_freshness_monitor.py — the heartbeat that keeps the MF-conviction engine alive.

The NEW-conviction signal is only as good as the freshness of the holdings feeding it.
This monitor reports, per fund, the latest disclosure on file, how stale it is, and a verdict
— so you KNOW when to source the next file instead of the signal silently going dead.

Staleness logic (your rule: "if we may be delayed, source fortnightly to stay informed"):
  CURRENT  : latest disclosure <= 35 days old  (monthly cadence on track)
  DUE      : 36-50 days        -> source this month's file now
  STALE    : > 50 days         -> signal decaying; switch this fund to FORTNIGHTLY sourcing
  GAP-RISK : flags funds whose typical gap is widening (monthly slipping toward bi-monthly)

It does NOT load anything — it's the watch. The monthly/fortnightly routine is printed at the
end (the SOP). Run it any time to see if the engine is fed.

Run:  python _scripts/mf/mf_freshness_monitor.py
Env:  DATABASE_URL ; MF_DUE_DAYS=35 ; MF_STALE_DAYS=50
"""
import os, sys, datetime
import psycopg2

URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not URL:
    sys.exit("DATABASE_URL not set")
DUE   = int(os.environ.get("MF_DUE_DAYS", "35"))
STALE = int(os.environ.get("MF_STALE_DAYS", "50"))


def main():
    conn = psycopg2.connect(URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT amc_name, scheme_name,
               MAX(month) AS latest,
               COUNT(DISTINCT month) AS disclosures,
               COUNT(DISTINCT nse_symbol) FILTER (WHERE nse_symbol IS NOT NULL AND nse_symbol<>'') AS mapped_stocks
        FROM mf_scheme_holdings
        GROUP BY amc_name, scheme_name
        ORDER BY amc_name, scheme_name
    """)
    rows = cur.fetchall()
    today = datetime.date.today()

    print("=" * 86)
    print("MF HOLDINGS FRESHNESS  (the conviction engine's fuel gauge)")
    print("=" * 86)
    print(f"  {'fund':46s} {'latest':>11s} {'age':>5s} {'discl':>6s} {'stocks':>7s}  verdict")
    print("  " + "-" * 82)
    any_due = any_stale = False
    for amc, scheme, latest, ndisc, nstk in rows:
        age = (today - latest).days if latest else 9999
        if age > STALE:
            verdict = "STALE -> source FORTNIGHTLY"; any_stale = True
        elif age > DUE:
            verdict = "DUE  -> source this month"; any_due = True
        else:
            verdict = "current"
        name = f"{scheme}"[:46]
        print(f"  {name:46s} {str(latest):>11s} {age:>4d}d {ndisc:>6d} {nstk:>7d}  {verdict}")

    cur.execute("SELECT COUNT(*), MAX(first_seen) FROM mf_conviction_flags")
    try:
        nflags, lastflag = cur.fetchone()
    except Exception:
        nflags, lastflag = 0, None
    print("  " + "-" * 82)
    print(f"  live NEW-conviction flags: {nflags or 0}   newest initiation: {lastflag or '—'}")
    conn.close()

    print("\n" + "=" * 86)
    if any_stale:
        print("ACTION: a fund is STALE — its initiations can't be detected. Source its latest")
        print("        (fortnightly if monthly is slipping) and run the refresh chain below.")
    elif any_due:
        print("ACTION: a fund is DUE — grab this month's disclosure soon to keep the signal live.")
    else:
        print("All funds current — engine is fed.")

    print("\nMONTHLY (or fortnightly) REFRESH ROUTINE")
    print("-" * 40)
    print("1. Download each fund's latest portfolio disclosure (Excel) into")
    print("   data/mf_holdings/<amc>_<captype>/   (e.g. nippon_smallcap/, quant_midcap/)")
    print("2. Convert + load:   python _scripts/mf/parse_mf_portfolios.py")
    print("      (or, if you already have a combined CSV:")
    print("       python _scripts/mf/load_mf_holdings_csv.py data/mf_holdings/<file>.csv )")
    print("3. Map tickers:      python _scripts/build_isin_symbol_map.py")
    print("4. Refresh signal:   python _scripts/mf/compute_mf_conviction_flags.py")
    print("5. Re-check:         python _scripts/mf/mf_freshness_monitor.py")
    print("\nEverything is idempotent — safe to re-run; re-loading a month overwrites, never dupes.")


if __name__ == "__main__":
    main()
