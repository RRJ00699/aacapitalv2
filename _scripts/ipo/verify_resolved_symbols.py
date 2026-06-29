#!/usr/bin/env python3
"""
verify_resolved_symbols.py — turn fuzzy-matched symbols into candle-verified facts.

The resolver fuzzy-matched company names to NSE symbols. Most are right, some aren't.
The truth test: a CORRECT symbol's first price_candles row lands on (≈) its listing_date.
A wrong match's trading history won't line up.

For every mainboard row with a symbol, this:
  1) NORMALISES NSE series suffixes (-BE/-SM/-BZ/-EQ/...) to the canonical symbol,
     preferring whichever variant actually has candles.
  2) FILLS listing_date from the first candle where it's still null (bonus — the real
     first trading day, now that backfill_ipo_ohlc has synced candles).
  3) VERIFIES alignment: |first_candle_date - listing_date| <= --tol days  -> VERIFIED.
     Candles exist but > tol off  -> MISMATCH (wrong symbol).
     No candles for either variant -> UNVERIFIED (can't conclude; left as-is).
  4) REVERTS (sets symbol = NULL) on MISMATCH and on the known-wrong list, so they go
     back into the resolve queue instead of poisoning the table.

Dry-run by default. --apply writes (normalise + fill listing_date + revert mismatches).

  python _scripts/ipo/verify_resolved_symbols.py                 # report only
  python _scripts/ipo/verify_resolved_symbols.py --apply         # write fixes
  python _scripts/ipo/verify_resolved_symbols.py --tol 7         # looser alignment window
"""
import os, sys, argparse, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("verify-sym")

try:
    import psycopg2
except ImportError:
    sys.exit("pip install psycopg2-binary")

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
if not DB:
    sys.exit("DATABASE_URL not set.")

# NSE trading-series suffixes that aren't part of the canonical symbol
NSE_SERIES = {"BE", "BZ", "SM", "EQ", "BL", "ST", "GS", "IL", "DR", "IT", "T0",
              "N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "N9"}

# matches we already know are wrong (revert regardless of candles)
KNOWN_WRONG = {"Credo Brands Marketing Ltd."}


def canonical(sym: str) -> str:
    if sym and "-" in sym:
        base, _, suf = sym.rpartition("-")
        if base and suf.upper() in NSE_SERIES:
            return base
    return sym


def first_candle(cur, sym):
    cur.execute("SELECT MIN(date) FROM price_candles WHERE symbol = %s", [sym])
    r = cur.fetchone()
    return r[0] if r and r[0] else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write fixes (default: dry-run)")
    ap.add_argument("--tol", type=int, default=5, help="days tolerance for candle/listing alignment")
    args = ap.parse_args()

    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, company_name, symbol, listing_date
        FROM ipo_intelligence
        WHERE symbol IS NOT NULL AND btrim(symbol) <> ''
          AND COALESCE(is_sme, false) = false
        ORDER BY company_name
    """)
    rows = cur.fetchall()
    log.info(f"mainboard rows with a symbol: {len(rows)}")

    n_norm = n_fill_ld = n_verified = n_mismatch = n_unverified = n_known = 0

    for rid, name, sym, ld in rows:
        canon = canonical(sym)

        # pick the symbol variant that actually has candles (canonical preferred)
        cand_sym, fcd = None, None
        for s in dict.fromkeys([canon, sym]):
            d = first_candle(cur, s)
            if d:
                cand_sym, fcd = s, d
                break

        # known-wrong: revert outright
        if name in KNOWN_WRONG:
            n_known += 1
            log.info(f"  [KNOWN-WRONG] {name[:40]:40} {sym} -> NULL")
            if args.apply:
                cur.execute("UPDATE ipo_intelligence SET symbol = NULL WHERE id = %s", [rid])
            continue

        if fcd is None:
            n_unverified += 1
            log.info(f"  [UNVERIFIED ] {name[:40]:40} {sym:14} (no candles for {canon}/{sym})")
            continue

        normalise_to = cand_sym if cand_sym != sym else None

        # fill listing_date from first candle if missing
        new_ld = None
        if ld is None:
            new_ld = fcd
            n_fill_ld += 1

        # alignment check (only if we have a listing_date to compare)
        status = "VERIFIED"
        compare_ld = ld or new_ld
        if ld is not None:
            delta = abs((fcd - ld).days)
            if delta > args.tol:
                status = "MISMATCH"

        if status == "MISMATCH":
            n_mismatch += 1
            log.info(f"  [MISMATCH   ] {name[:40]:40} {sym:14} listing={ld} but candles start {fcd} "
                     f"(Δ{abs((fcd-ld).days)}d) -> NULL")
            if args.apply:
                cur.execute("UPDATE ipo_intelligence SET symbol = NULL WHERE id = %s", [rid])
            continue

        n_verified += 1
        tags = []
        if normalise_to:
            tags.append(f"normalise {sym}->{normalise_to}"); n_norm += 1
        if new_ld:
            tags.append(f"listing_date<-{new_ld}")
        tagstr = ("  [" + ", ".join(tags) + "]") if tags else ""
        log.info(f"  [VERIFIED   ] {name[:40]:40} {(normalise_to or sym):14} (candles {fcd}){tagstr}")

        if args.apply and (normalise_to or new_ld):
            sets, vals = [], []
            if normalise_to:
                sets.append("symbol = %s"); vals.append(normalise_to)
            if new_ld:
                sets.append("listing_date = %s"); vals.append(new_ld)
            vals.append(rid)
            cur.execute(f"UPDATE ipo_intelligence SET {', '.join(sets)} WHERE id = %s", vals)

    if args.apply:
        conn.commit()

    log.info("\n" + "=" * 60)
    log.info(f"VERIFIED   : {n_verified}   (symbol's candles align with listing_date)")
    log.info(f"  normalised suffix : {n_norm}")
    log.info(f"  listing_date filled: {n_fill_ld}")
    log.info(f"MISMATCH   : {n_mismatch}   (reverted to NULL — wrong symbol)")
    log.info(f"KNOWN-WRONG: {n_known}   (reverted to NULL)")
    log.info(f"UNVERIFIED : {n_unverified}   (no candles — left as-is, sync candles to check)")
    log.info("=" * 60)
    if not args.apply:
        log.info("DRY-RUN — re-run with --apply to write normalisations, listing_date fills, and reverts.")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
