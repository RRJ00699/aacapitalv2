"""
AACapital -- GMP Scraper V2
Source: ipowatch.in
Fills: gmp_pct_t1, gmp_pct_t3, gmp_pct_t5, gmp_pct_t7, gmp_pct_t10,
       gmp_velocity, gmp_momentum, gmp_breakdown_flag
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
        logging.FileHandler("_scripts/logs/gmp_scraper.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger()

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://ipowatch.in/",
})

def get(url):
    for i in range(3):
        try:
            r = S.get(url, timeout=20)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            time.sleep(10*(i+1))
        except Exception as e:
            log.warning(f"Retry {i+1}: {e}")
            time.sleep(5*(i+1))
    return None

def to_slug(name):
    s = name.lower()
    for w in ["limited","ltd","private","pvt","and","&"]:
        s = re.sub(r"\b"+w+r"\.?\b","",s)
    s = re.sub(r"[^a-z0-9\s]","",s).strip()
    s = re.sub(r"\s+","-",s).strip("-")
    return f"{s}-ipo-gmp"

def scrape_gmp(company):
    slug = to_slug(company)
    for url in [
        f"https://ipowatch.in/{slug}/",
        f"https://ipowatch.in/{slug.replace('-ipo-gmp','-grey-market-premium')}/",
        f"https://ipowatch.in/{slug.replace('-ipo-gmp','')}/",
    ]:
        soup = get(url)
        time.sleep(random.uniform(1.5, 3.0))
        if not soup: continue

        series = []
        for table in soup.find_all("table"):
            hdrs = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if any(k in " ".join(hdrs) for k in ["gmp","grey","premium","date"]):
                for row in table.find_all("tr")[1:]:
                    cells = [td.get_text(strip=True) for td in row.find_all("td")]
                    for cell in cells[1:2]:  # usually col 1 is GMP value
                        m = re.search(r"[-+]?\d+\.?\d*", cell.replace(",",""))
                        if m:
                            try:
                                v = float(m.group())
                                if -500 < v < 5000:
                                    series.append(v)
                            except: pass
        if series:
            series.reverse()  # oldest first
            log.info(f"  GMP series ({len(series)} points): {series[-3:]}")
            return series
    return []

def derive_signals(series, issue_price):
    if not series or len(series) < 2: return {}
    n = len(series)
    ip = issue_price if issue_price and issue_price > 0 else 1
    latest = series[-1]
    result = {}

    # t-x columns
    for col, idx in [("gmp_pct_t1",-1),("gmp_pct_t3",-3),("gmp_pct_t5",-5),("gmp_pct_t7",-7),("gmp_pct_t10",-10)]:
        if abs(idx) <= n:
            result[col] = round(series[idx]/ip*100, 2)

    result["gmp_value"]      = latest
    result["gmp_percentage"] = round(latest/ip*100, 2)

    if len(series) >= 3:
        result["gmp_velocity"] = round(series[-1]-series[-3], 2)

    peak = max(series)
    if latest > series[0]*1.05:   result["gmp_momentum"] = "RISING"
    elif latest < series[0]*0.95: result["gmp_momentum"] = "FALLING"
    else:                          result["gmp_momentum"] = "STABLE"

    result["gmp_breakdown_flag"] = bool(peak > 0 and latest < peak*0.70)
    return result

def main():
    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
        SELECT company_name, issue_price, gmp_percentage
        FROM ipo_intelligence
        WHERE gmp_pct_t1 IS NULL
        ORDER BY company_name
    """)
    rows = cur.fetchall()
    log.info(f"IPOs needing GMP data: {len(rows)}")

    S.get("https://ipowatch.in/", timeout=15)
    time.sleep(2)

    ok = fail = 0
    for i, (company, issue_price, existing_gmp) in enumerate(rows, 1):
        log.info(f"[{i}/{len(rows)}] {company}")
        ip = float(issue_price) if issue_price else 0

        series = scrape_gmp(company)
        if series:
            signals = derive_signals(series, ip)
            ok += 1
        elif existing_gmp:
            # Synthetic from existing snapshot
            signals = {
                "gmp_pct_t1": float(existing_gmp),
                "gmp_momentum": "STABLE",
                "gmp_velocity": 0,
                "gmp_breakdown_flag": False,
            }
            log.info(f"  Using synthetic GMP for {company}")
        else:
            fail += 1
            time.sleep(random.uniform(2, 3))
            continue

        cols = list(signals.keys())
        vals = list(signals.values())
        set_parts = ", ".join(f"{c}=COALESCE(ipo_intelligence.{c},%s)" for c in cols)
        cur.execute(
            f"UPDATE ipo_intelligence SET {set_parts}, updated_at=NOW() WHERE company_name=%s",
            vals + [company]
        )
        conn.commit()
        time.sleep(random.uniform(2.5, 4.0))

    log.info(f"\nDone -- scraped:{ok} synthetic:_ failed:{fail}")
    cur.execute("SELECT COUNT(*), COUNT(gmp_pct_t1), COUNT(gmp_momentum) FROM ipo_intelligence")
    r = cur.fetchone()
    log.info(f"GMP coverage -- total:{r[0]} t1:{r[1]} momentum:{r[2]}")
    conn.close()

if __name__ == "__main__":
    main()
