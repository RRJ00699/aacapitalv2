"""
AACapital — IPO Data Enricher V2 (333 IPOs)
Task 3: Complete IPO enricher for all 333 IPOs

Multi-source scraping:
  1. Chittorgarh   — subscription, GMP, anchor, financials
  2. InvestorGain  — subscription, cosine similarity hits
  3. IPOWatch      — listing day signals
  4. Trendlyne     — sector PE, promoter, OFS data

Usage:
    python _scripts/ipo_data_enricher_v2.py               # all pending IPOs
    python _scripts/ipo_data_enricher_v2.py --sleep 1.5   # custom delay
    python _scripts/ipo_data_enricher_v2.py --limit 50    # batch of 50
    python _scripts/ipo_data_enricher_v2.py --retry-failed # retry errored rows
"""

import os
import re
import sys
import time
import json
import argparse
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

NEON_URL = os.environ["NEON_DATABASE_URL"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(open(1, "w", encoding="utf-8", closefd=False)),
        logging.FileHandler("_output/enricher_v2.log", mode="a", encoding="utf-8"),
    ],
)
log = logging.getLogger("enricher")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ── helpers ────────────────────────────────────────────────────────────────────

def safe_float(val) -> Optional[float]:
    try:
        return float(str(val).replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def safe_int(val) -> Optional[int]:
    try:
        return int(str(val).replace(",", "").strip())
    except Exception:
        return None


def fetch_page(url: str, sleep: float = 1.5, retries: int = 3) -> Optional[BeautifulSoup]:
    for attempt in range(retries):
        try:
            time.sleep(sleep)
            r = SESSION.get(url, timeout=15)
            r.raise_for_status()
            return BeautifulSoup(r.text, "lxml")
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 429:
                wait = 30 * (attempt + 1)
                log.warning(f"Rate limited. Waiting {wait}s… (attempt {attempt+1})")
                time.sleep(wait)
            else:
                log.warning(f"HTTP {e} for {url} (attempt {attempt+1})")
        except Exception as e:
            log.warning(f"Fetch error {url}: {e} (attempt {attempt+1})")
            time.sleep(5)
    return None


def slug(name: str) -> str:
    """Convert company name to URL-friendly slug."""
    return re.sub(r"[^a-z0-9-]", "-", name.lower().strip()).strip("-")


# ── Chittorgarh scraper ────────────────────────────────────────────────────────

def scrape_chittorgarh(ipo_name: str, sleep: float) -> dict:
    s = slug(ipo_name)
    url = f"https://www.chittorgarh.com/ipo/{s}-ipo/1/"
    log.info(f"  Chittorgarh -> {url}")
    soup = fetch_page(url, sleep=sleep)
    if not soup:
        return {}

    data = {}

    # Subscription table
    try:
        tables = soup.find_all("table")
        for table in tables:
            text = table.get_text()
            if "QIB" in text and "NII" in text:
                rows = table.find_all("tr")
                for row in rows:
                    cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
                    if len(cells) < 2:
                        continue
                    key = cells[0].upper()
                    val = safe_float(cells[-1])
                    if "QIB"    in key: data["qib_subscription"]    = val
                    elif "NII"  in key: data["nii_subscription"]    = val
                    elif "RETAIL" in key: data["retail_subscription"] = val
                    elif "TOTAL" in key: data["total_subscription"]  = val
    except Exception as e:
        log.debug(f"Subscription parse error: {e}")

    # GMP
    try:
        gmp_section = soup.find(string=re.compile(r"GMP", re.I))
        if gmp_section:
            parent = gmp_section.parent
            for _ in range(5):
                text = parent.get_text()
                match = re.search(r"GMP.*?₹?\s*([\d.]+)", text, re.I)
                if match:
                    gmp_val = safe_float(match.group(1))
                    price   = data.get("issue_price") or safe_float(
                        (soup.find(string=re.compile(r"Issue Price", re.I)) or {}).parent
                        .find_next(string=re.compile(r"\d+"))
                        if gmp_val else "0"
                    ) or 0
                    if gmp_val and price:
                        data["gmp_value"]      = gmp_val
                        data["gmp_percentage"] = round(gmp_val / price * 100, 2)
                    break
                parent = parent.parent
    except Exception as e:
        log.debug(f"GMP parse error: {e}")

    # Issue details
    try:
        for row in soup.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
            if len(cells) < 2:
                continue
            key = cells[0].lower()
            val = cells[-1]
            if "issue size"     in key: data["issue_size_cr"]       = safe_float(val)
            elif "issue price"  in key: data["issue_price"]         = safe_float(val)
            elif "lot size"     in key: data["lot_size"]            = safe_int(val)
            elif "listing"      in key and "date" in key:
                try:
                    data["listing_date"] = datetime.strptime(val, "%d %b %Y").date().isoformat()
                except Exception:
                    pass
            elif "ofs"          in key: data["ofs_cr"]              = safe_float(val)
            elif "fresh"        in key: data["fresh_issue_cr"]      = safe_float(val)
    except Exception as e:
        log.debug(f"Issue details parse error: {e}")

    # OFS %
    if data.get("issue_size_cr") and data.get("ofs_cr"):
        data["ofs_percentage"] = round(data["ofs_cr"] / data["issue_size_cr"] * 100, 1)

    return data


# ── InvestorGain scraper ───────────────────────────────────────────────────────

def scrape_investorgain(ipo_name: str, sleep: float) -> dict:
    s = slug(ipo_name).replace("-", "+")
    url = f"https://www.investorgain.com/report/ipo-subscription-live/{s}/"
    log.info(f"  InvestorGain -> {url}")
    soup = fetch_page(url, sleep=sleep)
    if not soup:
        return {}

    data = {}
    try:
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
                if len(cells) < 2:
                    continue
                key = cells[0].upper()
                val = safe_float(cells[1]) if len(cells) > 1 else None
                if not data.get("total_subscription") and "TOTAL" in key and val:
                    data["total_subscription"] = val
    except Exception as e:
        log.debug(f"InvestorGain parse error: {e}")

    # Allotment status
    try:
        allot_text = soup.get_text()
        if "allotted" in allot_text.lower():
            data["allotment_status"] = "ALLOTTED"
        elif "basis of allotment" in allot_text.lower():
            data["allotment_status"] = "FINALISED"
    except Exception:
        pass

    return data


# ── IPOWatch scraper ───────────────────────────────────────────────────────────

def scrape_ipowatch(ipo_name: str, sleep: float) -> dict:
    s = slug(ipo_name)
    url = f"https://ipowatch.in/{s}-ipo-listing/"
    log.info(f"  IPOWatch -> {url}")
    soup = fetch_page(url, sleep=sleep)
    if not soup:
        return {}

    data = {}
    try:
        text = soup.get_text()
        # Listing gain
        match = re.search(r"listed.*?(\+?-?[\d.]+)%", text, re.I)
        if match:
            data["listing_gap_pct"] = safe_float(match.group(1))

        # Listing price
        match2 = re.search(r"listing price.*?₹?\s*([\d,]+)", text, re.I)
        if match2:
            data["listing_price"] = safe_float(match2.group(1))
    except Exception as e:
        log.debug(f"IPOWatch parse error: {e}")

    return data


# ── Trendlyne scraper ──────────────────────────────────────────────────────────

def scrape_trendlyne(ipo_name: str, sleep: float) -> dict:
    s = slug(ipo_name)
    url = f"https://trendlyne.com/ipo/{s}/"
    log.info(f"  Trendlyne -> {url}")
    soup = fetch_page(url, sleep=sleep)
    if not soup:
        return {}

    data = {}
    try:
        for row in soup.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
            if len(cells) < 2:
                continue
            key = cells[0].lower()
            val = cells[-1]
            if "promoter" in key and "holding" in key:
                data["promoter_holding_post"] = safe_float(val)
            elif "sector" in key and "p/e" in key:
                data["sector_pe_median"]      = safe_float(val)
            elif "p/e" in key and "issue" in key:
                data["pe_ratio"]              = safe_float(val)
            elif "revenue growth" in key:
                data["revenue_growth_3yr"]    = safe_float(val)
            elif "pat growth" in key:
                data["pat_growth_3yr"]        = safe_float(val)
    except Exception as e:
        log.debug(f"Trendlyne parse error: {e}")

    return data


# ── anchor classifier ──────────────────────────────────────────────────────────

TIER1_ANCHORS = {
    "fidelity", "blackrock", "vanguard", "government pension fund",
    "singapore gic", "temasek", "norges", "abu dhabi", "mirae",
    "axis mutual", "hdfc mutual", "icici prudential", "sbi mutual",
    "nippon india", "kotak mutual", "franklin", "dsp",
}

def classify_anchor(anchor_text: str) -> str:
    lower = anchor_text.lower()
    tier1_hits = sum(1 for a in TIER1_ANCHORS if a in lower)
    count = len(re.findall(r"\n", anchor_text.strip()))
    if tier1_hits >= 3 or count >= 20:
        return "STRONG"
    if tier1_hits >= 1 or count >= 10:
        return "MEDIUM"
    return "WEAK"


# ── DB ─────────────────────────────────────────────────────────────────────────

def get_pending_ipos(conn, retry_failed: bool = False, limit: int = 0) -> list[dict]:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if retry_failed:
        cur.execute("""
            SELECT * FROM ipo_intelligence
            WHERE enrichment_status = 'ERROR'
            ORDER BY listing_date DESC
            LIMIT %s
        """, (limit or 9999,))
    else:
        cur.execute("""
            SELECT * FROM ipo_intelligence
            WHERE (enrichment_status IS NULL OR enrichment_status = 'PARTIAL')
            ORDER BY listing_date DESC
            LIMIT %s
        """, (limit or 9999,))

    return [dict(r) for r in cur.fetchall()]


def upsert_ipo(conn, ipo_id: int, data: dict, status: str):
    if not data:
        return
    cur = conn.cursor()

    # Dynamically build SET clause from non-null data keys
    set_parts = []
    values    = []
    for k, v in data.items():
        if v is not None:
            set_parts.append(f"{k} = %s")
            values.append(v)

    set_parts.append("enrichment_status = %s")
    values.append(status)
    set_parts.append("enriched_at = now()")

    values.append(ipo_id)

    sql = f"UPDATE ipo_intelligence SET {', '.join(set_parts)} WHERE id = %s"
    try:
        cur.execute(sql, values)
        conn.commit()
    except psycopg2.Error as e:
        conn.rollback()
        log.error(f"DB upsert error for id={ipo_id}: {e}")


def ensure_columns(conn):
    """Add new enrichment columns if they don't exist yet."""
    cols = [
        ("gmp_value",           "NUMERIC(10,2)"),
        ("gmp_percentage",      "NUMERIC(8,2)"),
        ("qib_subscription",    "NUMERIC(10,2)"),
        ("nii_subscription",    "NUMERIC(10,2)"),
        ("retail_subscription", "NUMERIC(10,2)"),
        ("total_subscription",  "NUMERIC(10,2)"),
        ("issue_size_cr",       "NUMERIC(12,2)"),
        ("issue_price",         "NUMERIC(10,2)"),
        ("lot_size",            "INT"),
        ("ofs_cr",              "NUMERIC(12,2)"),
        ("ofs_percentage",      "NUMERIC(6,2)"),
        ("fresh_issue_cr",      "NUMERIC(12,2)"),
        ("listing_price",       "NUMERIC(10,2)"),
        ("listing_gap_pct",    "NUMERIC(8,2)"),
        ("promoter_holding_post","NUMERIC(6,2)"),
        ("sector_pe_median",    "NUMERIC(8,2)"),
        ("pe_ratio",            "NUMERIC(8,2)"),
        ("revenue_growth_3yr",  "NUMERIC(8,2)"),
        ("pat_growth_3yr",      "NUMERIC(8,2)"),
        ("anchor_classification","TEXT"),
        ("allotment_status",    "TEXT"),
        ("enrichment_status",   "TEXT"),
        ("enriched_at",         "TIMESTAMPTZ"),
    ]
    cur = conn.cursor()
    for col, dtype in cols:
        cur.execute(f"""
            ALTER TABLE ipo_intelligence
            ADD COLUMN IF NOT EXISTS {col} {dtype}
        """)
    conn.commit()
    log.info("Schema ensured — enrichment columns ready")


# ── main enricher loop ─────────────────────────────────────────────────────────

def enrich_ipo(ipo: dict, sleep: float) -> tuple[dict, str]:
    name = ipo.get("company_name", "")
    log.info(f"\n▶ Enriching: {name}")

    merged = {}

    # Source 1: Chittorgarh
    try:
        d = scrape_chittorgarh(name, sleep)
        merged.update({k: v for k, v in d.items() if v is not None})
        log.info(f"  Chittorgarh: {len(d)} fields")
    except Exception as e:
        log.warning(f"  Chittorgarh FAILED: {e}")

    # Source 2: InvestorGain (fill gaps)
    try:
        d = scrape_investorgain(name, sleep)
        for k, v in d.items():
            if k not in merged or merged[k] is None:
                merged[k] = v
        log.info(f"  InvestorGain: {len(d)} fields")
    except Exception as e:
        log.warning(f"  InvestorGain FAILED: {e}")

    # Source 3: IPOWatch (listing outcome)
    try:
        d = scrape_ipowatch(name, sleep)
        for k, v in d.items():
            if k not in merged or merged[k] is None:
                merged[k] = v
        log.info(f"  IPOWatch: {len(d)} fields")
    except Exception as e:
        log.warning(f"  IPOWatch FAILED: {e}")

    # Source 4: Trendlyne (financials)
    try:
        d = scrape_trendlyne(name, sleep)
        for k, v in d.items():
            if k not in merged or merged[k] is None:
                merged[k] = v
        log.info(f"  Trendlyne: {len(d)} fields")
    except Exception as e:
        log.warning(f"  Trendlyne FAILED: {e}")

    # Determine completeness
    critical_fields = [
        "total_subscription", "listing_gap_pct", "gmp_percentage",
        "issue_size_cr", "pe_ratio",
    ]
    filled = sum(1 for f in critical_fields if merged.get(f) is not None)

    if filled >= 4:
        status = "COMPLETE"
    elif filled >= 2:
        status = "PARTIAL"
    elif not merged:
        status = "ERROR"
    else:
        status = "PARTIAL"

    log.info(f"  Status: {status} | {len(merged)} total fields enriched")
    return merged, status


def main():
    parser = argparse.ArgumentParser(description="AACapital IPO Data Enricher V2")
    parser.add_argument("--sleep",        type=float, default=1.5,
                        help="Delay between requests (default 1.5s)")
    parser.add_argument("--limit",        type=int,   default=0,
                        help="Max IPOs to process (0 = all)")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Retry IPOs with enrichment_status=ERROR")
    args = parser.parse_args()

    os.makedirs("_output", exist_ok=True)
    conn = psycopg2.connect(NEON_URL)

    ensure_columns(conn)

    pending = get_pending_ipos(conn, retry_failed=args.retry_failed, limit=args.limit)
    log.info(f"\n{'═'*50}")
    log.info(f"AACapital — IPO Enricher V2")
    log.info(f"{'═'*50}")
    log.info(f"IPOs to enrich: {len(pending)}")
    log.info(f"Sleep: {args.sleep}s | Limit: {args.limit or 'all'}")

    complete = partial = error = 0

    for i, ipo in enumerate(pending, 1):
        log.info(f"\n[{i}/{len(pending)}] ─────────────────────")
        try:
            data, status = enrich_ipo(ipo, sleep=args.sleep)
            upsert_ipo(conn, ipo["id"], data, status)
            if status == "COMPLETE":  complete += 1
            elif status == "PARTIAL": partial  += 1
            else:                     error    += 1
        except Exception as e:
            log.error(f"Unhandled error for {ipo.get('company_name')}: {e}")
            upsert_ipo(conn, ipo["id"], {}, "ERROR")
            error += 1

    conn.close()

    log.info(f"\n{'═'*50}")
    log.info(f"ENRICHMENT COMPLETE")
    log.info(f"  Complete: {complete}")
    log.info(f"  Partial:  {partial}")
    log.info(f"  Error:    {error}")
    log.info(f"  Total:    {len(pending)}")
    log.info(f"{'═'*50}")


if __name__ == "__main__":
    main()
