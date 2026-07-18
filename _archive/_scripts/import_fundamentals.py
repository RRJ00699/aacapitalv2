
import os, sys, re, json, time, logging, argparse, socket
import requests, psycopg2
from bs4 import BeautifulSoup
import requests.packages.urllib3.util.connection as _c
def _ipv4(): return socket.AF_INET
_c.allowed_gai_family = _ipv4

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
SCREENER_UN  = os.environ.get("SCREENER_USERNAME")
SCREENER_PW  = os.environ.get("SCREENER_PASSWORD")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"}

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=10)

def screener_login():
    s = requests.Session()
    s.headers.update(HEADERS)
    r = s.get("https://www.screener.in/login/", timeout=10)
    csrf = BeautifulSoup(r.text, "html.parser").find("input", {"name": "csrfmiddlewaretoken"})
    if not csrf:
        raise RuntimeError("Cannot get CSRF")
    s.post("https://www.screener.in/login/", data={"csrfmiddlewaretoken": csrf["value"], "username": SCREENER_UN, "password": SCREENER_PW}, timeout=10)
    log.info("Screener.in login successful")
    return s

def get_num(soup, label):
    for li in soup.find_all("li"):
        spans = li.find_all("span")
        if len(spans) >= 2 and label.lower() in spans[0].get_text().lower():
            try: return float(re.sub(r"[,%]", "", spans[-1].get_text().strip()))
            except: pass
    return None

def scrape_fundamentals(session, symbol):
    for url in [f"https://www.screener.in/company/{symbol}/consolidated/", f"https://www.screener.in/company/{symbol}/"]:
        r = session.get(url, timeout=12)
        if r.status_code == 200: break
    else:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else symbol
    sector_tag = soup.find("a", href=lambda h: h and "/stocks/" in h)
    industry = sector_tag.get_text(strip=True) if sector_tag else None
    return {
        "nse_symbol": symbol, "name": name, "industry": industry,
        "market_cap": get_num(soup, "Market Cap"),
        "roce": get_num(soup, "ROCE"), "roe": get_num(soup, "ROE"),
        "pe_ratio": get_num(soup, "P/E"),
        "debt_to_equity": get_num(soup, "Debt to equity"),
    }

def upsert_fundamentals(data):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO stock_fundamentals (nse_symbol, name, industry, market_cap, roce, roe, pe_ratio, debt_to_equity, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (nse_symbol) DO UPDATE SET
            name=EXCLUDED.name,
            industry=COALESCE(EXCLUDED.industry, stock_fundamentals.industry),
            market_cap=COALESCE(EXCLUDED.market_cap, stock_fundamentals.market_cap),
            roce=COALESCE(EXCLUDED.roce, stock_fundamentals.roce),
            roe=COALESCE(EXCLUDED.roe, stock_fundamentals.roe),
            pe_ratio=COALESCE(EXCLUDED.pe_ratio, stock_fundamentals.pe_ratio),
            debt_to_equity=COALESCE(EXCLUDED.debt_to_equity, stock_fundamentals.debt_to_equity),
            updated_at=NOW()
    """, (data["nse_symbol"], data["name"], data["industry"], data["market_cap"],
          data["roce"], data["roe"], data["pe_ratio"], data["debt_to_equity"]))
    conn.commit(); cur.close(); conn.close()

def get_missing_symbols(limit):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ts.symbol FROM technical_signals ts
        WHERE ts.symbol NOT IN (SELECT nse_symbol FROM stock_fundamentals WHERE nse_symbol IS NOT NULL)
        UNION
        SELECT DISTINCT ii.symbol FROM ipo_intelligence ii
        WHERE ii.symbol IS NOT NULL
          AND ii.symbol NOT IN (SELECT nse_symbol FROM stock_fundamentals WHERE nse_symbol IS NOT NULL)
        ORDER BY 1 LIMIT %s
    """, (limit,))
    syms = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    return syms

def get_stale_symbols(days, limit):
    """Existing rows whose updated_at is older than `days` (refresh, not backfill)."""
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT nse_symbol FROM stock_fundamentals
        WHERE nse_symbol IS NOT NULL
          AND (updated_at IS NULL OR updated_at < NOW() - (%s || ' days')::interval)
        ORDER BY updated_at NULLS FIRST
        LIMIT %s
    """, (days, limit))
    syms = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    return syms

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+")
    p.add_argument("--stale", type=int, metavar="DAYS",
                   help="refresh existing rows older than DAYS (e.g. --stale 7)")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if not DATABASE_URL: log.error("DATABASE_URL not set"); sys.exit(1)
    if not SCREENER_UN: log.error("SCREENER_USERNAME not set"); sys.exit(1)
    session = screener_login()
    if args.symbols:
        symbols = args.symbols
    elif args.stale is not None:
        symbols = get_stale_symbols(args.stale, args.limit)
        log.info(f"Stale-refresh mode: {len(symbols)} rows older than {args.stale}d")
    else:
        symbols = get_missing_symbols(args.limit)
    log.info(f"Importing fundamentals for {len(symbols)} stocks")
    log.info("=" * 60)
    ok = 0
    for sym in symbols:
        log.info(f"  Scraping {sym}...")
        data = scrape_fundamentals(session, sym)
        if data:
            if not args.dry_run:
                try:
                    upsert_fundamentals(data)
                    ok += 1
                    log.info(f"  + {sym}: {data['name']} ROCE={data['roce']} MCap={data['market_cap']}")
                except Exception as e:
                    log.warning(f"  ! {sym}: DB error: {e}")
        else:
            log.warning(f"  - {sym}: not found on Screener")
        time.sleep(1.5)
    log.info("=" * 60)
    log.info(f"Done. {ok}/{len(symbols)} imported.")

if __name__ == "__main__":
    main()
