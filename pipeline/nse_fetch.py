#!/usr/bin/env python3
"""
nse_fetch.py — item 6: NSE issue details + subscription -> ipo_issue, subscription_snapshots.

WHAT THE ENDPOINT ACTUALLY RETURNS (probed 08-01, 5/5 symbols HTTP 200)
  https://www.nseindia.com/api/ipo-detail?symbol={SYM}&series=EQ
  Top-level: companyName, metaInfo, bidDetails, issueInfo, activeCat, demandGraph...

  The fields we need are NOT typed JSON keys. issueInfo.dataList is a list of
  {"title": "...", "value": "..."} TEXT PAIRS:
      {"title": "Face Value",  "value": "Rs. 5 per Equity Share"}
      {"title": "Bid Lot",     "value": "70 Equity Shares and in multiples thereof"}
      {"title": "Price Range", "value": "Rs. 203 to Rs. 214 per Equity Share"}
      {"title": "Issue Period","value": "09-Jul-2026 to 13-Jul-2026"}
  So this is a PARSER, not a field map. A key-name probe reports these ABSENT —
  that is exactly what happened on the first probe run, and it was the probe that
  was wrong, not NSE.

  bidDetails is the subscription table: per-category noOfTime (x-subscribed) and
  noOfsharesBid. "Mutual funds" -> mf_shares_bid, the field the JUNK rule gates on.

WHAT IT CANNOT GIVE
  anchor_count (NUMBER of anchor investors) is not in this payload — only the anchor
  PORTION in shares, inside the Issue Size prose. anchor_count lives in the separate
  Anchor Allocation Report. Reported honestly as still-missing rather than faked.

  python nse_fetch.py --ids 710 --dry-run     # parse + print, writes NOTHING
  python nse_fetch.py --limit 5 --dry-run
  python nse_fetch.py --ids 710 --write
  python nse_fetch.py --selftest              # offline, real captured payload
"""
import os, sys, io, re, json, time, argparse, datetime as dt
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass

FILE_BUILD = "nse_fetch 2026-08-01d — never store an all-zero final snapshot"

NSE_BASE = "https://www.nseindia.com"
API = NSE_BASE + "/api/ipo-detail?symbol={sym}&series=EQ"
HEADERS = {
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "referer": NSE_BASE + "/market-data/all-upcoming-issues-ipo",
}

# ---------------------------------------------------------------- unit handling
# NSE states issue size in its own unit ("Rs. 5,420 million"). Same discipline as the
# RHP extractor: convert in ONE place, refuse unknown units rather than assume crore.
UNIT_CR = {"crore": 1.0, "cr": 1.0, "million": 0.1, "mn": 0.1,
           "lakh": 0.01, "lakhs": 0.01, "lac": 0.01, "billion": 100.0, "bn": 100.0}

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _num(s):
    """'1,04,01,867' or '5,420' -> float. Indian grouping is irregular; strip commas."""
    if s is None: return None
    s = str(s).replace(",", "").strip()
    try: return float(s)
    except ValueError: return None


def _date(s):
    """'09-Jul-2026' -> date. Returns None on anything unexpected (never a guess)."""
    m = re.match(r"(\d{1,2})[-\s]([A-Za-z]{3})[a-z]*[-\s](\d{4})", (s or "").strip())
    if not m: return None
    mon = MONTHS.get(m.group(2).lower())
    if not mon: return None
    try: return dt.date(int(m.group(3)), mon, int(m.group(1)))
    except ValueError: return None


def _amount_to_cr(text):
    """'Rs. 5,420 million' -> 542.0 crore. Returns (value_cr, note).

    The unit is captured as ANY trailing word, then looked up — deliberately NOT
    restricted to the known list in the regex itself. If the pattern only matched
    known units, an unfamiliar one ('bushels', or a new NSE wording) would simply
    fail to match and disappear as 'no amount found'. Capturing first and validating
    second is what makes an unknown unit REPORTABLE instead of silent."""
    m = re.search(r"(?:Rs\.?|₹)\s*([\d,]+(?:\.\d+)?)\s*([A-Za-z]+)", text or "", re.I)
    if not m: return None, "no_amount_found"
    v = _num(m.group(1))
    unit = m.group(2).lower()
    f = UNIT_CR.get(unit)
    if v is None: return None, "unparseable_amount"
    if f is None: return None, f"unknown_unit:{unit}"
    return round(v * f, 4), None


# A firm name can CONTAIN "and" — "D and A Financial Services Private Limited" is ONE
# BRLM, not two (caught on the Alpine dry-run 08-01, which returned brlm_count=2).
# NSE writes the list as "A, B and C", so: split on commas, then split the remaining
# " and " ONLY where the left-hand fragment already looks like a complete firm name,
# i.e. it ends in a corporate suffix. "IIFL ... Limited and ICICI ... Limited" splits;
# "D and A Financial ..." does not, because "D" is not a firm name.
CORP_SUFFIX = re.compile(r"(limited|ltd|llp|plc|inc|corporation|company)\.?$", re.I)

def _count_brlms(text):
    if not text or not text.strip():
        return None
    parts = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        pieces = re.split(r"\s+and\s+", chunk, flags=re.I)
        merged = [pieces[0]]
        for nxt in pieces[1:]:
            if CORP_SUFFIX.search(merged[-1].strip()):
                merged.append(nxt)                    # genuine separator
            else:
                merged[-1] = merged[-1] + " and " + nxt   # part of one name
        parts.extend(p for p in merged if p.strip())
    return len(parts) or None


def parse_issue_info(payload):
    """issueInfo.dataList text pairs -> ipo_issue columns. Returns (record, extras, notes)."""
    rec, extras, notes = {}, {}, []
    info = ((payload or {}).get("issueInfo") or {}).get("dataList") or []
    d = {}
    for item in info:
        t = (item.get("title") or "").strip().lower()
        v = (item.get("value") or "").strip().strip('"')
        if t: d[t] = v

    # Face Value: "Rs. 5 per Equity Share"
    if "face value" in d:
        m = re.search(r"(?:Rs\.?|Re\.?|₹)\s*([\d.,]+)", d["face value"])
        if m: rec["face_value"] = _num(m.group(1))

    # Bid Lot / Minimum Order Quantity: "70 Equity Shares and in multiples thereof"
    for key in ("bid lot", "minimum order quantity", "market lot"):
        if key in d and rec.get("lot_size") is None:
            m = re.search(r"([\d,]+)\s*Equity\s*Shares", d[key], re.I)
            if m: rec["lot_size"] = int(_num(m.group(1)))

    # Price Range: "Rs. 203 to Rs. 214 per Equity Share"
    if "price range" in d:
        nums = re.findall(r"(?:Rs\.?|₹)\s*([\d,.]+)", d["price range"])
        if len(nums) >= 2:
            rec["band_lo"], rec["band_hi"] = _num(nums[0]), _num(nums[1])
        elif len(nums) == 1:
            rec["band_lo"] = rec["band_hi"] = _num(nums[0])

    # Issue Period: "09-Jul-2026 to 13-Jul-2026"
    if "issue period" in d:
        parts = re.split(r"\s+to\s+", d["issue period"], flags=re.I)
        if len(parts) == 2:
            rec["open_date"], rec["close_date"] = _date(parts[0]), _date(parts[1])

    # Issue Size prose: fresh + OFS amounts, and the anchor portion in shares
    if "issue size" in d:
        txt = d["issue size"]
        fresh = re.search(r"Fresh\s+Issue[^.]*?((?:Rs\.?|₹)\s*[\d,.]+\s*\w+)", txt, re.I)
        ofs = re.search(r"Offer\s+for\s+Sale[^.]*?((?:Rs\.?|₹)\s*[\d,.]+\s*\w+)", txt, re.I)
        f_cr, f_note = _amount_to_cr(fresh.group(1)) if fresh else (None, "no_fresh")
        o_cr, o_note = _amount_to_cr(ofs.group(1)) if ofs else (None, "no_ofs")
        if f_cr is not None: rec["fresh_cr"] = f_cr
        if o_cr is not None: rec["ofs_cr"] = o_cr
        if f_cr is not None or o_cr is not None:
            rec["issue_size_cr"] = round((f_cr or 0) + (o_cr or 0), 4)
        for n in (f_note, o_note):
            if n and not n.startswith("no_"): notes.append(f"issue_size:{n}")
        a = re.search(r"Anchor\s+investor\s+portion\s+of\s+([\d,]+)\s*Equity", txt, re.I)
        if a: extras["anchor_portion_shares"] = int(_num(a.group(1)))

    if "name of the registrar" in d:
        rec["registrar"] = d["name of the registrar"][:200]

    if "book running lead managers" in d:
        brlm = d["book running lead managers"]
        rec["brlm_count"] = _count_brlms(brlm)
        extras["brlm_names"] = brlm[:400]

    meta = (payload or {}).get("metaInfo") or {}
    if meta.get("isin"): extras["isin"] = meta["isin"]
    if meta.get("listingDate"): extras["listing_date"] = meta["listingDate"]
    if meta.get("industry"): extras["industry"] = meta["industry"]

    return rec, extras, notes


# bidDetails category -> subscription_snapshots column. Matched on a distinctive
# substring because NSE's category strings are long and punctuation varies.
CAT_MAP = [
    ("qualified institutional buyers", "qib_x"),
    ("non institutional investors(bid amount of more than ten lakh", "bnii_x"),
    ("non institutional investors(bid amount of more than two lakh", "snii_x"),
    ("retail individual investors", "retail_x"),
]


def parse_bid_details(payload):
    """bidDetails -> subscription_snapshots record."""
    rec = {}
    rows = (payload or {}).get("bidDetails") or []
    for r in rows:
        cat = (r.get("category") or "").strip()
        low = cat.lower().replace(" ", " ")
        times = _num(r.get("noOfTime"))
        # plain "Non Institutional Investors" (no bracket) is the aggregate NII
        if low.startswith("non institutional investors") and "(" not in cat:
            if times is not None: rec["nii_x"] = round(times, 4)
            continue
        if low == "total":
            if times is not None: rec["total_x"] = round(times, 4)
            continue
        if low == "mutual funds":
            shares = _num(r.get("noOfsharesBid"))
            if shares is not None: rec["mf_shares_bid"] = int(shares)
            continue
        for needle, col in CAT_MAP:
            if low.startswith(needle):
                if times is not None: rec[col] = round(times, 4)
                break
    # mf_pct_qib is derivable only if both sides are present; never half-derived
    return rec


def prime(cffi):
    s = cffi.Session(impersonate="chrome124")
    s.get(NSE_BASE, headers=HEADERS, timeout=12); time.sleep(0.8)
    s.get(NSE_BASE + "/market-data/all-upcoming-issues-ipo", headers=HEADERS, timeout=12)
    time.sleep(0.8)
    return s


def fetch_one(session, symbol):
    r = session.get(API.format(sym=symbol), headers=HEADERS, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    return r.json()


def apply_to_db(conn, ipo_id, payload, source="nse", *, subscription_final=True,
                apply_issue=True, apply_subscription=True):
    """Route parsed NSE data through the TESTED fill_v2 writers. Returns a report.

    SUBSCRIPTION IS APPEND-ONLY. subscription_snapshots carries UNIQUE(ipo_id) WHERE
    is_final (index sub_one_final_uq), and upsert_subscription's own contract is
    "never update a past snapshot" (ON CONFLICT DO NOTHING). NSE's ipo-detail table is
    the post-close FINAL position, so a naive is_final=True insert violates that index
    the moment an IPO already has one — which is exactly what happened on the 08-01
    write run for SBIFUNDS.

    So: if a final snapshot already exists we do NOT write, do NOT force an update, and
    do NOT quietly insert a second non-final row. We skip it and COMPARE, reporting any
    field where NSE disagrees with what is stored — a disagreement is worth seeing, not
    worth overwriting silently.
    """
    from fill_v2 import upsert_ipo_issue, upsert_subscription, log_source_fact
    from fill_ipo import upsert_ipo
    issue, extras, notes = parse_issue_info(payload)
    subs = parse_bid_details(payload)
    rep = {"ipo_id": ipo_id, "issue_fields": sorted(issue.keys()) if apply_issue else [],
           "subs_fields": sorted(subs.keys()) if apply_subscription else [], "extras": sorted(extras.keys()),
           "notes": notes, "subs_action": "none", "subs_diff": [], "spine": []}

    # IDENTITY SPINE FIRST. metaInfo carries the ISIN and it was previously only logged
    # to source_facts — so ipo.isin stayed NULL while the value sat in hand, and
    # kite_fetch could not resolve an instrument token by ISIN (rule 5). COALESCE-empty
    # -only, so this can only ever fill a null, never rewrite a known identity.
    cur = conn.cursor()
    cur.execute("SELECT isin, name_display, name_norm FROM ipo WHERE id=%s", (ipo_id,))
    row = cur.fetchone()
    if apply_issue and row and not row[0] and extras.get("isin"):
        upsert_ipo(conn, dict(isin=extras["isin"], name_display=row[1],
                              name_norm=row[2], industry=extras.get("industry"),
                              listing_date=extras.get("listing_date")), source=source)
        rep["spine"].append(f"isin={extras['isin']}")

    if apply_issue and issue:
        upsert_ipo_issue(conn, ipo_id, issue, source=source)

    # AN ALL-ZERO PAYLOAD MEANS "NOT REPORTED YET", NOT "ZERO DEMAND".
    # NSE returns the bidDetails table before an issue has any bids, so a pre-close fetch
    # yields zeros across the board. Writing that as is_final is doubly destructive:
    #   1. mf_shares_bid=0 is the FIRST rule in verdict_engine's JUNK line, so a brand-new
    #      IPO with no data yet is classified JUNK before anything else is considered.
    #   2. subscription_snapshots is APPEND-ONLY with UNIQUE(ipo_id) WHERE is_final, so the
    #      zero row can never be corrected and the real close-day numbers are locked out.
    # Caught on the 08-01 cron run: Propshop and Metalic both got a zero-filled final row.
    meaningful = any((subs.get(c) or 0) > 0
                     for c in ("qib_x", "nii_x", "retail_x", "total_x", "mf_shares_bid"))
    if apply_subscription and subs and not meaningful:
        rep["subs_action"] = "skipped_all_zero_not_reported_yet"
        subs = {}

    if apply_subscription and subs:
        cols = ["qib_x", "nii_x", "bnii_x", "snii_x", "retail_x", "total_x", "mf_shares_bid"]
        cur.execute(f"""SELECT captured_at, {', '.join(cols)} FROM subscription_snapshots
                         WHERE ipo_id=%s AND is_final ORDER BY captured_at DESC LIMIT 1""",
                    (ipo_id,))
        existing = cur.fetchone()
        if subscription_final and existing:
            rep["subs_action"] = "skipped_final_exists"
            for col, stored in zip(cols, existing[1:]):
                fresh = subs.get(col)
                if fresh is None or stored is None:
                    continue
                if abs(float(stored) - float(fresh)) > 0.01:
                    rep["subs_diff"].append(f"{col}: stored={stored} nse={fresh}")
        elif subscription_final:
            cur.execute("SELECT now()")
            upsert_subscription(conn, ipo_id, cur.fetchone()[0], subs, is_final=True)
            rep["subs_action"] = "inserted_final"
        else:
            cur.execute("SELECT now()")
            upsert_subscription(conn, ipo_id, cur.fetchone()[0], subs, is_final=False)
            rep["subs_action"] = "inserted_forward"

    for k in ("anchor_portion_shares", "brlm_names", "industry"):
        if apply_issue and extras.get(k) is not None:
            log_source_fact(conn, ipo_id, k, extras[k], source)
    return rep


# ---------------------------------------------------------------- offline fixture
# The REAL Laser Power payload captured 08-01 (trimmed to the parsed parts). Having a
# captured payload means the parser is testable with no network and no NSE dependency.
FIXTURE = {
  "companyName": "Laser Power & Infra Limited",
  "metaInfo": {"symbol": "LASERPOWER", "industry": "Cables - Electricals",
               "isin": "INE17IR01028", "listingDate": "2026-07-16"},
  "bidDetails": [
    {"category": "Qualified Institutional Buyers(QIBs)", "noOfTime": "53.60533736779865",
     "noOfsharesBid": "391873510"},
    {"category": "Mutual funds", "noOfTime": "", "noOfsharesBid": "27080130"},
    {"category": "Non Institutional Investors", "noOfTime": "32.867766028016185",
     "noOfsharesBid": "180206040"},
    {"category": "Non Institutional Investors(Bid amount of more than Ten Lakh Rupees)",
     "noOfTime": "36.48524160142352", "noOfsharesBid": "133359870"},
    {"category": "Non Institutional Investors(Bid amount of more than Two Lakh Rupees upto Ten Lakh Rupees)",
     "noOfTime": "25.632812901827876", "noOfsharesBid": "46846170"},
    {"category": "Retail Individual Investors(RIIs)", "noOfTime": "4.701419976060539",
     "noOfsharesBid": "60145750"},
    {"category": "Total", "noOfTime": "24.709614051039296", "noOfsharesBid": "6.322253E8"},
  ],
  "issueInfo": {"dataList": [
    {"title": "Symbol", "value": "LASERPOWER"},
    {"title": "Issue Period", "value": "09-Jul-2026 to 13-Jul-2026"},
    {"title": "Issue Size", "value": "\"Initial Public Offer comprising of Fresh Issue aggregating up to Rs. 5,420 million and Offer for Sale aggregating up to Rs. 2,000 million. (Including Anchor investor portion of 1,04,01,867 Equity Shares)\""},
    {"title": "Issue Type", "value": "100% Book Building"},
    {"title": "Price Range", "value": "Rs. 203 to Rs. 214 per Equity Share"},
    {"title": "Face Value", "value": "Rs. 5 per Equity Share"},
    {"title": "Tick Size", "value": "Re.1"},
    {"title": "Bid Lot", "value": "70 Equity Shares and in multiples thereof"},
    {"title": "Minimum Order Quantity", "value": "70 Equity Shares"},
    {"title": "Book Running Lead Managers", "value": "IIFL Capital Services Limited and ICICI Securities Limited"},
    {"title": "Name of the Registrar", "value": "MUFG Intime India Private Limited"},
  ]}
}


def selftest():
    ok = True
    print(f"  [build] {FILE_BUILD}")
    def chk(m, c):
        nonlocal ok; ok = ok and c; print(f"  [{'PASS' if c else 'FAIL'}] {m}")

    issue, extras, notes = parse_issue_info(FIXTURE)
    chk("face_value parsed from 'Rs. 5 per Equity Share' (5)", issue.get("face_value") == 5.0)
    chk("lot_size parsed from 'Bid Lot' (70)", issue.get("lot_size") == 70)
    chk("band_lo parsed (203)", issue.get("band_lo") == 203.0)
    chk("band_hi parsed (214)", issue.get("band_hi") == 214.0)
    chk("open_date parsed (2026-07-09)", issue.get("open_date") == dt.date(2026, 7, 9))
    chk("close_date parsed (2026-07-13)", issue.get("close_date") == dt.date(2026, 7, 13))
    chk("fresh_cr million->crore (5420mn = 542cr)", issue.get("fresh_cr") == 542.0)
    chk("ofs_cr million->crore (2000mn = 200cr)", issue.get("ofs_cr") == 200.0)
    chk("issue_size_cr = fresh + ofs (742)", issue.get("issue_size_cr") == 742.0)
    chk("registrar captured", "MUFG" in (issue.get("registrar") or ""))
    chk("brlm_count = 2 (IIFL and ICICI)", issue.get("brlm_count") == 2)
    # BRLM counting — real strings from the 08-01 dry-run
    chk("'D and A Financial Services Private Limited' = 1 BRLM, not 2 (Alpine bug)",
        _count_brlms("D and A Financial Services Private Limited") == 1)
    chk("'IIFL Capital Services Limited and ICICI Securities Limited' = 2",
        _count_brlms("IIFL Capital Services Limited and ICICI Securities Limited") == 2)
    chk("'Axis Capital Limited, IIFL Capital Services Limited and Motilal Oswal Limited' = 3",
        _count_brlms("Axis Capital Limited, IIFL Capital Services Limited and "
                     "Motilal Oswal Limited") == 3)
    chk("comma list of 4 counts 4",
        _count_brlms("A Limited, B Limited, C Limited, D Limited") == 4)
    chk("single firm with no 'and' = 1", _count_brlms("KFin Technologies Limited") == 1)
    chk("empty BRLM string -> None, not 0", _count_brlms("") is None)
    chk("anchor portion shares parsed (10401867)",
        extras.get("anchor_portion_shares") == 10401867)
    chk("isin captured from metaInfo", extras.get("isin") == "INE17IR01028")
    chk("no unit-conversion notes on a clean payload", not notes)

    subs = parse_bid_details(FIXTURE)
    chk("qib_x parsed (53.6053)", abs(subs.get("qib_x", 0) - 53.6053) < 0.001)
    chk("nii_x is the AGGREGATE row, not a bracketed sub-row",
        abs(subs.get("nii_x", 0) - 32.8678) < 0.001)
    chk("bnii_x = >10 lakh bucket (36.4852)", abs(subs.get("bnii_x", 0) - 36.4852) < 0.001)
    chk("snii_x = 2-10 lakh bucket (25.6328)", abs(subs.get("snii_x", 0) - 25.6328) < 0.001)
    chk("retail_x parsed (4.7014)", abs(subs.get("retail_x", 0) - 4.7014) < 0.001)
    chk("total_x parsed (24.7096)", abs(subs.get("total_x", 0) - 24.7096) < 0.001)
    chk("mf_shares_bid parsed (27080130) — the JUNK-rule field",
        subs.get("mf_shares_bid") == 27080130)
    chk("anchor_count NOT invented (absent from this endpoint)", "anchor_count" not in subs)

    # robustness: junk in, nothing out — never a guess
    empty_i, empty_e, _ = parse_issue_info({})
    chk("empty payload -> empty record, no crash", empty_i == {} and empty_e == {})
    chk("empty payload -> empty subscription", parse_bid_details({}) == {})
    bad = {"issueInfo": {"dataList": [
        {"title": "Face Value", "value": "not a number"},
        {"title": "Issue Period", "value": "sometime next year"},
        {"title": "Issue Size", "value": "Fresh Issue of Rs. 100 bushels"}]}}
    bi, _, bn = parse_issue_info(bad)
    chk("unparseable face value -> omitted, not zero", "face_value" not in bi)
    chk("unparseable dates -> omitted, not today", bi.get("open_date") is None)
    chk("unknown unit REFUSED and noted", any("unknown_unit" in n for n in bn))

    chk("_amount_to_cr: crore passes through", _amount_to_cr("Rs. 742 crore")[0] == 742.0)
    chk("_amount_to_cr: billion -> crore", _amount_to_cr("Rs. 1 billion")[0] == 100.0)
    print(f"\n{'ALL PASS ✓' if ok else 'SOME FAILED ✗'}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids"); ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if not (a.dry_run or a.write):
        sys.exit("choose --dry-run or --write")

    import psycopg2
    from curl_cffi import requests as cffi
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    if a.ids:
        ids = [int(x) for x in a.ids.split(",") if x.strip()]
        cur.execute("SELECT id, symbol, name_display FROM ipo WHERE id = ANY(%s)", (ids,))
    else:
        cur.execute("""SELECT id, symbol, name_display FROM ipo
                        WHERE in_backtest_universe=TRUE AND symbol IS NOT NULL
                        ORDER BY listing_date DESC NULLS LAST LIMIT %s""", (a.limit,))
    targets = cur.fetchall()
    print(f"  [build] {FILE_BUILD}")
    print(f"  {len(targets)} IPOs · mode={'WRITE' if a.write else 'DRY-RUN (no writes)'}\n")

    s = prime(cffi)
    ok_n = fail_n = 0
    for ipo_id, sym, name in targets:
        if not sym:
            print(f"  ! id={ipo_id} {name}: no symbol — skipped (cannot resolve on NSE)")
            continue
        try:
            payload = fetch_one(s, sym.upper())
            issue, extras, notes = parse_issue_info(payload)
            subs = parse_bid_details(payload)
            print(f"  === id={ipo_id} {sym} {str(name)[:34]}")
            for k, v in sorted(issue.items()):   print(f"        ipo_issue.{k:15} = {v}")
            for k, v in sorted(subs.items()):    print(f"        subscription.{k:14} = {v}")
            for k, v in sorted(extras.items()):  print(f"        [extra] {k:18} = {str(v)[:60]}")
            for n in notes:                      print(f"        [note] {n}")
            if a.write:
                rep = apply_to_db(conn, ipo_id, payload)
                act = rep["subs_action"]
                print(f"        -> WROTE ipo_issue({len(rep['issue_fields'])}) "
                      f"subscription={act}")
                for dmsg in rep["subs_diff"]:
                    print(f"        [DIFF] {dmsg}")
                ok_n += 1
        except Exception as e:
            # PER-IPO ISOLATION. Without the rollback, one failed statement poisons the
            # connection and every remaining IPO dies with InFailedSqlTransaction having
            # never been attempted — which is exactly what the 08-01 run did: SBIFUNDS
            # hit a unique violation and the other four were never tried.
            try: conn.rollback()
            except Exception: pass
            fail_n += 1
            print(f"  ! id={ipo_id} {sym}: {type(e).__name__}: {str(e)[:140]}")
        time.sleep(2.5)
    conn.close()
    print(f"\n  done. {ok_n} ok · {fail_n} failed."
          + ("" if a.write else "  Nothing was written."))


if __name__ == "__main__":
    main()
