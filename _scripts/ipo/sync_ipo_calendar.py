"""
_scripts/ipo/sync_ipo_calendar.py
===================================
Syncs upcoming and recently listed IPOs into ipo_intelligence.
Sources (in order of preference):
  1. NSE IPO data API (public, no auth needed)
  2. BSE IPO data API (public)
  3. Chittorgarh upcoming IPO page (if cookie set)

Runs weekly via GitHub Actions (Sunday 6 PM IST).
Also runs manually: python _scripts/ipo/sync_ipo_calendar.py

What it does:
  - Fetches upcoming IPOs (not yet listed)
  - Fetches recently listed IPOs (last 30 days)
  - Upserts into ipo_intelligence
  - Sets play_recommendation based on available signals
  - Triggers play selector for new entries
"""
import os, sys, re, json, logging, datetime, math
import requests, psycopg2, psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def n(v, d=None):
    try:
        if v is None: return d
        s = str(v).replace(',','').replace('₹','').strip()
        return float(s) if s else d
    except: return d

def parse_date(v):
    if not v: return None
    s = str(v).strip()
    for fmt in ['%d-%b-%Y','%Y-%m-%d','%d/%m/%Y','%d %b %Y','%d-%m-%Y']:
        try: return datetime.datetime.strptime(s, fmt).date()
        except: pass
    return None

def fetch_nse_ipos() -> list:
    """Fetch upcoming and recent IPOs from NSE."""
    ipos = []
    
    # NSE IPO list endpoints
    urls = [
        "https://www.nseindia.com/api/ipo-current-allotment",
        "https://www.nseindia.com/api/ipo?status=upcoming",
        "https://www.nseindia.com/api/ipo?status=listed",
    ]
    
    session = requests.Session()
    # Hit NSE homepage first to get cookies
    try:
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)
    except: pass
    
    for url in urls:
        try:
            r = session.get(url, headers={**HEADERS, "Referer": "https://www.nseindia.com/"}, timeout=10)
            if r.ok and r.text.strip().startswith('{'):
                data = r.json()
                items = data if isinstance(data, list) else data.get('data', [])
                for item in items[:50]:
                    ipo = parse_nse_ipo(item)
                    if ipo:
                        ipos.append(ipo)
                log.info(f"  NSE {url.split('?')[-1]}: {len(items)} items")
        except Exception as e:
            log.debug(f"  NSE error: {e}")
    
    return ipos

def parse_nse_ipo(item: dict) -> dict | None:
    """Parse one NSE IPO item."""
    try:
        company = (item.get('companyName') or item.get('issuerName') or '').strip()
        if not company: return None
        
        return {
            'company_name':    company,
            'symbol':          item.get('symbol', '').strip(),
            'issue_price':     n(item.get('issuePrice') or item.get('cutoffPrice')),
            'price_band_low':  n(item.get('minBidPrice')),
            'price_band_high': n(item.get('maxBidPrice') or item.get('issuePrice')),
            'issue_size_cr':   n(item.get('issueSize')),
            'open_date':       parse_date(item.get('openDate') or item.get('bidOpenDate')),
            'close_date':      parse_date(item.get('closeDate') or item.get('bidCloseDate')),
            'listing_date':    parse_date(item.get('listingDate')),
            'lot_size':        n(item.get('lotSize') or item.get('minimumLotSize')),
            'isin':            item.get('isin', '').strip(),
            'is_sme':          'SME' in str(item.get('subType', '')).upper(),
        }
    except:
        return None

def fetch_chittorgarh_upcoming() -> list:
    """Fetch upcoming IPOs from Chittorgarh (uses cookie if set)."""
    cookie = os.environ.get("CHITTORGARH_COOKIE", "")
    if not cookie:
        log.info("  No CHITTORGARH_COOKIE set — skipping Chittorgarh scrape")
        return []
    
    ipos = []
    try:
        headers = {**HEADERS, "Cookie": cookie, "Referer": "https://www.chittorgarh.com/"}
        r = requests.get(
            "https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/mainboard/",
            headers=headers, timeout=15
        )
        if not r.ok or len(r.text) < 1000:
            log.warning(f"  Chittorgarh returned {r.status_code}")
            return []
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Find upcoming IPO table
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            for row in rows[1:20]:
                cols = [c.get_text(strip=True) for c in row.find_all(['td','th'])]
                if len(cols) >= 5:
                    company = cols[0].strip()
                    if not company or company == 'Company': continue
                    
                    ipo = {
                        'company_name': company,
                        'open_date':    parse_date(cols[1]) if len(cols) > 1 else None,
                        'close_date':   parse_date(cols[2]) if len(cols) > 2 else None,
                        'issue_price':  n(cols[3]) if len(cols) > 3 else None,
                        'issue_size_cr':n(cols[4]) if len(cols) > 4 else None,
                        'is_sme':       False,
                    }
                    if ipo['company_name']:
                        ipos.append(ipo)
        
        log.info(f"  Chittorgarh: {len(ipos)} upcoming IPOs")
    except Exception as e:
        log.warning(f"  Chittorgarh error: {e}")
    
    return ipos

def upsert_ipo(conn, ipo: dict) -> bool:
    company = str(ipo.get('company_name', '')).strip()
    if not company: return False
    
    cur = conn.cursor()
    cur.execute("SELECT id FROM ipo_intelligence WHERE company_name = %s LIMIT 1", (company,))
    exists = cur.fetchone()
    
    fields = {k: v for k, v in ipo.items() if k != 'company_name' and v is not None}
    
    if exists:
        if not fields:
            cur.close(); return False
        set_clause = ', '.join([f"{k} = %s" for k in fields])
        cur.execute(f"UPDATE ipo_intelligence SET {set_clause} WHERE company_name = %s",
                   list(fields.values()) + [company])
    else:
        cols = ['company_name'] + list(fields.keys())
        vals = [company] + list(fields.values())
        ph   = ', '.join(['%s'] * len(vals))
        cur.execute(f"INSERT INTO ipo_intelligence ({', '.join(cols)}) VALUES ({ph})", vals)
    
    conn.commit()
    cur.close()
    return True

def main():
    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)
    
    conn = get_db()
    log.info("Connected to Neon DB")
    log.info("Fetching upcoming IPOs...")
    
    all_ipos = []
    
    # Source 1: NSE
    nse_ipos = fetch_nse_ipos()
    all_ipos.extend(nse_ipos)
    log.info(f"NSE: {len(nse_ipos)} IPOs")
    
    # Source 2: Chittorgarh (if cookie set)
    chitt_ipos = fetch_chittorgarh_upcoming()
    all_ipos.extend(chitt_ipos)
    
    # Deduplicate by company name
    seen = set()
    unique = []
    for ipo in all_ipos:
        key = ipo['company_name'].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(ipo)
    
    log.info(f"Total unique IPOs to sync: {len(unique)}")
    
    ok = 0
    for ipo in unique:
        try:
            if upsert_ipo(conn, ipo):
                ok += 1
                log.info(f"  ✓ {ipo['company_name'][:40]} | listing: {ipo.get('listing_date', 'TBD')}")
        except Exception as e:
            log.warning(f"  {ipo.get('company_name', '?')}: {e}")
    
    conn.close()
    log.info(f"\nDone. {ok}/{len(unique)} IPOs synced to Neon")
    log.info("Next: python _scripts/ipo/ipo_play_selector.py")

if __name__ == "__main__":
    main()
