#!/usr/bin/env python3
"""
completeness.py — item 9 of the automation: is this IPO's record READY?

WHAT IT IS
  check_completeness(conn, ipo_id) -> dict(stage, complete, missing[], present[])
  One function, one declared required-field map. Completeness is DERIVED on read,
  never stored — a stored flag goes stale the moment a column is filled elsewhere.

WHY IT IS BUILT FIRST
  It needs no external service (no SEBI, no NSE, no Kite, no API spend), and its
  output tells us WHICH fetchers the 5 target IPOs actually need. Building fetchers
  first would be guessing at what is missing.

STAGE-AWARE ON PURPOSE
  An IPO that has not listed cannot have listing_outcomes or candles, and demanding
  them would report every upcoming IPO as broken. Requirements are declared per
  lifecycle stage; an IPO is COMPLETE when its OWN stage's requirements are met.

SCHEMA SAFETY
  Every column named below is verified against information_schema before any check
  runs (--validate, and automatically on each run). A typo or a renamed column is
  reported loudly as a MAP ERROR rather than crashing mid-sweep or, worse, silently
  reporting an IPO complete because a bad column name was skipped.

  python completeness.py --validate          # check the map against the live schema
  python completeness.py --ids 85,42         # report specific IPOs
  python completeness.py --limit 5           # 5 most recent in-backtest IPOs
"""
import os, sys, io, argparse, json
if __name__ == "__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2

# ---------------------------------------------------------------- THE DECLARED MAP
# Column names taken from fill_v2.py's own upsert field lists and the 08-01 schema dump,
# not from memory. "one_row" tables are checked for NULL columns; "has_rows" tables are
# checked for existence (they are multi-row by nature — periods, snapshots, bars).
ONE_ROW = {
    "ipo":       ["isin", "name_display", "status"],
    "ipo_issue": ["open_date", "close_date", "band_lo", "band_hi",
                  "issue_size_cr", "lot_size", "face_value"],
}
ONE_ROW_LISTED = {
    "ipo":            ["listing_date", "symbol", "kite_token"],
    "ipo_issue":      ["issue_price"],
    "listing_outcomes": ["listing_open", "d1_close", "gap_pct", "pool"],
}
HAS_ROWS = {
    "documents":            "RHP document registered (sha256 provenance)",
    "rhp_findings":         "Sonnet extraction run stored",
    "financial_statements": "restated financials (>=1 period)",
    "valuation":            "ratios + score computed",
}
HAS_ROWS_OPEN = {
    "subscription_snapshots": "subscription / anchor / MF data",
}
HAS_ROWS_LISTED = {
    "market_candles":     "daily candles",
    "market_candles_15m": "15-min intraday bars",
    "decisions":          "verdict written",
}
# subscription columns that matter for the house rules — checked on the FINAL snapshot
SUBSCRIPTION_FIELDS = ["qib_x", "nii_x", "retail_x", "total_x",
                       "anchor_amount_cr", "anchor_count", "mf_shares_bid"]
# financial_statements columns that must be present on the latest period
FINANCIAL_FIELDS = ["revenue", "total_income", "pat", "net_worth", "total_debt"]


# Columns we have NO primary source for. Owner ruling 08-01: fall back to IPOMatrix.
# They are reported separately so a run is not permanently "incomplete" on columns that
# no primary fetcher can ever fill.
#   anchor_count / anchor_amount_cr — NSE ipo-detail gives the anchor PORTION IN SHARES
#     only; the investor count lives in the Anchor Allocation Report (probed 08-01).
#   GMP — no home in the 15 tables at all (sidecar by the 07-31 design).
VENDOR_FALLBACK = {"subscription_snapshots.anchor_count",
                   "subscription_snapshots.anchor_amount_cr"}


def _pending(stage, listing_date, close_date, today, col, has_rhp=False,
             wall_date=None, has_token=True):
    """Is this column NOT YET AVAILABLE rather than missing?

    Data arrives progressively and the pipeline must know the difference:
        RHP            ~2 weeks before the issue opens
        SBI notes      just before
        issue details  ~1 week before
        subscription   final position only after the issue CLOSES
        candles        only on and after listing; a meaningful series takes days
    Reporting 'missing candles' for an IPO that listed yesterday is noise that trains
    you to ignore the alert. Anything not yet due is reported as PENDING, with the
    reason, and does not block COMPLETE."""
    if col.startswith(("market_candles", "listing_outcomes")):
        if stage != "listed":
            return "not listed yet"
        if listing_date and (today - listing_date).days < 1:
            return "listed today — no session yet"
    # 15-min bars: coverage is UNKNOWN until the first backfill runs. We do NOT yet know
    # which old listings Kite can still return intraday for, so we must not flag any gap as
    # permanently unrefetchable — a wrong PERMANENT flag hides a gap we could still fill.
    # A listed IPO with no 15-min bars is reported as awaiting-backfill: visible, NON-
    # blocking, NOT permanent. AFTER the backfill runs, replace this with an EVIDENCE-BASED
    # rule: the earliest listing_date Kite actually returned bars for is the real floor;
    # anything older that is still empty is then genuinely permanent. Do not hardcode a year
    # before then. NOTE: HAS_ROWS only checks existence, so a PARTIAL series (a few 2017
    # bars) reads as present here — bar count / ts-range is the true coverage signal.
    if col == "market_candles_15m" and stage == "listed":
        # TWO DISTINCT states (not the same gap). wall_date = min(ts) = the earliest 15-min
        # bar we currently HOLD (rolling). NOTE: this is NOT Kite's true horizon — that is
        # unmeasured (backward-walking probe pending; see kite_fetch). So we do NOT claim
        # permanence:
        #  (1) listed BEFORE our earliest held bar -> listing-period 15-min not held; whether
        #      it is refetchable depends on the unmeasured Kite horizon.
        #  (2) token UNRESOLVED -> no series yet, but FIXABLE (resolve, then backfill).
        # Both non-blocking here; (2)'s real blocker is surfaced on ipo.kite_token.
        if wall_date and listing_date and listing_date < wall_date:
            return "listing-period 15-min not held (before our earliest bar; refetchability pending horizon probe)"
        if not has_token:
            return "15-min blocked: kite_token unresolved (fixable — resolve, then backfill)"
        return None    # listed after our earliest bar WITH a token -> actionable: the fetch should fill it
    if col.startswith("subscription_snapshots"):
        if stage in ("announced", "open"):
            return "issue not closed yet"
    if col == "financial_statements.revenue" and not has_rhp:
        # Revenue-from-operations is an RHP-ONLY field. IPOMatrix reports Total Income
        # and nothing else — that is the definitional difference the 07-31 comparison
        # established, and why both lines are stored separately. Until an RHP is
        # extracted there is no source for it, so it is awaiting, not missing.
        return "awaiting RHP (vendor supplies total_income only)"
    if col == "ipo.kite_token":
        if stage != "listed":
            return "no instrument until listing"
        if listing_date and (today - listing_date).days < 1:
            return "instrument may not be in the NSE dump on day 1"
    if col.startswith("valuation.rev_cagr"):
        return None
    return None


def _stage(status, listing_date, has_close, close_date, today):
    """Lifecycle stage from the spine. Deliberately simple and explainable."""
    if listing_date is not None and listing_date <= today:
        return "listed"
    if has_close and close_date is not None and close_date <= today:
        return "closed"
    if close_date is not None:
        return "open"
    return "announced"


def _requirements(stage):
    """The declared requirement set for one stage. ONE place, per the spec."""
    one_row = {t: list(c) for t, c in ONE_ROW.items()}
    has_rows = dict(HAS_ROWS)
    if stage in ("open", "closed", "listed"):
        has_rows.update(HAS_ROWS_OPEN)
    if stage == "listed":
        for t, cols in ONE_ROW_LISTED.items():
            one_row.setdefault(t, []).extend(cols)
        has_rows.update(HAS_ROWS_LISTED)
    return one_row, has_rows


def validate_map(conn, verbose=True):
    """Every column in the map must exist. Returns list of errors (empty = good)."""
    cur = conn.cursor()
    cur.execute("""SELECT table_name, column_name FROM information_schema.columns
                    WHERE table_schema='public'""")
    real = {}
    for t, c in cur.fetchall():
        real.setdefault(t, set()).add(c)
    errs = []
    checked = 0
    for src, mapping in [("ONE_ROW", ONE_ROW), ("ONE_ROW_LISTED", ONE_ROW_LISTED)]:
        for tbl, cols in mapping.items():
            if tbl not in real:
                errs.append(f"{src}: table '{tbl}' does not exist"); continue
            for c in cols:
                checked += 1
                if c not in real[tbl]:
                    errs.append(f"{src}: {tbl}.{c} does not exist")
    for src, mapping in [("HAS_ROWS", HAS_ROWS), ("HAS_ROWS_OPEN", HAS_ROWS_OPEN),
                         ("HAS_ROWS_LISTED", HAS_ROWS_LISTED)]:
        for tbl in mapping:
            checked += 1
            if tbl not in real:
                errs.append(f"{src}: table '{tbl}' does not exist")
    for tbl, cols in [("subscription_snapshots", SUBSCRIPTION_FIELDS),
                      ("financial_statements", FINANCIAL_FIELDS)]:
        for c in cols:
            checked += 1
            if tbl in real and c not in real[tbl]:
                errs.append(f"FIELDS: {tbl}.{c} does not exist")
    if verbose:
        print(f"  map validation: {checked} references checked, {len(errs)} error(s)")
        for e in errs:
            print(f"    ✗ MAP ERROR {e}")
    return errs


def check_completeness(conn, ipo_id, today=None):
    """The single completeness verdict for one IPO."""
    cur = conn.cursor()
    if today is None:
        cur.execute("SELECT current_date"); today = cur.fetchone()[0]

    cur.execute("""SELECT id, status, listing_date, name_display, kite_token FROM ipo WHERE id=%s""", (ipo_id,))
    row = cur.fetchone()
    if not row:
        return dict(ipo_id=ipo_id, stage=None, complete=False,
                    missing=["ipo.row_absent"], present=[], name=None)
    _, status, listing_date, name, kite_token = row
    has_token = kite_token is not None
    # The 15-min retention wall, read from the data (rolling): IPOs listed before it can
    # never have listing-period 15-min bars. Cheap; None if the table is empty/absent.
    try:
        cur.execute("SELECT min(ts)::date FROM market_candles_15m")
        wall_date = cur.fetchone()[0]
    except Exception:
        wall_date = None
    cur.execute("SELECT close_date FROM ipo_issue WHERE ipo_id=%s", (ipo_id,))
    ii = cur.fetchone()
    close_date = ii[0] if ii else None
    stage = _stage(status, listing_date, ii is not None, close_date, today)

    one_row, has_rows = _requirements(stage)
    missing, present = [], []

    # --- NULL checks on one-row tables ---
    for tbl, cols in one_row.items():
        key = "id" if tbl == "ipo" else "ipo_id"
        sel = ", ".join(cols)
        cur.execute(f"SELECT {sel} FROM {tbl} WHERE {key}=%s LIMIT 1", (ipo_id,))
        r = cur.fetchone()
        if r is None:
            missing.append(f"{tbl}.<no row>")
            continue
        for c, v in zip(cols, r):
            (present if v is not None else missing).append(f"{tbl}.{c}")

    # --- existence checks on multi-row tables ---
    for tbl, label in has_rows.items():
        cur.execute(f"SELECT count(*) FROM {tbl} WHERE ipo_id=%s", (ipo_id,))
        n = cur.fetchone()[0]
        (present if n > 0 else missing).append(f"{tbl}.<rows>" + ("" if n else f" [{label}]"))

    # --- column-level checks inside the multi-row tables that matter ---
    cur.execute(f"""SELECT {', '.join(FINANCIAL_FIELDS)} FROM financial_statements
                     WHERE ipo_id=%s ORDER BY (basis ILIKE '%consolidat%') DESC, period DESC
                     LIMIT 1""", (ipo_id,))
    f = cur.fetchone()
    if f:
        for c, v in zip(FINANCIAL_FIELDS, f):
            (present if v is not None else missing).append(f"financial_statements.{c}")

    if stage in ("open", "closed", "listed"):
        cur.execute(f"""SELECT {', '.join(SUBSCRIPTION_FIELDS)} FROM subscription_snapshots
                         WHERE ipo_id=%s ORDER BY is_final DESC NULLS LAST, captured_at DESC
                         LIMIT 1""", (ipo_id,))
        s = cur.fetchone()
        if s:
            for c, v in zip(SUBSCRIPTION_FIELDS, s):
                (present if v is not None else missing).append(f"subscription_snapshots.{c}")

    # --- valuation: reuse the engine's own missing_inputs rather than re-deriving ---
    # MUST read the SCORE engine's row, not simply the newest. Once an RHP extraction
    # lands, the newest valuation row is v2-rhp-1, whose missing_inputs legitimately say
    # "de_not_in_rhp / rev_cagr_3y_not_in_rhp / peer_median_pe_not_in_rhp" — the RHP does
    # not report those and score_engine computes them. Reading that row made Indo-MIM look
    # LESS complete after a successful extraction (08-01). v2-rhp-1 is a reporting row; the
    # scoring row is the one whose gaps are real work.
    cur.execute("""SELECT engine_version, missing_inputs FROM valuation
                    WHERE ipo_id=%s AND engine_version LIKE 'v2-score-%%'
                    ORDER BY engine_version DESC, computed_at DESC LIMIT 1""", (ipo_id,))
    v = cur.fetchone()
    if v is None:
        missing.append("valuation.<no score row> [score_engine has not run]")
    val_missing = []
    if v and v[1]:
        # engine-owned explanations are NOT gaps to fetch — they are by design
        val_missing = [m for m in v[1]
                       if not m.startswith(("pe_derived", "pb_derived", "ofs_pct_not"))
                       and not m.endswith("_not_in_rhp")]
    for m in val_missing:
        missing.append(f"valuation.{m}")

    # Has a v2-full RHP extraction landed? Decides whether RHP-only columns are
    # "missing" (extraction ran and did not produce it) or "awaiting" (never ran).
    cur.execute("""SELECT 1 FROM rhp_findings WHERE ipo_id=%s AND prompt_version='v2-full'
                   LIMIT 1""", (ipo_id,))
    has_rhp = cur.fetchone() is not None

    # Split what is genuinely absent from what is simply NOT DUE YET.
    pend = {}
    real_missing = []
    for m in missing:
        col = m.split(" [")[0]
        why = _pending(stage, listing_date, close_date, today, col, has_rhp,
                       wall_date=wall_date, has_token=has_token)
        if why:
            pend[col] = why
        else:
            real_missing.append(m)

    blocking = [m for m in real_missing if m not in VENDOR_FALLBACK]
    return dict(ipo_id=ipo_id, name=name, stage=stage,
                complete=(len(blocking) == 0),
                missing=sorted(blocking),
                pending=sorted(f"{k} ({v})" for k, v in pend.items()),
                vendor_gaps=sorted(m for m in real_missing if m in VENDOR_FALLBACK),
                present=sorted(present),
                engine_version=(v[0] if v else None))


def ntfy_line(rep):
    """The one-line body for the ntfy push (item 10 consumes this)."""
    who = f"IPO {rep.get('name') or rep['ipo_id']}"
    if rep["complete"]:
        vg = rep.get("vendor_gaps") or []
        pd_ = rep.get("pending") or []
        tail = ""
        if pd_: tail += f" · {len(pd_)} pending"
        if vg:  tail += f" · {len(vg)} vendor-fallback"
        return f"{who}: COMPLETE for {rep['stage']}{tail}"
    cols = ", ".join(m.split(" [")[0] for m in rep["missing"][:6])
    more = f" +{len(rep['missing'])-6} more" if len(rep["missing"]) > 6 else ""
    return f"{who}: missing {cols}{more} (null)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="comma-separated ipo ids")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--validate", action="store_true", help="check the map, then exit")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    errs = validate_map(conn)
    if errs:
        sys.exit("\n  MAP ERRORS — fix the declared map before trusting any result.")
    if a.validate:
        print("  map is valid against the live schema."); return

    if a.ids:
        ids = [int(x) for x in a.ids.split(",") if x.strip()]
    else:
        cur.execute("""SELECT id FROM ipo WHERE in_backtest_universe=TRUE
                        ORDER BY listing_date DESC NULLS LAST LIMIT %s""", (a.limit,))
        ids = [r[0] for r in cur.fetchall()]

    reps = [check_completeness(conn, i) for i in ids]
    if a.json:
        print(json.dumps(reps, indent=2, default=str)); return

    ncomplete = 0
    for r in reps:
        mark = "COMPLETE" if r["complete"] else "INCOMPLETE"
        ncomplete += 1 if r["complete"] else 0
        print(f"\n  [{mark}] id={r['ipo_id']} {str(r['name'])[:40]:42} stage={r['stage']}")
        print(f"     present {len(r['present'])} · missing {len(r['missing'])}")
        for m in r["missing"]:
            print(f"       - {m}")
        for m in r.get("pending", []):
            print(f"       . {m}  [not due yet]")
        for m in r.get("vendor_gaps", []):
            print(f"       ~ {m}  [IPOMatrix fallback — no primary source]")
    print(f"\n  RUN SUMMARY: {len(reps)} IPOs, {ncomplete} COMPLETE, "
          f"{len(reps)-ncomplete} missing columns")
    # what the ntfy push would say
    print("\n  ntfy preview:")
    for r in reps:
        print(f"    {ntfy_line(r)}")
    conn.close()


if __name__ == "__main__":
    main()
