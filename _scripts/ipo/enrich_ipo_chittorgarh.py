#!/usr/bin/env python3
"""
enrich_ipo_chittorgarh.py — live per-IPO enrichment (IPOMatrix index + Chittorgarh detail).

Two data sources, both Chittorgarh-family (trusted):
  1. IPOMatrix anchor-report API (alphanodejs.chittorgarh.com) — a clean POST API that
     returns the FULL YEAR of IPOs with: chittorgarh id, slug, nse_symbol, isin,
     issue_price, anchor ₹cr, anchor lock-in dates, open/close dates. This is the INDEX
     (name -> id) AND fills several fields inline. Covers listed + current (fixes the
     "current-only" gap of the old HTML list scrape).
  2. Chittorgarh detail page embedded JSON — for the RICH per-IPO fields the index lacks:
     final subscription by category, RoNW/PE KPIs, BRLM names, anchor names + count.

Resolution is now authoritative: IPOMatrix gives the exact id + nse_symbol, so no fuzzy
guessing of the symbol. (GMP still not here — Chittorgarh links out to investorgain.)

Usage:
  python _scripts/ipo/enrich_ipo_chittorgarh.py --resolve "Turtlemint"          # show matched id/symbol
  python _scripts/ipo/enrich_ipo_chittorgarh.py --company "CSM Technologies"     # auto-resolve + enrich (dry-run)
  python _scripts/ipo/enrich_ipo_chittorgarh.py --company "CSM Technologies" --apply
  python _scripts/ipo/enrich_ipo_chittorgarh.py --auto [--apply]                 # every bare row (post-NSE hook)
  python _scripts/ipo/enrich_ipo_chittorgarh.py --url "<chittorgarh sub url>" --probe
  python _scripts/ipo/enrich_ipo_chittorgarh.py --years 2026,2025,2024           # widen historical index
Install:  pip install curl_cffi psycopg2-binary
"""
import os, sys, re, json, time, argparse, logging, difflib
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("chittorgarh")

try:
    from curl_cffi import requests as cffi
except ImportError:
    sys.exit("pip install curl_cffi")

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
IPOMATRIX_URL = "https://alphanodejs.chittorgarh.com/api/media-report-data-read"
ANCHOR_REPORT_ID = 163

# Short-lived JWT the IPOMatrix SPA sends as x-access-token. This is a ONE-TIME
# historical backfill, so a hardcoded token is fine — it only needs to live for this run.
# If it ever returns "Invalid request!" again, the token expired: grab a fresh one from
# DevTools (any media-report-data-read request -> Copy as cURL -> the x-access-token header).
IPOMATRIX_TOKEN = os.environ.get("IPOMATRIX_TOKEN") or (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpZCI6MTAzOTU5LCJyb2xlX2lkIjoxLCJzaWQiOiJkMjA0Y2E1N2NmMTMwYjFiNzJhMjNjZTY5NTE3ZmMzZWUyZjRkYWQ1YjIyNzZmYjlkOTMxMWYwNmIxOTVmNzY5IiwidG9vbCI6Im1lZGlhIiwidGVtcF90b2tlbiI6ZmFsc2UsImlhdCI6MTc4MTk3ODQzNywiZXhwIjoxNzg0NTcwNDM3fQ."
    "he5NdvRAPDNocDbf0aY-OwoYVphf_hcFQEL70KQb3Ic"
)
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://www.ipomatrix.com",
    "referer": "https://www.ipomatrix.com/",
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"),
    "x-access-token": IPOMATRIX_TOKEN,
}
_NULLISH = {"", "-", "—", "n/a", "na", "nan", "none", "null", "tbd", "--"}


# ── parsers ──────────────────────────────────────────────────────────────────
def clean_str(v):
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in _NULLISH else s


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = clean_str(v)
    if s is None:
        return None
    s = s.replace("\u20b9", "").replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def parse_date(v):
    s = clean_str(v)
    if not s:
        return None
    s = re.sub(r"^[A-Za-z]+day,\s*", "", s).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %b %Y", "%d %b, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def isodate(v):
    s = clean_str(v)
    return s[:10] if s and re.match(r"\d{4}-\d{2}-\d{2}", s) else None


# ── IPOMatrix anchor-report API: the index (name -> id) + inline fields ───────
_IPOMATRIX_SESSION = None
DEBUG = False


def _ipomatrix_session():
    """One primed session — GET the site first so any cookie the API checks is set."""
    global _IPOMATRIX_SESSION
    if _IPOMATRIX_SESSION is None:
        s = cffi.Session(impersonate="chrome124")
        try:
            s.get("https://www.ipomatrix.com/report/163/mainboard/?year=2026",
                  headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        except Exception:  # noqa: BLE001
            pass
        _IPOMATRIX_SESSION = s
    return _IPOMATRIX_SESSION


def _post_ipomatrix(year, segment, month=None, pageno=1):
    if month is None:
        month = datetime.now().month          # API validates month against current month
    body = {
        "id": ANCHOR_REPORT_ID, "pageno": pageno, "month": month, "year": str(year),
        "fy": f"{year}-{(year + 1) % 100:02d}", "sort": "0", "param_id": segment,
        "sub_param_id": "0", "search": "", "extraParam": "", "minplandate": "2006-01-01",
    }
    s = _ipomatrix_session()
    # json=body lets curl_cffi set Content-Type + serialize so Express json middleware parses it
    r = s.post(IPOMATRIX_URL, headers=HEADERS, json=body, timeout=25)
    if DEBUG:
        log.info(f"  [debug] POST {r.status_code}  body={json.dumps(body)}")
        log.info(f"  [debug] resp={r.text[:400]}")
    if r.status_code != 200:
        raise RuntimeError(f"IPOMatrix HTTP {r.status_code}: {r.text[:200]}")
    j = r.json()
    if j.get("msg") != 1:
        raise RuntimeError(f"IPOMatrix error: {j.get('error')} (sent: {json.dumps(body)})")
    return j


_SUFFIX = re.compile(r'\b(ltd|limited|ipo|details|pvt|private|the|reit|invit|investment|trust)\b', re.I)
def _norm(n):
    n = re.sub(r'\([^)]*\)', ' ', str(n)).lower()
    n = _SUFFIX.sub(' ', n)
    n = re.sub(r'[^a-z0-9]+', ' ', n).strip()
    return re.sub(r'\s+', ' ', n)


def _record(row):
    """One IPOMatrix row -> our record dict (index value)."""
    return {
        "id": row.get("~id"),
        "slug": clean_str(row.get("~URLRewrite_Folder_Name")),
        "company": clean_str(row.get("Company")),
        "nse_symbol": clean_str(row.get("~nse_symbol")),
        "isin": clean_str(row.get("~isin")),
        "is_sme": row.get("Issue Category") == "SME",
        "issue_price": num(row.get("Anchor Issue Price (Rs.)")),
        "anchor_total_cr": num(row.get("Allocation to Anchor Investors (Rs.cr.)")),
        "anchor_lock30_date": parse_date(row.get("Anchor Lock In Expiry Date(30 Days)")),
        "anchor_lock90_date": parse_date(row.get("Anchor Lock In Expiry Date(90 Days)")),
        "close_date": isodate(row.get("~IssueCloseDate")),
        "open_date": isodate(row.get("~issue_open_date_plan")),
    }


def build_index(years):
    """{normalized_company -> record} from the IPOMatrix anchor report, full year(s).

    The API splits by segment (param_id), so we query 'mainboard' and 'sme' separately.
    """
    index = {}
    for y in years:
        for segment in ("mainboard",):   # mainboard only — SME not needed, and fewer near-name collisions
            try:
                page = 1
                while True:
                    j = _post_ipomatrix(y, segment, pageno=page)
                    rows = j.get("reportTableData") or []
                    n0 = len(index)
                    for row in rows:
                        rec = _record(row)
                        if rec["slug"] and rec["company"]:
                            key = _norm(rec["company"])
                            index.setdefault(key, rec)
                    log.info(f"  IPOMatrix {y} {segment} p{page}: {len(rows)} rows "
                             f"(+{len(index)-n0}, total {len(index)})")
                    if page >= int(j.get("totalPages", 1)):
                        break
                    page += 1
                    time.sleep(0.8)
            except Exception as e:  # noqa: BLE001
                log.warning(f"  IPOMatrix {y} {segment} failed: {e}")
            time.sleep(0.8)
    return index


def resolve(company, index):
    """EXACT normalized-name match only. No fuzzy — fuzzy across different companies
    produces dangerous false positives (e.g. Equitas -> Utkarsh). If a name isn't in
    the index, that's an honest no-match, not an excuse to grab the nearest string."""
    key = _norm(company)
    if key and key in index:
        return index[key], 1.0, "exact"
    return None, 0.0, "none"


def closest_hint(company, index):
    """Read-only: nearest name, shown as a hint in --resolve. NEVER used for writes."""
    key = _norm(company)
    m = difflib.get_close_matches(key, list(index), n=1, cutoff=0.6)
    if m:
        r = round(difflib.SequenceMatcher(None, key, m[0]).ratio(), 3)
        return index[m[0]], r
    return None, 0.0


def sub_url(rec):
    return f"https://www.chittorgarh.com/ipo_subscription/{rec['slug']}/{rec['id']}/"


def map_record(rec):
    """Inline fields from the IPOMatrix index (no detail fetch needed)."""
    f = {
        "nse_symbol": rec.get("nse_symbol"),
        "isin": rec.get("isin"),
        "issue_price": rec.get("issue_price"),
        "anchor_total_cr": rec.get("anchor_total_cr"),
        "anchor_lock30_date": rec.get("anchor_lock30_date"),
        "anchor_lock90_date": rec.get("anchor_lock90_date"),
        "close_date": rec.get("close_date"),
        "open_date": rec.get("open_date"),
    }
    return {k: v for k, v in f.items() if v is not None}


# ── Chittorgarh detail page: embedded JSON for the RICH fields ────────────────
def fetch_html(url):
    s = cffi.Session(impersonate="chrome124")
    try:
        s.get("https://www.chittorgarh.com/", headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
    except Exception:  # noqa: BLE001
        pass
    r = s.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.chittorgarh.com/"}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"detail HTTP {r.status_code} for {url}")
    return r.text


def _balanced(s, i):
    open_ch = s[i]; close_ch = {"{": "}", "[": "]"}[open_ch]
    depth = 0; in_str = False; esc = False
    for j in range(i, len(s)):
        c = s[j]
        if in_str:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': in_str = False
        else:
            if c == '"': in_str = True
            elif c == open_ch: depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return s[i:j + 1]
    return None


def _decode_next_payload(html):
    out = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,\s*("(?:[^"\\]|\\.)*")\s*\]\)', html, re.S):
        try:
            out.append(json.loads(m.group(1)))
        except Exception:  # noqa: BLE001
            pass
    return "".join(out)


def _grab(payload, key):
    m = re.search(r'"%s":\s*([\[{])' % re.escape(key), payload)
    if not m:
        return None
    blob = _balanced(payload, m.start(1))
    try:
        return json.loads(blob) if blob else None
    except Exception:  # noqa: BLE001
        return None


def detail_fields(url):
    """RICH fields from the detail page: subscription, KPIs, BRLMs, anchor names/count."""
    try:
        html = fetch_html(url)
    except RuntimeError as e:
        log.warning(f"  detail fetch failed: {e}")
        return {}
    payload = _decode_next_payload(html)
    ipo_list = _grab(payload, "ipoData")
    ipo = ipo_list[0] if isinstance(ipo_list, list) and ipo_list else None
    sub_resp = _grab(payload, "subscriptionDataResponse")
    sub = None
    if isinstance(sub_resp, dict):
        bids = sub_resp.get("ipoBiddingDetails") or []
        sub = bids[0] if bids else None
    f = {}
    if ipo:
        f["roe"] = num(ipo.get("kpi_ronw")) or num(ipo.get("kpi_roe"))
        f["ipo_pe"] = num(ipo.get("pe_ratio"))
        f["promoter_holding_post"] = num(ipo.get("promoter_shareholding_post_issue"))
        lms = ipo.get("ipoLeadManagersList") or []
        names = [clean_str(x.get("comp_name")) for x in lms if clean_str(x.get("comp_name"))]
        if names:
            f["brlm_names"] = ", ".join(names)
        if not ipo.get("issue_price_final") and not f.get("issue_price"):
            f["issue_price"] = num(ipo.get("issue_price_upper"))
    if sub:
        f["total_subscription_x"] = num(sub.get("total"))
        f["qib_subscription_x"] = num(sub.get("qib"))
    anchors = []
    mt = re.search(r"id=['\"]AnchorTable['\"].*?</table>", html, re.S) if 'html' in dir() else None
    if mt:
        for am in re.finditer(r'ipo-anchor-list-vs-listing-gain/\d+/\w+/\d+"[^>]*>\s*([^<]+?)\s*</a>', mt.group()):
            nm = clean_str(am.group(1))
            if nm:
                anchors.append(nm)
    if anchors:
        f["anchor_names"] = json.dumps(anchors)
        f["anchor_count"] = len(anchors)
    return {k: v for k, v in f.items() if v is not None}


# ── upsert ───────────────────────────────────────────────────────────────────
def upsert(company, fields, apply):
    if not fields:
        log.info("  nothing parsed.")
        return
    if not apply:
        for k, v in fields.items():
            log.info(f"      {k:22} {v}")
        log.info("  DRY-RUN — add --apply to write.")
        return
    import psycopg2
    if not DB:
        sys.exit("DATABASE_URL not set.")
    conn = psycopg2.connect(DB); cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    valid = {c for (c,) in cur.fetchall()}
    writable = {k: v for k, v in fields.items() if k in valid}
    skipped = sorted(set(fields) - set(writable))
    if skipped:
        log.info(f"  (skipped, no such column: {skipped})")
    if not writable:
        conn.close(); return
    cur.execute("SELECT id, company_name FROM ipo_intelligence WHERE company_name ILIKE %s", [f"%{company}%"])
    hits = cur.fetchall()
    if len(hits) != 1:
        log.info(f"  match ambiguous ({len(hits)}) — skipped.")
        conn.close(); return
    rid = hits[0][0]
    sets = ", ".join(f"{k} = COALESCE(%s, {k})" for k in writable)
    cur.execute(f"UPDATE ipo_intelligence SET {sets} WHERE id = %s", list(writable.values()) + [rid])
    conn.commit()
    log.info(f"  APPLIED id={rid}: {list(writable.keys())}")
    conn.close()


def enrich(company, rec, apply, with_detail=True):
    fields = map_record(rec)                 # inline IPOMatrix fields (cheap, authoritative)
    if with_detail:
        fields = {**detail_fields(sub_url(rec)), **fields}   # index wins on overlap
    log.info(f"  {company!r} -> id={rec['id']} sym={rec.get('nse_symbol')}  {len(fields)} fields")
    upsert(company, fields, apply)
    return fields


# ── modes ────────────────────────────────────────────────────────────────────
def cmd_resolve(company, years):
    index = build_index(years)
    rec, score, how = resolve(company, index)
    if rec:
        log.info(f"\n{company!r} -> id={rec['id']} symbol={rec.get('nse_symbol')} isin={rec.get('isin')} "
                 f"({how} {score})  [{rec['company']}]")
        log.info(f"  {sub_url(rec)}")
        log.info(f"  inline: issue_price={rec.get('issue_price')} anchor_cr={rec.get('anchor_total_cr')} "
                 f"lock30={rec.get('anchor_lock30_date')}")
    else:
        log.info(f"\n{company!r} -> NO EXACT MATCH (not in index for those years)")
        hint, hs = closest_hint(company, index)
        if hint:
            log.info(f"  closest name (HINT ONLY, never written): {hint['company']} "
                     f"id={hint['id']} sym={hint.get('nse_symbol')}  (ratio {hs})")
            log.info(f"  if that's truly the same IPO, enrich it explicitly with --url {sub_url(hint)}")


def cmd_company(company, years, apply):
    index = build_index(years)
    rec, score, how = resolve(company, index)
    if not rec:
        log.info(f"{company!r}: no match."); return
    enrich(company, rec, apply)


def cmd_auto(years, apply, limit):
    import psycopg2
    if not DB:
        sys.exit("DATABASE_URL not set.")
    conn = psycopg2.connect(DB); cur = conn.cursor()
    cur.execute("""SELECT id, company_name FROM ipo_intelligence
                   WHERE company_name IS NOT NULL
                     AND (issue_price IS NULL OR total_subscription_x IS NULL OR nse_symbol IS NULL)
                   ORDER BY id DESC LIMIT %s""", [limit])
    rows = cur.fetchall(); conn.close()
    log.info(f"{len(rows)} bare rows. Building IPOMatrix index...")
    index = build_index(years)
    stats = {"enriched": 0, "no_match": 0}
    for rid, name in rows:
        rec, score, how = resolve(name, index)
        if not rec:
            log.info(f"  [{rid}] {name[:36]:36} -> no match"); stats["no_match"] += 1; continue
        log.info(f"  [{rid}] {name[:36]:36} -> id={rec['id']} ({how} {score})"
                 + ("" if apply else " [dry-run]"))
        enrich(name, rec, apply)
        stats["enriched"] += 1
        time.sleep(1.2)
    log.info(f"\nDONE: {stats}  {'(APPLIED)' if apply else '(dry-run; add --apply)'}")


def probe(url):
    f = detail_fields(url)
    log.info(f"detail fields parsed ({len(f)}):")
    for k, v in f.items():
        log.info(f"    {k:22} {v}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--company")
    ap.add_argument("--resolve", metavar="COMPANY")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--years", default=None, help="comma years to index (default: current,prev)")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--debug", action="store_true", help="dump raw IPOMatrix POST + response")
    args = ap.parse_args()

    global DEBUG
    DEBUG = args.debug

    ty = datetime.now().year
    years = ([int(y) for y in args.years.split(",")] if args.years else [ty, ty - 1])

    if args.resolve:
        cmd_resolve(args.resolve, years); return
    if args.auto:
        cmd_auto(years, args.apply, args.limit); return
    if args.url and args.probe:
        probe(args.url); return
    if args.company:
        cmd_company(args.company, years, args.apply); return
    ap.error("need one of: --company, --resolve, --auto, or --url --probe")


if __name__ == "__main__":
    main()
