"""
AACapital — IPO Master Scraper V1
Source: chittorgarh.com
Fills: issue_price, price_band, lot_size, issue_size_cr, fresh_issue_cr, ofs_cr, ofs_pct,
       promoter_pre/post equity, free_float_pct, brlm_names, brlm_tier,
       listing_price, listing_gain_pct, listing_date, open_date, close_date,
       qib_x, nii_x, retail_x, total_x (final), sector
Writes to: Neon ipo_intelligence table (upsert by company_name)

Run from:  C:\\aacapital-v2>
Command:   python _scripts/scraper_chittorgarh.py
"""

import os
import re
import time
import logging
import random
import json
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
import psycopg2
import psycopg2.extras
import pandas as pd

# ─── Config ──────────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SLEEP_MIN = 2.0      # seconds between requests (be polite)
SLEEP_MAX = 4.5
MAX_RETRIES = 3
LOG_FILE = "_scripts/logs/chittorgarh_scrape.log"

os.makedirs("_scripts/logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("chittorgarh")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# ─── HTTP helpers ─────────────────────────────────────────────────────────────

session = requests.Session()
session.headers.update(HEADERS)


def get_page(url: str, retries: int = MAX_RETRIES) -> Optional[BeautifulSoup]:
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            elif r.status_code == 429:
                wait = 30 * attempt
                log.warning(f"Rate limited on {url}. Waiting {wait}s …")
                time.sleep(wait)
            elif r.status_code == 403:
                log.warning(f"403 on {url} (attempt {attempt}). Waiting …")
                time.sleep(10 * attempt)
            else:
                log.warning(f"HTTP {r.status_code} on {url}")
        except requests.RequestException as e:
            log.error(f"Request error ({attempt}/{retries}): {e}")
            time.sleep(5 * attempt)
    return None


def sleep_politely():
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))


# ─── Parse helpers ────────────────────────────────────────────────────────────

def clean_number(text: str) -> Optional[float]:
    """Extract first float from messy text like '₹850 to ₹900' → 900 (takes last)"""
    if not text:
        return None
    text = text.replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "")
    nums = re.findall(r"[\d]+\.?\d*", text)
    if not nums:
        return None
    try:
        return float(nums[-1])   # take last (upper band)
    except ValueError:
        return None


def clean_number_first(text: str) -> Optional[float]:
    """Take first number — for lower band"""
    if not text:
        return None
    text = text.replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "")
    nums = re.findall(r"[\d]+\.?\d*", text)
    if not nums:
        return None
    try:
        return float(nums[0])
    except ValueError:
        return None


def parse_cr(text: str) -> Optional[float]:
    """Parse crore values — handles lakhs/crores automatically"""
    if not text:
        return None
    text = text.replace(",", "").strip().lower()
    m = re.search(r"([\d.]+)\s*(?:cr|crore)?", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def parse_date(text: str) -> Optional[str]:
    """Parse Indian date formats → YYYY-MM-DD"""
    if not text:
        return None
    text = text.strip()
    formats = [
        "%d %B %Y", "%d-%b-%Y", "%d %b %Y", "%d/%m/%Y",
        "%B %d, %Y", "%b %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def classify_brlm(brlm_names: str) -> str:
    """Tier-1 = Goldman, Kotak, Axis, ICICI, JM, SBI, Morgan, HSBC, Citi, DSP"""
    if not brlm_names:
        return "UNKNOWN"
    tier1 = [
        "goldman", "kotak", "axis", "icici", "jm financial", "sbi", "morgan stanley",
        "hsbc", "citibank", "citi", "dsp", "ubs", "jp morgan", "credit suisse",
        "nomura", "iifl", "motilal", "jefferies",
    ]
    low = brlm_names.lower()
    for bank in tier1:
        if bank in low:
            return "TIER_1"
    return "TIER_2"


# ─── Step 1: Get all past IPO slugs from performance report ──────────────────

def scrape_ipo_listing_report() -> list[dict]:
    """
    Scrape https://www.chittorgarh.com/report/ipo-listing-performance/
    Returns list of {name, slug, listing_gain_pct, listing_price, issue_price, listing_date}
    """
    log.info("Fetching IPO listing performance report …")
    url = "https://www.chittorgarh.com/report/ipo-listing-performance/"
    soup = get_page(url)
    if not soup:
        log.error("Could not fetch listing report")
        return []

    results = []
    table = soup.find("table")
    if not table:
        log.warning("No table found on listing report page")
        return results

    rows = table.find_all("tr")
    headers_row = rows[0].find_all(["th", "td"])
    headers = [h.get_text(strip=True).lower() for h in headers_row]
    log.info(f"Columns found: {headers}")

    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        try:
            # First cell usually has the name + link
            link = cells[0].find("a")
            name = cells[0].get_text(strip=True)
            slug = ""
            if link and link.get("href"):
                href = link["href"]
                # Extract slug from URL like /ipo/ami-organics-ipo/1040/
                m = re.search(r"/ipo/([^/]+)/(\d+)/", href)
                if m:
                    slug = m.group(1)

            row_data = {c: cells[i].get_text(strip=True) if i < len(cells) else ""
                        for i, c in enumerate(headers)}
            row_data["name"] = name
            row_data["slug"] = slug
            results.append(row_data)
        except Exception as e:
            log.debug(f"Row parse error: {e}")

    log.info(f"Found {len(results)} IPOs on listing report")
    return results


# ─── Step 2: Scrape individual IPO page ──────────────────────────────────────

def scrape_ipo_page(slug: str, ipo_id: str = "") -> dict:
    """
    Scrape https://www.chittorgarh.com/ipo/{slug}/{id}/
    Returns dict of all extracted fields for ipo_intelligence upsert.
    """
    url = f"https://www.chittorgarh.com/ipo/{slug}/"
    if ipo_id:
        url = f"https://www.chittorgarh.com/ipo/{slug}/{ipo_id}/"

    soup = get_page(url)
    if not soup:
        return {}

    data = {"source_url_chittorgarh": url}

    # ── Helper: find table row value by label ──
    def find_by_label(label_fragment: str, table_soup=None) -> str:
        target = table_soup or soup
        for row in target.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                if label_fragment.lower() in label:
                    return cells[1].get_text(strip=True)
        return ""

    # ── Price band ──
    price_band = find_by_label("price band")
    if price_band:
        data["price_band_low"] = clean_number_first(price_band)
        data["price_band_high"] = clean_number(price_band)
        data["issue_price"] = data["price_band_high"]  # final = upper band

    # Also check "issue price" directly
    issue_price_raw = find_by_label("issue price")
    if issue_price_raw:
        data["issue_price"] = clean_number(issue_price_raw)

    # ── Lot size ──
    lot_raw = find_by_label("lot size")
    if lot_raw:
        data["lot_size"] = clean_number(lot_raw)

    # ── Issue size ──
    for label in ["issue size", "total issue size", "ipo size"]:
        raw = find_by_label(label)
        if raw:
            data["issue_size_cr"] = parse_cr(raw)
            break

    # ── Fresh issue / OFS ──
    fresh_raw = find_by_label("fresh issue")
    if fresh_raw:
        data["fresh_issue_cr"] = parse_cr(fresh_raw)

    ofs_raw = find_by_label("offer for sale")
    if not ofs_raw:
        ofs_raw = find_by_label("ofs")
    if ofs_raw:
        data["ofs_cr"] = parse_cr(ofs_raw)

    # Calculate OFS %
    if data.get("fresh_issue_cr") and data.get("ofs_cr") and data.get("issue_size_cr"):
        total = data["issue_size_cr"]
        if total and total > 0:
            data["ofs_pct"] = round(data["ofs_cr"] / total * 100, 2)
            data["fresh_issue_ratio"] = round(data["fresh_issue_cr"] / total * 100, 2)

    # ── BRLM ──
    for label in ["lead manager", "book running", "brlm", "merchant banker"]:
        raw = find_by_label(label)
        if raw:
            data["brlm_names"] = raw
            data["brlm_tier"] = classify_brlm(raw)
            break

    # ── Registrar ──
    registrar_raw = find_by_label("registrar")
    if registrar_raw:
        data["registrar"] = registrar_raw

    # ── Dates ──
    for label, key in [
        ("open date", "open_date"),
        ("close date", "close_date"),
        ("listing date", "listing_date"),
        ("allotment", "allotment_date"),
    ]:
        raw = find_by_label(label)
        if raw:
            parsed = parse_date(raw)
            if parsed:
                data[key] = parsed
            else:
                data[key] = raw  # keep raw if parse fails

    # ── Sector ──
    for label in ["industry", "sector"]:
        raw = find_by_label(label)
        if raw:
            data["sector"] = raw
            break

    # ── Promoter holding ──
    pre_raw = find_by_label("pre issue")
    if pre_raw:
        data["promoter_pre_equity"] = clean_number(pre_raw)

    post_raw = find_by_label("post issue")
    if post_raw:
        data["promoter_post_equity"] = clean_number(post_raw)

    if data.get("promoter_pre_equity") and data.get("promoter_post_equity"):
        data["promoter_dilution_pct"] = round(
            data["promoter_pre_equity"] - data["promoter_post_equity"], 2
        )

    # ── Subscription (final) ──
    for label, key in [
        ("qib", "qib_subscription_x"),
        ("nii", "nii_subscription_x"),
        ("hnii", "nii_subscription_x"),
        ("retail", "rii_subscription_x"),
        ("employee", "employee_sub_x"),
        ("total", "total_subscription_x"),
    ]:
        raw = find_by_label(label + " subscription")
        if not raw:
            raw = find_by_label(label)
        if raw:
            val = clean_number(raw.replace("x", "").replace("X", "").strip())
            if val and key not in data:
                data[key] = val

    # ── Listing performance ──
    listing_price_raw = find_by_label("listing price")
    if not listing_price_raw:
        listing_price_raw = find_by_label("listing at")
    if listing_price_raw:
        data["listing_price"] = clean_number(listing_price_raw)

    listing_gain_raw = find_by_label("listing gain")
    if not listing_gain_raw:
        listing_gain_raw = find_by_label("return")
    if listing_gain_raw:
        gain_match = re.search(r"([+-]?[\d.]+)\s*%", listing_gain_raw)
        if gain_match:
            data["listing_gap_pct"] = float(gain_match.group(1))

    # Calculate listing gain if we have prices
    if data.get("listing_price") and data.get("issue_price") and not data.get("listing_gap_pct"):
        ip = data["issue_price"]
        lp = data["listing_price"]
        if ip and ip > 0:
            data["listing_gap_pct"] = round((lp - ip) / ip * 100, 2)

    # ── GMP (current) ──
    gmp_raw = find_by_label("gmp")
    if not gmp_raw:
        gmp_raw = find_by_label("grey market")
    if gmp_raw:
        gmp_val = clean_number(gmp_raw)
        if gmp_val is not None:
            data["gmp_value"] = gmp_val
            if data.get("issue_price") and data["issue_price"] > 0:
                data["gmp_percentage"] = round(gmp_val / data["issue_price"] * 100, 2)

    # ── PE ratio ──
    pe_raw = find_by_label("p/e")
    if not pe_raw:
        pe_raw = find_by_label("pe ratio")
    if pe_raw:
        data["ipo_pe"] = clean_number(pe_raw)

    return data


# ─── Step 3: Slug generator for 304 companies ─────────────────────────────────

def company_to_slug(company_name: str) -> list[str]:
    """
    Generate likely chittorgarh URL slugs for a company name.
    chittorgarh slugs follow pattern: company-name-ipo
    """
    name = company_name.lower().strip()
    # Remove Ltd, Limited, Private, Pvt, Industries, etc. for cleaner slug
    name = re.sub(r"\b(limited|ltd\.?|private|pvt\.?|and|&)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    # Replace spaces and special chars with hyphens
    slug_base = re.sub(r"[^a-z0-9\s]", "", name).strip()
    slug_base = re.sub(r"\s+", "-", slug_base)
    # Remove trailing hyphens
    slug_base = slug_base.strip("-")

    # Try variants
    candidates = [
        f"{slug_base}-ipo",
        f"{slug_base}-limited-ipo",
        f"{slug_base}-ltd-ipo",
        slug_base,
    ]
    return candidates


# ─── Step 4: Search for IPO page by trying slug candidates ────────────────────

def find_ipo_slug(company_name: str, known_slugs: dict = {}) -> Optional[str]:
    """
    Try to find the correct chittorgarh slug for a company.
    First checks known_slugs dict, then tries guessing.
    """
    if company_name in known_slugs:
        return known_slugs[company_name]

    candidates = company_to_slug(company_name)
    for slug in candidates:
        url = f"https://www.chittorgarh.com/ipo/{slug}/"
        try:
            r = session.head(url, timeout=10, allow_redirects=True)
            if r.status_code == 200:
                log.info(f"  ✓ Found slug: {slug} for {company_name}")
                return slug
            sleep_politely()
        except Exception:
            pass

    # Try search as fallback
    search_url = f"https://www.chittorgarh.com/search/?q={requests.utils.quote(company_name)}"
    soup = get_page(search_url)
    if soup:
        for link in soup.find_all("a", href=True):
            href = link["href"]
            m = re.search(r"/ipo/([^/]+)/(\d+)/", href)
            if m:
                slug = m.group(1)
                log.info(f"  ✓ Found via search: {slug} for {company_name}")
                return slug

    log.warning(f"  ✗ Could not find slug for: {company_name}")
    return None


# ─── Step 5: Write to Neon ────────────────────────────────────────────────────

def upsert_to_neon(conn, company_name: str, data: dict):
    """Upsert scraped data into ipo_intelligence table."""
    if not data:
        return

    # Map scraped keys to DB columns
    allowed_cols = {
        "issue_price", "price_band_low", "price_band_high", "lot_size",
        "issue_size_cr", "fresh_issue_cr", "ofs_cr", "ofs_pct", "fresh_issue_ratio",
        "promoter_pre_equity", "promoter_post_equity", "promoter_dilution_pct",
        "brlm_names", "brlm_tier",
        "open_date", "close_date", "listing_date",
        "sector", "registrar",
        "qib_subscription_x", "nii_subscription_x", "rii_subscription_x",
        "total_subscription_x", "employee_sub_x",
        "listing_price", "listing_gap_pct",
        "gmp_value", "gmp_percentage",
        "ipo_pe", "data_source",
    }

    filtered = {k: v for k, v in data.items() if k in allowed_cols and v is not None}
    filtered["data_source"] = "chittorgarh"
    filtered["updated_at"] = datetime.utcnow()
    filtered["enrichment_status"] = "CHITTORGARH_DONE"

    if not filtered:
        return

    cols = list(filtered.keys())
    vals = [filtered[c] for c in cols]

    set_clause = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols if c != "company_name"])

    sql = f"""
        INSERT INTO ipo_intelligence (company_name, {", ".join(cols)})
        VALUES (%s, {", ".join(["%s"] * len(cols))})
        ON CONFLICT (company_name)
        DO UPDATE SET {set_clause}, updated_at = NOW()
    """

    try:
        with conn.cursor() as cur:
            cur.execute(sql, [company_name] + vals)
        conn.commit()
        log.info(f"  ✓ Neon upsert OK for {company_name} ({len(filtered)} fields)")
    except Exception as e:
        conn.rollback()
        log.error(f"  ✗ Neon upsert failed for {company_name}: {e}")


# ─── Main orchestration ───────────────────────────────────────────────────────

def load_companies() -> list[str]:
    """Load company list from Excel or environment."""
    xlsx_path = os.environ.get("IPO_EXCEL", "aacapital_ipo_master_304.xlsx")
    if os.path.exists(xlsx_path):
        df = pd.read_excel(xlsx_path)
        return df["company_name"].dropna().tolist()
    # Fallback: query Neon
    return []


def load_known_slugs() -> dict:
    """
    Manual override for companies with unusual slug patterns.
    Add more as you discover them.
    """
    return {
        "Angel Broking": "angel-one-ipo",
        "Adani Wilmar": "adani-wilmar-ipo",
        "Aditya Birla AMC": "aditya-birla-sun-life-amc-ipo",
        "CAMS": "cams-computer-age-management-services-ipo",
        "Anand Rathi Share and Stock Brokers Ltd": "anand-rathi-share-stock-brokers-ipo",
        "BLS E-Services": "bls-e-services-ipo",
        "Burger King": "restaurant-brands-asia-ipo",
        "Easy Trip Planners": "easemytrip-ipo",
        "CE Infosystems": "cartrade-tech-ipo",
    }


def main():
    log.info("=" * 60)
    log.info("AACapital — Chittorgarh IPO Scraper")
    log.info("=" * 60)

    # ── Connect to Neon ──
    db_url = DATABASE_URL
    if not db_url:
        log.error("DATABASE_URL not set. Set it in .env.local or environment.")
        return

    try:
        conn = psycopg2.connect(db_url)
        log.info("✓ Connected to Neon PostgreSQL")
    except Exception as e:
        log.error(f"DB connection failed: {e}")
        return

    # ── Load company list ──
    companies = load_companies()
    if not companies:
        log.error("No companies found. Check IPO_EXCEL env var or Neon connection.")
        return
    log.info(f"Found {len(companies)} companies to process")

    known_slugs = load_known_slugs()

    # ── Results tracking ──
    results = {"ok": [], "no_slug": [], "no_data": [], "errors": []}
    output_rows = []

    # ── Optional: warm up session ──
    log.info("Warming up session on chittorgarh.com …")
    session.get("https://www.chittorgarh.com/", timeout=15)
    sleep_politely()

    # ── Process each company ──
    for i, company in enumerate(companies, 1):
        log.info(f"\n[{i}/{len(companies)}] Processing: {company}")

        try:
            slug = find_ipo_slug(company, known_slugs)
            sleep_politely()

            if not slug:
                results["no_slug"].append(company)
                output_rows.append({"company_name": company, "status": "NO_SLUG"})
                continue

            data = scrape_ipo_page(slug)
            sleep_politely()

            if not data:
                results["no_data"].append(company)
                output_rows.append({"company_name": company, "slug": slug, "status": "NO_DATA"})
                continue

            # Write to Neon
            upsert_to_neon(conn, company, data)
            results["ok"].append(company)

            # Also collect to Excel output
            row = {"company_name": company, "slug": slug, "status": "OK"}
            row.update({k: v for k, v in data.items() if not isinstance(v, dict)})
            output_rows.append(row)

            log.info(f"  Fields collected: {[k for k in data if data[k] is not None]}")

        except KeyboardInterrupt:
            log.warning("Interrupted by user. Saving progress …")
            break
        except Exception as e:
            log.error(f"  Unhandled error for {company}: {e}")
            results["errors"].append(company)
            output_rows.append({"company_name": company, "status": "ERROR", "error": str(e)})

    # ── Save output Excel ──
    if output_rows:
        out_df = pd.DataFrame(output_rows)
        out_path = "_scripts/logs/chittorgarh_results.xlsx"
        out_df.to_excel(out_path, index=False)
        log.info(f"\nSaved results → {out_path}")

    # ── Summary ──
    log.info("\n" + "=" * 60)
    log.info(f"DONE — OK: {len(results['ok'])} | No slug: {len(results['no_slug'])} | "
             f"No data: {len(results['no_data'])} | Errors: {len(results['errors'])}")
    log.info(f"Failed slugs: {results['no_slug'][:20]}")

    conn.close()


if __name__ == "__main__":
    main()
