"""
_scripts/scrape_amfi.py
========================
Scrapes MF holdings from AMFI India public data — completely free, no login.

Data sources (all public, no auth needed):
  1. https://www.amfiindia.com/spages/NAVAll.txt       — all scheme NAVs
  2. https://www.amfiindia.com/research-information/amfi-data — monthly portfolio

For stock-level MF holdings we use the monthly portfolio disclosure:
  https://www.amfiindia.com/modules/HoldingDetails?mf=Jun2026&ftype=E&mftype=O

Populates: mf_stock_summary, mf_scheme_holdings

Schedule: 1st of every month via GitHub Actions (daily-pipeline.yml)
On-demand: python _scripts/scrape_amfi.py

Usage:
  python _scripts/scrape_amfi.py                   # all equity schemes, current month
  python _scripts/scrape_amfi.py --month May2026   # specific month
  python _scripts/scrape_amfi.py --symbols INFY TCS # filter to specific stocks
"""

import os, sys, re, csv, io, time, logging, argparse, datetime
import requests, psycopg2, psycopg2.extras
from collections import defaultdict
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "text/html,application/xhtml+xml,*/*",
    "Referer":    "https://www.amfiindia.com/",
}

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
            signal          TEXT,
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

def get_month_str(offset_months: int = 1) -> str:
    """Get month string like 'Jun2026' for last completed month."""
    today = datetime.date.today()
    # Go back offset_months
    month = today.month - offset_months
    year  = today.year
    while month <= 0:
        month += 12
        year  -= 1
    return datetime.date(year, month, 1).strftime("%b%Y")

def fetch_amfi_portfolio(month_str: str) -> dict:
    """
    Fetch MF portfolio holdings from AMFI monthly disclosure.
    Returns dict: {nse_symbol: [{scheme, amc, value_cr, weight}]}
    
    AMFI URL: https://www.amfiindia.com/modules/HoldingDetails?mf=Jun2026&ftype=E&mftype=O
    """
    holdings: dict = defaultdict(list)
    
    months_to_try = [month_str] + [get_month_str(i) for i in range(1, 4)]
    
    for month in months_to_try:
        # AMFI accepts both formats — try multiple
        month_dt = datetime.datetime.strptime(month, "%b%Y")
        month_yyyymm = month_dt.strftime("%Y%m")
        urls_to_try = [
            f"https://www.amfiindia.com/modules/HoldingDetails?mf={month}&ftype=E&mftype=O",
            f"https://www.amfiindia.com/modules/HoldingDetails?mf={month_yyyymm}&ftype=E&mftype=O",
            f"https://portal.amfiindia.com/DownloadData_Po.aspx?mf={month_yyyymm}&ftype=E",
        ]
        url = urls_to_try[0]  # will try others below
        log.info(f"Trying AMFI portfolio: {url}")
        
        try:
            r = None
            for try_url in urls_to_try:
                try:
                    r = requests.get(try_url, headers=HEADERS, timeout=30)
                    if r.ok and len(r.text) > 500:
                        log.info(f"  Got {len(r.text):,} chars from {try_url}")
                        break
                    log.debug(f"  {r.status_code} from {try_url}")
                except:
                    continue
            
            if not r or not r.ok or len(r.text) < 500:
                log.warning(f"  All URLs failed for {month}")
                continue
            
            # Parse the AMFI data format
            # Format varies — try both HTML table and pipe-delimited text
            if "<table" in r.text.lower():
                holdings = parse_amfi_html(r.text, month)
            else:
                holdings = parse_amfi_text(r.text, month)
            
            if holdings:
                log.info(f"  Parsed {len(holdings)} stocks from {month}")
                return dict(holdings)
                
        except Exception as e:
            log.warning(f"  {month} failed: {e}")
    
    return {}

def parse_amfi_html(html: str, month: str) -> dict:
    """Parse AMFI HTML table format."""
    holdings: dict = defaultdict(list)
    soup = BeautifulSoup(html, "html.parser")
    
    current_amc    = "Unknown"
    current_scheme = "Unknown"
    
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["td","th"])]
            if not cells:
                continue
            
            # Detect scheme/AMC header rows
            if len(cells) == 1 and len(cells[0]) > 5:
                text = cells[0]
                if "Fund" in text or "AMC" in text or "Mutual" in text:
                    current_amc = text.split("(")[0].strip()
                    current_scheme = text
                continue
            
            # Data rows: Symbol | Name | Qty | Value | Weight
            if len(cells) >= 4:
                symbol = cells[0].strip()
                # Must look like NSE symbol: uppercase, 2-20 chars
                if not re.match(r'^[A-Z&-]{2,20}$', symbol):
                    continue
                try:
                    value_str  = next((c for c in cells[1:] if re.search(r'\d', c)), "0")
                    weight_str = cells[-1] if cells[-1] != value_str else "0"
                    value  = float(re.sub(r'[^0-9.]', '', value_str)  or 0)
                    weight = float(re.sub(r'[^0-9.]', '', weight_str) or 0)
                    if value > 0:
                        holdings[symbol].append({
                            "scheme": current_scheme,
                            "amc":    current_amc,
                            "value":  value / 100,  # lakhs to crores
                            "weight": weight,
                        })
                except:
                    continue
    
    return dict(holdings)

def parse_amfi_text(text: str, month: str) -> dict:
    """Parse AMFI pipe-delimited or CSV text format."""
    holdings: dict = defaultdict(list)
    current_scheme = "Unknown"
    current_amc    = "Unknown"
    
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Scheme header line (no pipes, long text)
        if '|' not in line and ';' not in line and len(line) > 10:
            if any(k in line for k in ["Fund", "Scheme", "AMC", "Growth", "Dividend"]):
                current_scheme = line.split('(')[0].strip()
                current_amc    = line.split()[0] if line.split() else "Unknown"
            continue
        
        # Data line
        sep = '|' if '|' in line else ';'
        parts = [p.strip() for p in line.split(sep)]
        
        if len(parts) >= 4:
            symbol = parts[0].strip()
            if not re.match(r'^[A-Z&-]{2,20}$', symbol):
                continue
            try:
                # Find value (usually 3rd or 4th column)
                nums = []
                for p in parts[1:]:
                    cleaned = re.sub(r'[^0-9.]', '', p)
                    if cleaned and float(cleaned) > 0:
                        nums.append(float(cleaned))
                
                if nums:
                    value  = nums[-2] / 100 if len(nums) >= 2 else nums[0] / 100
                    weight = nums[-1]        if len(nums) >= 2 else 0
                    holdings[symbol].append({
                        "scheme": current_scheme,
                        "amc":    current_amc,
                        "value":  value,
                        "weight": weight,
                    })
            except:
                continue
    
    return dict(holdings)

def fetch_via_nse_api() -> dict:
    """
    Alternative: fetch MF holdings via NSE bulk deal / FII data.
    NSE provides shareholding data for free.
    """
    holdings: dict = defaultdict(list)
    
    # NSE MF holding summary API (if available)
    try:
        r = requests.get(
            "https://www.nseindia.com/api/snapshot-capital-market-largeCapSecurities",
            headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        if r.ok:
            data = r.json()
            for item in data.get("data", []):
                sym = item.get("symbol", "")
                # NSE large cap data has MF holding %
                mf_pct = item.get("mfHolding", 0)
                if sym and mf_pct:
                    holdings[sym].append({
                        "scheme": "NSE MF Aggregate",
                        "amc":    "All AMCs",
                        "value":  0,
                        "weight": float(mf_pct),
                    })
    except:
        pass
    
    return dict(holdings)

def save_to_db(conn, holdings: dict, filter_symbols: list | None = None):
    month_date = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
    month_date = month_date.replace(day=1)  # first of last month
    
    cur = conn.cursor()
    saved_stocks = 0
    saved_schemes = 0

    for symbol, fund_list in holdings.items():
        if filter_symbols and symbol not in filter_symbols:
            continue
        if not fund_list:
            continue

        total_value = sum(f.get("value", 0) for f in fund_list)
        fund_count  = len(fund_list)
        amc_count   = len(set(f.get("amc","") for f in fund_list))
        signal = ("HEAVY_BUYING" if total_value > 5000 else
                  "MODERATE"    if total_value > 500  else "LIGHT")

        cur.execute("""
            INSERT INTO mf_stock_summary
                (nse_symbol, month, total_value_cr, fund_count, amc_count, signal)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (nse_symbol, month) DO UPDATE SET
                total_value_cr = EXCLUDED.total_value_cr,
                fund_count     = EXCLUDED.fund_count,
                amc_count      = EXCLUDED.amc_count,
                signal         = EXCLUDED.signal
        """, (symbol, month_date, round(total_value, 2), fund_count, amc_count, signal))
        saved_stocks += 1

        for f in fund_list[:20]:
            cur.execute("""
                INSERT INTO mf_scheme_holdings
                    (nse_symbol, month, amc_name, scheme_name, market_value_cr, portfolio_weight_pct)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (nse_symbol, month, scheme_name) DO UPDATE SET
                    market_value_cr      = EXCLUDED.market_value_cr,
                    portfolio_weight_pct = EXCLUDED.portfolio_weight_pct
            """, (symbol, month_date,
                  (f.get("amc","Unknown") or "Unknown")[:100],
                  (f.get("scheme","Unknown") or "Unknown")[:200],
                  round(f.get("value", 0), 2),
                  round(f.get("weight", 0), 4)))
            saved_schemes += 1

    conn.commit()
    cur.close()
    return saved_stocks, saved_schemes

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+")
    p.add_argument("--month",   default=get_month_str(1),
                   help="Month string e.g. Jun2026 (default: last completed month)")
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_db()
    log.info(f"Connected to DB")
    ensure_tables(conn)

    log.info(f"Fetching AMFI portfolio for {args.month}")
    holdings = fetch_amfi_portfolio(args.month)

    if not holdings:
        log.warning("AMFI direct fetch returned no data — trying NSE API fallback")
        holdings = fetch_via_nse_api()

    if not holdings:
        log.error("No MF holdings data found from any source")
        log.info("Manual option: Download from https://www.amfiindia.com/research-information/amfi-data")
        conn.close()
        sys.exit(0)

    stocks, schemes = save_to_db(conn, holdings, args.symbols)
    conn.close()

    log.info("=" * 60)
    log.info(f"Done. {stocks} stocks, {schemes} scheme holdings saved")

if __name__ == "__main__":
    main()
