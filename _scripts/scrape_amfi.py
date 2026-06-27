"""
_scripts/scrape_amfi.py — UPDATED
===================================
Fetches MF holdings from Screener.in (authenticated) instead of AMFI direct.
Screener shows MF holdings per stock including fund names, weights, values.

Why Screener instead of AMFI:
  - AMFI blocks automated requests (returns empty)
  - Screener.in paid subscription gives full MF data
  - Already used by score_management_commentary.py

Usage:
  python _scripts/scrape_amfi.py                          # top 200 stocks
  python _scripts/scrape_amfi.py --symbols ABCAPITAL INFY # specific stocks
  python _scripts/scrape_amfi.py --limit 50               # limit to 50
"""
import os, sys, re, json, time, logging, argparse, datetime
import requests, psycopg2, psycopg2.extras
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL      = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
SCREENER_USERNAME = os.environ.get("SCREENER_USERNAME")
SCREENER_PASSWORD = os.environ.get("SCREENER_PASSWORD")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.screener.in/",
}

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def ensure_tables(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mf_stock_summary (
            id             SERIAL PRIMARY KEY,
            nse_symbol     TEXT NOT NULL,
            month          DATE NOT NULL,
            total_value_cr NUMERIC(14,2),
            fund_count     INTEGER,
            amc_count      INTEGER,
            signal         TEXT,
            UNIQUE(nse_symbol, month)
        );
        CREATE TABLE IF NOT EXISTS mf_scheme_holdings (
            id                   SERIAL PRIMARY KEY,
            nse_symbol           TEXT NOT NULL,
            month                DATE NOT NULL,
            amc_name             TEXT,
            scheme_name          TEXT,
            market_value_cr      NUMERIC(14,2),
            portfolio_weight_pct NUMERIC(6,2),
            UNIQUE(nse_symbol, month, scheme_name)
        );
    """)
    conn.commit()
    cur.close()

def login_screener() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    # Get CSRF token
    r = session.get("https://www.screener.in/login/", timeout=10)
    soup = BeautifulSoup(r.text, 'html.parser')
    csrf = soup.find('input', {'name': 'csrfmiddlewaretoken'})
    csrf_token = csrf['value'] if csrf else ''
    # Login
    r = session.post("https://www.screener.in/login/", data={
        "username": SCREENER_USERNAME,
        "password": SCREENER_PASSWORD,
        "csrfmiddlewaretoken": csrf_token,
    }, headers={"Referer": "https://www.screener.in/login/"}, timeout=10)
    if 'logout' in r.text.lower():
        log.info("  ✓ Screener login successful")
        return session
    # Login failed. Do NOT continue with an unauthenticated session — Screener's
    # per-scheme MF tables are login-gated, so an anonymous scrape returns zero
    # holdings and every fund quietly goes stale with no error. Fail loudly.
    log.error("  ✗ Screener login FAILED — check SCREENER_USERNAME / SCREENER_PASSWORD "
              "(rotate + update the GitHub secret if the password changed).")
    raise SystemExit(2)

def fetch_mf_holdings(session, symbol: str) -> list:
    """Get MF holdings from Screener company page."""
    url = f"https://www.screener.in/company/{symbol}/"
    r = session.get(url, timeout=12)
    if not r.ok:
        log.warning(f"  {symbol}: HTTP {r.status_code}")
        return []
    
    soup = BeautifulSoup(r.text, 'html.parser')
    holdings = []
    
    # Look for "Mutual Fund Holdings" section
    for section in soup.find_all(['section', 'div']):
        heading = section.find(['h2', 'h3', 'h4'])
        if not heading or 'mutual fund' not in heading.get_text().lower():
            continue
        
        table = section.find('table')
        if not table:
            continue
            
        rows = table.find_all('tr')
        for row in rows[1:]:
            cols = [td.get_text(strip=True) for td in row.find_all(['td','th'])]
            if len(cols) >= 3:
                scheme = cols[0]
                # Parse value (e.g. "₹1,234 Cr")
                val_str = re.sub(r'[₹,\s]', '', cols[1].replace('Cr',''))
                val = float(val_str) if val_str else 0
                # Parse weight (e.g. "2.34%")
                wt_str = cols[2].replace('%','').strip()
                wt = float(wt_str) if wt_str else 0
                
                if scheme and val > 0:
                    # Guess AMC from scheme name
                    amc = scheme.split()[0] if scheme else "Unknown"
                    holdings.append({
                        'scheme_name': scheme,
                        'amc_name': amc,
                        'market_value_cr': val,
                        'portfolio_weight_pct': wt,
                    })
    
    return holdings

def save_holdings(conn, symbol: str, holdings: list):
    if not holdings: return
    
    month = datetime.date.today().replace(day=1)
    cur = conn.cursor()
    
    # Save individual scheme holdings
    for h in holdings:
        cur.execute("""
            INSERT INTO mf_scheme_holdings 
                (nse_symbol, month, amc_name, scheme_name, market_value_cr, portfolio_weight_pct)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (nse_symbol, month, scheme_name) DO UPDATE SET
                market_value_cr = EXCLUDED.market_value_cr,
                portfolio_weight_pct = EXCLUDED.portfolio_weight_pct
        """, (symbol, month, h['amc_name'], h['scheme_name'],
              h['market_value_cr'], h['portfolio_weight_pct']))
    
    # Save summary
    total_val = sum(h['market_value_cr'] for h in holdings)
    amcs = len(set(h['amc_name'] for h in holdings))
    signal = "HEAVY" if len(holdings) >= 10 else "MODERATE" if len(holdings) >= 3 else "LIGHT"
    
    cur.execute("""
        INSERT INTO mf_stock_summary (nse_symbol, month, total_value_cr, fund_count, amc_count, signal)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (nse_symbol, month) DO UPDATE SET
            total_value_cr = EXCLUDED.total_value_cr,
            fund_count = EXCLUDED.fund_count,
            amc_count = EXCLUDED.amc_count,
            signal = EXCLUDED.signal
    """, (symbol, month, total_val, len(holdings), amcs, signal))
    
    conn.commit()
    cur.close()

def get_symbols(conn, limit: int) -> list:
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT symbol FROM technical_signals
        WHERE symbol NOT ILIKE 'ANTELOP%%' AND symbol NOT ILIKE 'ACUTAAS%%'
        ORDER BY symbol LIMIT %s
    """, (limit,))
    symbols = [r[0] for r in cur.fetchall()]
    cur.close()
    return symbols

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", help="Specific symbols")
    p.add_argument("--limit",   type=int, default=200)
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_db()
    ensure_tables(conn)
    log.info("Connected to DB")

    symbols = args.symbols or get_symbols(conn, args.limit)
    log.info(f"Fetching MF holdings for {len(symbols)} stocks from Screener.in")

    session = login_screener()
    ok = 0

    for i, symbol in enumerate(symbols, 1):
        try:
            holdings = fetch_mf_holdings(session, symbol)
            if holdings:
                save_holdings(conn, symbol, holdings)
                total = sum(h['market_value_cr'] for h in holdings)
                log.info(f"  ✓ {symbol}: {len(holdings)} funds, ₹{total:.0f}Cr total")
                ok += 1
            else:
                log.debug(f"  {symbol}: no MF holdings found")
            
            if i % 20 == 0:
                log.info(f"  [{i}/{len(symbols)}] {ok} with holdings...")
            
            time.sleep(1.5)  # Be polite to Screener
        except Exception as e:
            log.warning(f"  {symbol}: {e}")

    conn.close()
    log.info(f"\nDone. {ok}/{len(symbols)} stocks with MF holdings data")
    # Safety net: if NOTHING was captured, the run effectively failed (auth dropped,
    # Screener layout changed, network). Exit non-zero so the Action turns red instead
    # of "succeeding" while writing zero rows and letting the conviction engine rot.
    if ok == 0:
        log.error("✗ Captured MF holdings for 0 stocks — treating as failure. "
                  "Check the login line above and whether Screener's page layout changed.")
        raise SystemExit(3)

if __name__ == "__main__":
    main()
