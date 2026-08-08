"""
_scripts/ipo/sync_ipo_calendar.py
===================================
Syncs upcoming IPOs from Chittorgarh into Neon.

HOW IT WORKS:
  - cf_clearance cookie is IP-bound to YOUR Windows machine
  - Must run on Windows (not GitHub Actions)
  - Fetches upcoming IPO list → subscription data → GMP → stores in Neon
  - GitHub Actions cron just runs play selector on what's already in Neon

Run daily on Windows (add to Task Scheduler):
  python _scripts\ipo\sync_ipo_calendar.py

Or manually:
  python _scripts\ipo\sync_ipo_calendar.py --debug
  python _scripts\ipo\sync_ipo_calendar.py --report-only
"""

import os, sys, re, json, logging, datetime, argparse
import requests, psycopg2, psycopg2.extras
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL        = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
CHITTORGARH_COOKIE  = os.environ.get("CHITTORGARH_COOKIE", "")
INVESTORGAIN_COOKIE = os.environ.get("INVESTORGAIN_COOKIE", "")

CHITT_LIST_URL = "https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/mainboard/"
CHITT_BASE     = "https://www.chittorgarh.com"

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def parse_date(v):
    if not v: return None
    s = re.sub(r'\s+', ' ', str(v).strip())
    for fmt in ['%d-%b-%Y','%Y-%m-%d','%d/%m/%Y','%d %b %Y','%b %d, %Y','%d-%m-%Y']:
        try: return datetime.datetime.strptime(s, fmt).date()
        except: pass
    # Handle "19 Jun - 23 Jun" range → take first date + year
    m = re.search(r'(\d{1,2})\s+(\w+)', s)
    if m:
        try:
            return datetime.datetime.strptime(f"{m.group(1)} {m.group(2)} 2026", '%d %b %Y').date()
        except: pass
    return None

def n(v, d=None):
    try:
        s = re.sub(r'[₹,Cr\s]', '', str(v or '')).strip()
        return float(s) if s else d
    except: return d

def make_session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.chittorgarh.com/",
    })
    if cookie:
        s.headers["Cookie"] = cookie
    return s

def fetch(session, url, label="") -> str | None:
    try:
        r = session.get(url, timeout=15)
        if r.ok and len(r.text) > 500:
            log.debug(f"  {label or url}: {r.status_code} {len(r.text):,}c")
            return r.text
        log.warning(f"  {label or url}: {r.status_code} {len(r.text)}c")
        if r.status_code == 403:
            log.warning("  → cf_clearance expired. Open chittorgarh.com in Chrome, press F12 → Console → copy(document.cookie)")
    except Exception as e:
        log.warning(f"  {label}: {e}")
    return None

def parse_ipo_list(html: str) -> list:
    """Parse the main IPO list page."""
    soup = BeautifulSoup(html, 'html.parser')
    ipos = []

    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 2: continue

        # Check if this looks like an IPO table
        header_text = ' '.join(th.get_text() for th in rows[0].find_all(['th','td'])).lower()
        if not any(k in header_text for k in ['company','open','close','price','size','ipo']):
            continue

        log.debug(f"  Found IPO table: {len(rows)} rows, headers: {header_text[:80]}")

        for row in rows[1:]:
            cols = row.find_all(['td','th'])
            if len(cols) < 3: continue

            texts = [c.get_text(strip=True) for c in cols]
            company = texts[0].strip()

            # Skip header rows, empty, totals
            if not company or len(company) < 3: continue
            if any(skip in company.lower() for skip in ['company','total','grand','ipo name']): continue

            # Get IPO detail URL if available
            link = cols[0].find('a')
            detail_url = CHITT_BASE + link['href'] if link and link.get('href') else None

            ipo = {
                'company_name': company,
                'chittorgarh_url': detail_url,
            }

            # Parse remaining columns by content
            for text in texts[1:]:
                text = text.strip()
                if not text: continue

                # Date range like "19 Jun - 23 Jun" or "23-Jun-2026"
                d = parse_date(text)
                if d:
                    if 'open_date' not in ipo:      ipo['open_date'] = d
                    elif 'close_date' not in ipo:   ipo['close_date'] = d
                    elif 'listing_date' not in ipo: ipo['listing_date'] = d
                    continue

                # Price band like "₹100 to ₹105" or just "₹100"
                price_match = re.findall(r'[\d,]+(?:\.\d+)?', text.replace(',',''))
                if price_match:
                    nums = [float(p) for p in price_match if float(p) > 0]
                    if nums:
                        v = max(nums)  # take upper band
                        if 1 < v < 10000 and 'issue_price' not in ipo:
                            ipo['issue_price'] = v
                        elif v > 10 and 'issue_size_cr' not in ipo:
                            ipo['issue_size_cr'] = v

            ipos.append(ipo)
            log.debug(f"    → {company[:40]} | open:{ipo.get('open_date')} close:{ipo.get('close_date')} price:{ipo.get('issue_price')}")

    return ipos

def fetch_ipo_detail(session, url: str, ipo: dict) -> dict:
    """Fetch individual IPO page for subscription, GMP, lot size."""
    html = fetch(session, url, label=ipo['company_name'][:30])
    if not html: return ipo

    soup = BeautifulSoup(html, 'html.parser')

    # Look for key data points
    text = soup.get_text()

    # GMP
    gmp_match = re.search(r'GMP[^\d]*([+-]?\d+)', text, re.I)
    if gmp_match:
        gmp_val = float(gmp_match.group(1))
        if ipo.get('issue_price') and ipo['issue_price'] > 0:
            ipo['gmp_pct_t1'] = round(gmp_val / ipo['issue_price'] * 100, 2)

    # QIB subscription
    qib_match = re.search(r'QIB[^\d]*(\d+\.?\d*)\s*x', text, re.I)
    if qib_match:
        ipo['qib_subscription_x'] = float(qib_match.group(1))

    # NII subscription
    nii_match = re.search(r'NII[^\d]*(\d+\.?\d*)\s*x', text, re.I)
    if nii_match:
        ipo['nii_subscription_x'] = float(nii_match.group(1))

    # Retail
    retail_match = re.search(r'(?:Retail|RII)[^\d]*(\d+\.?\d*)\s*x', text, re.I)
    if retail_match:
        ipo['rii_subscription_x'] = float(retail_match.group(1))

    # Lot size
    lot_match = re.search(r'Lot Size[^\d]*(\d+)', text, re.I)
    if lot_match:
        ipo['lot_size'] = int(lot_match.group(1))

    return ipo

def upsert(conn, ipo: dict) -> bool:
    company = ipo.get('company_name', '').strip()
    if not company: return False

    cur = conn.cursor()
    cur.execute("SELECT id FROM ipo_intelligence WHERE company_name = %s LIMIT 1", (company,))
    exists = cur.fetchone()

    skip = {'company_name', 'chittorgarh_url'}
    fields = {k: v for k, v in ipo.items() if k not in skip and v is not None}

    if exists:
        if not fields: cur.close(); return False
        set_clause = ', '.join([f"{k} = %s" for k in fields])
        cur.execute(f"UPDATE ipo_intelligence SET {set_clause} WHERE company_name = %s",
                    list(fields.values()) + [company])
    else:
        cols = ['company_name'] + list(fields.keys())
        vals = [company] + list(fields.values())
        cur.execute(
            f"INSERT INTO ipo_intelligence ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(vals))})",
            vals
        )

    conn.commit()
    cur.close()
    return True

def show_db(conn):
    today = datetime.date.today()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT company_name, open_date, close_date, listing_date,
               issue_price, qib_subscription_x, gmp_pct_t1,
               play_recommendation, play_confidence
        FROM ipo_intelligence
        WHERE listing_date IS NULL
           OR listing_date >= %s - INTERVAL '7 days'
        ORDER BY
          CASE WHEN listing_date IS NULL OR listing_date >= %s THEN 0 ELSE 1 END,
          listing_date ASC NULLS FIRST
        LIMIT 20
    """, (today, today))
    rows = cur.fetchall()
    cur.close()

    log.info(f"\n{'='*70}")
    log.info(f"UPCOMING & RECENT IPOs IN NEON ({len(rows)})")
    log.info(f"{'='*70}")
    for r in rows:
        status = "UPCOMING" if (not r['listing_date'] or r['listing_date'] >= today) else f"Listed {r['listing_date']}"
        qib    = f"QIB {r['qib_subscription_x']:.0f}x" if r['qib_subscription_x'] else "QIB ?"
        gmp    = f"GMP {r['gmp_pct_t1']:+.1f}%" if r['gmp_pct_t1'] else ""
        play   = r['play_recommendation'] or "not scored"
        log.info(f"  {r['company_name'][:32]:32s} {status:18s} {qib:10s} {gmp:10s} → {play}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report-only", action="store_true")
    p.add_argument("--debug",       action="store_true")
    p.add_argument("--detail",      action="store_true", help="Also fetch individual IPO pages")
    args = p.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_db()
    log.info("Connected to Neon DB")

    show_db(conn)

    if args.report_only:
        conn.close()
        return

    if not CHITTORGARH_COOKIE:
        log.error("""
CHITTORGARH_COOKIE not set.

To get it:
1. Open Chrome → go to chittorgarh.com → log in
2. Press F12 → Console tab
3. Type: copy(document.cookie)
4. Paste into PowerShell:
   $env:CHITTORGARH_COOKIE = "paste_here"
5. Re-run this script
""")
        conn.close()
        sys.exit(1)

    session = make_session(CHITTORGARH_COOKIE)

    log.info(f"\nFetching IPO list from Chittorgarh...")
    html = fetch(session, CHITT_LIST_URL, "IPO list")

    if not html:
        log.error("Failed — cf_clearance may have expired")
        log.info("Get fresh cookie: F12 → Console → copy(document.cookie)")
        conn.close()
        sys.exit(1)

    ipos = parse_ipo_list(html)
    log.info(f"Parsed {len(ipos)} IPOs from page")

    if not ipos:
        log.warning("No IPOs parsed — page structure may have changed")
        log.info("Run with --debug to see details")
        conn.close()
        return

    # Optionally fetch individual pages for subscription/GMP
    if args.detail:
        import time, random
        for i, ipo in enumerate(ipos):
            if ipo.get('chittorgarh_url'):
                ipos[i] = fetch_ipo_detail(session, ipo['chittorgarh_url'], ipo)
                time.sleep(random.uniform(2, 4))

    ok = 0
    for ipo in ipos:
        try:
            if upsert(conn, ipo):
                ok += 1
                log.info(f"  ✓ {ipo['company_name'][:40]:40s} open:{ipo.get('open_date','?')} close:{ipo.get('close_date','?')}")
        except Exception as e:
            log.warning(f"  ✗ {ipo.get('company_name','?')}: {e}")
            conn.rollback()

    conn.close()
    show_db(get_db())
    log.info(f"\n✅ Done. {ok}/{len(ipos)} IPOs synced to Neon")
    log.info("Next: python _scripts/ipo/ipo_play_selector.py")

if __name__ == "__main__":
    main()
