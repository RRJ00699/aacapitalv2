#!/usr/bin/env python3
"""
ipomatrix_fallback.py — vendor backfill for columns no primary source filled.

OWNER RULING 08-01: authenticated sources first, IPOMatrix as the FALLBACK.
So this NEVER overwrites anything. Every write goes through upsert_financials, which is
COALESCE-empty-only — an RHP-extracted figure always wins, and the vendor only ever
fills a NULL. Run it as often as you like; it is idempotent by construction.

Source: ipomatrix_raw.raw_json (641 rows), joined to ipo via ipo.ipomatrix_id.

THE PAYLOAD SHAPE IS NOT ASSUMED. I have never seen inside raw_json, so the field map
below is a set of CANDIDATE key names, and --inspect prints what is actually there.
Run --inspect first, confirm the mapping, then --dry-run, then --write.

  python ipomatrix_fallback.py --inspect 710      # show the real JSON shape
  python ipomatrix_fallback.py --ids 285,659,710,709,175 --dry-run
  python ipomatrix_fallback.py --ids 285,659,710,709,175 --write
"""
import os, sys, io, re, json, argparse, datetime as dt
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

FILE_BUILD = "ipomatrix_fallback 2026-08-01b — period_ended + rupees->crore + total_income only"

# candidate key names per target column, matched case/underscore-insensitively
# IPOMatrix's top line is TOTAL INCOME, not revenue-from-operations — established by the
# 07-31 Indo-MIM comparison, where the single "differing" field turned out to be
# definitional: RHP 4192.98 (rev from ops) vs vendor 4320.70 (total income). So
# total_revenue maps ONLY to total_income. Mapping it to both would invent a
# revenue-from-operations figure the vendor never supplied.
FIELD_CANDIDATES = {
    "revenue":      ["revenuefromoperations", "revenue_from_operations",
                     "revenueoperations"],
    "total_income": ["totalincome", "total_income", "totalrevenue", "income"],
    "ebitda":       ["ebitda"],
    "pat":          ["profitaftertax", "pat", "netprofit", "profitfortheyear", "profit"],
    "net_worth":    ["networth", "net_worth", "totalequity", "shareholdersfunds",
                     "equity", "totalnetworth"],
    "total_debt":   ["totaldebt", "total_debt", "totalborrowing", "totalborrowings",
                     "borrowings", "borrowing", "debt"],
    "total_assets": ["totalassets", "total_assets", "assets"],
}
PERIOD_KEYS = ["periodended", "period_ended", "period", "periodending", "period_end",
               "financialdate", "financial_date", "fy", "year", "date", "asondate"]

# Vendor figures are ABSOLUTE RUPEES (Laser Power total_revenue 23478940000.00 = 2347.89
# crore). financial_statements stores crore, so every money column is divided by 1e7.
# Skipping this would store a figure ten million times too large — and because
# upsert_financials is COALESCE-empty-only, a wrong value could never be corrected by a
# later run. Ratios/counts are NOT money and are excluded.
RUPEES_PER_CRORE = 10_000_000.0
MONEY_COLS = {"revenue", "total_income", "ebitda", "pat", "net_worth",
              "total_debt", "total_assets"}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _flat_key(k):
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").strip()
    if not s or s in ("-", "NA", "N/A", "null"):
        return None
    try: return float(s)
    except ValueError: return None


def norm_period(raw):
    """Vendor period -> the stored convention DD-Mon-YY with a 2-DIGIT year.

    financial_statements' key is (ipo_id, period, basis) and existing rows use
    '31-Mar-26'. A vendor row written as 'FY2026' or '2026-03-31' would create a
    SECOND row for the same period instead of filling the existing one — the exact
    duplication the ISIN/period discipline exists to prevent."""
    if raw is None:
        return None
    s = str(raw).strip()
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{2})$", s)
    if m:
        return s
    m = re.match(r"^(\d{1,2})[-/ ]([A-Za-z]{3})[a-z]*[-/ ](\d{4})$", s)
    if m:
        return f"{int(m.group(1)):02d}-{m.group(2).title()}-{m.group(3)[2:]}"
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return f"{int(m.group(3)):02d}-{MONTHS[int(m.group(2))-1].title()}-{m.group(1)[2:]}"
    m = re.match(r"^FY\s?(\d{4})$", s, re.I)
    if m:
        return f"31-Mar-{m.group(1)[2:]}"
    m = re.match(r"^FY\s?(\d{2})$", s, re.I)
    if m:
        return f"31-Mar-{m.group(1)}"
    return None


def find_financials(payload):
    """Locate the list of per-period financial rows anywhere in the payload."""
    best = None
    def walk(o, path=""):
        nonlocal best
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(o, list) and o and isinstance(o[0], dict):
            keys = {_flat_key(k) for k in o[0].keys()}
            score = sum(1 for cands in FIELD_CANDIDATES.values()
                        if any(c in keys for c in cands))
            if score >= 2 and (best is None or score > best[0]):
                best = (score, path, o)
    walk(payload)
    return (best[2], best[1]) if best else (None, None)


def map_row(row):
    """One vendor row -> (period, record) using the candidate map."""
    flat = {_flat_key(k): v for k, v in row.items()}
    period = None
    for pk in PERIOD_KEYS:
        fk = _flat_key(pk)
        if fk in flat:
            period = norm_period(flat[fk])
            if period:
                break
    # basis from the vendor's own label rather than an assumption
    stmt = str(flat.get("financialstmt") or "").lower()
    basis = "standalone" if "standalone" in stmt else "consolidated"

    rec = {}
    for col, cands in FIELD_CANDIDATES.items():
        for c in cands:
            if c in flat:
                v = _num(flat[c])
                if v is not None:
                    rec[col] = round(v / RUPEES_PER_CRORE, 4) if col in MONEY_COLS else v
                break
    return period, basis, rec


def load_raw(cur, ipo_id):
    cur.execute("""SELECT r.raw_json FROM ipomatrix_raw r
                     JOIN ipo i ON i.ipomatrix_id = r.ipomatrix_id
                    WHERE i.id = %s LIMIT 1""", (ipo_id,))
    r = cur.fetchone()
    return r[0] if r else None


def existing_nulls(cur, ipo_id):
    """Which (period, basis) rows exist and which columns are NULL — the fill targets."""
    cur.execute("""SELECT period, basis, revenue, total_income, ebitda, pat,
                          net_worth, total_debt, total_assets
                     FROM financial_statements WHERE ipo_id=%s ORDER BY period DESC""",
                (ipo_id,))
    cols = ["revenue", "total_income", "ebitda", "pat", "net_worth", "total_debt", "total_assets"]
    out = {}
    for row in cur.fetchall():
        out[(row[0], row[1])] = [c for c, v in zip(cols, row[2:]) if v is None]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", type=int, help="print the real raw_json shape for one ipo id")
    ap.add_argument("--ids"); ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    conn = psycopg2.connect(os.environ["DATABASE_URL"]); cur = conn.cursor()
    print(f"  [build] {FILE_BUILD}")

    if a.inspect:
        payload = load_raw(cur, a.inspect)
        if payload is None:
            sys.exit(f"  no ipomatrix_raw row for ipo id={a.inspect}")
        print(f"  top-level keys: {list(payload.keys())[:20] if isinstance(payload, dict) else type(payload)}")
        rows, path = find_financials(payload)
        if not rows:
            print("  NO financial row-list found — dumping first 3000 chars so we can look:")
            print(json.dumps(payload, indent=2)[:3000]); return
        print(f"  financial rows found at: {path}  ({len(rows)} rows)")
        print(f"  first row keys: {list(rows[0].keys())}")
        print(f"  first row: {json.dumps(rows[0], indent=2)[:1200]}")
        for r in rows[:4]:
            p, b, rec = map_row(r)
            print(f"    -> period={p} basis={b}  mapped={rec}")
        return

    if not (a.dry_run or a.write):
        sys.exit("choose --inspect <id>, --dry-run or --write")
    if a.ids:
        ids = [int(x) for x in a.ids.split(",") if x.strip()]
    else:
        cur.execute("""SELECT id FROM ipo WHERE in_backtest_universe=TRUE
                        ORDER BY listing_date DESC NULLS LAST LIMIT %s""", (a.limit,))
        ids = [r[0] for r in cur.fetchall()]

    from fill_v2 import upsert_financials
    filled_total = 0
    for ipo_id in ids:
        cur.execute("SELECT name_display FROM ipo WHERE id=%s", (ipo_id,))
        nm = (cur.fetchone() or ["?"])[0]
        payload = load_raw(cur, ipo_id)
        if payload is None:
            print(f"  == id={ipo_id} {str(nm)[:34]:36} no vendor row (no ipomatrix_id match)")
            continue
        rows, path = find_financials(payload)
        if not rows:
            print(f"  == id={ipo_id} {str(nm)[:34]:36} vendor payload has no financial rows")
            continue
        nulls = existing_nulls(cur, ipo_id)
        print(f"  == id={ipo_id} {str(nm)[:34]:36} {len(rows)} vendor rows @ {path}")
        for r in rows:
            period, basis, rec = map_row(r)
            if not period:
                print(f"       [skip] unrecognised period {list(r.items())[:2]}")
                continue
            target_nulls = nulls.get((period, basis))
            if target_nulls is None:
                fill = rec
                note = "new row"
            else:
                fill = {k: v for k, v in rec.items() if k in target_nulls}
                note = f"filling {len(fill)} null(s) of {len(target_nulls)}"
            if not fill:
                print(f"       {period} {basis}: nothing to fill (already populated)")
                continue
            print(f"       {period} {basis}: {note} -> {sorted(fill.keys())}")
            if a.write:
                upsert_financials(conn, ipo_id, period, basis, fill, source="ipomatrix")
                filled_total += len(fill)
    print(f"\n  done. {filled_total} column-values filled."
          + ("" if a.write else "  Nothing was written (dry-run)."))
    conn.close()


if __name__ == "__main__":
    main()
