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
import os, sys, io, argparse, datetime as dt, traceback
from pathlib import Path
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

FILE_BUILD = "kite_fetch 2026-08-03e — NSE/BSE resolve + exchange provenance, market_candles_15m, ceiling_20 fix, score-scope 699"
_INSTRUMENTS = None
REPO_ROOT = Path(__file__).resolve().parent.parent
KITE_CONNECT_SCRIPT = "_scripts/kite_connect.py"
SHARED_SCRIPTS_DIR = (REPO_ROOT / KITE_CONNECT_SCRIPT).parent

# NOTE: a 15-min fetch-start clamp (today - LOOKBACK) is DEFERRED. The horizon must be
# MEASURED with a backward-walking probe (request today-300/-400/-600/-1000 for a token
# that listed well before the wall, find where Kite returns empty) — min(ts) across
# market_candles_15m is self-confirming (old IPOs returned 0 because from_date was out of
# range under the OLD code, not because Kite refuses recent data). Set LOOKBACK from the
# probe, then re-add the clamp.


def load_shared_get_kite():
    """Import the repository's shared helper independently of the caller's cwd."""
    scripts_path = str(SHARED_SCRIPTS_DIR)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    from kite_connect import get_kite as _g
    return _g


def get_kite():
    """Authenticate through the existing shared token source."""
    return load_shared_get_kite()()


def db():
    """Return a new, deliberately short-lived database connection."""
    return psycopg2.connect(os.environ["DATABASE_URL"])


def with_db(fn, *args, **kwargs):
    conn = db()
    try:
        return fn(conn, *args, **kwargs)
    finally:
        conn.close()


def instruments(kite):
    """Full instrument dump (ALL exchanges), fetched once per run.

    kite.instruments() with NO exchange argument returns every exchange (NSE, BSE, …)
    in a SINGLE HTTP call to /instruments — one call, not one-per-exchange — and is the
    source for both the NSE-preferred and the BSE-fallback token lookups below."""
    global _INSTRUMENTS
    if _INSTRUMENTS is None:
        _INSTRUMENTS = kite.instruments()
    return _INSTRUMENTS


_TOKEN_EXCH = None
def exchange_for_token(kite, token):
    """Which exchange a STORED instrument_token belongs to (NSE|BSE|…), read back from the
    dump. Lets us record provenance for tokens resolved before this module existed (the old
    resolver was NSE-only but never wrote the fact). None if the token isn't in the current
    dump (e.g. delisted) — then the exchange can't be asserted, so nothing is recorded."""
    global _TOKEN_EXCH
    if _TOKEN_EXCH is None:
        _TOKEN_EXCH = {r.get("instrument_token"): r.get("exchange") for r in instruments(kite)}
    return _TOKEN_EXCH.get(token)


def resolve_token(kite, isin, symbol):
    """instrument_token for one IPO: NSE-exact FIRST, then BSE-exact fallback.

    Returns (token, how) where how is 'NSE' | 'BSE' | 'unresolved'. Only an EXACT,
    case-normalised match on a NON-EMPTY tradingsymbol counts — a fuzzy or partial
    match would attach the wrong price series to an IPO, which is worse than a null
    token. NSE is preferred (primary listing, deeper candle history); BSE recovers the
    ~BSE-only mainboard listings the old NSE-only lookup silently dropped."""
    rows = instruments(kite)
    # ISIN branch kept INERT (documented, not deleted): Kite's combined dump does not
    # carry a usable `isin` for equities, so this never matched in practice. Re-enable
    # only if a future dump populates the field.
    #   if isin:
    #       for r in rows:
    #           if (r.get("isin") or "").strip().upper() == isin.strip().upper():
    #               return r["instrument_token"], "isin"
    if symbol and symbol.strip():
        want = symbol.strip().upper()
        for exch in ("NSE", "BSE"):                       # NSE preferred, BSE fallback
            for r in rows:
                if (r.get("tradingsymbol") or "").strip().upper() == want \
                   and r.get("exchange") == exch:
                    return r["instrument_token"], exch
    return None, "unresolved"


def fetch_candles(kite, token, start, end):
    """Daily OHLCV -> {d,o,h,l,c,v}. PAGINATED at <=2000 days/request (Kite's cap for the
    day interval). A listing->today range for a pre-2020 IPO exceeds 2000 days; an
    unpaginated call errored, and that error used to early-return and skip the 15-min
    fetch too — so old IPOs (the early-era sample) silently got no intraday bars."""
    bars = []
    win_start = start
    step = dt.timedelta(days=2000)
    while win_start <= end:
        win_end = min(win_start + step - dt.timedelta(days=1), end)
        raw = kite.historical_data(token, from_date=win_start, to_date=win_end, interval="day")
        for c in raw:
            d = c["date"]
            bars.append({"d": d.date() if hasattr(d, "date") else d,
                         "o": c.get("open"), "h": c.get("high"), "l": c.get("low"),
                         "c": c.get("close"), "v": c.get("volume")})
        win_start = win_end + dt.timedelta(days=1)
    return bars


def fetch_candles_15m(kite, token, start, end):
    """15-minute OHLCV, PAGINATED at <=200 days/request (Kite's per-request cap for
    the 15minute interval). Walks [start, end] in <=200-day windows and concatenates.
    Returns bars in the shape upsert_candles_15m expects: {ts,o,h,l,c,v}. `ts` is the
    tz-aware bar timestamp Kite returns (stored verbatim as timestamptz)."""
    bars = []
    win_start = start
    step = dt.timedelta(days=200)
    while win_start <= end:
        win_end = min(win_start + step - dt.timedelta(days=1), end)
        raw = kite.historical_data(token, from_date=win_start, to_date=win_end,
                                   interval="15minute")
        for c in raw:
            bars.append({"ts": c["date"],
                         "o": c.get("open"), "h": c.get("high"), "l": c.get("low"),
                         "c": c.get("close"), "v": c.get("volume")})
        win_start = win_end + dt.timedelta(days=1)
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
    highs = [float(x[2]) for x in rows if x[2] is not None]
    if closes:
        rec["best_close"] = max(closes)
        rec["worst_close"] = min(closes)
    if highs and rec.get("listing_open"):
        # ceiling_20 (BOOLEAN): reached +20% above the listing OPEN, on the intraday HIGH,
        # within the first 30 sessions (D30). The "20" is the +20% threshold (cf. winner_35
        # = +35%); the window is D30. Definition RECOVERED EMPIRICALLY, not guessed — it
        # reproduces 98.4% of the 457 pre-existing stored booleans; close-based, vs-issue,
        # and D20/unbounded variants scored 66-91%. The old code wrote a PRICE
        # (max(closes[:20])) into this boolean column — every listed IPO failed the upsert.
        rec["ceiling_20"] = max(highs[:30]) >= rec["listing_open"] * 1.20
    if rec.get("listing_open") and closes:
        rec["hold_positive_vs_open"] = closes[-1] > rec["listing_open"]
        if issue_price:
            rec["winner_35"] = max(closes) >= issue_price * 1.35
    return rec, None


def process(kite, ipo_id, isin, symbol, name, listing_date, days, write, fetch_15m=True):
    """One IPO through the whole chain. Returns a step report."""
    from fill_v2 import upsert_candles, upsert_listing_outcome, upsert_candles_15m
    from fill_ipo import upsert_ipo, _log_fact
    out = {"ipo_id": ipo_id, "token": None, "bars": 0, "bars_15m": 0,
           "outcome": None, "notes": []}

    def read_token(conn):
        cur = conn.cursor()
        cur.execute("SELECT kite_token FROM ipo WHERE id=%s", (ipo_id,))
        return (cur.fetchone() or [None])[0]
    token = with_db(read_token)

    if token is None:
        token, how = resolve_token(kite, isin, symbol)
        out["resolved_by"] = how
        if token is None:
            out["notes"].append("token unresolved (no exact NSE or BSE symbol match) "
                                "-> candles and listing_outcomes both blocked")
            return out
        if write:
            # COALESCE-empty-only, so this can only fill a null token
            def store_token(conn):
                upsert_ipo(conn, dict(isin=isin, name_display=name,
                                      name_norm=None, kite_token=token), source="kite")
                cur = conn.cursor()
                _log_fact(cur, ipo_id, "kite_token_exchange", how, "kite")
                conn.commit()
            with_db(store_token)
    elif write:
        # Token already stored (possibly by the old NSE-only resolver, which never wrote
        # provenance). Backfill kite_token_exchange from the token itself — but only if NO
        # exchange fact exists yet, so this fills the gap on every re-run without duplicating
        # freshly-resolved rows. source='kite-backfill' keeps it distinguishable from 'kite'.
        out["resolved_by"] = "already stored"
        # Resolve over the network with no DB connection held, then persist separately.
        exch = exchange_for_token(kite, token)
        if exch:
            def backfill_exchange(conn):
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM source_facts WHERE ipo_id=%s AND field='kite_token_exchange' LIMIT 1",
                            (ipo_id,))
                if cur.fetchone() is None:
                    _log_fact(cur, ipo_id, "kite_token_exchange", exch, "kite-backfill")
                    conn.commit()
            with_db(backfill_exchange)
    out["token"] = token

    end = dt.date.today()
    start = (listing_date or (end - dt.timedelta(days=days))) - dt.timedelta(days=2)
    if (end - start).days > days and listing_date is None:
        start = end - dt.timedelta(days=days)
    try:
        bars = fetch_candles(kite, token, start, end)
        out["bars"] = len(bars)
        if write and bars:
            with_db(upsert_candles, ipo_id, bars)
    except Exception as e:
        # A daily failure must NOT skip the (independently paginated) 15-min fetch below —
        # they are separate series, and the old IPOs that most need 15-min data are exactly
        # the ones whose long daily range is most likely to hit an API edge. Log and go on.
        out["notes"].append(f"daily candles failed: {type(e).__name__}: {str(e)[:80]}")
        traceback.print_exc(file=sys.stdout)

    # 15-minute intraday -> market_candles_15m. INCREMENTAL: start at the day after
    # the last stored bar (or listing_date on first backfill), paginate to today.
    if write and fetch_15m:
        def read_latest(conn):
            cur = conn.cursor()
            cur.execute("SELECT max(ts) FROM market_candles_15m WHERE ipo_id=%s", (ipo_id,))
            return (cur.fetchone() or [None])[0]
        last = with_db(read_latest)
        i_start = last.date() if last else (listing_date or (end - dt.timedelta(days=days)))
        # (clamp to a MEASURED lookback horizon deferred — see the note at LOOKBACK above)
        try:
            bars15 = fetch_candles_15m(kite, token, i_start, end)
            out["bars_15m"] = with_db(upsert_candles_15m, ipo_id, bars15) if bars15 else 0
        except Exception as e:
            out["notes"].append(f"15m candles failed: {type(e).__name__}: {str(e)[:80]}")
            traceback.print_exc(file=sys.stdout)

    if not write:
        out["notes"].append("dry-run: outcome not derived (needs candles stored)")
        return out
    rec, note = with_db(derive_outcome, ipo_id)
    if note:
        out["notes"].append(note)
    elif rec:
        with_db(upsert_listing_outcome, ipo_id, rec, dataset_version="v2")
        out["outcome"] = {k: rec[k] for k in ("gap_pct", "pool", "listing_open", "d1_close")
                          if k in rec}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids"); ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-15m", action="store_true",
                    help="skip the 15-minute market_candles_15m fetch (daily only)")
    a = ap.parse_args()
    if not (a.write or a.dry_run):
        sys.exit("choose --write or --dry-run")
    write = a.write and not a.dry_run
    fetch_15m = not a.no_15m

    if write and fetch_15m:
        from fill_v2 import ensure_15m_table
        with_db(ensure_15m_table)          # idempotent; creates market_candles_15m once
    def select_targets(conn):
        from nse_fetch import CANONICAL_UNIVERSE_SQL
        cur = conn.cursor()
        if a.ids:
            ids = [int(x) for x in a.ids.split(",") if x.strip()]
            cur.execute(f"""SELECT i.id, i.isin, i.symbol, i.name_display, i.listing_date FROM ipo i
                            WHERE {CANONICAL_UNIVERSE_SQL}
                              AND i.id = ANY(%s) ORDER BY i.id""", (ids,))
            return cur.fetchall()
        # Scope is aligned to the official structured mainboard spine and the 100-day
        # monitoring window. An ipo_issue row is required classification evidence;
        # issue size is deliberately not an eligibility condition.
        cur.execute(f"""SELECT i.id, i.isin, i.symbol, i.name_display, i.listing_date
                        FROM ipo i
                        WHERE {CANONICAL_UNIVERSE_SQL}
                          AND i.listing_date BETWEEN current_date-100 AND current_date
                        ORDER BY i.listing_date DESC NULLS LAST LIMIT %s""", (a.limit,))
        return cur.fetchall()
    targets = with_db(select_targets)

    print(f"  [build] {FILE_BUILD}")
    print(f"  {len(targets)} IPOs · mode={'WRITE' if write else 'DRY-RUN'}")
    if not write:
        for ipo_id, isin, symbol, name, listing_date in targets:
            print(f"  dry id={ipo_id} isin={isin} symbol={symbol} listing_date={listing_date} name={name}")
        print("  Nothing was written; Kite authentication/network calls were not attempted.")
        return
    try:
        kite = get_kite()
        n_inst = len(instruments(kite))
        print(f"  kite authenticated · {n_inst} instruments loaded (all exchanges)\n")
    except Exception as e:
        sys.exit(f"  ✗ Kite auth failed: {type(e).__name__}: {str(e)[:160]}\n"
                 "    Run _scripts/refresh_kite_token.py first (TOTP, no browser).")

    ok = failed = 0
    for ipo_id, isin, symbol, name, listing_date in targets:
        print(f"  == id={ipo_id} {str(symbol or '(no symbol)'):14} {str(name)[:34]}")
        try:
            r = process(kite, ipo_id, isin, symbol, name, listing_date, a.days,
                        write, fetch_15m)
            print(f"       token={r['token']} ({r.get('resolved_by','already stored')})  "
                  f"bars={r['bars']}  bars_15m={r['bars_15m']}")
            if r["outcome"]:
                print(f"       outcome {r['outcome']}")
            for n in r["notes"]:
                print(f"       [note] {n}")
            ok += 1 if r["token"] else 0
            # Authentication/request errors are returned as notes by process so that
            # one IPO cannot abort the batch. They still make this selected target fail.
            if any("candles failed:" in note for note in r["notes"]):
                failed += 1
        except Exception as e:
            failed += 1
            print(f"  ! id={ipo_id}: {type(e).__name__}: {str(e)[:120]}")
            traceback.print_exc(file=sys.stdout)
    print(f"\n  done. {ok}/{len(targets)} with a token · {failed} failed."
          + ("" if write else "  Nothing was written."))
    # A step where EVERY IPO threw is a failed step. Exiting 0 let the 08-01 cron print
    # "6. Kite candles + listing outcomes  ok" over four CheckViolations — a green light
    # on a run in which nothing was written is worse than no light at all.
    if targets and failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
