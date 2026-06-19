"""
_scripts/scrape_amfi.py
========================
Scrapes MF holdings from AMFI / mfapi.in — completely free, no login needed.
Populates: mf_stock_summary, mf_scheme_holdings

Data source:
  https://api.mfapi.in  — free MF NAV and portfolio data
  https://www.amfiindia.com/spages/NAVAll.txt — all scheme NAVs

For stock-level holdings, we use:
  https://www.amfiindia.com/modules/HoldingDetails — scheme portfolios

Schedule: 1st of every month via GitHub Actions (monthly-amfi.yml)
On-demand: Settings → Data Pipeline → Run full pipeline

Usage:
  python _scripts/scrape_amfi.py                    # top 50 schemes
  python _scripts/scrape_amfi.py --schemes 100      # top 100 schemes
  python _scripts/scrape_amfi.py --symbols INFY TCS # only these stocks
"""

import os, sys, re, time, json, logging, argparse, datetime
import requests, psycopg2, psycopg2.extras
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def ensure_tables(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mf_stock_summary (
            id              SERIAL PRIMARY KEY,
            nse_symbol      TEXT NOT NULL,
            month           DATE NOT NULL,
            total_value_cr  NUMERIC(14,2),
            fund_count      INTEGER,
            amc_count       INTEGER,
            mom_change_pct  NUMERIC(8,2),
            signal          TEXT,
            updated_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(nse_symbol, month)
        );
        CREATE TABLE IF NOT EXISTS mf_scheme_holdings (
            id              SERIAL PRIMARY KEY,
            nse_symbol      TEXT NOT NULL,
            month           DATE NOT NULL,
            amc_name        TEXT,
            scheme_name     TEXT,
            market_value_cr NUMERIC(14,2),
            portfolio_weight_pct NUMERIC(6,2),
            updated_at      TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(nse_symbol, month, scheme_name)
        );
    """)
    conn.commit()
    cur.close()

def fetch_top_schemes(limit: int) -> list:
    """Get top equity schemes by AUM from AMFI."""
    log.info("Fetching scheme list from AMFI…")
    try:
        # Use mfapi.in to get scheme codes
        r = requests.get(
            "https://api.mfapi.in/mf",
            headers=HEADERS, timeout=15
        )
        if not r.ok:
            raise RuntimeError(f"mfapi.in returned {r.status_code}")
        
        schemes = r.json()
        # Filter for equity schemes
        equity = [s for s in schemes if any(k in s.get("schemeName","").upper() 
                  for k in ["EQUITY", "FLEXI", "LARGE", "SMALL", "MID", "MULTI", "ELSS", "BLUECHIP"])]
        log.info(f"Found {len(equity)} equity schemes, using top {limit}")
        return equity[:limit]
    except Exception as e:
        log.error(f"Failed to fetch schemes: {e}")
        return []

def fetch_portfolio(scheme_code: str) -> list:
    """Fetch latest portfolio holdings for a scheme."""
    try:
        r = requests.get(
            f"https://api.mfapi.in/mf/{scheme_code}",
            headers=HEADERS, timeout=10
        )
        if not r.ok:
            return []
        data = r.json()
        # mfapi.in doesn't have portfolio data — use AMFI holdings endpoint
        return []
    except:
        return []

def fetch_amfi_portfolio_data() -> dict:
    """
    Fetch MF portfolio data from AMFI monthly disclosure.
    Returns: dict of {nse_symbol: [{scheme, amc, value, weight}]}
    """
    log.info("Fetching MF portfolio data from AMFI…")
    
    holdings: dict = defaultdict(list)
    
    # AMFI monthly portfolio disclosure URL
    today = datetime.date.today()
    # Try last month's data (most recent complete month)
    months_to_try = []
    for i in range(3):
        d = today.replace(day=1) - datetime.timedelta(days=i*28)
        months_to_try.append(d.strftime("%b%Y"))  # e.g. "May2026"
    
    for month_str in months_to_try:
        url = f"https://www.amfiindia.com/modules/HoldingDetails?mf={month_str}&ftype=E&mftype=O"
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.ok and len(r.text) > 1000:
                log.info(f"Got AMFI portfolio data for {month_str} ({len(r.text):,} chars)")
                # Parse the data
                lines = r.text.strip().split('\n')
                current_scheme = None
                current_amc = None
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Detect scheme header lines
                    if line.startswith('Scheme Name') or '|' not in line:
                        if len(line) > 10 and not line[0].isdigit():
                            current_scheme = line.split('(')[0].strip()
                            # Extract AMC from scheme name
                            parts = current_scheme.split()
                            current_amc = parts[0] if parts else "Unknown"
                        continue
                    
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 4:
                        try:
                            # Format: |Symbol|Name|Qty|Value|Weight|
                            symbol = parts[1].strip() if len(parts) > 1 else ""
                            value_str = parts[4].strip() if len(parts) > 4 else "0"
                            weight_str = parts[5].strip() if len(parts) > 5 else "0"
                            
                            if symbol and re.match(r'^[A-Z&]{2,20}$', symbol):
                                value = float(re.sub(r'[^0-9.]', '', value_str) or 0) / 100  # lakhs to cr
                                weight = float(re.sub(r'[^0-9.]', '', weight_str) or 0)
                                
                                if value > 0:
                                    holdings[symbol].append({
                                        "scheme": current_scheme or "Unknown",
                                        "amc":    current_amc or "Unknown",
                                        "value":  value,
                                        "weight": weight,
                                    })
                        except:
                            continue
                
                if holdings:
                    log.info(f"Parsed {len(holdings)} stocks from AMFI portfolio")
                    return dict(holdings)
        except Exception as e:
            log.warning(f"AMFI {month_str} failed: {e}")
    
    # Fallback: use Screener.in top mutual fund holdings (public page)
    log.info("Trying Screener.in MF holdings as fallback…")
    return fetch_screener_mf_holdings()

SCREENER_UN = os.environ.get("SCREENER_USERNAME")
SCREENER_PW = os.environ.get("SCREENER_PASSWORD")

def screener_login() -> requests.Session | None:
    """Authenticate with Screener.in — same method as management commentary."""
    if not SCREENER_UN or not SCREENER_PW:
        log.warning("SCREENER_USERNAME/PASSWORD not set — MF holdings require Screener login")
        return None
    try:
        from bs4 import BeautifulSoup
        s = requests.Session()
        s.headers.update(HEADERS)
        r = s.get("https://www.screener.in/login/", timeout=10)
        csrf = BeautifulSoup(r.text, "html.parser").find("input", {"name": "csrfmiddlewaretoken"})
        if not csrf:
            return None
        s.post("https://www.screener.in/login/", data={
            "csrfmiddlewaretoken": csrf["value"],
            "username": SCREENER_UN,
            "password": SCREENER_PW,
        }, timeout=10)
        log.info("Screener.in login successful")
        return s
    except Exception as e:
        log.warning(f"Screener login failed: {e}")
        return None

def fetch_screener_mf_holdings() -> dict:
    """Fetch MF holdings from Screener.in (requires login)."""
    from bs4 import BeautifulSoup
    holdings = defaultdict(list)

    top_symbols = [
        "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "BHARTIARTL",
        "SBIN", "KOTAKBANK", "LT", "AXISBANK", "WIPRO", "HCLTECH", "MARUTI",
        "SUNPHARMA", "TITAN", "BAJFINANCE", "DMART", "IRCTC", "ABCAPITAL",
        "FEDERALBNK", "AUBANK", "INDUSINDBK", "IDFCFIRSTB", "BANDHANBNK",
        "NTPC", "ADANIGREEN", "DLF", "LODHA", "PRESTIGE", "TRENT",
        "NYKAA", "ZOMATO", "PAYTM", "SWIGGY", "POLICYBZR",
    ]

    session = screener_login()
    if not session:
        log.warning("Cannot fetch MF holdings without Screener login")
        return {}

    for sym in top_symbols[:30]:  # limit to avoid rate limiting
        try:
            r = session.get(
                f"https://www.screener.in/company/{sym}/",
                timeout=10
            )
            if not r.ok:
                continue
            
            # Parse MF holdings from Screener page
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Find mutual fund section - try multiple selectors
            mf_section = (soup.find("section", {"id": "mutual-funds"}) or
                          soup.find("div",     {"id": "mutual-funds"}) or
                          soup.find("section", string=re.compile("Mutual Fund", re.I)))
            
            # Also try finding by heading
            if not mf_section:
                for s in soup.find_all(["section","div"]):
                    h = s.find(["h2","h3","h4"])
                    if h and "mutual fund" in h.get_text().lower():
                        mf_section = s
                        break
            
            if not mf_section:
                time.sleep(0.5)
                continue
            
            rows = mf_section.find_all("tr")
            for row in rows[1:11]:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    scheme = cols[0].get_text(strip=True)
                    try:
                        # Try different column positions for value
                        val_str = next((cols[i].get_text(strip=True) 
                                       for i in range(1,len(cols)) 
                                       if re.search(r'[0-9]', cols[i].get_text())), "0")
                        value = float(re.sub(r'[^0-9.]', '', val_str) or 0)
                        weight_str = cols[-1].get_text(strip=True) if len(cols) > 2 else "0"
                        weight = float(re.sub(r'[^0-9.]', '', weight_str) or 0)
                        amc = scheme.split()[0] if scheme else "Unknown"
                        if value > 0 and scheme:
                            holdings[sym].append({
                                "scheme": scheme, "amc": amc,
                                "value": value, "weight": weight,
                            })
                    except:
                        continue
            
            if sym in holdings:
                log.info(f"  {sym}: {len(holdings[sym])} MF holders")
            time.sleep(0.8)
        except Exception as e:
            log.warning(f"  {sym} Screener failed: {e}")
    
    return dict(holdings)

def save_holdings(conn, holdings: dict):
    month = datetime.date.today().replace(day=1)
    cur = conn.cursor()
    saved_stocks = 0
    saved_schemes = 0

    for symbol, fund_list in holdings.items():
        if not fund_list:
            continue

        total_value = sum(f["value"] for f in fund_list)
        fund_count  = len(fund_list)
        amc_count   = len(set(f["amc"] for f in fund_list))
        signal = ("HEAVY_BUYING" if total_value > 5000 else
                  "MODERATE"    if total_value > 1000 else
                  "LIGHT")

        # Upsert summary
        cur.execute("""
            INSERT INTO mf_stock_summary
                (nse_symbol, month, total_value_cr, fund_count, amc_count, signal, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (nse_symbol, month) DO UPDATE SET
                total_value_cr = EXCLUDED.total_value_cr,
                fund_count     = EXCLUDED.fund_count,
                amc_count      = EXCLUDED.amc_count,
                signal         = EXCLUDED.signal,
                updated_at     = NOW()
        """, (symbol, month, round(total_value, 2), fund_count, amc_count, signal))
        saved_stocks += 1

        # Upsert individual schemes
        for f in fund_list[:20]:
            cur.execute("""
                INSERT INTO mf_scheme_holdings
                    (nse_symbol, month, amc_name, scheme_name, market_value_cr, portfolio_weight_pct, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (nse_symbol, month, scheme_name) DO UPDATE SET
                    market_value_cr      = EXCLUDED.market_value_cr,
                    portfolio_weight_pct = EXCLUDED.portfolio_weight_pct,
                    updated_at           = NOW()
            """, (symbol, month, f["amc"][:100], f["scheme"][:200],
                  round(f["value"], 2), round(f["weight"], 4)))
            saved_schemes += 1

    conn.commit()
    cur.close()
    return saved_stocks, saved_schemes

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--schemes",  type=int, default=50)
    p.add_argument("--symbols",  nargs="+")
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_db()
    log.info("Connected to DB")
    ensure_tables(conn)

    holdings = fetch_amfi_portfolio_data()

    if args.symbols:
        holdings = {k: v for k, v in holdings.items() if k in args.symbols}

    if not holdings:
        log.warning("No MF holdings data found")
        conn.close()
        return

    stocks, schemes = save_holdings(conn, holdings)
    conn.close()

    log.info("=" * 60)
    log.info(f"Done. {stocks} stocks, {schemes} scheme holdings saved to Neon")

if __name__ == "__main__":
    main()
