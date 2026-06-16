"""
AACapital — IPO Anchor Investor Scraper V1
Source: chittorgarh.com/ipo/{slug}/anchor-investors/
        + ipo_anchor_history table (already in Neon)
Fills:  anchor_total_cr, anchor_domestic_pct, anchor_foreign_pct,
        anchor_top5_pct, anchor_quality, anchor_investors,
        anchor_stalwart_names, anchor_offshore_names,
        anchor_classification, anchor_flip_risk

Run:  python _scripts/scraper_anchors.py
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
import psycopg2.extras
import pandas as pd

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SLEEP_MIN = 2.5
SLEEP_MAX = 5.0
LOG_FILE = "_scripts/logs/anchor_scrape.log"
os.makedirs("_scripts/logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("anchor_scraper")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.chittorgarh.com/",
}

session = requests.Session()
session.headers.update(HEADERS)

# ─── Anchor quality classification ────────────────────────────────────────────

# ELITE tier investors — sovereign, major domestic MFs, top global funds
ELITE_ANCHORS = [
    "sbi mutual", "hdfc mutual", "icici prudential", "nippon", "lic",
    "axis mutual", "kotak mutual", "dsp", "mirae", "franklin",
    "goldman sachs", "morgan stanley", "blackrock", "fidelity",
    "jpmorganam", "jp morgan", "ubs", "nomura", "aberdeen",
    "adia", "gic", "temasek", "sovereign",
]

GOOD_ANCHORS = [
    "motilal", "aditya birla", "tata mutual", "sundaram", "pgim",
    "white oak", "nj mutual", "edelweiss", "invesco", "hsbc mutual",
    "bank of india mutual", "canara robeco",
]


def classify_anchor_quality(anchor_names: list[str], domestic_pct: float, foreign_pct: float) -> dict:
    """Classify anchor quality and compute flip risk."""
    all_names = " ".join(anchor_names).lower()

    elite_count = sum(1 for e in ELITE_ANCHORS if e in all_names)
    good_count = sum(1 for g in GOOD_ANCHORS if g in all_names)
    total = len(anchor_names)

    if elite_count >= 3:
        quality = "ELITE"
        flip_risk = "LOW"
    elif elite_count >= 1 or good_count >= 3:
        quality = "GOOD"
        flip_risk = "MEDIUM"
    elif total >= 5:
        quality = "AVERAGE"
        flip_risk = "MEDIUM"
    else:
        quality = "WEAK"
        flip_risk = "HIGH"

    # High domestic = lower flip risk (domestic MFs are stickier post-30d)
    if domestic_pct and domestic_pct > 70:
        if flip_risk == "HIGH":
            flip_risk = "MEDIUM"

    stalwart_names = [n for n in anchor_names
                      if any(e in n.lower() for e in ELITE_ANCHORS)]
    offshore_names = [n for n in anchor_names
                      if any(kw in n.lower() for kw in
                             ["foreign", "global", "international", "fpi", "overseas",
                              "goldman", "morgan", "blackrock", "fidelity", "jp morgan",
                              "gic", "adia", "temasek", "nomura", "ubs", "aberdeen"])]

    return {
        "anchor_quality": quality,
        "anchor_flip_risk": flip_risk,
        "anchor_stalwart_names": ", ".join(stalwart_names[:5]),
        "anchor_offshore_names": ", ".join(offshore_names[:5]),
        "anchor_classification": f"ELITE:{elite_count} GOOD:{good_count} TOTAL:{total}",
    }


# ─── Scraper ──────────────────────────────────────────────────────────────────

def get_page(url: str) -> Optional[BeautifulSoup]:
    for attempt in range(1, 4):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            elif r.status_code in (403, 429):
                time.sleep(20 * attempt)
        except requests.RequestException as e:
            log.error(f"Request error: {e}")
            time.sleep(5 * attempt)
    return None


def sleep_politely():
    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))


def scrape_anchor_page(slug: str, issue_size_cr: float = 0) -> dict:
    """
    Scrape anchor investor data from chittorgarh anchor subpage.
    URL: https://www.chittorgarh.com/ipo/{slug}/anchor-investors/
    """
    url = f"https://www.chittorgarh.com/ipo/{slug}/anchor-investors/"
    soup = get_page(url)
    sleep_politely()

    if not soup:
        return {}

    result = {}
    anchor_names = []
    domestic_amount = 0.0
    foreign_amount = 0.0
    total_amount = 0.0
    top5_amount = 0.0

    # Look for anchor data tables
    tables = soup.find_all("table")
    for table in tables:
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]

        if any(kw in " ".join(headers) for kw in ["investor", "anchor", "name", "allot"]):
            rows = table.find_all("tr")[1:]
            amounts = []

            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if not cells:
                    continue

                name = cells[0] if cells else ""
                if name and len(name) > 2 and name.lower() not in ("total", "grand total", ""):
                    anchor_names.append(name)

                # Try to find amount column
                for cell in cells[1:]:
                    m = re.search(r"([\d,]+\.?\d*)", cell.replace(",", ""))
                    if m:
                        try:
                            val = float(m.group(1))
                            if val > 1:   # sanity check (crores)
                                amounts.append(val)
                                # Classify domestic vs foreign by name
                                name_lower = name.lower()
                                is_foreign = any(
                                    kw in name_lower for kw in
                                    ["foreign", "fpi", "global", "international",
                                     "goldman", "morgan", "blackrock", "fidelity",
                                     "jp morgan", "ubs", "nomura", "aberdeen",
                                     "gic", "adia", "temasek"]
                                )
                                if is_foreign:
                                    foreign_amount += val
                                else:
                                    domestic_amount += val
                            break
                        except ValueError:
                            pass

            if amounts:
                amounts_sorted = sorted(amounts, reverse=True)
                total_amount = sum(amounts)
                top5_amount = sum(amounts_sorted[:5])

    # Look for summary info (total anchor amount)
    page_text = soup.get_text()
    total_match = re.search(r"total\s+anchor\s+(?:allotment|amount)[^\d]*([\d,]+\.?\d*)\s*cr", 
                            page_text, re.IGNORECASE)
    if total_match:
        total_amount = float(total_match.group(1).replace(",", ""))

    if not anchor_names:
        return {}

    result["anchor_investors"] = ", ".join(anchor_names[:20])
    result["anchor_total_cr"] = round(total_amount, 2) if total_amount else None

    if total_amount > 0:
        result["anchor_domestic_pct"] = round(domestic_amount / total_amount * 100, 2)
        result["anchor_foreign_pct"] = round(foreign_amount / total_amount * 100, 2)
        if top5_amount:
            result["anchor_top5_pct"] = round(top5_amount / total_amount * 100, 2)

    # Issue size reference for anchor_pct
    if issue_size_cr and issue_size_cr > 0 and total_amount:
        result["anchor_total_pct"] = round(total_amount / issue_size_cr * 100, 2)

    # Quality classification
    dom_pct = result.get("anchor_domestic_pct", 0)
    for_pct = result.get("anchor_foreign_pct", 0)
    quality_data = classify_anchor_quality(anchor_names, dom_pct, for_pct)
    result.update(quality_data)

    log.info(
        f"  ✓ Anchors: {len(anchor_names)} names | quality={quality_data['anchor_quality']} "
        f"| domestic={dom_pct:.0f}% | foreign={for_pct:.0f}%"
    )
    return result


# ─── Also pull from existing ipo_anchor_history table ─────────────────────────

def pull_from_anchor_history(conn, company_name: str) -> dict:
    """
    Your ipo_anchor_history table already has some data.
    Pull it and compute quality scores.
    """
    sql = """
        SELECT
            ipo_name, anchor_amount_cr, anchor_shares,
            named_anchors, tier1_mf_present, large_fpi_present,
            sovereign_present, insurance_present,
            anchor_quality_score, anchor_price, confidence,
            sector, year
        FROM ipo_anchor_history
        WHERE LOWER(ipo_name) LIKE LOWER(%s)
        ORDER BY year DESC
        LIMIT 1
    """
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, [f"%{company_name.split()[0]}%"])
            row = cur.fetchone()
        if not row:
            return {}

        result = {}
        if row["anchor_amount_cr"]:
            result["anchor_total_cr"] = float(row["anchor_amount_cr"])

        if row["named_anchors"]:
            names = row["named_anchors"] if isinstance(row["named_anchors"], list) else []
            if names:
                result["anchor_investors"] = ", ".join(str(n) for n in names[:20])
                quality_data = classify_anchor_quality(
                    [str(n) for n in names], 0, 0
                )
                result.update(quality_data)

        # Boolean flags → quality boost
        tier1_mf = bool(row.get("tier1_mf_present"))
        large_fpi = bool(row.get("large_fpi_present"))
        sovereign = bool(row.get("sovereign_present"))

        if sovereign:
            result["anchor_quality"] = "ELITE"
            result["anchor_flip_risk"] = "LOW"
        elif tier1_mf and large_fpi:
            result["anchor_quality"] = "ELITE"
        elif tier1_mf:
            result["anchor_quality"] = "GOOD"

        return result
    except Exception as e:
        log.debug(f"anchor_history query failed: {e}")
        return {}


# ─── Neon upsert ──────────────────────────────────────────────────────────────

def upsert_anchor_to_neon(conn, company_name: str, data: dict):
    allowed_cols = {
        "anchor_total_cr", "anchor_domestic_pct", "anchor_foreign_pct",
        "anchor_top5_pct", "anchor_total_pct", "anchor_quality",
        "anchor_flip_risk", "anchor_investors",
        "anchor_stalwart_names", "anchor_offshore_names", "anchor_classification",
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
        log.info(f"  ✓ Anchor upsert OK: {company_name}")
    except Exception as e:
        conn.rollback()
        log.error(f"  ✗ Anchor upsert failed for {company_name}: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("AACapital — Anchor Investor Scraper")
    log.info("=" * 60)

    if not DATABASE_URL:
        log.error("DATABASE_URL not set.")
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        log.info("✓ Connected to Neon")
    except Exception as e:
        log.error(f"Connection failed: {e}")
        return

    # Load slug map from chittorgarh results
    slug_map = {}
    result_file = "_scripts/logs/chittorgarh_results.xlsx"
    if os.path.exists(result_file):
        df = pd.read_excel(result_file)
        if "company_name" in df.columns and "slug" in df.columns:
            slug_map = dict(zip(df["company_name"], df["slug"].fillna("")))

    # Load companies and their issue sizes
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT company_name, issue_size_cr, anchor_quality
            FROM ipo_intelligence
            ORDER BY company_name
        """)
        companies = cur.fetchall()

    log.info(f"Companies to process: {len(companies)}")
    stats = {"scraped": 0, "from_history": 0, "failed": 0}

    session.get("https://www.chittorgarh.com/", timeout=15)
    sleep_politely()

    for i, row in enumerate(companies, 1):
        company = row["company_name"]
        issue_size = float(row.get("issue_size_cr") or 0)
        existing_quality = row.get("anchor_quality", "")

        # Skip if already has real quality data (not the placeholder)
        if existing_quality and existing_quality not in ("Tier-2 Neutral", "UNKNOWN", ""):
            log.info(f"[{i}] Skipping {company} (already has: {existing_quality})")
            continue

        log.info(f"\n[{i}/{len(companies)}] {company}")

        # Try ipo_anchor_history first (already in Neon, zero scraping)
        data = pull_from_anchor_history(conn, company)
        if data:
            stats["from_history"] += 1
            upsert_anchor_to_neon(conn, company, data)
            continue

        # Try scraping chittorgarh anchor page
        slug = slug_map.get(company, "")
        if slug:
            data = scrape_anchor_page(slug, issue_size)
            if data:
                stats["scraped"] += 1
                upsert_anchor_to_neon(conn, company, data)
                sleep_politely()
                continue

        stats["failed"] += 1
        log.warning(f"  ✗ No anchor data for {company}")
        sleep_politely()

    log.info(f"\nDone — Scraped: {stats['scraped']} | From history: {stats['from_history']} "
             f"| Failed: {stats['failed']}")
    conn.close()


if __name__ == "__main__":
    main()
