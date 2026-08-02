#!/usr/bin/env python3
"""
kite_fetch.py — item 7: the authenticated Kite path.
  ipo.kite_token  ->  market_candles  ->  listing_outcomes
That is a hard dependency chain: no token means no candles, and listing_outcomes is
DERIVED from candles. Each link is skipped with a stated reason, never half-done.

AUTH IS NOT REBUILT. The repo already has a working TOTP flow:
  _scripts/refresh_kite_token.py  — TOTP login, writes platform_config.kite_access_token
                                    and bridges it into kite_session
  _scripts/kite_connect.py        — get_kite() reads that token
This module imports get_kite() and assumes the token is fresh. If it is stale, run the
refresh script first — that is the pre-market step, and it is fully scriptable.

WHY NOT REUSE kite-sync-candles.py: it writes price_candles / ipo_intelligence, which
are V1 tables. Same API calls, but everything here routes through the tested fill_v2
writers into the V2 tables.

  python kite_fetch.py --ids 285 --dry-run
  python kite_fetch.py --limit 5 --write
  python kite_fetch.py --ids 285 --write --days 60
"""
import os, sys, io, argparse, datetime as dt
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

FILE_BUILD = "kite_fetch 2026-08-01b — UPPERCASE pool labels + honest exit code"
_INSTRUMENTS = None


def get_kite():
    """Import the repo's shared helper wherever it lives."""
    for path in ("_scripts", os.path.join("aacapitalv2", "_scripts"), "."):
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
    from kite_connect import get_kite as _g
    return _g()


def instruments(kite):
    """NSE instrument dump, fetched once per run (it is a large call)."""
    global _INSTRUMENTS
    if _INSTRUMENTS is None:
        _INSTRUMENTS = kite.instruments("NSE")
    return _INSTRUMENTS


def resolve_token(kite, isin, symbol):
    """instrument_token for one IPO. ISIN FIRST — rule 5, never a blank/fuzzy symbol.

    Kite's NSE dump does not always carry an isin field, so symbol is the documented
    fallback — but ONLY an exact, case-normalised match on a non-empty symbol. A fuzzy
    or partial match here would attach the wrong price series to an IPO, which is worse
    than leaving the token null."""
    rows = instruments(kite)
    if isin:
        for r in rows:
            if (r.get("isin") or "").strip().upper() == isin.strip().upper():
                return r["instrument_token"], "isin"
    if symbol and symbol.strip():
        want = symbol.strip().upper()
        for r in rows:
            if (r.get("tradingsymbol") or "").strip().upper() == want \
               and r.get("segment") == "NSE":
                return r["instrument_token"], "symbol_exact"
    return None, "unresolved"


def fetch_candles(kite, token, start, end):
    """Daily OHLCV -> the bar shape upsert_candles expects: {d,o,h,l,c,v}."""
    raw = kite.historical_data(token, from_date=start, to_date=end, interval="day")
    bars = []
    for c in raw:
        d = c["date"]
        bars.append({"d": d.date() if hasattr(d, "date") else d,
                     "o": c.get("open"), "h": c.get("high"), "l": c.get("low"),
                     "c": c.get("close"), "v": c.get("volume")})
    return bars


def derive_outcome(conn, ipo_id):
    """listing_outcomes from stored candles + the issue price. DERIVED, never fetched.

    Runs off market_candles rather than the API response so it is reproducible from the
    DB alone and gives the same answer whether candles arrived today or last month.
    Returns (record, note). Any field that cannot be computed stays absent — the pool
    doctrine buckets are only assigned when a real gap exists."""
    cur = conn.cursor()
    cur.execute("""SELECT d, o, h, l, c FROM market_candles
                    WHERE ipo_id=%s ORDER BY d ASC""", (ipo_id,))
    rows = cur.fetchall()
    if not rows:
        return None, "no candles stored"
    cur.execute("""SELECT COALESCE(issue_price, band_hi) FROM ipo_issue WHERE ipo_id=%s""",
                (ipo_id,))
    r = cur.fetchone()
    issue_price = float(r[0]) if r and r[0] is not None else None

    d1 = rows[0]
    rec = {"listing_open": float(d1[1]) if d1[1] is not None else None,
           "d1_close": float(d1[4]) if d1[4] is not None else None}
    if issue_price and rec["listing_open"]:
        gap = (rec["listing_open"] - issue_price) / issue_price * 100
        rec["gap_pct"] = round(gap, 4)
        # Pool doctrine (business case §3): Negative <0, Flat 0-15, Warm 15-50, Heavy >=50.
        # LABELS ARE UPPERCASE — CHECK outcome_pool_valid allows only
        # HEAVY|WARM|FLAT|NEGATIVE, and the 462 existing rows use that casing. Title case
        # was rejected on every write in the 08-01 run.
        rec["pool"] = ("NEGATIVE" if gap < 0 else "FLAT" if gap < 15
                       else "WARM" if gap < 50 else "HEAVY")
    closes = [float(x[4]) for x in rows if x[4] is not None]
    if closes:
        rec["best_close"] = max(closes)
        rec["worst_close"] = min(closes)
    if len(rows) >= 20 and closes:
        rec["ceiling_20"] = max(closes[:20])
    if rec.get("listing_open") and closes:
        rec["hold_positive_vs_open"] = closes[-1] > rec["listing_open"]
        if issue_price:
            rec["winner_35"] = max(closes) >= issue_price * 1.35
    return rec, None


def process(conn, kite, ipo_id, isin, symbol, name, listing_date, days, write):
    """One IPO through the whole chain. Returns a step report."""
    from fill_v2 import upsert_candles, upsert_listing_outcome
    from fill_ipo import upsert_ipo
    out = {"ipo_id": ipo_id, "token": None, "bars": 0, "outcome": None, "notes": []}

    cur = conn.cursor()
    cur.execute("SELECT kite_token FROM ipo WHERE id=%s", (ipo_id,))
    token = (cur.fetchone() or [None])[0]

    if token is None:
        token, how = resolve_token(kite, isin, symbol)
        out["resolved_by"] = how
        if token is None:
            out["notes"].append("token unresolved (no ISIN match, no exact symbol) "
                                "-> candles and listing_outcomes both blocked")
            return out
        if write:
            # COALESCE-empty-only, so this can only fill a null token
            upsert_ipo(conn, dict(isin=isin, name_display=name,
                                  name_norm=None, kite_token=token), source="kite")
    out["token"] = token

    end = dt.date.today()
    start = (listing_date or (end - dt.timedelta(days=days))) - dt.timedelta(days=2)
    if (end - start).days > days and listing_date is None:
        start = end - dt.timedelta(days=days)
    try:
        bars = fetch_candles(kite, token, start, end)
    except Exception as e:
        out["notes"].append(f"candles failed: {type(e).__name__}: {str(e)[:90]}")
        return out
    out["bars"] = len(bars)
    if write and bars:
        upsert_candles(conn, ipo_id, bars)

    if not write:
        out["notes"].append("dry-run: outcome not derived (needs candles stored)")
        return out
    rec, note = derive_outcome(conn, ipo_id)
    if note:
        out["notes"].append(note)
    elif rec:
        upsert_listing_outcome(conn, ipo_id, rec, dataset_version="v2")
        out["outcome"] = {k: rec[k] for k in ("gap_pct", "pool", "listing_open", "d1_close")
                          if k in rec}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids"); ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not (a.write or a.dry_run):
        sys.exit("choose --write or --dry-run")
    write = a.write and not a.dry_run

    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    if a.ids:
        ids = [int(x) for x in a.ids.split(",") if x.strip()]
        cur.execute("""SELECT id, isin, symbol, name_display, listing_date FROM ipo
                        WHERE id = ANY(%s) ORDER BY id""", (ids,))
    else:
        cur.execute("""SELECT id, isin, symbol, name_display, listing_date FROM ipo
                        WHERE in_backtest_universe=TRUE
                        ORDER BY listing_date DESC NULLS LAST LIMIT %s""", (a.limit,))
    targets = cur.fetchall()

    print(f"  [build] {FILE_BUILD}")
    print(f"  {len(targets)} IPOs · mode={'WRITE' if write else 'DRY-RUN'}")
    try:
        kite = get_kite()
        n_inst = len(instruments(kite))
        print(f"  kite authenticated · {n_inst} NSE instruments loaded\n")
    except Exception as e:
        sys.exit(f"  ✗ Kite auth failed: {type(e).__name__}: {str(e)[:160]}\n"
                 "    Run _scripts/refresh_kite_token.py first (TOTP, no browser).")

    ok = failed = 0
    for ipo_id, isin, symbol, name, listing_date in targets:
        print(f"  == id={ipo_id} {str(symbol or '(no symbol)'):14} {str(name)[:34]}")
        try:
            r = process(conn, kite, ipo_id, isin, symbol, name, listing_date, a.days, write)
            print(f"       token={r['token']} ({r.get('resolved_by','already stored')})  "
                  f"bars={r['bars']}")
            if r["outcome"]:
                print(f"       outcome {r['outcome']}")
            for n in r["notes"]:
                print(f"       [note] {n}")
            ok += 1 if r["token"] else 0
        except Exception as e:
            try: conn.rollback()
            except Exception: pass
            failed += 1
            print(f"  ! id={ipo_id}: {type(e).__name__}: {str(e)[:120]}")
    conn.close()
    print(f"\n  done. {ok}/{len(targets)} with a token · {failed} failed."
          + ("" if write else "  Nothing was written."))
    # A step where EVERY IPO threw is a failed step. Exiting 0 let the 08-01 cron print
    # "6. Kite candles + listing outcomes  ok" over four CheckViolations — a green light
    # on a run in which nothing was written is worse than no light at all.
    if targets and failed == len(targets):
        sys.exit(1)


if __name__ == "__main__":
    main()
