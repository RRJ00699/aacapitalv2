"""
_scripts/ipo/scrape_gmp_with_cookie.py
========================================
Scrapes GMP history and anchor investor data from Chittorgarh/InvestorGain
using your subscription session cookie to bypass Cloudflare.

HOW TO GET YOUR SESSION COOKIE:
1. Open Chrome → go to chittorgarh.com → log in with your Pro subscription
2. Press F12 → Network tab → refresh the page
3. Click any request → Headers → Request Headers
4. Copy the full "Cookie:" value
5. Set it as environment variable: CHITTORGARH_COOKIE="your_cookie_here"

OR for InvestorGain:
1. Same steps on investorgain.com
2. Set: INVESTORGAIN_COOKIE="your_cookie_here"

Usage:
  python _scripts/ipo/scrape_gmp_with_cookie.py --source chittorgarh --limit 50
  python _scripts/ipo/scrape_gmp_with_cookie.py --source investorgain --limit 50
  python _scripts/ipo/scrape_gmp_with_cookie.py --source investorgain --company "Bajaj Housing"
"""

import os, sys, re, time, json, math, random, logging, argparse, datetime
import requests, psycopg2, psycopg2.extras
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL        = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
CHITTORGARH_COOKIE  = os.environ.get("CHITTORGARH_COOKIE", "")
INVESTORGAIN_COOKIE = os.environ.get("INVESTORGAIN_COOKIE", "")

# ── Browser headers ───────────────────────────────────────────────────────────
BASE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest":  "document",
    "Sec-Fetch-Mode":  "navigate",
    "Sec-Fetch-Site":  "same-origin",
    "Cache-Control":   "max-age=0",
}

TIER1 = {
    "lic","life insurance","sbi mutual","sbi mf","icici prudential","icici pru",
    "nippon","hdfc mutual","hdfc mf","kotak mutual","kotak mf","adia","abu dhabi",
    "gic","singapore","norway","temasek","axis mutual","axis mf","dsp","mirae",
    "franklin","motilal","canara robeco","tata mutual","tata mf","aditya birla",
    "pgim","sundaram","uti mutual","uti mf",
}

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def n(v, d=None):
    try:
        if v is None: return d
        s = str(v).replace(',','').replace('₹','').replace('Rs.','').replace('%','').strip()
        m = re.search(r'[-+]?\d*\.?\d+', s)
        return float(m.group()) if m else d
    except: return d

def parse_date(s) -> datetime.date | None:
    s = str(s or '').strip()
    for fmt in ('%d-%b-%Y','%d %b %Y','%Y-%m-%d','%d/%m/%Y','%b %d, %Y'):
        try: return datetime.datetime.strptime(s, fmt).date()
        except: pass
    return None

def make_session(cookie_str: str) -> requests.Session:
    """Create requests session with subscription cookie."""
    s = requests.Session()
    s.headers.update(BASE_HEADERS)
    if cookie_str:
        s.headers['Cookie'] = cookie_str
    return s

def make_slug(company: str) -> str:
    s = company.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'\s+', '-', s.strip())
    s = re.sub(r'-+', '-', s)
    # Remove common suffixes
    for suffix in ['-ltd', '-limited', '-pvt', '-private', '-india']:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
    return s.strip('-')

# ── GMP scraping (InvestorGain) ───────────────────────────────────────────────
def scrape_gmp_investorgain(session: requests.Session, company: str) -> list:
    """Scrape daily GMP history from InvestorGain."""
    slug = make_slug(company)
    urls = [
        f"https://www.investorgain.com/gmp/{slug}-ipo/",
        f"https://www.investorgain.com/ipo/{slug}-ipo-gmp/",
        f"https://www.investorgain.com/report/ipo-grey-market-premium/{slug}/",
    ]
    
    for url in urls:
        try:
            r = session.get(url, timeout=15)
            if not r.ok or len(r.text) < 500: continue
            
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Find GMP history table
            for table in soup.find_all('table'):
                text = table.get_text().lower()
                if 'gmp' in text and ('date' in text or 'day' in text):
                    rows = table.find_all('tr')
                    records = []
                    for row in rows[1:]:
                        cols = [c.get_text(strip=True) for c in row.find_all(['td','th'])]
                        if len(cols) >= 2:
                            date = parse_date(cols[0])
                            gmp  = n(cols[1])
                            if date and gmp is not None:
                                records.append({'date': date, 'gmp': gmp})
                    if records:
                        log.debug(f"  GMP: {len(records)} data points from {url}")
                        return records
        except Exception as e:
            log.debug(f"  {url}: {e}")
    return []

# ── GMP scraping (Chittorgarh) ────────────────────────────────────────────────
def scrape_gmp_chittorgarh(session: requests.Session, company: str,
                            chittorgarh_id: int = None) -> list:
    """Scrape GMP from Chittorgarh."""
    slug = make_slug(company)
    urls = []
    if chittorgarh_id:
        urls.append(f"https://www.chittorgarh.com/ipo/{slug}-ipo/{chittorgarh_id}/")
    urls.append(f"https://www.chittorgarh.com/ipo/{slug}-ipo/")
    
    for url in urls:
        try:
            r = session.get(url, timeout=15)
            if not r.ok or len(r.text) < 500: continue
            
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Look for GMP section
            for table in soup.find_all('table'):
                text = table.get_text().lower()
                if 'gmp' in text:
                    rows = table.find_all('tr')
                    records = []
                    for row in rows[1:]:
                        cols = [c.get_text(strip=True) for c in row.find_all(['td','th'])]
                        if len(cols) >= 2:
                            date = parse_date(cols[0])
                            gmp  = n(cols[1]) or n(cols[2]) if len(cols) > 2 else None
                            if date and gmp is not None:
                                records.append({'date': date, 'gmp': gmp})
                    if records:
                        return records
        except Exception as e:
            log.debug(f"  {url}: {e}")
    return []

# ── Anchor investor names (Chittorgarh) ───────────────────────────────────────
def scrape_anchors_chittorgarh(session: requests.Session, company: str,
                                chittorgarh_id: int = None) -> list:
    """Scrape anchor investor names from Chittorgarh."""
    slug = make_slug(company)
    urls = []
    if chittorgarh_id:
        urls.append(f"https://www.chittorgarh.com/ipo_report/anchor_investors/{chittorgarh_id}/")
    urls.append(f"https://www.chittorgarh.com/ipo/{slug}-ipo/")
    
    for url in urls:
        try:
            r = session.get(url, timeout=15)
            if not r.ok or len(r.text) < 500: continue
            
            soup = BeautifulSoup(r.text, 'html.parser')
            
            for section in soup.find_all(['div','section','table']):
                text = section.get_text().lower()
                if 'anchor investor' in text and len(text) > 200:
                    names = []
                    for row in section.find_all('tr')[1:]:
                        cols = row.find_all(['td','th'])
                        if cols:
                            name = cols[0].get_text(strip=True)
                            if name and len(name) > 3 and 'total' not in name.lower():
                                names.append(name)
                    if names:
                        return names
        except Exception as e:
            log.debug(f"  Anchor {url}: {e}")
    return []

# ── Day-wise subscription ──────────────────────────────────────────────────────
def scrape_daywise_subscription(session: requests.Session, company: str) -> dict:
    """Scrape day-wise subscription from Chittorgarh."""
    slug = make_slug(company)
    url = f"https://www.chittorgarh.com/ipo/{slug}-ipo/"
    
    try:
        r = session.get(url, timeout=15)
        if not r.ok: return {}
        
        soup = BeautifulSoup(r.text, 'html.parser')
        data = {}
        
        for table in soup.find_all('table'):
            text = table.get_text().lower()
            if 'day 1' in text or 'day1' in text:
                rows = table.find_all('tr')
                for row in rows:
                    cols = [c.get_text(strip=True) for c in row.find_all(['td','th'])]
                    if not cols: continue
                    label = cols[0].lower()
                    if 'qib' in label:
                        data.update({
                            'sub_day1_qib': n(cols[1]) if len(cols)>1 else None,
                            'sub_day2_qib': n(cols[2]) if len(cols)>2 else None,
                            'sub_day3_qib': n(cols[3]) if len(cols)>3 else None,
                        })
                    elif 'nii' in label or 'hni' in label:
                        data.update({
                            'sub_day1_nii': n(cols[1]) if len(cols)>1 else None,
                            'sub_day2_nii': n(cols[2]) if len(cols)>2 else None,
                            'sub_day3_nii': n(cols[3]) if len(cols)>3 else None,
                        })
                    elif 'retail' in label:
                        data.update({
                            'sub_day1_retail': n(cols[1]) if len(cols)>1 else None,
                            'sub_day2_retail': n(cols[2]) if len(cols)>2 else None,
                            'sub_day3_retail': n(cols[3]) if len(cols)>3 else None,
                        })
                if data: break
    except Exception as e:
        log.debug(f"  Day-wise sub error: {e}")
    return data

# ── GMP derived fields ────────────────────────────────────────────────────────
def process_gmp_history(gmp_records: list, issue_price: float) -> dict:
    """Compute GMP trend fields from daily records."""
    if not gmp_records:
        return {}
    
    # Sort by date desc (most recent first)
    records = sorted(gmp_records, key=lambda x: x['date'], reverse=True)
    
    gmps = [r['gmp'] for r in records]
    data = {
        'gmp_history':     json.dumps({str(r['date']): r['gmp'] for r in records}),
        'gmp_max_pct':     max(gmps) / issue_price * 100 if issue_price else None,
        'gmp_min_pct':     min(gmps) / issue_price * 100 if issue_price else None,
        'gmp_day_before_pct': gmps[0] / issue_price * 100 if issue_price and gmps else None,
    }
    
    # GMP momentum — rising or falling?
    if len(gmps) >= 3:
        recent_avg = sum(gmps[:3]) / 3
        older_avg  = sum(gmps[-3:]) / 3
        if recent_avg > older_avg * 1.05:
            data['gmp_momentum'] = 'RISING'
        elif recent_avg < older_avg * 0.95:
            data['gmp_momentum'] = 'FALLING'
        else:
            data['gmp_momentum'] = 'STABLE'
    
    # Map to T-N columns if we have enough history
    # T-1 = most recent, T-3 = 3 records ago, etc.
    t_map = {0: 'gmp_pct_t1', 2: 'gmp_pct_t3', 4: 'gmp_pct_t5',
             6: 'gmp_pct_t7', 9: 'gmp_pct_t10'}
    for idx, col in t_map.items():
        if idx < len(gmps) and issue_price:
            data[col] = round(gmps[idx] / issue_price * 100, 2)
    
    return data

def ensure_columns(conn):
    cols = [
        ("gmp_history","JSONB"), ("gmp_momentum","TEXT"),
        ("gmp_pct_t1","NUMERIC"), ("gmp_pct_t3","NUMERIC"),
        ("gmp_pct_t5","NUMERIC"), ("gmp_pct_t7","NUMERIC"),
        ("gmp_pct_t10","NUMERIC"), ("gmp_max_pct","NUMERIC"),
        ("gmp_min_pct","NUMERIC"), ("gmp_day_before_pct","NUMERIC"),
        ("sub_day1_qib","NUMERIC"), ("sub_day2_qib","NUMERIC"), ("sub_day3_qib","NUMERIC"),
        ("sub_day1_nii","NUMERIC"), ("sub_day2_nii","NUMERIC"), ("sub_day3_nii","NUMERIC"),
        ("sub_day1_retail","NUMERIC"),("sub_day2_retail","NUMERIC"),("sub_day3_retail","NUMERIC"),
        ("qib_backloaded","BOOLEAN"),
        ("anchor_names","JSONB"), ("anchor_count","INTEGER"),
        ("anchor_tier1_count","INTEGER"),
    ]
    cur = conn.cursor()
    for col, typ in cols:
        try:
            cur.execute(f"ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS {col} {typ}")
            conn.commit()
        except: conn.rollback()
    cur.close()

def save(conn, company: str, data: dict):
    if not data: return
    # Compute QIB backloaded
    d1 = data.get('sub_day1_qib') or 0
    d3 = data.get('sub_day3_qib') or 0
    if d1 > 0 and d3 > d1 * 2:
        data['qib_backloaded'] = True
    cur = conn.cursor()
    cols = list(data.keys())
    vals = [data[c] for c in cols]
    set_clause = ', '.join([f"{c} = %s" for c in cols])
    cur.execute(f"UPDATE ipo_intelligence SET {set_clause} WHERE company_name = %s",
                vals + [company])
    conn.commit()
    cur.close()

def get_ipos(conn, limit: int, year: int = None, company: str = None) -> list:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    q = """
        SELECT id, company_name, issue_price, listing_date, nse_symbol
        FROM ipo_intelligence
        WHERE (gmp_pct_t1 IS NULL OR sub_day1_qib IS NULL OR anchor_names IS NULL)
          AND listing_date IS NOT NULL AND is_sme = FALSE
    """
    params = []
    if company:
        q += " AND company_name ILIKE %s"
        params.append(f"%{company}%")
    elif year:
        q += " AND EXTRACT(YEAR FROM listing_date) = %s"
        params.append(year)
    q += " ORDER BY listing_date DESC LIMIT %s"
    params.append(limit)
    cur.execute(q, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source",  choices=["chittorgarh","investorgain","both"], default="both")
    p.add_argument("--limit",   type=int, default=50)
    p.add_argument("--year",    type=int)
    p.add_argument("--company", help="Filter by company name")
    p.add_argument("--delay",   type=float, default=2.5)
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    # Validate cookies
    if not CHITTORGARH_COOKIE and not INVESTORGAIN_COOKIE:
        log.error("""
No session cookie set. To get your cookie:
1. Open Chrome → go to chittorgarh.com → log in
2. Press F12 → Application tab → Cookies → chittorgarh.com
3. Copy the full cookie string
4. Run: set CHITTORGARH_COOKIE=your_cookie_here
5. Or: set INVESTORGAIN_COOKIE=your_cookie_here

Then re-run this script.
""")
        sys.exit(1)

    conn = get_db()
    ensure_columns(conn)

    ipos = get_ipos(conn, args.limit, args.year, args.company)
    log.info(f"Processing {len(ipos)} IPOs")
    log.info("=" * 60)

    # Create sessions
    chitt_session = make_session(CHITTORGARH_COOKIE) if CHITTORGARH_COOKIE else None
    ig_session    = make_session(INVESTORGAIN_COOKIE) if INVESTORGAIN_COOKIE else None

    ok = 0
    for i, ipo in enumerate(ipos):
        company     = ipo['company_name']
        issue_price = float(ipo.get('issue_price') or 0)
        log.info(f"  [{i+1}/{len(ipos)}] {company[:50]}")

        data = {}

        # 1. GMP history
        gmp_records = []
        if ig_session and args.source in ('investorgain','both'):
            gmp_records = scrape_gmp_investorgain(ig_session, company)
        if not gmp_records and chitt_session and args.source in ('chittorgarh','both'):
            gmp_records = scrape_gmp_chittorgarh(chitt_session, company)

        if gmp_records and issue_price:
            data.update(process_gmp_history(gmp_records, issue_price))
            log.info(f"    ✓ GMP: {len(gmp_records)} data points, T-1={data.get('gmp_pct_t1','?')}%")
        else:
            log.info(f"    ✗ GMP: no data")

        # 2. Anchor names
        if chitt_session:
            anchors = scrape_anchors_chittorgarh(chitt_session, company)
            if anchors:
                data['anchor_names']       = json.dumps(anchors)
                data['anchor_count']       = len(anchors)
                data['anchor_tier1_count'] = sum(1 for a in anchors
                                                  if any(t in a.lower() for t in TIER1))
                log.info(f"    ✓ Anchors: {len(anchors)} ({data['anchor_tier1_count']} tier-1)")

        # 3. Day-wise subscription
        if chitt_session:
            sub_data = scrape_daywise_subscription(chitt_session, company)
            if sub_data:
                data.update(sub_data)
                log.info(f"    ✓ Day-wise: QIB D1={sub_data.get('sub_day1_qib')} D3={sub_data.get('sub_day3_qib')}")

        if data:
            save(conn, company, data)
            ok += 1

        # Randomized delay to avoid detection
        sleep = args.delay + random.uniform(0.5, 1.5)
        time.sleep(sleep)

    conn.close()
    log.info("=" * 60)
    log.info(f"Done. {ok}/{len(ipos)} IPOs enriched with GMP/anchor/subscription data")

if __name__ == "__main__":
    main()
