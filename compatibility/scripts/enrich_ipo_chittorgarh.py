#!/usr/bin/env python3
"""
enrich_ipo_chittorgarh.py — live per-IPO enrichment from Chittorgarh.

Chittorgarh is a Next.js app that embeds the WHOLE IPO as a structured JSON blob
in the page (the __next_f payload). We parse that JSON directly — far more robust
than scraping HTML tables, which restyle often. curl_cffi (chrome impersonation)
clears the bot-wall, same trick fetch_nse_ipos.py uses for NSE.

Fills the fields NSE feeds can't give for a freshly-caught IPO: issue_price, final
subscription by category, anchors, KPIs (RoNW/PE), promoter holding, BRLMs — so it
can run right after fetch_nse_ipos.py and every new IPO arrives enriched.
(GMP is NOT on this page — Chittorgarh links out to investorgain for GMP; that's a
separate later fetch into gmp_history_json.)

STEP 1 (this script): enrich ONE IPO by explicit Chittorgarh URL, with --probe.
STEP 2 (next): name->id resolver via the IPO-list report + post-NSE hook.

Usage:
  python _scripts/ipo/enrich_ipo_chittorgarh.py --url ".../ipo_subscription/csm-technologies-ipo/2641/" --probe
  python _scripts/ipo/enrich_ipo_chittorgarh.py --url "<url>" --company "CSM Technologies"          # dry-run
  python _scripts/ipo/enrich_ipo_chittorgarh.py --url "<url>" --company "CSM Technologies" --apply  # write
Install:  pip install curl_cffi psycopg2-binary
"""
import os, sys, re, json, argparse, logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("chittorgarh")

try:
    from curl_cffi import requests as cffi
except ImportError:
    sys.exit("pip install curl_cffi")

DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9",
           "Referer": "https://www.chittorgarh.com/"}
_NULLISH = {"", "-", "—", "n/a", "na", "nan", "none", "null", "tbd", "--"}


def clean_str(v):
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in _NULLISH else s


def num(v):
    """'18.49%' -> 18.49 ; '113.00' -> 113.0 ; 31.05 -> 31.05 ; nullish -> None"""
    if isinstance(v, (int, float)):
        return float(v)
    s = clean_str(v)
    if s is None:
        return None
    s = s.replace("\u20b9", "").replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def parse_date(v):
    """'June 29, 2026' / 'Thursday, July 2, 2026' -> '2026-06-29'."""
    s = clean_str(v)
    if not s:
        return None
    s = re.sub(r"^[A-Za-z]+day,\s*", "", s).strip()  # drop weekday
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def fetch_html(url):
    s = cffi.Session(impersonate="chrome124")
    try:
        s.get("https://www.chittorgarh.com/", headers=HEADERS, timeout=12)
    except Exception as e:  # noqa: BLE001
        log.warning("prime warning (continuing): %s", e)
    r = s.get(url, headers=HEADERS, timeout=20)
    if r.status_code != 200:
        sys.exit(f"HTTP {r.status_code} for {url} — Chittorgarh may be blocking; retry or check URL.")
    return r.text


# ---- embedded-JSON extraction (the robust core) ----------------------------
def _balanced(s, i):
    """Return the balanced {...}/[...] starting at s[i], string-literal aware."""
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
    """Concatenate every self.__next_f.push([1,"..."]) decoded string into one blob."""
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
    if blob is None:
        return None
    try:
        return json.loads(blob)
    except Exception:  # noqa: BLE001
        return None


def extract(url, want_raw=False):
    html = fetch_html(url)
    payload = _decode_next_payload(html)
    ipo_list = _grab(payload, "ipoData")
    sub_resp = _grab(payload, "subscriptionDataResponse")
    ipo = ipo_list[0] if isinstance(ipo_list, list) and ipo_list else None
    sub = None
    if isinstance(sub_resp, dict):
        bids = sub_resp.get("ipoBiddingDetails") or []
        sub = bids[0] if bids else None
    if want_raw:
        return ipo, sub, html
    return ipo, sub, html


def map_fields(ipo, sub, html):
    """Translate the embedded JSON into ipo_intelligence columns (candidates)."""
    f = {}
    if ipo:
        f["issue_price"] = num(ipo.get("issue_price_final")) or num(ipo.get("issue_price_upper"))
        f["nse_symbol"] = clean_str(ipo.get("nse_symbol"))
        f["close_date"] = parse_date(ipo.get("issue_close_date"))
        f["open_date"] = parse_date(ipo.get("issue_open_date"))
        f["roe"] = num(ipo.get("kpi_ronw")) or num(ipo.get("kpi_roe"))
        f["ipo_pe"] = num(ipo.get("pe_ratio"))
        f["promoter_holding_pre"] = num(ipo.get("promoter_shareholding_pre_issue"))
        f["promoter_holding_post"] = num(ipo.get("promoter_shareholding_post_issue"))
        # BRLMs
        lms = ipo.get("ipoLeadManagersList") or []
        names = [clean_str(x.get("comp_name")) for x in lms if clean_str(x.get("comp_name"))]
        if not names and ipo.get("primary_lead_data"):
            n = clean_str(ipo["primary_lead_data"].get("comp_name"))
            if n: names = [n]
        if names:
            f["brlm_names"] = ", ".join(names)
        # anchors: amount/shares present in JSON; names from the AnchorTable HTML
        if ipo.get("shares_offered_anchor_investor"):
            f["anchor_total_shares"] = num(ipo.get("shares_offered_anchor_investor"))
    if sub:
        f["total_subscription_x"] = num(sub.get("total"))
        f["qib_subscription_x"] = num(sub.get("qib"))
        f["nii_subscription_x"] = num(sub.get("nii"))
        f["retail_subscription_x"] = num(sub.get("rii"))
        f["emp_subscription_x"] = num(sub.get("emp"))
    # anchor names from AnchorTable in raw HTML (best-effort)
    anchors = []
    mt = re.search(r"id=['\"]AnchorTable['\"].*?</table>", html, re.S)
    if mt:
        for am in re.finditer(r'ipo-anchor-list-vs-listing-gain/\d+/\w+/\d+"[^>]*>\s*([^<]+?)\s*</a>', mt.group()):
            nm = clean_str(am.group(1))
            if nm:
                anchors.append(nm)
    if anchors:
        f["anchor_names"] = json.dumps(anchors)
        f["anchor_count"] = len(anchors)
    return {k: v for k, v in f.items() if v is not None}


def upsert(company, fields, apply):
    if not fields:
        log.info("nothing parsed — embedded JSON not found; re-run with --probe.")
        return
    log.info(f"parsed {len(fields)} fields for {company!r}:")
    for k, v in fields.items():
        log.info(f"    {k:24} {v}")
    if not apply:
        log.info("DRY-RUN — add --apply to write (only columns that exist in ipo_intelligence).")
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
        log.info(f"(no such columns, skipped: {skipped})")
    if not writable:
        log.info("nothing maps to an existing column — nothing written.")
        conn.close(); return
    cur.execute("SELECT id, company_name FROM ipo_intelligence WHERE company_name ILIKE %s", [f"%{company}%"])
    hits = cur.fetchall()
    if len(hits) != 1:
        log.info(f"company match ambiguous ({len(hits)}) — be more specific with --company:")
        for h in hits[:10]:
            log.info(f"    {h}")
        conn.close(); return
    rid = hits[0][0]
    sets = ", ".join(f"{k} = COALESCE(%s, {k})" for k in writable)
    cur.execute(f"UPDATE ipo_intelligence SET {sets} WHERE id = %s", list(writable.values()) + [rid])
    conn.commit()
    log.info(f"APPLIED to id={rid} ({hits[0][1]}): {list(writable.keys())}")
    conn.close()


def probe(url):
    ipo, sub, html = extract(url, want_raw=True)
    log.info(f"fetched {len(html)} chars")
    log.info(f"ipoData found: {bool(ipo)}   subscription found: {bool(sub)}\n")
    if ipo:
        keys = [k for k in ("company_name", "nse_symbol", "issue_price_upper", "issue_price_final",
                            "issue_close_date", "timetable_listing_dt", "kpi_ronw", "kpi_roe",
                            "pe_ratio", "post_pe_ratio", "shares_offered_anchor_investor",
                            "promoter_shareholding_pre_issue", "promoter_shareholding_post_issue") if k in ipo]
        log.info("ipoData key fields:")
        for k in keys:
            log.info(f"    {k:34} {ipo[k]}")
    if sub:
        log.info("\nsubscription (times):")
        for k in ("qib", "nii", "rii", "emp", "total", "total_application"):
            if k in sub:
                log.info(f"    {k:34} {sub[k]}")
    log.info("\n--- mapped candidate fields ---")
    for k, v in map_fields(ipo, sub, html).items():
        log.info(f"    {k:24} {v}")



# ============================ STEP 2: name -> id resolver + post-NSE hook ====
import time, difflib

_SUFFIX = re.compile(r'\b(ltd|limited|ipo|details|pvt|private|the)\b', re.I)
def _norm(n):
    n = re.sub(r'\([^)]*\)', ' ', str(n)).lower()
    n = _SUFFIX.sub(' ', n)
    n = re.sub(r'[^a-z0-9]+', ' ', n).strip()
    return re.sub(r'\s+', ' ', n)

_ANCHOR_RX = re.compile(r'/ipo/([a-z0-9][a-z0-9-]+?)/(\d+)/[^>]*>\s*([^<]+?)\s*</a>')

def build_index(years):
    """Fetch Chittorgarh IPO-list reports and map {normalized_company -> (slug,id,name)}."""
    base = "https://www.chittorgarh.com/report/ipo-in-india-list-main-board-sme/82"
    index = {}
    for ex in ("mainboard", "sme"):
        for y in years:
            url = f"{base}/{ex}/?year={y}"
            try:
                html = fetch_html(url)
            except SystemExit:
                log.warning(f"  list fetch failed: {ex} {y} (skipping)")
                continue
            n0 = len(index)
            for slug, ipo_id, name in _ANCHOR_RX.findall(html):
                if "ipo" not in slug:        # detail links contain '-ipo' slugs
                    continue
                key = _norm(name)
                if key and key not in index:
                    index[key] = (slug, ipo_id, name.strip())
            log.info(f"  indexed {ex} {y}: +{len(index)-n0} (total {len(index)})")
            time.sleep(1.0)
    return index

def resolve(company, index, cutoff=0.80):
    key = _norm(company)
    if key in index:
        return index[key], 1.0, "exact"
    m = difflib.get_close_matches(key, list(index), n=1, cutoff=cutoff)
    if m:
        r = round(difflib.SequenceMatcher(None, key, m[0]).ratio(), 3)
        return index[m[0]], r, "fuzzy"
    return None, 0.0, "none"

def sub_url(slug, ipo_id):
    return f"https://www.chittorgarh.com/ipo_subscription/{slug}/{ipo_id}/"

def cmd_resolve(company, years):
    """Print the matched Chittorgarh id/slug for a company (verify before --auto). No enrich."""
    index = build_index(years)
    hit, score, how = resolve(company, index)
    if hit:
        log.info(f"\n{company!r} -> id={hit[1]} slug={hit[0]}  ({how} {score})  [{hit[2]}]")
        log.info(f"  {sub_url(hit[0], hit[1])}")
    else:
        log.info(f"\n{company!r} -> NO MATCH (raise --years or check name)")

def cmd_company(company, years, apply):
    """Auto-resolve one company -> enrich (no --url needed)."""
    index = build_index(years)
    hit, score, how = resolve(company, index)
    if not hit:
        log.info(f"{company!r}: no Chittorgarh match — skipped.")
        return
    log.info(f"{company!r} -> id={hit[1]} ({how} {score}); fetching {sub_url(hit[0],hit[1])}")
    ipo, sub, html = extract(sub_url(hit[0], hit[1]), want_raw=True)
    upsert(company, map_fields(ipo, sub, html), apply)

def cmd_auto(years, apply, limit):
    """Post-NSE hook: enrich every bare ipo_intelligence row (missing issue_price or subscription)."""
    import psycopg2
    if not DB:
        sys.exit("DATABASE_URL not set.")
    conn = psycopg2.connect(DB); cur = conn.cursor()
    cur.execute("""SELECT id, company_name FROM ipo_intelligence
                   WHERE company_name IS NOT NULL
                     AND (issue_price IS NULL OR total_subscription_x IS NULL)
                   ORDER BY id DESC LIMIT %s""", [limit])
    rows = cur.fetchall(); conn.close()
    log.info(f"{len(rows)} bare rows to try (issue_price or subscription null). Building index...")
    index = build_index(years)
    stats = {"enriched": 0, "no_match": 0, "no_data": 0}
    for rid, name in rows:
        hit, score, how = resolve(name, index)
        if not hit:
            log.info(f"  [{rid}] {name[:34]:34} -> no match"); stats["no_match"] += 1; continue
        try:
            ipo, sub, html = extract(sub_url(hit[0], hit[1]), want_raw=True)
            fields = map_fields(ipo, sub, html)
        except SystemExit:
            log.info(f"  [{rid}] {name[:34]:34} -> fetch failed"); stats["no_data"] += 1; continue
        if not fields:
            log.info(f"  [{rid}] {name[:34]:34} -> id={hit[1]} but no parse"); stats["no_data"] += 1; continue
        log.info(f"  [{rid}] {name[:34]:34} -> id={hit[1]} ({how} {score}) {len(fields)} fields"
                 + ("" if apply else " [dry-run]"))
        if apply:
            upsert(name, fields, True)
        stats["enriched"] += 1
        time.sleep(1.5)
    log.info(f"\nDONE: {stats}  {'(APPLIED)' if apply else '(dry-run; add --apply)'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="explicit Chittorgarh subscription/ipo URL")
    ap.add_argument("--company", help="company_name to resolve+enrich (or upsert target with --url)")
    ap.add_argument("--resolve", metavar="COMPANY", help="just print the matched Chittorgarh id/slug, no enrich")
    ap.add_argument("--auto", action="store_true", help="enrich every bare ipo_intelligence row (post-NSE hook)")
    ap.add_argument("--years", default=None, help="comma list of years to index (default: current,prev)")
    ap.add_argument("--limit", type=int, default=50, help="--auto: max bare rows to try")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    this_year = datetime.now().year
    years = ([int(y) for y in args.years.split(",")] if args.years
             else [this_year, this_year - 1])

    if args.resolve:
        cmd_resolve(args.resolve, years); return
    if args.auto:
        cmd_auto(years, args.apply, args.limit); return
    if args.url and args.probe:
        probe(args.url); return
    if args.url:
        ipo, sub, html = extract(args.url, want_raw=True)
        upsert(args.company or "", map_fields(ipo, sub, html), args.apply); return
    if args.company:
        cmd_company(args.company, years, args.apply); return
    ap.error("need one of: --url, --company, --resolve, or --auto")


if __name__ == "__main__":
    main()
