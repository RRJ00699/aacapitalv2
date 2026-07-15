#!/usr/bin/env python3
"""
scrape_chittorgarh.py (v3, FINAL) — Chittorgarh mainboard IPO calendar -> ipo_intelligence.

Built on probe evidence (chittorgarh_probe.py, 2026-07-05):
  * URL slot after the report id is the PAGE NUMBER (pages of ~5, date desc):
      .../data-read/82/{PAGE}/7/{YEAR}/{FY}/0/mainboard/0
    v3 walks pages until empty/repeat -> full year coverage.
  * Dates come from clean ISO tilde keys: ~Issue_Open_Date, ~IssueCloseDate,
    ~ListingDate (display keys are '21-Dec-2021' and unreliable).
  * ~nse_symbol / ~isin / ~URLRewrite_Folder_Name confirmed present.
  * 'Lead Manager' present -> fills brlm_names (fill-empty, column-checked).

WRITE DISCIPLINE (Rule 1):
  * fill-EMPTY-only (COALESCE) for raw facts; INSERT only when no fuzzy match.
  * join by fuzzy company name (rapidfuzz token_sort_ratio >= 90), never by
    Chittorgarh's unreliable ~nse_symbol (Dixon->KFINTECH, Advit->RAMBHAJO).
  * scraped symbol written ONLY where BOTH nse_symbol and symbol are blank AND
    the symbol prefix matches the company name. Never overwrites.
  * value-sanity per row BEFORE commit; HARD failures skipped and counted.
  * COVERAGE WARN if a 2010-2025 year yields <10 rows (truncation alarm).

Usage (VM):
  venv/bin/python _scripts/scrape_chittorgarh.py --year 2021              # dry-run gate
  venv/bin/python _scripts/scrape_chittorgarh.py --from 2010 --to 2026 --write-db
  venv/bin/python _scripts/scrape_chittorgarh.py --write-db               # pipeline mode: current year
Prints:  ins= upd= symw= skip=
"""
import os, sys, re, json, time, argparse, datetime, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scrape_chittorgarh")

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
API = ("https://webnodejs.chittorgarh.com/cloud/report/data-read/"
       "82/{page}/7/{year}/{fy}/0/mainboard/0?search=&v=21-38")
WARMUP_URL = "https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82/mainboard/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
FUZZ_THRESHOLD = 90
MAX_PAGES = 60          # 60 * ~5 = 300 IPOs/year headroom
MIN_EXPECTED = 10
_NULLISH = {"", "-", "\u2014", "n/a", "na", "nan", "none", "null", "tbd", "--"}

# ---------------------------------------------------------------- parsers ---
def clean_str(v):
    if v is None:
        return None
    s = re.sub(r"<[^>]+>", " ", str(v))
    s = re.sub(r"\s+", " ", s).strip()
    return None if s.lower() in _NULLISH else s

def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = clean_str(v)
    if s is None:
        return None
    s = s.replace("\u20b9", "").replace(",", "")
    nums = [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", s)]
    return max(nums) if nums else None       # bands like '300 to 316' -> upper

def iso_date(v):
    """'2021-12-21T00:00:00.000Z' or '2021-12-21' -> date; '21-Dec-2021' fallback."""
    s = None if v is None else str(v).strip()
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", s)
    if m:
        try:
            return datetime.datetime.strptime(m.group(), "%d-%b-%Y").date()
        except ValueError:
            return None
    return None

def norm_name(s):
    s = (s or "").lower()
    s = re.sub(r"\b(limited|ltd\.?|ipo|india|the)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # NSE series-code artifacts at the tail ("kusumgar lt" == "kusumgar")
    return re.sub(r"\s+(lt|o|ct)$", "", s).strip()

def symbol_prefix_ok(symbol, company):
    if not symbol or not company:
        return False
    sym = re.sub(r"[^A-Z0-9]", "", symbol.upper())
    comp = re.sub(r"[^A-Z0-9]", "", norm_name(company).upper())
    if len(sym) < 3 or len(comp) < 3:
        return False
    k = min(4, len(sym), len(comp))
    return comp.startswith(sym[:k]) or sym.startswith(comp[:k])

# ---------------------------------------------------------------- mapping ---
def pick(row, *patterns):
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for k in row.keys():
            if rx.search(k):
                return row[k]
    return None

def map_row(row):
    company = clean_str(row.get("Company") or pick(row, r"company|issuer"))
    if company:
        company = re.sub(r"\s*IPO$", "", company, flags=re.I).strip()
        # strip trailing NSE series-code artifacts (" LT"/" O"/" CT") that created
        # twin rows (Kusumgar 2026-07-15: "Ltd. LT" variant split the data)
        company = re.sub(r"\s+(LT|O|CT)$", "", company).strip()
    return {
        "company_name":  company,
        # tilde ISO keys are authoritative (probe-verified); display keys fallback
        "open_date":     iso_date(row.get("~Issue_Open_Date")) or iso_date(pick(row, r"open(ing)?\s*date")),
        "close_date":    iso_date(row.get("~IssueCloseDate")) or iso_date(pick(row, r"clos(e|ing)\s*date")),
        "listing_date":  iso_date(row.get("~ListingDate")) or iso_date(pick(row, r"listing\s*date")),
        "issue_price":   num(pick(row, r"issue\s*price")),
        "issue_size_cr": num(pick(row, r"total\s*issue|issue\s*(amount|size)")),
        "nse_symbol":    clean_str(row.get("~nse_symbol")),
        "isin":          clean_str(row.get("~isin")),
        "slug":          clean_str(row.get("~URLRewrite_Folder_Name")),
        "brlm_names":    clean_str(row.get("Lead Manager") or pick(row, r"lead\s*manager")),
    }

def rec_key(rec):
    return rec.get("slug") or (norm_name(rec.get("company_name")), str(rec.get("open_date")))

# ------------------------------------------------------------ sanity gate ---
def sane(rec, year):
    lo, hi = datetime.date(2005, 1, 1), datetime.date.today() + datetime.timedelta(days=180)
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
def _get_rows(ctx, url):
    try:
        r = ctx.request.get(url, headers={"accept": "application/json"}, timeout=30000)
        if not r.ok:
            return []
        return (r.json() or {}).get("reportTableData") or []
    except Exception:  # noqa: BLE001
        return []

def fetch_year(ctx, year):
    fy = f"{year}-{(year + 1) % 100:02d}"
    seen, out = set(), []
    for page in range(1, MAX_PAGES + 1):
        rows = _get_rows(ctx, API.format(page=page, year=year, fy=fy))
        if not rows:
            break
        new = 0
        for r in rows:
            m = map_row(r)
            if not m["company_name"]:
                continue
            k = rec_key(m)
            if k not in seen:
                seen.add(k); out.append(m); new += 1
        if new == 0:                     # page repeated -> past the end
            break
        time.sleep(0.25)
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
            warn = ("  <-- COVERAGE WARN (truncated year?)"
                    if 2010 <= year <= 2025 and len(recs) < MIN_EXPECTED else "")
            log.info(f"{year}: {len(recs)} unique IPOs{warn}")
            out[year] = recs
            time.sleep(0.8)
        b.close()
    return out

# ------------------------------------------------------------------ writer --
UPDATE_COLS = ["open_date", "close_date", "listing_date", "issue_price",
               "issue_size_cr", "isin", "brlm_names"]

def valid_columns(cur):
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name='ipo_intelligence'")
    return {c for (c,) in cur.fetchall()}

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

def write_db(cur, recs, year, counters, cols_ok):
    existing = load_existing(cur)
    upd_cols = [c for c in UPDATE_COLS if c in cols_ok]
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
            for c in upd_cols:
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
            cols = ["company_name"] + [c for c in upd_cols if rec.get(c) is not None]
            vals = [rec["company_name"]] + [rec[c] for c in upd_cols if rec.get(c) is not None]
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
        cols_ok = valid_columns(cur)
        for year in years:
            log.info(f"{year}: writing {len(raw.get(year, []))} rows")
            write_db(cur, raw.get(year, []), year, counters, cols_ok)
            conn.commit()
        conn.close()
    else:
        for year in years:
            for m in raw.get(year, []):
                ok, reasons = sane(m, year)
                flag = "" if ok else "  REJECT"
                log.info(f"  {(m['company_name'] or '?')[:38]:38} open={m['open_date']} "
                         f"list={m['listing_date']} px={m['issue_price']} "
                         f"sz={m['issue_size_cr']} sym={m['nse_symbol']} brlm={m['brlm_names']}{flag}"
                         + (f"  [{'; '.join(reasons)}]" if reasons else ""))
        log.info("DRY-RUN — add --write-db to write.")
    print(f"ins={counters['ins']} upd={counters['upd']} symw={counters['symw']} skip={counters['skip']}")

if __name__ == "__main__":
    main()
