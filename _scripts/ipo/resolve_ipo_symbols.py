#!/usr/bin/env python3
"""
resolve_ipo_symbols.py — fill the ONE missing link for bare IPO rows.

Background: NSE's IPO feeds are open/upcoming only. Once an IPO lists it drops off
them, so fetch_nse_ipos.py can leave a row with a company name but NULL symbol /
listing_date (e.g. TURTLEMINT). Without symbol+listing_date, backfill_ipo_ohlc.py
can't fill listing_open/OHLC and the analyzer can't compute gap. This resolves that
link, then the EXISTING tools take over.

Two modes:

  AUTO  — for every mainboard row with NULL symbol, fuzzy-match its company_name to
          the NSE instruments list (Kite) and, above a confidence threshold, write the
          tradingsymbol. listing_date is then derived from the first price_candles row
          for that symbol (the real first trading day). Confidence-gated:
            >= --auto-th (default 0.88)  -> auto-write
            0.70 .. auto-th              -> LOGGED for manual review, NOT written
            < 0.70                       -> skipped
          Dry-run by default.

  MANUAL — fill one known row directly (no guessing), e.g. Turtlemint:
          --company "Turtlemint Fintech Solutions Limited" --symbol TURTLEMINT \
          --issue-price 152 --listing-date 2026-06-29

After this, run:
  python _scripts/ipo/backfill_ipo_ohlc.py            # fills listing_open/OHLC/gains
  python _scripts/ipo/analyze_listing_day.py --auto-today   # gap now resolves

Usage:
  python _scripts/ipo/resolve_ipo_symbols.py --auto                  # dry-run report
  python _scripts/ipo/resolve_ipo_symbols.py --auto --apply          # write confident matches
  python _scripts/ipo/resolve_ipo_symbols.py --company "..." --symbol X --issue-price 152 --listing-date 2026-06-29 --apply
"""
import os, sys, argparse, logging, re
from difflib import SequenceMatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("resolve-ipo")

try:
    import psycopg2
except ImportError:
    sys.exit("pip install psycopg2-binary")

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
KITE_API_KEY = os.environ.get("KITE_API_KEY", "br9m41pn8nvvywnl")

_SUFFIX = re.compile(r"\b(limited|ltd|private|pvt|fintech|solutions|industries|"
                     r"technologies|technology|company|corporation|corp|enterprises|"
                     r"india|services|holdings|finance|financial)\b", re.I)

def norm(name: str) -> str:
    s = (name or "").lower()
    s = _SUFFIX.sub(" ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def db():
    if not DB:
        sys.exit("DATABASE_URL not set.")
    return psycopg2.connect(DB)


def kite_instruments():
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        sys.exit("pip install kiteconnect")
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT value FROM platform_config WHERE key='kite_access_token'")
    row = cur.fetchone(); conn.close()
    if not row or not row[0]:
        sys.exit("No kite_access_token in platform_config — run refresh_kite_token.py first.")
    kite = KiteConnect(api_key=KITE_API_KEY)
    kite.set_access_token(row[0])
    insts = kite.instruments("NSE")
    # equity only (segment NSE, instrument_type EQ)
    return [{"symbol": i["tradingsymbol"], "name": i.get("name") or ""}
            for i in insts if i.get("instrument_type") == "EQ"]


def first_candle_date(conn, symbol):
    cur = conn.cursor()
    cur.execute("SELECT MIN(date) FROM price_candles WHERE symbol = %s", [symbol])
    r = cur.fetchone(); cur.close()
    return r[0] if r else None


def auto_resolve(apply, auto_th):
    conn = db(); cur = conn.cursor()
    cur.execute("""
        SELECT id, company_name FROM ipo_intelligence
        WHERE (symbol IS NULL OR btrim(symbol) = '')
          AND COALESCE(is_sme, false) = false
          AND company_name IS NOT NULL
        ORDER BY company_name
    """)
    bare = cur.fetchall()
    log.info(f"bare mainboard rows (no symbol): {len(bare)}")
    if not bare:
        conn.close(); return

    log.info("loading NSE instruments from Kite…")
    insts = kite_instruments()
    log.info(f"  {len(insts)} NSE equity instruments")

    auto, review, skip = 0, 0, 0
    for rid, company in bare:
        best, best_r = None, 0.0
        for inst in insts:
            if not inst["name"]:
                continue
            r = ratio(company, inst["name"])
            if r > best_r:
                best_r, best = r, inst
        if best is None:
            skip += 1; continue
        tag = "AUTO " if best_r >= auto_th else ("REVIEW" if best_r >= 0.70 else "skip ")
        if best_r < 0.70:
            skip += 1; continue
        ld = first_candle_date(conn, best["symbol"])
        log.info(f"  [{tag}] {company[:38]:38} -> {best['symbol']:12} "
                 f"({best_r:.2f}) listing_date≈{ld}")
        if best_r >= auto_th:
            auto += 1
            if apply:
                sets = "symbol = %s"
                vals = [best["symbol"]]
                if ld:
                    sets += ", listing_date = COALESCE(listing_date, %s)"
                    vals.append(ld)
                vals.append(rid)
                cur.execute(f"UPDATE ipo_intelligence SET {sets} WHERE id = %s", vals)
        else:
            review += 1

    if apply:
        conn.commit()
    log.info(f"\nsummary: {auto} auto, {review} need review, {skip} skipped"
             + ("" if apply else "  (DRY-RUN — add --apply to write the AUTO ones)"))
    conn.close()


def manual(args):
    conn = db(); cur = conn.cursor()
    sets, vals = [], []
    if args.symbol:       sets.append("symbol = %s");       vals.append(args.symbol.strip().upper())
    if args.issue_price:  sets.append("issue_price = %s");  vals.append(args.issue_price)
    if args.listing_date: sets.append("listing_date = %s"); vals.append(args.listing_date)
    if not sets:
        sys.exit("Nothing to set — give --symbol / --issue-price / --listing-date.")
    where = "company_name ILIKE %s" if args.company else "symbol = %s"
    key = f"%{args.company}%" if args.company else args.match_symbol
    if not key:
        sys.exit("Identify the row with --company \"...\" (or --match-symbol).")
    cur.execute(f"SELECT id, company_name, symbol, issue_price, listing_date "
                f"FROM ipo_intelligence WHERE {where}", [key])
    hits = cur.fetchall()
    if not hits:
        sys.exit("No matching row.")
    if len(hits) > 1:
        log.info("Multiple rows matched — be more specific:")
        for h in hits: log.info(f"  {h}")
        sys.exit(1)
    rid, name, sym, ip, ld = hits[0]
    log.info(f"row: {name} (symbol={sym}, issue_price={ip}, listing_date={ld})")
    log.info(f"will set: {', '.join(sets)} -> {vals}")
    if args.apply:
        cur.execute(f"UPDATE ipo_intelligence SET {', '.join(sets)} WHERE id = %s", vals + [rid])
        conn.commit()
        log.info("APPLIED.")
    else:
        log.info("DRY-RUN — add --apply to write.")
    conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", action="store_true", help="fuzzy-match all bare mainboard rows to NSE instruments")
    ap.add_argument("--auto-th", type=float, default=0.88, help="confidence threshold for auto-write (default 0.88)")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    # manual one-off
    ap.add_argument("--company", help="company_name (ILIKE) to identify the row for manual fill")
    ap.add_argument("--match-symbol", help="existing symbol to identify the row (alternative to --company)")
    ap.add_argument("--symbol", help="symbol to set")
    ap.add_argument("--issue-price", type=float, help="issue price to set")
    ap.add_argument("--listing-date", help="listing date YYYY-MM-DD to set")
    args = ap.parse_args()

    if args.auto:
        auto_resolve(args.apply, args.auto_th)
    elif args.company or args.match_symbol:
        manual(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
