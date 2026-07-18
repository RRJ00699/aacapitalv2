"""Phase 3 B5 — ALL-routes SQL contract.

Every sql`...` block in every app/api/**/route.ts is extracted VERBATIM,
JS-template-cooked, and executed against the seeded contract schema. A renamed
column, broken alias, or failed join in ANY route fails here — the class that
caused the all-awaiting-cards incident.

Frozen-failure pattern (same as A3): blocks that CANNOT run against the
contract schema today (their tables aren't declared yet) are FROZEN as
KNOWN_GAPS = LEDGER #14. A NEW failure fails CI; a cured gap must be pruned
(the list only shrinks). Contract tables get added gap by gap.
"""
import re, pathlib, datetime
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration

# ---------- extraction (shared semantics with test_api_contract) ----------

_VALID = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "`": "`", "$": "$", "'": "'", '"': '"'}

def _cook(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(_VALID.get(s[i + 1], s[i + 1])); i += 2
        else:
            out.append(s[i]); i += 1
    return "".join(out)

def all_blocks():
    for f in sorted(ROOT.glob("app/api/**/route.ts")):
        src = f.read_text(encoding="utf-8")
        for i, block in enumerate(re.findall(r"sql`([^`]+)`", src)):
            yield str(f.relative_to(ROOT)), i, _cook(block)

def _bind(q):
    """${expr} -> %s with a type-guessed dummy: ANY( -> list, LIMIT/OFFSET ->
    int, date-ish -> date, else text '1' (valid int-in-text for numeric casts)."""
    params = []
    def sub(m):
        before = q[:m.start()].rstrip().upper()
        if before.endswith("ANY("):
            params.append(["X"])
        elif before.endswith(("LIMIT", "OFFSET")):
            params.append(1)
        elif before.endswith(("DATE", ">=", "<=")) and "DATE" in before[-30:]:
            params.append(datetime.date.today())
        else:
            params.append("1")
        return "%s"
    q2 = re.sub(r"\$\{[^}]*\}", sub, q)
    return q2, params


# ---------- contract schema (superset: api_db tables + route tables) ----------

CONTRACT_DDL = """
DROP SCHEMA public CASCADE; CREATE SCHEMA public;
CREATE TABLE ipo_consolidated (
    company_name TEXT, listing_date DATE, ipo_open_date DATE, ipo_close_date DATE,
    issue_size_cr NUMERIC, issue_price NUMERIC, ipo_score INT, score_band TEXT,
    score_evidence TEXT, gap_bucket TEXT, listing_gap_pct NUMERIC,
    final_qib NUMERIC, final_nii NUMERIC, final_retail NUMERIC, final_total NUMERIC,
    brlm_names TEXT, symbol_final TEXT, nse_symbol TEXT, symbol TEXT, isin TEXT,
    ipo_pe NUMERIC, eps_post NUMERIC, peer_median_pe NUMERIC, roe NUMERIC,
    revenue_cagr_3y NUMERIC, profit_cagr_3y NUMERIC, debt_equity NUMERIC,
    ofs_pct NUMERIC, structure_type TEXT, return_listing_open NUMERIC,
    gmp_day_before_pct NUMERIC, gmp_max_pct NUMERIC, gmp_min_pct NUMERIC,
    sector TEXT, industry TEXT, is_sme BOOLEAN, ipo_status TEXT,
    price_band_low NUMERIC, price_band_high NUMERIC, lot_size INT,
    india_vix NUMERIC, regime_at_listing TEXT, valuation_premium NUMERIC,
    is_profitable BOOLEAN, tp1_exit_note TEXT, floor_price NUMERIC,
    ceiling_price NUMERIC, floor_defenses INT, level_verdict TEXT,
    d10_best_pct NUMERIC, updated_at TIMESTAMPTZ);
CREATE TABLE ipo_intelligence (
    id SERIAL PRIMARY KEY, company_name TEXT, nse_symbol TEXT, symbol TEXT,
    isin TEXT, sector TEXT, listing_date DATE, open_date DATE, close_date DATE,
    issue_price NUMERIC, issue_size_cr NUMERIC, ipo_pe NUMERIC,
    peer_median_pe NUMERIC, eps_post NUMERIC, roe NUMERIC, debt_equity NUMERIC,
    ofs_pct NUMERIC, anchor_count INT, ofs_cr NUMERIC, fresh_issue_cr NUMERIC,
    price_band_high NUMERIC, price_band_low NUMERIC, chittorgarh_slug TEXT,
    score_band TEXT, ipo_score INT, score_expected_win NUMERIC,
    quality_score INT, quality_conf INT, listing_open NUMERIC,
    listing_gap_pct NUMERIC, gmp_day_before_pct NUMERIC, sbi_rating TEXT,
    is_sme BOOLEAN, ipo_status TEXT, updated_at TIMESTAMPTZ);
CREATE TABLE ipo_verdicts (company_name TEXT, verdict TEXT, why_trade TEXT,
    why_caution TEXT, why_avoid TEXT, why_passes TEXT, regime TEXT,
    quality_promoter BOOLEAN, ai_summary TEXT, score NUMERIC, confidence NUMERIC,
    sub_scores JSONB, computed_at TIMESTAMPTZ);
CREATE TABLE ipo_flags (company_name TEXT, red_flags TEXT[], green_checks TEXT[],
    red_count INT, green_count INT, computed_at TIMESTAMPTZ);
CREATE TABLE ipo_broker_consensus (company TEXT, consensus TEXT, n_brokers INT,
    consensus_score NUMERIC);
CREATE TABLE ipo_rhp_intel (company_name TEXT, verdict TEXT, one_line TEXT,
    quality_gate TEXT, margin_of_safety NUMERIC, full_json TEXT, confidence TEXT,
    rhp_url TEXT, pdf_sha256 TEXT);
CREATE TABLE ipo_research_notes (source TEXT, company TEXT, nse_symbol TEXT,
    rating TEXT, full_json TEXT, one_line TEXT, peer_name TEXT, peer_ps NUMERIC,
    note_ps NUMERIC);
CREATE TABLE price_candles (symbol TEXT, date DATE, open NUMERIC, low NUMERIC,
    high NUMERIC, close NUMERIC, volume BIGINT);
CREATE TABLE ipo_tick_feed (symbol TEXT, ltp NUMERIC, vwap NUMERIC,
    vwap_dist NUMERIC, obir NUMERIC, day_volume BIGINT, momentum TEXT,
    divergence TEXT, signal TEXT, recorded_at TIMESTAMPTZ);
CREATE TABLE ipo_level_analysis (symbol TEXT, trade_date DATE, issue_price NUMERIC,
    listing_open NUMERIC, gap_pct NUMERIC, gap_bucket TEXT, floor_price NUMERIC,
    ceiling_price NUMERIC, floor_defenses INT, poc_price NUMERIC, verdict TEXT,
    risk_note TEXT, circuit_locked BOOLEAN, session_vwap NUMERIC);
CREATE TABLE market_regimes (evaluation_date DATE, active_regime TEXT,
    india_vix NUMERIC);
CREATE TABLE ipo_gmp (company_name TEXT, gmp NUMERIC, gmp_pct NUMERIC,
    captured_at TIMESTAMPTZ);
CREATE TABLE pipeline_steps (id SERIAL, run_date DATE, step TEXT, script TEXT,
    ok BOOLEAN, error TEXT, ran_at TIMESTAMPTZ);
CREATE TABLE pipeline_failures (id SERIAL, step TEXT, script TEXT,
    stderr_tail TEXT, failed_at TIMESTAMPTZ);
"""


@pytest.fixture(scope="module")
def contract_db(pg_uri):
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True
    c.cursor().execute(CONTRACT_DDL)
    yield c
    c.close()


# ---------- LEDGER #14: blocks the contract schema can't run YET ----------
# (file, block_index) -> short reason. FROZEN 2026-07-17 first audit.
# The list may only SHRINK: declare the table/columns in CONTRACT_DDL, run,
# prune the entry. A NEW entry appearing = a route broke the contract = CI red.
KNOWN_GAPS = {   # FROZEN first audit 2026-07-17 — may only SHRINK
    ("app/api/access-note/route.ts", 0): "UndefinedTable: relation \"access_requests\" does not exist",
    ("app/api/access-note/route.ts", 1): "UndefinedTable: relation \"access_requests\" does not exist",
    ("app/api/admin/diagnostics/route.ts", 1): "UndefinedFunction: operator does not exist: text ->> unknown",
    ("app/api/admin/diagnostics/route.ts", 2): "UndefinedColumn: column \"pdf_path\" does not exist",
    ("app/api/admin/diagnostics/route.ts", 4): "UndefinedTable: relation \"kite_session\" does not exist",
    ("app/api/admin/diagnostics/route.ts", 5): "UndefinedTable: relation \"rhp_run_log\" does not exist",
    ("app/api/admin/diagnostics/route.ts", 6): "UndefinedTable: relation \"ipo_preopen_book\" does not exist",
    ("app/api/admin/diagnostics/route.ts", 7): "UndefinedColumn: column \"eps_source\" does not exist",
    ("app/api/admin/secrets/route.ts", 0): "UndefinedTable: relation \"platform_config\" does not exist",
    ("app/api/admin/secrets/route.ts", 1): "UndefinedTable: relation \"kite_session\" does not exist",
    ("app/api/admin/secrets/route.ts", 2): "UndefinedTable: relation \"platform_config\" does not exist",
    ("app/api/auth/zerodha/callback/route.ts", 0): "UndefinedTable: relation \"kite_session\" does not exist",
    ("app/api/auth/zerodha/callback/route.ts", 1): "UndefinedTable: relation \"kite_session\" does not exist",
    ("app/api/auth/zerodha/status/route.ts", 0): "UndefinedTable: relation \"kite_session\" does not exist",
    ("app/api/ipo/cum-volume/route.ts", 0): "InvalidDatetimeFormat: invalid input syntax for type date: \"1\"",
    ("app/api/ipo/intelligence/route.ts", 0): "UndefinedColumn: column \"archetype\" does not exist",
    ("app/api/ipo/intelligence/route.ts", 1): "UndefinedColumn: column \"lqi_final\" does not exist",
    ("app/api/ipo/levels/route.ts", 0): "UndefinedColumn: column \"day_open\" does not exist",
    ("app/api/ipo/levels/route.ts", 1): "UndefinedTable: relation \"ipo_daily_levels\" does not exist",
    ("app/api/ipo/live-preopen/route.ts", 0): "UndefinedColumn: column \"anchor_count\" does not exist",
    ("app/api/ipo/playbook/route.ts", 0): "UndefinedColumn: column \"play_recommendation\" does not exist",
    ("app/api/ipo/post-listing/route.ts", 0): "UndefinedColumn: column \"listing_day_close\" does not exist",
    ("app/api/ipo/route.ts", 0): "UndefinedColumn: column \"listing_day_close\" does not exist",
    ("app/api/market/snapshot/route.ts", 0): "UndefinedTable: relation \"market_snapshot\" does not exist",
    ("app/api/market/snapshot/route.ts", 2): "UndefinedTable: relation \"daily_institutional_flows\" does not exist",
    ("app/api/pipeline/status/route.ts", 1): "UndefinedTable: relation \"technical_signals\" does not exist",
    ("app/api/pipeline/status/route.ts", 2): "UndefinedTable: relation \"management_commentary\" does not exist",
    ("app/api/pipeline/status/route.ts", 3): "UndefinedTable: relation \"technical_signals\" does not exist",
    ("app/api/post-listing/route.ts", 1): "UndefinedTable: relation \"delivery_data\" does not exist",
    ("app/api/post-listing/route.ts", 2): "UndefinedColumn: column \"anchor_lock30_date\" does not exist",
    ("app/api/tracker/route.ts", 3): "InvalidDatetimeFormat: invalid input syntax for type timestamp with time zone: \"",
}


def test_B5_every_route_sql_block_runs_or_is_known_gap(contract_db):
    new_failures, cured = {}, []
    blocks = list(all_blocks())
    assert len(blocks) >= 40, f"extractor regressed: only {len(blocks)} sql blocks found"
    cur = contract_db.cursor()
    for f, i, q in blocks:
        q2, params = _bind(q)
        try:
            cur.execute(q2, params or None)
            try: cur.fetchall()
            except Exception: pass
            if (f, i) in KNOWN_GAPS:
                cured.append((f, i))
        except Exception as e:
            contract_db.rollback() if not contract_db.autocommit else None
            key = (f, i)
            reason = f"{type(e).__name__}: {str(e).splitlines()[0][:90]}"
            if key not in KNOWN_GAPS:
                new_failures[key] = reason
    assert not new_failures, (
        "NEW route-SQL contract failures (renamed column / broken join / new "
        "table not declared):\n" +
        "\n".join(f"  {f}[{i}]: {r}" for (f, i), r in sorted(new_failures.items())))
    assert not cured, f"gaps cured — prune from KNOWN_GAPS: {sorted(cured)}"
