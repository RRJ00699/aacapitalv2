#!/usr/bin/env python3
"""
scrape_chittorgarh.py (v2) — Chittorgarh mainboard IPO calendar -> ipo_intelligence.

v2 FIX: the calendar endpoint returns only the LAST ~5 IPOs (December) for past
years when called once. v2 walks EVERY month (1-12) AND pages per year, unions the
results, and dedupes by slug/(name,open_date). A year in 2010-2025 yielding <10
rows prints a COVERAGE WARN so truncation is never silent again.

Endpoint (JSON, Cloudflare cleared once via Playwright, then fast ctx.request):
  https://webnodejs.chittorgarh.com/cloud/report/data-read/82/1/7/{YEAR}/{FY}/{MONTH}/mainboard/{PAGE}?search=&v=21-38

WRITE DISCIPLINE (Rule 1, unchanged from v1):
  * fill-EMPTY-only (COALESCE) for raw facts; INSERT only when no fuzzy match.
  * join by fuzzy company name (rapidfuzz token_sort_ratio >= 90) — NEVER by
    Chittorgarh's unreliable ~nse_symbol (Dixon->KFINTECH, Advit->RAMBHAJO).
  * scraped symbol written ONLY into a row where BOTH nse_symbol and symbol are
    blank AND the symbol prefix matches the company name. Never overwrites.
  * value-sanity per row BEFORE commit; HARD failures skipped and counted.

Usage (VM):
  venv/bin/python _scripts/scrape_chittorgarh.py --year 2021              # dry-run one year
  venv/bin/python _scripts/scrape_chittorgarh.py --from 2010 --to 2026 --write-db
Prints:  ins=<inserted> upd=<fill-empty updated> symw=<symbols written> skip=<sanity/dup skips>
Needs: DATABASE_URL, playwright chromium, rapidfuzz, psycopg2 (use venv/bin/python).
"""
import os, sys, re, json, time, argparse, datetime, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scrape_chittorgarh")

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
API = ("https://webnodejs.chittorgarh.com/cloud/report/data-read/"
       "82/1/7/{year}/{fy}/{month}/mainboard/{page}?search=&v=21-38")
WARMUP_URL = "https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/mainboard/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
FUZZ_THRESHOLD = 90
MAX_PAGES = 8           # per (year, month) — stop early on empty/repeat
MIN_EXPECTED = 10       # 2010-2025 mainboard years below this trigger COVERAGE WARN
_NULLISH = {"", "-", "\u2014", "n/a", "na", "nan", "none", "null", "tbd", "--"}

# ---------------------------------------------------------------- parsers ---
def clean_str(v):
    if v is None:
        return None
    s = re.sub(r"<[^>]+>", " ", str(v))
    s = re.sub(r"\s+", " ", s).strip()
    return None if s.lower() in _NULLISH else s

def num(v, take="max"):
    if isinstance(v, (int, float)):
        return float(v)
    s = clean_str(v)
    if s is None:
        return None
    s = s.replace("\u20b9", "").replace(",", "")
    nums = [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", s)]
    if not nums:
        return None
    return max(nums) if take == "max" else nums[0]

def parse_date(v):
    s = clean_str(v)
    if not s:
        return None
    s = re.sub(r"^[A-Za-z]+day,\s*", "", s).strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %b, %Y", "%d-%m-%Y",
                "%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return datetime.date.fromisoformat(m.group(1)) if m else None

def norm_name(s):
    s = (s or "").lower()
    s = re.sub(r"\b(limited|ltd\.?|ipo|india|the)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def symbol_prefix_ok(symbol, company):
    if not symbol or not company:
        return False
    sym = re.sub(r"[^A-Z0-9]", "", symbol.upper())
    comp = re.sub(r"[^A-Z0-9]", "", norm_name(company).upper())
    if len(sym) < 3 or len(comp) < 3:
        return False
    k = min(4, len(sym), len(comp))
    return comp.startswith(sym[:k]) or sym.startswith(comp[:k])

# ------------------------------------------------------- key discovery ------
def pick(row, *patterns):
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for k in row.keys():
            if rx.search(k):
                return row[k]
    return None

def map_row(row):
    company = clean_str(pick(row, r"^(issuer\s*)?company", r"company\s*name", r"^issuer"))
    if company:
        company = re.sub(r"\s*IPO$", "", company, flags=re.I).strip()
    return {
        "company_name":  company,
        "open_date":     parse_date(pick(row, r"open(ing)?\s*date", r"^open")),
        "close_date":    parse_date(pick(row, r"clos(e|ing)\s*date", r"^close")),
        "listing_date":  parse_date(pick(row, r"listing\s*date")),
        "issue_price":   num(pick(row, r"issue\s*price", r"price\s*band", r"offer\s*price")),
        "issue_size_cr": num(pick(row, r"issue\s*(amount|size)", r"total\s*issue")),
        "nse_symbol":    clean_str(pick(row, r"~?nse_?symbol")),
        "isin":          clean_str(pick(row, r"~?isin")),
        "slug":          clean_str(pick(row, r"URLRewrite", r"~?slug")),
    }

def rec_key(rec):
    """Dedupe key across month/page calls: slug if present, else (name, open)."""
    return rec.get("slug") or (norm_name(rec.get("company_name")), str(rec.get("open_date")))

# ------------------------------------------------------------ sanity gate ---
def sane(rec, year):
    lo, hi = datetime.date(2005, 1, 1), datetime.date.today() + datetime.timedelta(days=120)
    reasons = []
    if not rec["company_name"] or len(rec["company_name"]) < 3:
        return False, ["missing company_name"]
    if rec["issue_price"] is not None and not (0 < rec["issue_price"] < 100000):
        reasons.append(f"issue_price {rec['issue_price']} out of range"); rec["issue_price"] = None
    if rec["issue_size_cr"] is not None and not (0 < rec["issue_size_cr"] < 500000):
        reasons.append(f"issue_size_cr {rec['issue_size_cr']} out of range"); rec["issue_size_cr"] = None
    for k in ("open_date", "close_date", "listing_date"):
        if rec[k] is not None and not (lo <= rec[k] <= hi):
            reasons.append(f"{k} {rec[k]} out of range"); rec[k] = None
    if rec["open_date"] and rec["close_date"] and rec["open_date"] > rec["close_date"]:
        reasons.append("open_date > close_date"); rec["open_date"] = rec["close_date"] = None
    if rec["close_date"] and rec["listing_date"] and rec["close_date"] > rec["listing_date"]:
        reasons.append("close_date > listing_date"); rec["listing_date"] = None
    if rec["isin"] and not re.fullmatch(r"IN[A-Z0-9]{10}", rec["isin"]):
        reasons.append(f"isin {rec['isin']} malformed"); rec["isin"] = None
    dates = [d for d in (rec["open_date"], rec["close_date"], rec["listing_date"]) if d]
    if dates and all(abs(d.year - year) > 1 for d in dates):
        return False, reasons + [f"all dates outside year {year}"]
    if not dates and rec["issue_price"] is None and rec["issue_size_cr"] is None:
        return False, reasons + ["no usable fields"]
    return True, reasons

# ---------------------------------------------------------------- fetcher ---
def fy_candidates(year):
    return [f"{year}-{(year + 1) % 100:02d}", f"{year - 1}-{year % 100:02d}", str(year)]

def _get_json(ctx, url):
    try:
        r = ctx.request.get(url, headers={"accept": "application/json"}, timeout=30000)
        if not r.ok:
            return []
        data = r.json()
        return data.get("reportTableData") or []
    except Exception:  # noqa: BLE001
        return []

def fetch_year(ctx, year):
    """Union of: FY probe + every month 1-12 + page walk. Deduped by rec_key."""
    # 1. probe FY forms with month=0/page=0; keep the FY that returns most rows
    best_fy, base_rows = fy_candidates(year)[0], []
    for fy in fy_candidates(year):
        rows = _get_json(ctx, API.format(year=year, fy=fy, month=0, page=0))
        if len(rows) > len(base_rows):
            best_fy, base_rows = fy, rows
    seen, out = set(), []
    def add(raw_rows):
        for r in raw_rows:
            m = map_row(r)
            if not m["company_name"]:
                continue
            k = rec_key(m)
            if k not in seen:
                seen.add(k); out.append(m)
    add(base_rows)
    # 2. month walk (the truncation killer): month 1..12, each with a page walk
    for month in range(1, 13):
        prev = -1
        for page in range(0, MAX_PAGES):
            rows = _get_json(ctx, API.format(year=year, fy=best_fy, month=month, page=page))
            if not rows or len(seen) == prev:
                break
            prev = len(seen)
            add(rows)
            time.sleep(0.3)
    # 3. page walk on month=0 too (covers endpoints that page instead of month-filter)
    for page in range(1, MAX_PAGES):
        rows = _get_json(ctx, API.format(year=year, fy=best_fy, month=0, page=page))
        before = len(seen)
        add(rows)
        if not rows or len(seen) == before:
            break
        time.sleep(0.3)
    return out

def fetch_all(years):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright missing — use venv/bin/python (system python3 lacks it)")
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        log.info("warming up (Cloudflare) ...")
        pg.goto(WARMUP_URL, wait_until="domcontentloaded", timeout=60000)
        for _ in range(15):
            if "moment" not in pg.title().lower():
                break
            pg.wait_for_timeout(1500)
        for year in years:
            recs = fetch_year(ctx, year)
            warn = ("  <-- COVERAGE WARN (truncated year? expected more)"
                    if 2010 <= year <= 2025 and len(recs) < MIN_EXPECTED else "")
            log.info(f"{year}: {len(recs)} unique IPOs{warn}")
            out[year] = recs
            time.sleep(1.0)
        b.close()
    return out

# ------------------------------------------------------------------ writer --
UPDATE_COLS = ["open_date", "close_date", "listing_date", "issue_price", "issue_size_cr", "isin"]

def load_existing(cur):
    cur.execute("""SELECT id, company_name, nse_symbol, symbol
                   FROM ipo_intelligence WHERE company_name IS NOT NULL""")
    return [(rid, name, norm_name(name), nsym, sym) for (rid, name, nsym, sym) in cur.fetchall()]

def best_match(rec_norm, existing):
    from rapidfuzz import fuzz
    best, best_score = None, 0
    for row in existing:
        score = fuzz.token_sort_ratio(rec_norm, row[2])
        if score > best_score:
            best, best_score = row, score
    return (best, best_score) if best_score >= FUZZ_THRESHOLD else (None, best_score)

def write_db(cur, recs, year, counters):
    existing = load_existing(cur)
    for rec in recs:
        ok, reasons = sane(rec, year)
        if reasons:
            log.info(f"  sanity {rec.get('company_name')!r}: {'; '.join(reasons)}")
        if not ok:
            counters["skip"] += 1
            continue
        match, _ = best_match(norm_name(rec["company_name"]), existing)
        if match:
            rid, db_name, _, db_nsym, db_sym = match
            sets, vals = [], []
            for c in UPDATE_COLS:
                if rec.get(c) is not None:
                    sets.append(f"{c} = COALESCE({c}, %s)"); vals.append(rec[c])
            if (not (db_nsym or "").strip() and not (db_sym or "").strip()
                    and rec["nse_symbol"] and symbol_prefix_ok(rec["nse_symbol"], db_name)):
                sets.append("nse_symbol = COALESCE(nse_symbol, %s)")
                vals.append(rec["nse_symbol"].upper())
                counters["symw"] += 1
            if sets:
                cur.execute(f"UPDATE ipo_intelligence SET {', '.join(sets)} WHERE id = %s",
                            vals + [rid])
                counters["upd"] += 1
        else:
            cur.execute("SELECT 1 FROM ipo_intelligence WHERE company_name = %s LIMIT 1",
                        (rec["company_name"],))
            if cur.fetchone():
                counters["skip"] += 1
                continue
            cols = ["company_name"] + [c for c in UPDATE_COLS if rec.get(c) is not None]
            vals = [rec["company_name"]] + [rec[c] for c in UPDATE_COLS if rec.get(c) is not None]
            if rec["nse_symbol"] and symbol_prefix_ok(rec["nse_symbol"], rec["company_name"]):
                cols.append("nse_symbol"); vals.append(rec["nse_symbol"].upper())
                counters["symw"] += 1
            ph = ", ".join(["%s"] * len(cols))
            cur.execute(f"INSERT INTO ipo_intelligence ({', '.join(cols)}) VALUES ({ph})", vals)
            counters["ins"] += 1
            existing.append((None, rec["company_name"], norm_name(rec["company_name"]),
                             rec.get("nse_symbol"), None))

# -------------------------------------------------------------------- main --
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int)
    ap.add_argument("--from", dest="y0", type=int)
    ap.add_argument("--to", dest="y1", type=int)
    ap.add_argument("--write-db", action="store_true")
    a = ap.parse_args()
    if a.year:
        years = [a.year]
    elif a.y0 and a.y1:
        years = list(range(a.y0, a.y1 + 1))
    else:
        years = [datetime.date.today().year]

    raw = fetch_all(years)
    counters = {"ins": 0, "upd": 0, "symw": 0, "skip": 0}
    if a.write_db:
        try:
            import psycopg2
        except ImportError:
            sys.exit("psycopg2 missing — use venv/bin/python")
        if not DB:
            sys.exit("DATABASE_URL not set (run: set -a && . ./.env && set +a)")
        conn = psycopg2.connect(DB, connect_timeout=15)
        cur = conn.cursor()
        for year in years:
            log.info(f"{year}: writing {len(raw.get(year, []))} rows")
            write_db(cur, raw.get(year, []), year, counters)
            conn.commit()
        conn.close()
    else:
        for year in years:
            for m in raw.get(year, []):
                ok, reasons = sane(m, year)
                flag = "" if ok else "  REJECT"
                log.info(f"  {m['company_name'][:38]:38} open={m['open_date']} "
                         f"list={m['listing_date']} px={m['issue_price']} "
                         f"sz={m['issue_size_cr']} sym={m['nse_symbol']}{flag}"
                         + (f"  [{'; '.join(reasons)}]" if reasons else ""))
        log.info("DRY-RUN — add --write-db to write.")
    print(f"ins={counters['ins']} upd={counters['upd']} symw={counters['symw']} skip={counters['skip']}")

if __name__ == "__main__":
    main()
