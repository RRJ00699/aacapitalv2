"""
_scripts/ipo/scrape_ipo_gmp_and_details.py
============================================
Scrapes from Chittorgarh what's NOT in the Excel exports:
  1. GMP history (T-10, T-7, T-5, T-3, T-1) per IPO
  2. Day-wise subscription (Day1/Day2/Day3 QIB/NII/Retail)
  3. Anchor investor names per IPO
  4. Post-listing returns (Day7, Day30, Day90, Day180, Day365)

Source: https://www.chittorgarh.com/ipo/ (public pages, no login needed)

Usage:
  python _scripts/ipo/scrape_ipo_gmp_and_details.py --limit 50
  python _scripts/ipo/scrape_ipo_gmp_and_details.py --symbol BAJAJ
  python _scripts/ipo/scrape_ipo_gmp_and_details.py --year 2024
"""

import os, sys, re, time, json, logging, argparse, datetime
import requests, psycopg2, psycopg2.extras
from bs4 import BeautifulSoup
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.chittorgarh.com/",
}

TIER1 = {
    "lic","life insurance","sbi mutual","sbi mf","icici prudential","icici pru",
    "nippon","hdfc mutual","hdfc mf","kotak mutual","kotak mf","adia","abu dhabi",
    "gic","singapore government","norway","temasek","axis mutual","axis mf",
    "dsp","mirae","franklin","motilal","canara robeco","tata mutual","tata mf",
    "aditya birla","pgim","sundaram","uti mutual","uti mf",
}

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def n(v, d=None):
    try:
        if v is None: return d
        s = str(v).replace(',','').replace('%','').strip()
        return float(s) if s else d
    except: return d

def get_ipo_list(session, year=None, limit=100) -> list:
    """Get list of IPOs with their Chittorgarh URLs."""
    cur = get_db().cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = """
        SELECT id, company_name, symbol, nse_symbol, listing_date, open_date
        FROM ipo_intelligence
        WHERE gmp_pct_t1 IS NULL
          AND listing_date IS NOT NULL
    """
    params = []
    if year:
        query += " AND EXTRACT(YEAR FROM listing_date) = %s"
        params.append(year)
    query += " ORDER BY listing_date DESC LIMIT %s"
    params.append(limit)
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.connection.close()
    log.info(f"Found {len(rows)} IPOs needing GMP/subscription data")
    return [dict(r) for r in rows]

def make_slug(company_name: str) -> str:
    """Convert company name to Chittorgarh URL slug."""
    s = company_name.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'\s+', '-', s.strip())
    s = re.sub(r'-+', '-', s)
    return s

def scrape_ipo_page(session: requests.Session, company: str) -> dict:
    """Scrape a single IPO page from Chittorgarh."""
    slug = make_slug(company)
    
    # Try multiple URL formats
    urls = [
        f"https://www.chittorgarh.com/ipo/{slug}-ipo/",
        f"https://www.chittorgarh.com/ipo/{slug}/",
    ]
    
    soup = None
    for url in urls:
        try:
            r = session.get(url, headers=HEADERS, timeout=15)
            if r.ok and 'ipo' in r.url.lower():
                soup = BeautifulSoup(r.text, 'html.parser')
                log.debug(f"  Got {len(r.text):,} chars from {url}")
                break
        except Exception as e:
            log.debug(f"  URL failed: {url} — {e}")
    
    if not soup:
        return {}
    
    data = {}
    
    # ── GMP history ──────────────────────────────────────────────────────────
    # Look for GMP table or GMP section
    gmp_table = None
    for table in soup.find_all('table'):
        text = table.get_text().lower()
        if 'gmp' in text and ('₹' in text or 'rs' in text):
            gmp_table = table
            break
    
    if gmp_table:
        gmp_history = {}
        rows = gmp_table.find_all('tr')
        for row in rows[1:]:
            cols = [c.get_text(strip=True) for c in row.find_all(['td','th'])]
            if len(cols) >= 2:
                # Date | GMP ₹ | GMP % | Expected Price
                date_str = cols[0]
                gmp_val  = n(cols[1].replace('₹','').replace('Rs.',''))
                gmp_pct  = n(cols[2]) if len(cols) > 2 else None
                if date_str and (gmp_val is not None or gmp_pct is not None):
                    gmp_history[date_str] = {'gmp_rs': gmp_val, 'gmp_pct': gmp_pct}
        
        if gmp_history:
            data['gmp_history'] = json.dumps(gmp_history)
            # Extract T-1 (most recent)
            vals = list(gmp_history.values())
            if vals:
                data['gmp_pct_t1'] = vals[0].get('gmp_pct')
                data['gmp_max_pct'] = max((v.get('gmp_pct') or 0 for v in vals), default=None)
                data['gmp_min_pct'] = min((v.get('gmp_pct') or 999 for v in vals), default=None)
                if data['gmp_min_pct'] == 999: data['gmp_min_pct'] = None

    # ── Day-wise subscription ─────────────────────────────────────────────────
    for table in soup.find_all('table'):
        text = table.get_text().lower()
        if 'day 1' in text or 'day1' in text:
            rows = table.find_all('tr')
            headers = [c.get_text(strip=True).lower() for c in rows[0].find_all(['th','td'])]
            
            for row in rows[1:]:
                cols = [c.get_text(strip=True) for c in row.find_all(['td','th'])]
                if not cols: continue
                label = cols[0].lower()
                
                # Map row labels to our fields
                if 'qib' in label:
                    data['sub_day1_qib']    = n(cols[1]) if len(cols)>1 else None
                    data['sub_day2_qib']    = n(cols[2]) if len(cols)>2 else None
                    data['sub_day3_qib']    = n(cols[3]) if len(cols)>3 else None
                elif 'nii' in label or 'hni' in label:
                    data['sub_day1_nii']    = n(cols[1]) if len(cols)>1 else None
                    data['sub_day2_nii']    = n(cols[2]) if len(cols)>2 else None
                    data['sub_day3_nii']    = n(cols[3]) if len(cols)>3 else None
                elif 'retail' in label or 'rii' in label:
                    data['sub_day1_retail'] = n(cols[1]) if len(cols)>1 else None
                    data['sub_day2_retail'] = n(cols[2]) if len(cols)>2 else None
                    data['sub_day3_retail'] = n(cols[3]) if len(cols)>3 else None
            break

    # ── Anchor investor names ─────────────────────────────────────────────────
    anchor_section = None
    for section in soup.find_all(['div','section','table']):
        text = section.get_text().lower()
        if 'anchor investor' in text and len(text) > 100:
            anchor_section = section
            break
    
    if anchor_section:
        anchor_names = []
        for row in anchor_section.find_all('tr')[1:]:
            cols = row.find_all(['td','th'])
            if cols:
                name = cols[0].get_text(strip=True)
                if name and len(name) > 3 and name.lower() not in ('anchor investor','name','sl.no.','#'):
                    anchor_names.append(name)
        
        if anchor_names:
            data['anchor_names']        = json.dumps(anchor_names[:30])
            data['anchor_count']        = len(anchor_names)
            data['anchor_tier1_count']  = sum(1 for n in anchor_names if any(t in n.lower() for t in TIER1))

    # ── Post-listing returns ──────────────────────────────────────────────────
    for table in soup.find_all('table'):
        text = table.get_text().lower()
        if ('1 month' in text or '1 week' in text or '6 month' in text) and 'return' in text:
            rows = table.find_all('tr')
            for row in rows:
                cols = [c.get_text(strip=True) for c in row.find_all(['td','th'])]
                if len(cols) >= 2:
                    label = cols[0].lower()
                    if '1 week' in label or '7 day' in label:
                        data['return_day7']   = n(cols[1])
                    elif '1 month' in label or '30 day' in label:
                        data['return_day30']  = n(cols[1])
                    elif '3 month' in label or '90 day' in label:
                        data['return_day90']  = n(cols[1])
                    elif '6 month' in label or '180 day' in label:
                        data['return_day180'] = n(cols[1])
                    elif '1 year' in label or '365 day' in label:
                        data['return_day365'] = n(cols[1])
            break

    return data

def ensure_columns(conn):
    cols = [
        ("gmp_history","JSONB"), ("gmp_pct_t1","NUMERIC"),
        ("gmp_max_pct","NUMERIC"), ("gmp_min_pct","NUMERIC"),
        ("sub_day1_qib","NUMERIC"), ("sub_day2_qib","NUMERIC"), ("sub_day3_qib","NUMERIC"),
        ("sub_day1_nii","NUMERIC"), ("sub_day2_nii","NUMERIC"), ("sub_day3_nii","NUMERIC"),
        ("sub_day1_retail","NUMERIC"), ("sub_day2_retail","NUMERIC"), ("sub_day3_retail","NUMERIC"),
        ("qib_backloaded","BOOLEAN"),
        ("anchor_names","JSONB"), ("anchor_count","INTEGER"), ("anchor_tier1_count","INTEGER"),
        ("return_day7","NUMERIC"), ("return_day30","NUMERIC"), ("return_day90","NUMERIC"),
        ("return_day180","NUMERIC"), ("return_day365","NUMERIC"),
    ]
    cur = conn.cursor()
    for col, typ in cols:
        try:
            cur.execute(f"ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS {col} {typ}")
            conn.commit()
        except: conn.rollback()
    cur.close()

def save_to_db(conn, company_name: str, data: dict):
    if not data: return False
    cur = conn.cursor()
    
    # Compute QIB backloaded flag
    d1 = data.get('sub_day1_qib') or 0
    d3 = data.get('sub_day3_qib') or 0
    if d1 > 0 and d3 > d1 * 2:
        data['qib_backloaded'] = True
    
    cols = list(data.keys())
    vals = [data[c] for c in cols]
    set_clause = ', '.join([f"{c} = %s" for c in cols])
    cur.execute(f"UPDATE ipo_intelligence SET {set_clause} WHERE company_name = %s",
                vals + [company_name])
    conn.commit()
    cur.close()
    return cur.rowcount > 0 or True

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit",   type=int, default=50)
    p.add_argument("--year",    type=int)
    p.add_argument("--company", help="Specific company name")
    p.add_argument("--delay",   type=float, default=2.0, help="Delay between requests")
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    conn = get_db()
    ensure_columns(conn)
    log.info("Connected to Neon DB")

    session = requests.Session()
    session.headers.update(HEADERS)

    # Get IPO list
    if args.company:
        ipos = [{'company_name': args.company, 'nse_symbol': ''}]
    else:
        ipos = get_ipo_list(session if False else get_db(), args.year, args.limit)
        # Re-get with fresh connection
        conn2 = get_db()
        cur2 = conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        q = "SELECT id, company_name, nse_symbol, listing_date FROM ipo_intelligence WHERE gmp_pct_t1 IS NULL AND listing_date IS NOT NULL"
        params = []
        if args.year:
            q += " AND EXTRACT(YEAR FROM listing_date) = %s"
            params.append(args.year)
        q += " ORDER BY listing_date DESC LIMIT %s"
        params.append(args.limit)
        cur2.execute(q, params)
        ipos = [dict(r) for r in cur2.fetchall()]
        conn2.close()

    log.info(f"Scraping {len(ipos)} IPOs from Chittorgarh")
    log.info("=" * 60)

    ok = 0; skipped = 0
    for i, ipo in enumerate(ipos):
        company = ipo['company_name']
        log.info(f"  [{i+1}/{len(ipos)}] {company[:50]}")
        
        try:
            data = scrape_ipo_page(session, company)
            if data:
                save_to_db(conn, company, data)
                fields = [k for k, v in data.items() if v is not None]
                log.info(f"    ✓ {len(fields)} fields: {', '.join(fields[:5])}")
                ok += 1
            else:
                log.info(f"    ✗ No data found")
                skipped += 1
        except Exception as e:
            log.warning(f"    ✗ Error: {e}")
            skipped += 1
        
        time.sleep(args.delay)

    conn.close()
    log.info("=" * 60)
    log.info(f"Done. {ok} scraped, {skipped} skipped")

if __name__ == "__main__":
    main()
