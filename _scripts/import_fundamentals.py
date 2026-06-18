"""
_scripts/import_fundamentals.py
================================
Imports stock fundamentals from Screener.in for stocks missing from Neon.
Currently 790/1436 loaded — this fills the remaining 646.

Usage:
  python _scripts/import_fundamentals.py --dry-run     # show what would be imported
  python _scripts/import_fundamentals.py --limit 50    # import 50 stocks
  python _scripts/import_fundamentals.py --symbols ABCAPITAL INFY

Requires: pip install requests beautifulsoup4 psycopg2-binary
"""

import os, sys, re, json, time, logging, argparse, socket
import requests, psycopg2, psycopg2.extras
from bs4 import BeautifulSoup
import requests.packages.urllib3.util.connection as _c

# Force IPv4
def _ipv4(): return socket.AF_INET
_c.allowed_gai_family = _ipv4

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
SCREENER_UN  = os.environ.get("SCREENER_USERNAME")
SCREENER_PW  = os.environ.get("SCREENER_PASSWORD")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36",
    "Accept": "text/html,*/*",
}


def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=10)


def screener_login():
    s = requests.Session()
    s.headers.update(HEADERS)
    r = s.get("https://www.screener.in/login/", timeout=10)
    csrf = BeautifulSoup(r.text, "html.parser").find("input", {"name": "csrfmiddlewaretoken"})
    if not csrf:
        raise RuntimeError("Cannot get CSRF from Screener")
    s.post("https://www.screener.in/login/", data={
        "csrfmiddlewaretoken": csrf["value"],
        "username": SCREENER_UN,
        "password": SCREENER_PW,
    }, timeout=10)
    log.info("Screener.in login successful")
    return s


def scrape_fundamentals(session, symbol: str) -> dict | None:
    for url in [f"https://www.screener.in/company/{symbol}/consolidated/",
                f"https://www.screener.in/company/{symbol}/"]:
        r = session.get(url, timeout=12)
        if r.status_code == 200:
            break
    else:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    def get_ratio(label: str) -> float | None:
        for li in soup.find_all("li", class_="flex flex-space-between"):
            span = li.find("span", class_="name")
            val  = li.find("span", class_="nowrap value")
            if span and val and label.lower() in span.get_text().lower():
                try:
                    return float(re.sub(r"[,%]", "", val.get_text().strip()))
                except:
                    pass
        return None

    # Get company name from h1
    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else symbol

    # Get sector/industry
    sector_tag = soup.find("a", href=lambda h: h and "/stocks/" in h and "/industry/" in h)
    industry = sector_tag.get_text(strip=True) if sector_tag else None

    # Get market cap from top section
    mcap_el = soup.find("li", class_="flex flex-space-between")
    market_cap = get_ratio("Market Cap")

    return {
        "nse_symbol":        symbol,
        "name":              name,
        "industry":          industry,
        "market_cap":        market_cap,
        "roce":              get_ratio("ROCE"),
        "roe":               get_ratio("ROE"),
        "pe_ratio":          get_ratio("P/E"),
        "pb_ratio":          get_ratio("Price to Book"),
        "debt_to_equity":    get_ratio("Debt to equity"),
        "current_ratio":     get_ratio("Current ratio"),
        "promoter_holding":  get_ratio("Promoter holding"),
    }


def get_missing_symbols(limit: int) -> list[str]:
    """Get NSE symbols not yet in stock_fundamentals."""
    conn = get_db()
    cur  = conn.cursor()
    # Get all NSE symbols we should have (from ipo_intelligence + known NSE list)
    # For now get from technical_signals + any IPO intel symbols not in fundamentals
    cur.execute("""
        SELECT DISTINCT ts.symbol
        FROM technical_signals ts
        WHERE ts.symbol NOT IN (SELECT nse_symbol FROM stock_fundamentals WHERE nse_symbol IS NOT NULL)
        UNION
        SELECT DISTINCT ii.symbol FROM ipo_intelligence ii
        WHERE ii.symbol NOT IN (SELECT nse_symbol FROM stock_fundamentals WHERE nse_symbol IS NOT NULL)
          AND ii.symbol IS NOT NULL
        ORDER BY 1
        LIMIT %s
    """, (limit,))
    syms = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return syms


def upsert_fundamentals(data: dict):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO stock_fundamentals (
            nse_symbol, name, industry, market_cap, roce, roe,
            pe_ratio, pb_ratio, debt_to_equity, current_ratio, promoter_holding,
            updated_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (nse_symbol) DO UPDATE SET
            name              = EXCLUDED.name,
            industry          = COALESCE(EXCLUDED.industry, stock_fundamentals.industry),
            market_cap        = COALESCE(EXCLUDED.market_cap, stock_fundamentals.market_cap),
            roce              = COALESCE(EXCLUDED.roce, stock_fundamentals.roce),
            roe               = COALESCE(EXCLUDED.roe, stock_fundamentals.roe),
            pe_ratio          = COALESCE(EXCLUDED.pe_ratio, stock_fundamentals.pe_ratio),
            debt_to_equity    = COALESCE(EXCLUDED.debt_to_equity, stock_fundamentals.debt_to_equity),
            promoter_holding  = COALESCE(EXCLUDED.promoter_holding, stock_fundamentals.promoter_holding),
            updated_at        = NOW()
    """, (
        data["nse_symbol"], data["name"], data["industry"], data["market_cap"],
        data["roce"], data["roe"], data["pe_ratio"], data["pb_ratio"],
        data["debt_to_equity"], data["current_ratio"], data["promoter_holding"],
    ))
    conn.commit()
    cur.close()
    conn.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols",  nargs="+")
    p.add_argument("--limit",    type=int, default=50)
    p.add_argument("--dry-run",  action="store_true")
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)
    if not SCREENER_UN:
        log.error("SCREENER_USERNAME not set"); sys.exit(1)

    session = screener_login()

    symbols = args.symbols or get_missing_symbols(args.limit)
    log.info(f"Importing fundamentals for {len(symbols)} stocks")
    log.info("=" * 60)

    ok = 0
    for sym in symbols:
        log.info(f"  Scraping {sym}…")
        data = scrape_fundamentals(session, sym)
        if data:
            if not args.dry_run:
                upsert_fundamentals(data)
            log.info(f"  ✓ {sym}: {data['name']} | ROCE={data['roce']} | MCap={data['market_cap']}")
            ok += 1
        else:
            log.warning(f"  ✗ {sym}: not found on Screener")
        time.sleep(1.5)

    log.info("=" * 60)
    log.info(f"Done. {ok}/{len(symbols)} imported.")

if __name__ == "__main__":
    main()
