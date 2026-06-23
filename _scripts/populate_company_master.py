"""
_scripts/populate_company_master.py
=====================================
Seeds company_master with the stocks you already track.

Strategy: use price_candles DISTINCT symbols as the universe
(those are the stocks you've actually synced via Kite), then
enrich company names from the Kite instrument list.

This avoids trying to classify Kite's 9741 "EQ" instruments
(which includes bonds, SGBs, SME micro-caps etc.)

Usage:
  python _scripts/populate_company_master.py          # reads from local price_candles
  python _scripts/populate_company_master.py --neon   # also writes to Neon
  python _scripts/populate_company_master.py --dry-run
"""

import os, sys, logging, argparse
import psycopg2, psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

LOCAL_URL = (os.getenv("CANDLES_DATABASE_URL")
             or os.getenv("LOCAL_DATABASE_URL")
             or "postgresql://postgres:Ashrith%402820@localhost:5432/aacapital?sslmode=disable")
NEON_URL  = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")

SECTOR_MAP = {
    "BANK": ("Financials", "Banks"), "FINANCE": ("Financials", "NBFC"),
    "CAPITAL": ("Financials", "NBFC"), "INSURANCE": ("Financials", "Insurance"),
    "PHARMA": ("Healthcare", "Pharmaceuticals"), "HOSPITAL": ("Healthcare", "Hospitals"),
    "HEALTH": ("Healthcare", "Healthcare Services"), "TECH": ("Technology", "IT Services"),
    "INFOTECH": ("Technology", "IT Services"), "SOFT": ("Technology", "Software"),
    "INFRA": ("Infrastructure", "Infrastructure"), "POWER": ("Utilities", "Power"),
    "ENERGY": ("Energy", "Oil & Gas"), "OIL": ("Energy", "Oil & Gas"),
    "AUTO": ("Automobile", "Auto"), "MOTOR": ("Automobile", "Auto"),
    "STEEL": ("Materials", "Steel"), "CEMENT": ("Materials", "Cement"),
    "CHEMICAL": ("Materials", "Chemicals"), "REALTY": ("Real Estate", "Realty"),
    "HOTEL": ("Consumer", "Hospitality"), "RETAIL": ("Consumer", "Retail"),
    "FMCG": ("Consumer", "FMCG"), "FOOD": ("Consumer", "Food"),
    "AGRI": ("Agriculture", "Agro"), "MEDIA": ("Media", "Media"),
    "DEFENCE": ("Industrials", "Defence"), "ENGINEER": ("Industrials", "Engineering"),
}

def guess_sector(name):
    n = (name or "").upper()
    for kw, (sec, ind) in SECTOR_MAP.items():
        if kw in n:
            return sec, ind
    return None, None


def get_kite_name_lookup():
    """Build {tradingsymbol: name} from Kite instruments. No filtering needed."""
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        log.warning("kiteconnect not installed — company names will default to symbol")
        return {}

    api_key = os.getenv("KITE_API_KEY")
    token   = os.getenv("KITE_ACCESS_TOKEN")
    if not token:
        try:
            import psycopg2 as _pg
            _db = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL", "")
            if _db:
                _c = _pg.connect(_db); _cur = _c.cursor()
                _cur.execute("SELECT value FROM platform_config WHERE key = 'kite_access_token'")
                _r = _cur.fetchone(); _cur.close(); _c.close()
                if _r and _r[0]: token = str(_r[0]).strip()
        except Exception:
            pass
    if not api_key or not token:
        log.warning("KITE_API_KEY or KITE_ACCESS_TOKEN not set — names will default to symbol")
        return {}

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(token)
    log.info("Loading Kite instrument names…")
    instruments = kite.instruments("NSE")
    lookup = {i["tradingsymbol"]: i.get("name", "") for i in instruments if i.get("tradingsymbol")}
    log.info(f"  {len(lookup)} instrument names loaded")
    return lookup


def get_tracked_symbols(conn):
    """Get symbols from price_candles — the stocks we actually track."""
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT DISTINCT symbol FROM price_candles
            WHERE symbol IS NOT NULL AND symbol != ''
            ORDER BY symbol
        """)
        syms = [r[0] for r in cur.fetchall()]
        log.info(f"  {len(syms)} symbols found in price_candles")
        return syms
    except Exception as e:
        log.warning(f"  price_candles query failed: {e}")
        # Fallback to existing company_master
        try:
            cur.execute("SELECT symbol FROM company_master WHERE symbol IS NOT NULL ORDER BY symbol")
            syms = [r[0] for r in cur.fetchall()]
            log.info(f"  {len(syms)} symbols from existing company_master (fallback)")
            return syms
        except Exception:
            return []
    finally:
        cur.close()


def ensure_columns(conn):
    """Add any missing columns to company_master."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS company_master (
            id           SERIAL PRIMARY KEY,
            symbol       TEXT UNIQUE NOT NULL,
            nse_symbol   TEXT,
            company_name TEXT,
            sector       TEXT,
            is_active    BOOLEAN DEFAULT TRUE,
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            updated_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    for col, defn in [
        ("industry_group", "TEXT"),
        ("lot_size",        "INTEGER"),
        ("tick_size",       "NUMERIC(10,4)"),
        ("is_active",       "BOOLEAN DEFAULT TRUE"),
        ("created_at",      "TIMESTAMPTZ DEFAULT NOW()"),
        ("updated_at",      "TIMESTAMPTZ DEFAULT NOW()"),
    ]:
        cur.execute(f"ALTER TABLE company_master ADD COLUMN IF NOT EXISTS {col} {defn}")
    conn.commit()
    cur.close()


def upsert(conn, rows):
    cur = conn.cursor()
    psycopg2.extras.execute_values(cur, """
        INSERT INTO company_master
            (symbol, nse_symbol, company_name, sector, industry_group, is_active, updated_at)
        VALUES %s
        ON CONFLICT (symbol) DO UPDATE SET
            company_name   = COALESCE(EXCLUDED.company_name, company_master.company_name),
            nse_symbol     = EXCLUDED.nse_symbol,
            sector         = COALESCE(EXCLUDED.sector, company_master.sector),
            industry_group = COALESCE(EXCLUDED.industry_group, company_master.industry_group),
            updated_at     = NOW()
    """, rows, template="(%s,%s,%s,%s,%s,%s,NOW())")
    conn.commit()
    cur.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--neon",    action="store_true", help="Also sync to Neon")
    ap.add_argument("--dry-run", action="store_true", help="Print without writing")
    args = ap.parse_args()

    # Load Kite names (best-effort)
    name_lookup = get_kite_name_lookup()

    # Connect to local and get tracked symbols
    log.info("Connecting to local Postgres…")
    local = psycopg2.connect(LOCAL_URL)
    ensure_columns(local)

    symbols = get_tracked_symbols(local)
    if not symbols:
        log.error("No symbols found — make sure price_candles has data")
        sys.exit(1)

    # Build rows
    rows = []
    for sym in symbols:
        name = name_lookup.get(sym) or name_lookup.get(f"{sym}-EQ") or sym
        sec, ind = guess_sector(name)
        rows.append((sym, sym, name, sec, ind, True))

    if args.dry_run:
        log.info(f"Dry run: {len(rows)} rows to upsert")
        for r in rows[:10]:
            print(f"  {r[0]:15}  {r[2][:40]:40}  {r[3] or '—'}")
        print(f"  ... and {len(rows)-10} more")
        return

    log.info(f"Upserting {len(rows)} rows → local company_master…")
    upsert(local, rows)
    local.close()
    log.info(f"  ✅ {len(rows)} rows upserted to local company_master")

    if args.neon:
        if not NEON_URL:
            log.error("DATABASE_URL not set — cannot sync to Neon")
        else:
            log.info(f"Upserting {len(rows)} rows → Neon company_master…")
            neon = psycopg2.connect(NEON_URL)
            ensure_columns(neon)
            upsert(neon, rows)
            neon.close()
            log.info(f"  ✅ {len(rows)} rows upserted to Neon company_master")

    log.info("Done.")


if __name__ == "__main__":
    main()
