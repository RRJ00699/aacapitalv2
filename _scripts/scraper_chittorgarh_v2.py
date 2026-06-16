"""
AACapital -- Chittorgarh Scraper V2
Fills: qib_x, nii_x, retail_x, gmp, brlm, issue_price, ofs_pct, sector, listing_date
Runs overnight -- 2-3 sec per IPO, ~330 IPOs = ~15-20 min total
"""

import os, re, time, random, logging
import requests
from bs4 import BeautifulSoup
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL", "")
os.makedirs("_scripts/logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler("_scripts/logs/scraper.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger()

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.chittorgarh.com/",
})

def get(url):
    for i in range(3):
        try:
            r = S.get(url, timeout=20)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            time.sleep(10 * (i+1))
        except Exception as e:
            log.warning(f"Retry {i+1}: {e}")
            time.sleep(5 * (i+1))
    return None

def find_val(soup, *labels):
    for row in soup.find_all("tr"):
        cells = row.find_all(["th","td"])
        if len(cells) >= 2:
            label = cells[0].get_text(" ", strip=True).lower()
            if any(l in label for l in labels):
                return cells[1].get_text(" ", strip=True)
    return ""

def num(text):
    if not text: return None
    text = str(text).replace(",","").replace("₹","").replace("%","").strip()
    m = re.search(r"[-+]?\d+\.?\d*", text)
    return float(m.group()) if m else None

def to_slug(name):
    s = name.lower()
    for w in ["limited","ltd","private","pvt","and","&","industries","technology",
               "solutions","services","india","international"]:
        s = re.sub(r"\b"+w+r"\.?\b", "", s)
    s = re.sub(r"[^a-z0-9\s]", "", s).strip()
    s = re.sub(r"\s+", "-", s).strip("-")
    return f"{s}-ipo"

MANUAL = {
    "Angel Broking": "angel-one-ipo",
    "Burger King": "restaurant-brands-asia-ipo",
    "Easy Trip Planners": "easemytrip-ipo",
    "FSN E-Commerce Ventures (Nykaa)": "nykaa-ipo",
    "Global Health (Medanta)": "medanta-ipo",
    "Go Fashion (India)": "go-fashion-india-ipo",
    "Lodha Macrotech Developers": "macrotech-developers-ipo",
    "Sona BLW Precisions": "sona-blw-precision-forgings-ipo",
    "CAMS": "cams-ipo",
    "CE Infosystems": "cartrade-tech-ipo",
    "One 97": "paytm-ipo",
}

def scrape(slug):
    url = f"https://www.chittorgarh.com/ipo/{slug}/"
    soup = get(url)
    if not soup: return {}

    d = {}
    def s(key, *labels):
        v = find_val(soup, *labels)
        if v: d[key] = v

    s("price_band_raw",    "price band", "issue price")
    s("lot_size_raw",      "lot size")
    s("issue_size_raw",    "issue size", "ipo size")
    s("fresh_issue_raw",   "fresh issue")
    s("ofs_raw",           "offer for sale", "ofs")
    s("brlm_raw",          "lead manager", "book running", "brlm")
    s("sector_raw",        "industry", "sector")
    s("open_date_raw",     "open date", "issue open")
    s("close_date_raw",    "close date", "issue close")
    s("listing_date_raw",  "listing date")
    s("listing_price_raw", "listing price", "listing at")
    s("listing_gain_raw",  "listing gain", "listing return")
    s("qib_raw",           "qib subscription", "qib")
    s("nii_raw",           "nii subscription", "nii", "hnii")
    s("retail_raw",        "retail subscription", "retail", "rii")
    s("total_raw",         "total subscription", "total")
    s("gmp_raw",           "grey market", "gmp")
    s("pe_raw",            "p/e", "pe ratio", "price earning")
    return d

def parse_and_upsert(conn, company, raw):
    if not raw: return

    def pn(key): return num(raw.get(key,""))

    price_high = pn("price_band_raw")
    issue_cr   = pn("issue_size_raw")
    fresh_cr   = pn("fresh_issue_raw")
    ofs_cr     = pn("ofs_raw")
    ofs_pct    = round(ofs_cr/issue_cr*100,1) if ofs_cr and issue_cr and issue_cr>0 else None

    qib   = pn("qib_raw")
    nii   = pn("nii_raw")
    retail= pn("retail_raw")
    total = pn("total_raw")
    gmp   = pn("gmp_raw")
    gmp_pct = round(gmp/price_high*100,1) if gmp and price_high and price_high>0 else None
    pe    = pn("pe_raw")

    brlm  = raw.get("brlm_raw","").strip() or None
    sector= raw.get("sector_raw","").strip() or None

    # Parse listing date
    from datetime import datetime
    listing_date = None
    for fmt in ["%d %B %Y","%d-%b-%Y","%B %d, %Y","%d/%m/%Y"]:
        try:
            listing_date = datetime.strptime(raw.get("listing_date_raw","").strip(), fmt).date()
            break
        except: pass

    # Listing gain
    lg_text = raw.get("listing_gain_raw","") or raw.get("listing_price_raw","")
    listing_gain = pn("listing_gain_raw")

    fields = {
        "issue_price":          price_high,
        "issue_size_cr":        issue_cr,
        "fresh_issue_cr":       fresh_cr,
        "ofs_cr":               ofs_cr,
        "ofs_pct":              ofs_pct,
        "qib_subscription_x":  qib,
        "nii_subscription_x":  nii,
        "rii_subscription_x":  retail,
        "total_subscription_x":total,
        "gmp_value":            gmp,
        "gmp_percentage":       gmp_pct,
        "ipo_pe":               pe,
        "brlm_names":           brlm,
        "sector":               sector,
        "listing_date":         listing_date,
        "listing_gap_pct":      listing_gain,
    }
    fields = {k:v for k,v in fields.items() if v is not None}
    if not fields: return

    set_parts = ", ".join(f"{k}=COALESCE(ipo_intelligence.{k},%s)" for k in fields)
    cur = conn.cursor()
    cur.execute(
        f"UPDATE ipo_intelligence SET {set_parts}, updated_at=NOW() WHERE company_name=%s",
        list(fields.values()) + [company]
    )
    conn.commit()
    log.info(f"  OK: {company} ({len(fields)} fields)")

def main():
    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); return
    conn = psycopg2.connect(DATABASE_URL)

    cur = conn.cursor()
    cur.execute("SELECT company_name FROM ipo_intelligence ORDER BY company_name")
    companies = [r[0] for r in cur.fetchall()]
    log.info(f"Companies to scrape: {len(companies)}")

    # Warm up session
    S.get("https://www.chittorgarh.com/", timeout=15)
    time.sleep(2)

    ok = fail = 0
    for i, company in enumerate(companies, 1):
        log.info(f"[{i}/{len(companies)}] {company}")
        slug = MANUAL.get(company) or to_slug(company)
        raw = scrape(slug)
        if raw:
            parse_and_upsert(conn, company, raw)
            ok += 1
        else:
            log.warning(f"  FAIL: {company}")
            fail += 1
        time.sleep(random.uniform(2.5, 4.0))

    log.info(f"\nDone -- OK:{ok} FAIL:{fail}")

    cur.execute("""
        SELECT COUNT(*), COUNT(qib_subscription_x), COUNT(gmp_percentage),
               COUNT(brlm_names), COUNT(listing_date), COUNT(ipo_pe)
        FROM ipo_intelligence
    """)
    r = cur.fetchone()
    log.info(f"Coverage -- total:{r[0]} qib:{r[1]} gmp:{r[2]} brlm:{r[3]} dates:{r[4]} pe:{r[5]}")
    conn.close()

if __name__ == "__main__":
    main()
