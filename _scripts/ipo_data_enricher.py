#!/usr/bin/env python3
"""
AACapital IPO Data Enricher

Purpose:
  Enrich a list of Indian IPOs with fields needed for AACapital IPO Intelligence Engine:
  qib_x, nii_x, retail_x, total_x, gmp_t1, gmp_pct_of_issue, gmp_direction,
  ofs_pct, brlm_names, anchor_quality, ipo_pe, peer_median_pe.

Important:
  Public IPO pages vary heavily by site and year. This script is designed as a
  robust starter pipeline with:
    - multiple source attempts
    - regex/table extraction
    - source URL tracking
    - confidence labels
    - manual review queue

Install:
  pip install pandas requests beautifulsoup4 lxml openpyxl rapidfuzz

Usage:
  python ipo_data_enricher.py --input ipo_seed_304.csv --output enriched_ipo_data.xlsx
  python ipo_data_enricher.py --input ipo_seed_304.csv --output enriched_ipo_data.xlsx --limit 25
  python ipo_data_enricher.py --input ipo_seed_304.csv --output enriched_ipo_data.xlsx --sleep 2.0

Notes:
  1. Use final subscription values only, not interim day-1/day-2 values.
  2. GMP T-1 means the GMP one day before listing.
  3. For GMP direction, use T-3 to T-1 if available; otherwise compare min/max in recent GMP table.
  4. Do not use post-listing returns in scoring fields.
"""

from __future__ import annotations

import argparse
import math
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from io import StringIO
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote_plus

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

OUTPUT_COLUMNS = [
    "id", "ipo_name", "status",
    "qib_x", "nii_x", "retail_x", "total_x",
    "gmp_t1", "issue_price", "gmp_pct_of_issue",
    "gmp_direction", "gmp_min", "gmp_max",
    "fresh_issue_amt_cr", "ofs_amt_cr", "total_issue_amt_cr", "ofs_pct",
    "brlm_names", "anchor_quality", "ipo_pe", "peer_median_pe", "valuation_gap_pct",
    "source_subscription", "source_gmp", "source_ofs", "source_brlm_pe",
    "confidence", "notes", "last_updated"
]


@dataclass
class IpoEnrichment:
    ipo_name: str
    qib_x: Optional[float] = None
    nii_x: Optional[float] = None
    retail_x: Optional[float] = None
    total_x: Optional[float] = None
    gmp_t1: Optional[float] = None
    issue_price: Optional[float] = None
    gmp_pct_of_issue: Optional[float] = None
    gmp_direction: Optional[str] = None
    gmp_min: Optional[float] = None
    gmp_max: Optional[float] = None
    fresh_issue_amt_cr: Optional[float] = None
    ofs_amt_cr: Optional[float] = None
    total_issue_amt_cr: Optional[float] = None
    ofs_pct: Optional[float] = None
    brlm_names: Optional[str] = None
    anchor_quality: Optional[str] = None
    ipo_pe: Optional[float] = None
    peer_median_pe: Optional[float] = None
    valuation_gap_pct: Optional[float] = None
    source_subscription: Optional[str] = None
    source_gmp: Optional[str] = None
    source_ofs: Optional[str] = None
    source_brlm_pe: Optional[str] = None
    confidence: str = "low"
    notes: str = ""


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"&", " and ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def clean_num(x: Any) -> Optional[float]:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    s = str(x)
    s = s.replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "")
    s = s.replace("times", "").replace("x", "").replace("%", "").strip()
    s = re.sub(r"\([^)]*\)", "", s).strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def get_url(url: str, timeout: int = 20) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
    except Exception:
        return None
    return None


def read_tables(html: str) -> List[pd.DataFrame]:
    try:
        return pd.read_html(StringIO(html))
    except Exception:
        return []


def row_text(row: pd.Series) -> str:
    return " | ".join([str(v) for v in row.values if str(v) != "nan"]).lower()


def find_subscription_in_tables(tables: List[pd.DataFrame]) -> Dict[str, Optional[float]]:
    """
    Attempts to parse subscription tables from common IPO websites.
    Handles rows/columns such as:
      QIB, NII, Retail, Total
      Qualified Institutional Buyers, Non Institutional Investors, Retail Individual Investors
    """
    out = {"qib_x": None, "nii_x": None, "retail_x": None, "total_x": None}
    aliases = {
        "qib_x": ["qib", "qualified institutional", "qualified institutional buyers"],
        "nii_x": ["nii", "hni", "non institutional", "non-institutional"],
        "retail_x": ["retail", "rii", "retail individual"],
        "total_x": ["total", "overall"]
    }

    for df in tables:
        if df.empty:
            continue
        # Normalize columns
        df2 = df.copy()
        df2.columns = [str(c).strip().lower() for c in df2.columns]
        # Find rows that look like category rows and values that look like subscription times
        for _, row in df2.iterrows():
            txt = row_text(row)
            for key, names in aliases.items():
                if out[key] is None and any(a in txt for a in names):
                    nums = [clean_num(v) for v in row.values]
                    nums = [n for n in nums if n is not None]
                    # Subscription multiples are often the last numeric value in row
                    if nums:
                        out[key] = nums[-1]

        # Sometimes categories are columns and final values in last row
        col_text = " ".join(df2.columns)
        if any(a in col_text for a in ["qib", "nii", "retail", "total"]):
            last = df2.tail(1).iloc[0]
            for col in df2.columns:
                low = str(col).lower()
                for key, names in aliases.items():
                    if out[key] is None and any(a in low for a in names):
                        out[key] = clean_num(last[col])
    return out


def find_issue_mix_in_tables(tables: List[pd.DataFrame]) -> Dict[str, Optional[float]]:
    out = {"fresh_issue_amt_cr": None, "ofs_amt_cr": None, "total_issue_amt_cr": None, "issue_price": None}
    for df in tables:
        if df.empty:
            continue
        text = " ".join(str(x).lower() for x in df.astype(str).values.flatten())
        # General key-value tables
        for _, row in df.iterrows():
            txt = row_text(row)
            nums = [clean_num(v) for v in row.values]
            nums = [n for n in nums if n is not None]
            if not nums:
                continue
            val = nums[-1]
            if out["fresh_issue_amt_cr"] is None and "fresh" in txt and "issue" in txt:
                out["fresh_issue_amt_cr"] = val
            if out["ofs_amt_cr"] is None and ("offer for sale" in txt or "ofs" in txt):
                out["ofs_amt_cr"] = val
            if out["total_issue_amt_cr"] is None and ("issue size" in txt or "total issue" in txt):
                out["total_issue_amt_cr"] = val
            if out["issue_price"] is None and ("price band" in txt or "issue price" in txt or "ipo price" in txt):
                # Usually upper band is the max number
                out["issue_price"] = max(nums)
    return out


def find_gmp_in_tables(tables: List[pd.DataFrame]) -> Dict[str, Optional[Any]]:
    """
    Parses GMP from common tables. For best accuracy, manually verify T-1 against listing date.
    """
    gmps: List[float] = []
    dates_or_rows = []
    for df in tables:
        if df.empty:
            continue
        df2 = df.copy()
        df2.columns = [str(c).strip().lower() for c in df2.columns]
        if not any("gmp" in c or "grey" in c or "premium" in c for c in df2.columns) and "gmp" not in " ".join(map(str, df2.values.flatten())).lower():
            continue

        for _, row in df2.iterrows():
            txt = row_text(row)
            if "gmp" in txt or "premium" in txt:
                nums = [clean_num(v) for v in row.values]
                nums = [n for n in nums if n is not None]
                if nums:
                    # In GMP tables the rupee GMP is commonly one of the last numbers.
                    # Exclude very large issue sizes by preferring values under 1000.
                    candidates = [n for n in nums if abs(n) < 1000]
                    if candidates:
                        gmps.append(candidates[-1])
                        dates_or_rows.append(txt[:120])

    out = {"gmp_t1": None, "gmp_min": None, "gmp_max": None, "gmp_direction": None}
    if gmps:
        out["gmp_t1"] = gmps[0]  # many sources sort latest first
        out["gmp_min"] = min(gmps)
        out["gmp_max"] = max(gmps)
        if len(gmps) >= 2:
            latest, older = gmps[0], gmps[-1]
            if latest > older:
                out["gmp_direction"] = "rising"
            elif latest < older:
                out["gmp_direction"] = "falling"
            else:
                out["gmp_direction"] = "flat"
        else:
            out["gmp_direction"] = "unknown"
    return out


def search_investorgain_url(name: str) -> str:
    # Site supports many URLs by slug but IDs differ. We use search URL as stable fallback.
    return f"https://www.investorgain.com/report/live-ipo-gmp/331/ipo/{quote_plus(name)}"


def candidate_urls(name: str) -> List[Tuple[str, str]]:
    slug = slugify(name)
    return [
        ("chittorgarh", f"https://www.chittorgarh.com/ipo/{slug}-ipo/"),
        ("investorgain_search", search_investorgain_url(name)),
        ("ipowatch_search", f"https://ipowatch.in/?s={quote_plus(name + ' IPO GMP subscription')}"),
        ("moneycontrol_search", f"https://www.moneycontrol.com/news/tags/{slug}-ipo.html"),
    ]


def enrich_one(name: str, sleep: float = 1.0) -> IpoEnrichment:
    result = IpoEnrichment(ipo_name=name)
    notes = []
    for source_name, url in candidate_urls(name):
        html = get_url(url)
        time.sleep(sleep)
        if not html:
            notes.append(f"{source_name}: no html")
            continue

        tables = read_tables(html)
        if tables:
            sub = find_subscription_in_tables(tables)
            if not result.source_subscription and any(v is not None for v in sub.values()):
                for k, v in sub.items():
                    setattr(result, k, v)
                result.source_subscription = url

            mix = find_issue_mix_in_tables(tables)
            if not result.source_ofs and any(v is not None for v in mix.values()):
                for k, v in mix.items():
                    if getattr(result, k) is None:
                        setattr(result, k, v)
                result.source_ofs = url

            gmp = find_gmp_in_tables(tables)
            if not result.source_gmp and any(v is not None for v in gmp.values()):
                for k, v in gmp.items():
                    setattr(result, k, v)
                result.source_gmp = url

        # Basic text extraction for BRLM and P/E
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        if not result.brlm_names:
            m = re.search(r"(?:book running lead manager|lead manager|brlm)[s]?\s*[:\-]?\s*([^\.]{5,180})", text, re.I)
            if m:
                result.brlm_names = m.group(1).strip()
                result.source_brlm_pe = url

        if not result.ipo_pe:
            m = re.search(r"(?:p/e|pe ratio|price to earnings)[^\d]{0,20}(\d+(?:\.\d+)?)", text, re.I)
            if m:
                result.ipo_pe = clean_num(m.group(1))
                result.source_brlm_pe = result.source_brlm_pe or url

    # Derived fields
    if result.gmp_t1 is not None and result.issue_price:
        result.gmp_pct_of_issue = result.gmp_t1 / result.issue_price

    if result.ofs_amt_cr is not None and result.total_issue_amt_cr:
        result.ofs_pct = result.ofs_amt_cr / result.total_issue_amt_cr

    if result.ipo_pe is not None and result.peer_median_pe:
        result.valuation_gap_pct = (result.ipo_pe - result.peer_median_pe) / result.peer_median_pe

    populated = sum(
        getattr(result, k) is not None
        for k in ["qib_x", "nii_x", "retail_x", "total_x", "gmp_t1", "ofs_pct"]
    )
    result.confidence = "high" if populated >= 5 else "medium" if populated >= 3 else "low"
    result.notes = "; ".join(notes[:5])
    return result


def load_input(path: str) -> pd.DataFrame:
    if path.lower().endswith(".xlsx"):
        return pd.read_excel(path)
    return pd.read_csv(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="CSV/XLSX containing ipo_name column")
    ap.add_argument("--output", default="enriched_ipo_data.xlsx")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=1.5, help="seconds between source requests")
    ap.add_argument("--force-update", action="store_true", help="overwrite rows marked Verified")
    args = ap.parse_args()

    df = load_input(args.input)
    if "ipo_name" not in df.columns:
        raise ValueError("Input must contain ipo_name column")

    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = None

    work = df.head(args.limit).copy() if args.limit else df.copy()
    enriched_rows = []

    for i, row in work.iterrows():
        name = str(row["ipo_name"]).strip()
        status = str(row.get("status", "")).lower()
        if status == "verified" and not args.force_update:
            enriched_rows.append(row.to_dict())
            continue

        print(f"[{i+1}/{len(work)}] Enriching: {name}")
        try:
            enr = enrich_one(name, sleep=args.sleep)
            data = row.to_dict()
            for k, v in asdict(enr).items():
                if k == "ipo_name":
                    continue
                # don't overwrite existing non-empty values unless auto field is blank
                if pd.isna(data.get(k)) or data.get(k) in ("", None):
                    data[k] = v
            data["status"] = "Auto Filled" if enr.confidence in ("high", "medium") else "Needs Review"
            data["last_updated"] = datetime.utcnow().strftime("%Y-%m-%d")
            enriched_rows.append(data)
        except Exception as e:
            data = row.to_dict()
            data["status"] = "Needs Review"
            data["notes"] = f"{data.get('notes','')}; error={e}"
            enriched_rows.append(data)

    outdf = pd.DataFrame(enriched_rows)
    for col in OUTPUT_COLUMNS:
        if col not in outdf.columns:
            outdf[col] = None
    outdf = outdf[OUTPUT_COLUMNS]

    if args.output.lower().endswith(".csv"):
        outdf.to_csv(args.output, index=False)
    else:
        with pd.ExcelWriter(args.output, engine="openpyxl") as writer:
            outdf.to_excel(writer, index=False, sheet_name="IPO_Data_Collection")
            # Manual review sheet
            review = outdf[outdf["status"].isin(["Needs Review", "Not Started"]) | (outdf["confidence"].isin(["low", "unknown"]))]
            review.to_excel(writer, index=False, sheet_name="Manual_Review")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
