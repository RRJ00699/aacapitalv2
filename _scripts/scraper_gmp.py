"""
AACapital — IPO GMP History Scraper V1
Source: ipowatch.in  (primary)  +  chittorgarh.com/ipo/{slug}/gmp/  (fallback)
Fills:  gmp_pct_t1, gmp_pct_t3, gmp_pct_t5, gmp_pct_t7, gmp_pct_t10,
        gmp_velocity, gmp_momentum, gmp_breakdown_flag, gmp_volatility
Writes to: Neon ipo_intelligence table (upsert by company_name)

Run:  python _scripts/scraper_gmp.py
"""

import os
import re
import time
import logging
import random
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
import psycopg2
import pandas as pd

# ─── Config ──────────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SLEEP_MIN = 2.5
SLEEP_MAX = 5.0
LOG_FILE = "_scripts/logs/gmp_scrape.log"
os.makedirs("_scripts/logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("gmp_scraper")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://ipowatch.in/",
}

session = requests.Session()
session.headers.update(HEADERS)


def sleep_politely():
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))


def get_page(url: str) -> Optional[BeautifulSoup]:
    for attempt in range(1, 4):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            elif r.status_code == 429:
                time.sleep(30 * attempt)
            elif r.status_code == 403:
                time.sleep(15 * attempt)
            else:
                log.warning(f"HTTP {r.status_code}: {url}")
        except requests.RequestException as e:
            log.error(f"Error ({attempt}): {e}")
            time.sleep(5 * attempt)
    return None


# ─── GMP Analysis ─────────────────────────────────────────────────────────────

def derive_gmp_signals(gmp_series: list[float], issue_price: float) -> dict:
    """
    Given a time-series of GMP values [oldest→newest] and issue price,
    compute velocity, direction, volatility, breakdown flag.
    
    gmp_series: e.g. [50, 55, 60, 70, 80]  (t-10 to t-1, oldest first)
    """
    if not gmp_series or len(gmp_series) < 2:
        return {}

    result = {}

    # Latest GMP
    latest = gmp_series[-1]
    earliest = gmp_series[0]

    # GMP as % of issue price
    if issue_price and issue_price > 0:
        result["gmp_percentage"] = round(latest / issue_price * 100, 2)
        result["gmp_pct_of_issue"] = result["gmp_percentage"]

    # Velocity = change over last 3 days
    if len(gmp_series) >= 3:
        velocity = gmp_series[-1] - gmp_series[-3]
        result["gmp_velocity"] = round(velocity, 2)

    # Overall direction
    if latest > earliest * 1.05:
        result["gmp_momentum"] = "RISING"
    elif latest < earliest * 0.95:
        result["gmp_momentum"] = "FALLING"
    else:
        result["gmp_momentum"] = "STABLE"

    # Volatility = max deviation from mean
    mean = sum(gmp_series) / len(gmp_series)
    if mean != 0:
        deviations = [abs(v - mean) / abs(mean) * 100 for v in gmp_series]
        result["gmp_volatility"] = round(max(deviations), 2)

    # Breakdown flag: GMP fell >30% from peak
    peak = max(gmp_series)
    if peak > 0 and latest < peak * 0.70:
        result["gmp_breakdown_flag"] = True
    else:
        result["gmp_breakdown_flag"] = False

    # Map to t-x columns
    n = len(gmp_series)
    issue_p = issue_price if issue_price and issue_price > 0 else 1

    # t-1 = most recent, t-10 = oldest
    # Series is [oldest...newest], so index -1 is t-1
    mapping = {
        "gmp_pct_t1": -1,
        "gmp_pct_t3": -3,
        "gmp_pct_t5": -5,
        "gmp_pct_t7": -7,
        "gmp_pct_t10": -10,
    }
    for col, idx in mapping.items():
        if abs(idx) <= n:
            val = gmp_series[idx]
            result[col] = round(val / issue_p * 100, 2) if issue_p else val

    return result


# ─── Source 1: ipowatch.in ────────────────────────────────────────────────────

def company_to_ipowatch_slug(company_name: str) -> list[str]:
    """Generate ipowatch slug candidates."""
    name = company_name.lower().strip()
    name = re.sub(r"\b(limited|ltd\.?|private|pvt\.?|and|&|co\.?|india|group)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    slug_base = re.sub(r"[^a-z0-9\s]", "", name).strip()
    slug_base = re.sub(r"\s+", "-", slug_base).strip("-")

    return [
        f"{slug_base}-ipo-gmp",
        f"{slug_base}-grey-market-premium",
        f"{slug_base}-ipo",
    ]


def scrape_ipowatch_gmp(company_name: str, issue_price: float = 0) -> dict:
    """
    Try to scrape GMP history from ipowatch.in
    URL pattern: https://ipowatch.in/{slug}/
    """
    session.headers.update({"Referer": "https://ipowatch.in/"})
    candidates = company_to_ipowatch_slug(company_name)

    for slug in candidates:
        url = f"https://ipowatch.in/{slug}/"
        soup = get_page(url)
        sleep_politely()

        if not soup:
            continue

        # Look for GMP table
        tables = soup.find_all("table")
        gmp_series = []

        for table in tables:
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if any(kw in " ".join(headers) for kw in ["gmp", "grey", "premium", "date"]):
                rows = table.find_all("tr")[1:]
                for row in rows:
                    cells = [td.get_text(strip=True) for td in row.find_all("td")]
                    if len(cells) >= 2:
                        # Usually: Date | GMP | Expected Price | Expected Gain
                        gmp_cell = cells[1] if len(cells) > 1 else cells[0]
                        m = re.search(r"([+-]?[\d.]+)", gmp_cell.replace(",", ""))
                        if m:
                            try:
                                gmp_series.append(float(m.group(1)))
                            except ValueError:
                                pass

        if gmp_series:
            log.info(f"  ✓ ipowatch: {len(gmp_series)} GMP points for {company_name}")
            # Reverse so oldest first
            gmp_series.reverse()
            return derive_gmp_signals(gmp_series, issue_price)

    return {}


# ─── Source 2: chittorgarh GMP subpage ────────────────────────────────────────

def scrape_chittorgarh_gmp(slug: str, issue_price: float = 0) -> dict:
    """
    Chittorgarh has a /gmp/ subpage for each IPO.
    URL: https://www.chittorgarh.com/ipo/{slug}/gmp/
    """
    session.headers.update({"Referer": "https://www.chittorgarh.com/"})
    url = f"https://www.chittorgarh.com/ipo/{slug}/gmp/"
    soup = get_page(url)
    sleep_politely()

    if not soup:
        return {}

    gmp_series = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            for cell in cells:
                m = re.search(r"([+-]?[\d.]+)", cell.replace(",", ""))
                if m:
                    try:
                        val = float(m.group(1))
                        if 0 < val < 5000:   # sanity: GMP won't be 5000+
                            gmp_series.append(val)
                            break
                    except ValueError:
                        pass

    if gmp_series:
        log.info(f"  ✓ Chittorgarh GMP: {len(gmp_series)} points for {slug}")
        gmp_series.reverse()
        return derive_gmp_signals(gmp_series, issue_price)

    return {}


# ─── Source 3: GMP from main ipo_intelligence row (existing gmp_percentage) ──

def compute_synthetic_gmp(gmp_pct_of_issue: float) -> dict:
    """
    If we only have a single GMP snapshot (from existing data),
    synthesize a minimal signal. Not ideal but better than nothing.
    """
    if not gmp_pct_of_issue:
        return {}
    return {
        "gmp_pct_t1": gmp_pct_of_issue,
        "gmp_pct_t3": gmp_pct_of_issue,
        "gmp_momentum": "STABLE",
        "gmp_velocity": 0,
        "gmp_breakdown_flag": False,
    }


# ─── Neon upsert ──────────────────────────────────────────────────────────────

def upsert_gmp_to_neon(conn, company_name: str, data: dict):
    allowed_cols = {
        "gmp_pct_t1", "gmp_pct_t3", "gmp_pct_t5", "gmp_pct_t7", "gmp_pct_t10",
        "gmp_value", "gmp_percentage", "gmp_pct_of_issue",
        "gmp_velocity", "gmp_momentum", "gmp_volatility", "gmp_breakdown_flag",
    }
    filtered = {k: v for k, v in data.items() if k in allowed_cols and v is not None}
    if not filtered:
        return

    set_clause = ", ".join([f"{c} = EXCLUDED.{c}" for c in filtered])
    cols = list(filtered.keys())
    vals = [filtered[c] for c in cols]

    sql = f"""
        INSERT INTO ipo_intelligence (company_name, {", ".join(cols)}, updated_at)
        VALUES (%s, {", ".join(["%s"] * len(cols))}, NOW())
        ON CONFLICT (company_name)
        DO UPDATE SET {set_clause}, updated_at = NOW()
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, [company_name] + vals)
        conn.commit()
        log.info(f"  ✓ GMP upsert OK for {company_name}")
    except Exception as e:
        conn.rollback()
        log.error(f"  ✗ GMP upsert failed for {company_name}: {e}")


# ─── Load chittorgarh slugs from results file ─────────────────────────────────

def load_slug_map() -> dict:
    """Load company→slug mapping from chittorgarh results if available."""
    result_file = "_scripts/logs/chittorgarh_results.xlsx"
    if not os.path.exists(result_file):
        return {}
    df = pd.read_excel(result_file)
    if "company_name" in df.columns and "slug" in df.columns:
        return dict(zip(df["company_name"], df["slug"].fillna("")))
    return {}


def load_companies_with_prices() -> list[dict]:
    """Load company list with existing issue_price from Neon or Excel."""
    db_url = DATABASE_URL
    if db_url:
        try:
            conn = psycopg2.connect(db_url)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT company_name, issue_price, gmp_pct_of_issue, gmp_percentage
                    FROM ipo_intelligence
                    ORDER BY company_name
                """)
                rows = cur.fetchall()
            conn.close()
            return [
                {
                    "company_name": r[0],
                    "issue_price": r[1] or 0,
                    "gmp_pct_of_issue": r[2] or r[3] or 0,
                }
                for r in rows
            ]
        except Exception as e:
            log.error(f"Neon query failed: {e}")

    # Fallback: Excel
    xlsx = os.environ.get("IPO_EXCEL", "aacapital_ipo_master_304.xlsx")
    if os.path.exists(xlsx):
        df = pd.read_excel(xlsx)
        return df[["company_name", "gmp_pct_of_issue"]].to_dict("records")

    return []


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("AACapital — GMP History Scraper")
    log.info("=" * 60)

    db_url = DATABASE_URL
    if not db_url:
        log.error("DATABASE_URL not set.")
        return

    try:
        conn = psycopg2.connect(db_url)
        log.info("✓ Connected to Neon")
    except Exception as e:
        log.error(f"DB connection failed: {e}")
        return

    companies = load_companies_with_prices()
    slug_map = load_slug_map()
    log.info(f"Companies: {len(companies)} | Slug map: {len(slug_map)}")

    stats = {"ipowatch": 0, "chittorgarh": 0, "synthetic": 0, "failed": 0}

    # Warm up
    session.get("https://ipowatch.in/", timeout=15)
    sleep_politely()

    for i, row in enumerate(companies, 1):
        company = row["company_name"]
        issue_price = float(row.get("issue_price") or 0)
        existing_gmp = float(row.get("gmp_pct_of_issue") or 0)

        log.info(f"\n[{i}/{len(companies)}] {company} (₹{issue_price})")

        try:
            # Try ipowatch first
            data = scrape_ipowatch_gmp(company, issue_price)
            if data:
                stats["ipowatch"] += 1
                upsert_gmp_to_neon(conn, company, data)
                sleep_politely()
                continue

            # Try chittorgarh GMP subpage
            slug = slug_map.get(company, "")
            if slug:
                data = scrape_chittorgarh_gmp(slug, issue_price)
                if data:
                    stats["chittorgarh"] += 1
                    upsert_gmp_to_neon(conn, company, data)
                    sleep_politely()
                    continue

            # Synthetic fallback from existing snapshot
            if existing_gmp:
                data = compute_synthetic_gmp(existing_gmp)
                if data:
                    stats["synthetic"] += 1
                    upsert_gmp_to_neon(conn, company, data)
                    log.info(f"  ⚠ Used synthetic GMP for {company}")
                    sleep_politely()
                    continue

            stats["failed"] += 1
            log.warning(f"  ✗ No GMP data found for {company}")
            sleep_politely()

        except KeyboardInterrupt:
            log.warning("Interrupted. Saving progress …")
            break
        except Exception as e:
            log.error(f"  Error for {company}: {e}")
            stats["failed"] += 1

    log.info("\n" + "=" * 60)
    log.info(f"DONE — ipowatch: {stats['ipowatch']} | chittorgarh: {stats['chittorgarh']} "
             f"| synthetic: {stats['synthetic']} | failed: {stats['failed']}")
    conn.close()


if __name__ == "__main__":
    main()
