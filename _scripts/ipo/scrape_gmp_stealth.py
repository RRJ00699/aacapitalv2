"""
_scripts/ipo/scrape_gmp_stealth.py
=====================================
Stealth GMP + anchor + day-wise subscription scraper.
Uses two bypass methods:

METHOD 1 — curl_cffi (lightweight, fast, no browser needed)
  Spoofs Chrome's TLS fingerprint at the network layer.
  Works for most Cloudflare-protected sites without a browser.

METHOD 2 — nodriver (full browser, guaranteed bypass)
  Launches real Chrome via CDP with no webdriver signature.
  Solves Cloudflare Turnstile natively.
  Use when curl_cffi fails (heavy JS-rendered pages).

Install:
  pip install curl_cffi nodriver psycopg2-binary beautifulsoup4

Usage:
  python _scripts/ipo/scrape_gmp_stealth.py --method curl --year 2024 --limit 50
  python _scripts/ipo/scrape_gmp_stealth.py --method nodriver --limit 10
  python _scripts/ipo/scrape_gmp_stealth.py --method curl --company "Bajaj Housing"
"""

import os, sys, re, time, json, math, random, logging, argparse, asyncio, datetime
import psycopg2, psycopg2.extras
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

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
        s = re.sub(r'[₹Rs.,\s%]', '', str(v)).strip()
        m = re.search(r'[-+]?\d*\.?\d+', s)
        return float(m.group()) if m else d
    except: return d

def parse_date(s) -> datetime.date | None:
    s = str(s or '').strip()
    for fmt in ('%d-%b-%Y','%d %b %Y','%Y-%m-%d','%d/%m/%Y','%b %d, %Y','%d-%b-%y'):
        try: return datetime.datetime.strptime(s, fmt).date()
        except: pass
    return None

def make_slug(company: str) -> str:
    s = company.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'\s+', '-', s.strip())
    s = re.sub(r'-+', '-', s)
    for suffix in ['-ltd','-limited','-pvt','-private','-india','-inc','-corp']:
        if s.endswith(suffix): s = s[:-len(suffix)]
    return s.strip('-')

# ── METHOD 1: curl_cffi (TLS fingerprint spoof) ───────────────────────────────

def fetch_curl(url: str, retries: int = 3) -> str | None:
    """Fetch URL with Chrome TLS fingerprint using curl_cffi."""
    try:
        from curl_cffi import requests as curl_requests
        for attempt in range(retries):
            try:
                r = curl_requests.get(url, impersonate="chrome120", timeout=15,
                                      headers={"Referer": "https://www.investorgain.com/"})
                if r.ok and len(r.text) > 500:
                    log.debug(f"  curl_cffi OK: {len(r.text):,}c from {url}")
                    return r.text
                log.debug(f"  curl_cffi {r.status_code} from {url}")
            except Exception as e:
                log.debug(f"  curl_cffi attempt {attempt+1}: {e}")
            time.sleep(1 + attempt)
    except ImportError:
        log.warning("curl_cffi not installed. Run: pip install curl_cffi")
    return None

# ── METHOD 2: nodriver (full stealth browser) ─────────────────────────────────

_nd_browser = None

async def get_nd_browser():
    """Get or create a persistent nodriver browser instance."""
    global _nd_browser
    import nodriver as uc
    if _nd_browser is None:
        _nd_browser = await uc.start(headless=True)
        log.info("  nodriver: Chrome started")
    return _nd_browser

async def fetch_nodriver_async(url: str, wait_selector: str = "table") -> str | None:
    """Fetch URL using persistent nodriver browser instance."""
    try:
        import nodriver as uc
        browser = await get_nd_browser()
        page = await browser.get(url)
        # Wait for Cloudflare challenge + JS rendering
        await asyncio.sleep(6)
        # Try to wait for table or key content
        for selector in [wait_selector, ".gmp-table", "#gmp", ".table", "tbody"]:
            try:
                await page.wait_for(selector, timeout=8)
                break
            except:
                continue
        # Extra wait for JS-rendered tables
        await asyncio.sleep(3)
        html = await page.get_content()
        await page.close()
        return html if html and len(html) > 500 else None
    except ImportError:
        log.warning("nodriver not installed. Run: pip install nodriver")
    except Exception as e:
        log.debug(f"  nodriver error: {e}")
    return None

async def close_nd_browser():
    global _nd_browser
    if _nd_browser:
        try: _nd_browser.stop()
        except: pass
        _nd_browser = None

_nd_loop = None
def fetch_nodriver(url: str) -> str | None:
    """Fetch using persistent browser - reuses same Chrome instance."""
    global _nd_loop
    if _nd_loop is None:
        _nd_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_nd_loop)
    return _nd_loop.run_until_complete(fetch_nodriver_async(url))

def close_nodriver():
    global _nd_loop
    if _nd_loop:
        _nd_loop.run_until_complete(close_nd_browser())

# ── Parse GMP from HTML ───────────────────────────────────────────────────────

def parse_gmp_from_html(html: str, company: str) -> list:
    """Extract GMP history table from HTML — handles both server-rendered and JS tables."""
    soup = BeautifulSoup(html, 'html.parser')
    records = []

    # Try 1: Look for JSON data in script tags (React/Next.js sites)
    for script in soup.find_all('script'):
        txt = script.string or ''
        if 'gmp' in txt.lower() and ('date' in txt.lower() or 'price' in txt.lower()):
            # Try to extract JSON arrays
            import json
            # Look for patterns like [{"date":"...","gmp":...}]
            json_matches = re.findall(r'\[(\{[^[\]]{10,500}\}[,\{][^[\]]*\}*)\]', txt)
            for jm in json_matches:
                try:
                    items = json.loads(f'[{jm}]')
                    for item in items:
                        keys = [k.lower() for k in item.keys()]
                        if 'date' in keys or 'gmp' in keys:
                            date_key = next((k for k in item if 'date' in k.lower()), None)
                            gmp_key  = next((k for k in item if 'gmp' in k.lower()), None)
                            if date_key and gmp_key:
                                d = parse_date(str(item[date_key]))
                                g = n(item[gmp_key])
                                if d and g is not None:
                                    records.append({'date': str(d), 'gmp': g})
                except: pass
            if records:
                log.debug(f"  Found {len(records)} GMP records in JSON script")
                return records

    for table in soup.find_all('table'):
        text = table.get_text().lower()
        if 'gmp' not in text: continue

        rows = table.find_all('tr')
        if len(rows) < 2: continue

        for row in rows[1:]:
            cols = [c.get_text(strip=True) for c in row.find_all(['td','th'])]
            if len(cols) < 2: continue

            # Common patterns:
            # Date | GMP ₹ | GMP % | Est. Price
            # Date | IPO Price | GMP | Expected
            date = parse_date(cols[0])
            if not date: continue

            # Try each column for GMP value
            gmp_val = None
            for col in cols[1:4]:
                v = n(col)
                if v is not None and -50 < v < 500:  # reasonable GMP range
                    gmp_val = v
                    break

            if date and gmp_val is not None:
                records.append({'date': str(date), 'gmp': gmp_val})

    if records:
        log.debug(f"  Parsed {len(records)} GMP records for {company}")
    return records

def parse_anchors_from_html(html: str) -> list:
    """Extract anchor investor names from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    names = []

    for section in soup.find_all(['div','section','table']):
        text = section.get_text().lower()
        if 'anchor investor' not in text or len(text) < 100: continue

        for row in section.find_all('tr')[1:20]:
            cols = row.find_all(['td','th'])
            if not cols: continue
            name = cols[0].get_text(strip=True)
            if name and len(name) > 3 and name.lower() not in ('anchor investor','#','sl','sr'):
                if not any(x in name.lower() for x in ['total','grand','sub-total']):
                    names.append(name)
        if names: break

    return names[:40]  # cap at 40

def parse_daywise_from_html(html: str) -> dict:
    """Extract day-wise subscription from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    data = {}

    for table in soup.find_all('table'):
        text = table.get_text().lower()
        if 'day 1' not in text and 'day1' not in text: continue

        for row in table.find_all('tr'):
            cols = [c.get_text(strip=True) for c in row.find_all(['td','th'])]
            if not cols: continue
            label = cols[0].lower()

            if 'qib' in label and len(cols) >= 4:
                data.update({'sub_day1_qib': n(cols[1]), 'sub_day2_qib': n(cols[2]), 'sub_day3_qib': n(cols[3])})
            elif ('nii' in label or 'hni' in label) and len(cols) >= 4:
                data.update({'sub_day1_nii': n(cols[1]), 'sub_day2_nii': n(cols[2]), 'sub_day3_nii': n(cols[3])})
            elif 'retail' in label and len(cols) >= 4:
                data.update({'sub_day1_retail': n(cols[1]), 'sub_day2_retail': n(cols[2]), 'sub_day3_retail': n(cols[3])})
        if data: break

    return data

def process_gmp(records: list, issue_price: float) -> dict:
    """Compute GMP columns from daily history."""
    if not records or not issue_price: return {}

    records = sorted(records, key=lambda x: x['date'], reverse=True)
    gmps    = [r['gmp'] for r in records]

    data = {
        'gmp_history':        json.dumps({r['date']: r['gmp'] for r in records}),
        'gmp_day_before_pct': round(gmps[0] / issue_price * 100, 2) if gmps else None,
        'gmp_max_pct':        round(max(gmps) / issue_price * 100, 2),
        'gmp_min_pct':        round(min(gmps) / issue_price * 100, 2),
    }

    # T-N columns
    t_map = {0:'gmp_pct_t1', 2:'gmp_pct_t3', 4:'gmp_pct_t5', 6:'gmp_pct_t7', 9:'gmp_pct_t10'}
    for idx, col in t_map.items():
        if idx < len(gmps):
            data[col] = round(gmps[idx] / issue_price * 100, 2)

    # Momentum
    if len(gmps) >= 3:
        recent = sum(gmps[:3]) / 3
        older  = sum(gmps[-3:]) / 3
        data['gmp_momentum'] = ('RISING'    if recent > older * 1.05 else
                                'FALLING'   if recent < older * 0.95 else 'STABLE')

    return data

def ensure_columns(conn):
    cols = [
        ("gmp_history","JSONB"), ("gmp_momentum","TEXT"),
        ("gmp_pct_t1","NUMERIC"),("gmp_pct_t3","NUMERIC"),
        ("gmp_pct_t5","NUMERIC"),("gmp_pct_t7","NUMERIC"),
        ("gmp_pct_t10","NUMERIC"),("gmp_max_pct","NUMERIC"),
        ("gmp_min_pct","NUMERIC"),("gmp_day_before_pct","NUMERIC"),
        ("sub_day1_qib","NUMERIC"),("sub_day2_qib","NUMERIC"),("sub_day3_qib","NUMERIC"),
        ("sub_day1_nii","NUMERIC"),("sub_day2_nii","NUMERIC"),("sub_day3_nii","NUMERIC"),
        ("sub_day1_retail","NUMERIC"),("sub_day2_retail","NUMERIC"),("sub_day3_retail","NUMERIC"),
        ("qib_backloaded","BOOLEAN"),
        ("anchor_names","JSONB"),("anchor_count","INTEGER"),("anchor_tier1_count","INTEGER"),
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
    # QIB backloaded flag
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

def get_ipos(conn, limit, year=None, company=None) -> list:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    q = """
        SELECT id, company_name, issue_price, listing_date, nse_symbol
        FROM ipo_intelligence
        WHERE (gmp_pct_t1 IS NULL OR anchor_names IS NULL OR sub_day1_qib IS NULL)
          AND listing_date IS NOT NULL AND is_sme = FALSE
          AND listing_date >= CURRENT_DATE - INTERVAL '18 months'
    """
    params = []
    if company:
        q += " AND company_name ILIKE %s"; params.append(f"%{company}%")
    elif year:
        q += " AND EXTRACT(YEAR FROM listing_date) = %s"; params.append(year)
    q += " ORDER BY listing_date DESC LIMIT %s"; params.append(limit)
    cur.execute(q, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows

def scrape_ipo(fetch_fn, company: str, issue_price: float, debug: bool = False) -> dict:
    """Scrape one IPO — try InvestorGain first, then Chittorgarh."""
    slug = make_slug(company)
    data = {}

    urls = [
        f"https://www.investorgain.com/gmp/{slug}-ipo/",
        f"https://www.chittorgarh.com/ipo/{slug}-ipo/",
        f"https://www.investorgain.com/report/ipo-grey-market-premium/{slug}/",
        f"https://www.chittorgarh.com/report/ipo-grey-market-premium-gmp/{slug}/",
    ]

    for url in urls:
        html = fetch_fn(url)
        if debug and html:
            log.info(f"    DEBUG {url}: {len(html)}c | tables={html.count('<table')} | gmp={'gmp' in html.lower()}")
            if html and len(html) > 100:
                # Show page title
                import re
                title = re.search(r'<title>(.*?)</title>', html, re.I)
                if title: log.info(f"    Title: {title.group(1)[:60]}")
        if not html or len(html) < 1000:
            continue

        # GMP
        if not data.get('gmp_history'):
            gmp_records = parse_gmp_from_html(html, company)
            if gmp_records and issue_price:
                data.update(process_gmp(gmp_records, issue_price))

        # Anchors
        if not data.get('anchor_names'):
            anchors = parse_anchors_from_html(html)
            if anchors:
                data['anchor_names']       = json.dumps(anchors)
                data['anchor_count']       = len(anchors)
                data['anchor_tier1_count'] = sum(1 for a in anchors if any(t in a.lower() for t in TIER1))

        # Day-wise subscription
        if not data.get('sub_day1_qib'):
            sub = parse_daywise_from_html(html)
            if sub:
                data.update(sub)

        if data: break

    return data

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--method", choices=["curl","nodriver","both"], default="curl")
    p.add_argument("--limit",   type=int, default=50)
    p.add_argument("--year",    type=int)
    p.add_argument("--company", help="Filter by company name")
    p.add_argument("--delay",   type=float, default=2.0)
    p.add_argument("--debug",   action="store_true", help="Show raw HTML debug info")
    p.add_argument("--recent",  action="store_true", help="Only IPOs from last 6 months (live GMP)")
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_db()
    ensure_columns(conn)

    ipos = get_ipos(conn, args.limit, args.year, args.company)
    if args.recent:
        from datetime import date, timedelta
        cutoff = date.today() - timedelta(days=180)
        ipos = [i for i in ipos if i.get('listing_date') and i['listing_date'] >= cutoff]
        log.info(f"  Filtered to {len(ipos)} IPOs from last 6 months")
    log.info(f"Processing {len(ipos)} IPOs using method: {args.method}")
    log.info("=" * 60)

    # Select fetch function
    if args.method == "nodriver":
        fetch_fn = fetch_nodriver
    elif args.method == "both":
        def fetch_fn(url):
            html = fetch_curl(url)
            if not html:
                log.debug("  curl failed, trying nodriver...")
                html = fetch_nodriver(url)
            return html
    else:
        fetch_fn = fetch_curl

    ok = 0; skipped = 0
    for i, ipo in enumerate(ipos):
        company     = ipo['company_name']
        issue_price = float(ipo.get('issue_price') or 0)
        log.info(f"  [{i+1}/{len(ipos)}] {company[:50]}")

        try:
            data = scrape_ipo(fetch_fn, company, issue_price, debug=args.debug)
            if data:
                save(conn, company, data)
                parts = []
                if data.get('gmp_pct_t1'): parts.append(f"GMP T-1={data['gmp_pct_t1']:.1f}%")
                if data.get('anchor_count'): parts.append(f"Anchors={data['anchor_count']}")
                if data.get('sub_day3_qib'): parts.append(f"QIB D3={data['sub_day3_qib']:.0f}x")
                log.info(f"    ✓ {' | '.join(parts) if parts else 'data saved'}")
                ok += 1
            else:
                log.info(f"    ✗ No data found")
                skipped += 1
        except Exception as e:
            log.warning(f"    ✗ Error: {e}")
            skipped += 1

        time.sleep(args.delay + random.uniform(0.5, 1.5))

    conn.close()
    # Clean up browser
    if args.method in ('nodriver', 'both'):
        close_nodriver()
    log.info("=" * 60)
    log.info(f"Done. {ok} enriched, {skipped} skipped")

if __name__ == "__main__":
    main()
