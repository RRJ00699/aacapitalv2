"""API-contract integration test — app/api/ipo-command/route.ts vs seeded DB.

Extracts every sql`...` block VERBATIM from the route source, applies JS
template-literal cooking (so we test the SQL that ACTUALLY runs — e.g. the
route's '\\s*&\\s*' cooks to 's*&s*'), and executes each against an embedded
Postgres seeded with contract-shaped rows.

What this guards:
  - the "column final_qib/company_name does not exist" failure class: any
    column the route references but the contract schema lacks fails here
  - every alias the UI binds is present in the result set
  - the canonical-name LEFT JOINs actually land (Ltd vs Limited)
  - the IST state machine (OPEN/LISTING/UPCOMING/INWINDOW) — class D
  - both hasD10 branches, floor/ceiling derivation, ANY(${syms}) params

The CONTRACT_SCHEMA below is the declared shape. Route adds a column ->
this fails until the schema (and prod) declare it. That is the point.
"""
import re, pathlib, datetime
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTE = ROOT / "app" / "api" / "ipo-command" / "route.ts"

pytestmark = pytest.mark.integration


# ---------- extract + cook the route's SQL ----------

_VALID = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "`": "`", "$": "$", "'": "'", '"': '"'}

def _cook(s):
    """JS template-literal cooking: '\\\\'->'\\', unrecognized '\\x'->'x'."""
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(_VALID.get(s[i+1], s[i+1])); i += 2
        else:
            out.append(s[i]); i += 1
    return "".join(out)

def extract_queries():
    src = ROUTE.read_text(encoding="utf-8")
    blocks = re.findall(r"await sql`([^`]+)`", src)
    assert len(blocks) >= 8, f"route changed shape: found {len(blocks)} sql blocks, expected >=8"
    return [_cook(b) for b in blocks]

def _bind(q):
    """Replace ${...} interpolations with psycopg2 placeholders; only ANY(syms) exists."""
    n = q.count("${")
    q2 = re.sub(r"\$\{[^}]+\}", "%s", q)
    return q2, [["TESTCO"]] * n     # each interpolation is the syms array


# ---------- contract schema + seed ----------

@pytest.fixture
def api_db(pg_uri):
    import psycopg2
    c = psycopg2.connect(pg_uri); c.autocommit = True; cur = c.cursor()
    cur.execute("""DROP SCHEMA public CASCADE; CREATE SCHEMA public;
      CREATE TABLE ipo_consolidated (
        company_name TEXT, listing_date DATE, ipo_open_date DATE, ipo_close_date DATE,
        issue_size_cr NUMERIC, issue_price NUMERIC, ipo_score INT, score_band TEXT,
        score_evidence TEXT, gap_bucket TEXT, listing_gap_pct NUMERIC,
        final_qib NUMERIC, final_nii NUMERIC, final_retail NUMERIC, final_total NUMERIC,
        brlm_names TEXT, symbol_final TEXT, nse_symbol TEXT, symbol TEXT,
        ipo_pe NUMERIC, eps_post NUMERIC, peer_median_pe NUMERIC, roe NUMERIC,
        revenue_cagr_3y NUMERIC, profit_cagr_3y NUMERIC, debt_equity NUMERIC,
        ofs_pct NUMERIC, structure_type TEXT, return_listing_open NUMERIC,
        gmp_day_before_pct NUMERIC, gmp_max_pct NUMERIC, gmp_min_pct NUMERIC,
        is_sme BOOLEAN);  -- added 2026-07-20: prod-truth (contract_schema.py:22); audit #6 filter reads it
      CREATE TABLE ipo_verdicts (
        company_name TEXT, verdict TEXT, why_trade TEXT, why_caution TEXT,
        why_avoid TEXT, regime TEXT, quality_promoter BOOLEAN, ai_summary TEXT,
        score INT, confidence TEXT, sub_scores TEXT, why_passes TEXT);
      CREATE TABLE ipo_flags (company_name TEXT, red_flags TEXT[],
        green_checks TEXT[], red_count INT, green_count INT);
      CREATE TABLE ipo_broker_consensus (company TEXT, consensus TEXT,
        n_brokers INT, consensus_score NUMERIC);
      CREATE TABLE ipo_rhp_intel (company_name TEXT, verdict TEXT, one_line TEXT,
        quality_gate TEXT, margin_of_safety NUMERIC, full_json TEXT,
        confidence TEXT, rhp_url TEXT);
      CREATE TABLE ipo_intelligence (company_name TEXT, anchor_count INT,
        ofs_cr NUMERIC, fresh_issue_cr NUMERIC, price_band_high NUMERIC,
        price_band_low NUMERIC, chittorgarh_slug TEXT, score_band TEXT,
        score_expected_win NUMERIC, quality_score NUMERIC, quality_conf TEXT);
      CREATE TABLE ipo_research_notes (source TEXT, company TEXT, nse_symbol TEXT,
        rating TEXT, full_json TEXT, one_line TEXT, peer_name TEXT,
        peer_ps NUMERIC, note_ps NUMERIC);
      CREATE TABLE price_candles (symbol TEXT, date DATE, low NUMERIC,
        high NUMERIC, close NUMERIC);
      CREATE TABLE ipo_tick_feed (symbol TEXT, ltp NUMERIC, vwap NUMERIC,
        vwap_dist NUMERIC, obir NUMERIC, day_volume BIGINT, momentum TEXT,
        divergence TEXT, signal TEXT, recorded_at TIMESTAMPTZ DEFAULT now());
      CREATE TABLE ipo_level_analysis (symbol TEXT, trade_date DATE,
        issue_price NUMERIC, listing_open NUMERIC, gap_pct NUMERIC,
        gap_bucket TEXT, floor_price NUMERIC, ceiling_price NUMERIC,
        floor_defenses INT, poc_price NUMERIC, verdict TEXT, risk_note TEXT,
        circuit_locked BOOLEAN, session_vwap NUMERIC);""")
    cur.execute("SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date")
    ist_today = cur.fetchone()[0]
    yield pg_uri, c, ist_today
    c.close()


def _seed(cur, ist):
    d = datetime.timedelta
    # 4 companies exercising each IST state + all joins
    cur.execute("""INSERT INTO ipo_consolidated
        (company_name, listing_date, ipo_open_date, ipo_close_date, symbol_final,
         issue_price, score_band, brlm_names, listing_gap_pct, eps_post, peer_median_pe)
        VALUES
        ('Open Now Ltd',    %s, %s, %s, 'OPENNOW.NS', 100, 'STRONG', 'Lead One, Other', NULL, 10, 20),
        ('Lists Today Ltd', %s, %s, %s, 'TESTCO',     100, 'STRONG', 'Lead One, Other', NULL, 10, 20),
        ('Upcoming Ltd',    %s, %s, %s, 'UPC',        100, 'STRONG', 'Lead One, Other', NULL, 10, 20),
        ('Test Corp Ltd',   %s, %s, %s, 'INWIN',      100, 'STRONG', 'Lead One, Other', 12, 10, 20)""",
        (None, ist - d(1), ist + d(1),                       # OPEN (open<=ist<=close)
         ist, ist - d(7), ist - d(5),                        # LISTING
         ist + d(5), ist + d(1), ist + d(3),                 # UPCOMING
         ist - d(10), ist - d(17), ist - d(15)))             # INWINDOW
    cur.execute("""INSERT INTO ipo_verdicts (company_name, verdict, score, confidence)
        VALUES ('Test Corp Ltd', 'CAUTION', 1, 'medium')""")
    cur.execute("""INSERT INTO ipo_flags VALUES
        ('Test Corp Ltd', ARRAY['x'], ARRAY['y'], 1, 1)""")
    cur.execute("""INSERT INTO ipo_broker_consensus VALUES ('Test Corp Ltd', 'Subscribe', 5, 4.2)""")
    # canonical-name join: Limited vs Ltd must still land
    cur.execute("""INSERT INTO ipo_rhp_intel (company_name, verdict) VALUES ('Test Corp Limited', 'accept')""")
    cur.execute("""INSERT INTO ipo_intelligence (company_name, anchor_count) VALUES ('Test Corp Limited', 42)""")
    cur.execute("""INSERT INTO ipo_research_notes (source, company, nse_symbol, rating)
        VALUES ('SBI', 'Test Corp', 'INWIN', 'Subscribe')""")
    # 6 candle sessions for the INWINDOW symbol -> floor/ceiling from first 5
    for i, (lo, hi, cl) in enumerate([(95,105,100),(90,110,102),(96,108,101),
                                      (97,112,105),(98,111,104),(99,120,118)]):
        cur.execute("INSERT INTO price_candles VALUES ('INWIN', %s, %s, %s, %s)",
                    (ist - d(10) + d(i), lo, hi, cl))
    cur.execute("""INSERT INTO ipo_tick_feed (symbol, ltp, day_volume, recorded_at)
        VALUES ('TESTCO', 105, 1000, now() - interval '10 minutes')""")
    cur.execute("""INSERT INTO ipo_level_analysis (symbol, trade_date, issue_price)
        VALUES ('TESTCO', %s, 100)""", (ist,))


# ---------- the contract tests ----------

def test_every_route_query_executes_against_contract_schema(api_db):
    """The core contract: no query may reference a column the schema lacks."""
    uri, c, ist = api_db
    cur = c.cursor(); _seed(cur, ist)
    for i, q in enumerate(extract_queries()):
        if i in (6, 8):
            # d10 branch-A queries: the route only runs these AFTER the hasD10
            # gate confirms ipo_consolidated.d10_best_pct exists. Covered
            # post-ALTER in test_post_audit_both_d10_branches.
            continue
        q2, params = _bind(q)
        try:
            cur.execute(q2, params or None)
            cur.fetchall()
        except Exception as e:
            pytest.fail(f"route SQL block #{i} failed against contract schema: {e}\n--- {q2[:300]}")

def test_cards_query_aliases_and_joins(api_db):
    uri, c, ist = api_db
    cur = c.cursor(); _seed(cur, ist)
    cards_q = extract_queries()[0]
    cur.execute(cards_q)
    cols = [d[0] for d in cur.description]
    # every alias the /dashboard/ipo2 UI binds
    for alias in ("sym", "open_date", "close_date", "state", "sbi_rating",
                  "vscore", "vconf", "rhp_verdict", "rhp_gate", "rhp_mos",
                  "street_consensus", "band_high", "band_low", "anchor_count"):
        assert alias in cols, f"UI-bound alias '{alias}' missing from cards query"
    rows = {r[cols.index("company_name")]: dict(zip(cols, r)) for r in cur.fetchall()}
    tc = rows["Test Corp Ltd"]
    assert tc["verdict"] == "CAUTION"                 # ipo_verdicts join
    assert tc["red_count"] == 1                       # ipo_flags join
    assert tc["street_consensus"] == "Subscribe"      # broker join
    assert tc["rhp_verdict"] == "accept"              # canonical join: Ltd vs Limited
    assert tc["anchor_count"] == 42                   # intelligence canonical join
    assert tc["sbi_rating"] == "Subscribe"            # research-notes symbol join
    assert tc["sym"] == "INWIN"
    assert rows["Open Now Ltd"]["sym"] == "OPENNOW"   # .NS stripped

def test_ist_state_machine(api_db):
    """Class D: the four states must resolve on the IST clock."""
    uri, c, ist = api_db
    cur = c.cursor(); _seed(cur, ist)
    cur.execute(extract_queries()[0])
    cols = [d[0] for d in cur.description]
    state = {r[cols.index("company_name")]: r[cols.index("state")] for r in cur.fetchall()}
    assert state["Open Now Ltd"] == "OPEN"
    assert state["Lists Today Ltd"] == "LISTING"
    assert state["Upcoming Ltd"] == "UPCOMING"
    assert state["Test Corp Ltd"] == "INWINDOW"

def test_floor_ceiling_first_five_sessions(api_db):
    uri, c, ist = api_db
    cur = c.cursor(); _seed(cur, ist)
    cur.execute(extract_queries()[1])   # dlRaw
    cols = [d[0] for d in cur.description]
    row = dict(zip(cols, cur.fetchone()))
    assert row["sym"] == "INWIN"
    assert float(row["floor"]) == 90 and float(row["ceiling"]) == 112   # session 6 (120) excluded
    assert float(row["last_close"]) == 118 and row["t"] == 6

def test_live_and_levels_with_any_param(api_db):
    uri, c, ist = api_db
    cur = c.cursor(); _seed(cur, ist)
    qs = extract_queries()
    live_q, _ = _bind(qs[3]); levels_q, _ = _bind(qs[4])
    cur.execute(live_q, (["TESTCO"],)); assert len(cur.fetchall()) == 1
    cur.execute(levels_q, (["TESTCO"],)); assert len(cur.fetchall()) == 1

def test_post_audit_both_d10_branches(api_db):
    """hasD10 gate: without the column branch B runs; after ALTER, branch A must too."""
    uri, c, ist = api_db
    cur = c.cursor(); _seed(cur, ist)
    qs = extract_queries()
    cur.execute(qs[5]); assert cur.fetchall() == []          # hasD10 -> no column yet
    cur.execute(qs[7])                                       # branch B (NULL AS d10_best_pct)
    assert any(r for r in cur.fetchall())                    # INWINDOW row is post-listing
    cur.execute("ALTER TABLE ipo_consolidated ADD COLUMN d10_best_pct NUMERIC")
    cur.execute(qs[5]); assert len(cur.fetchall()) == 1      # gate flips
    cur.execute(qs[6]); cur.fetchall()                       # branch A now valid

def test_brlm_aggregate_needs_eight(api_db):
    uri, c, ist = api_db
    cur = c.cursor(); _seed(cur, ist)
    qs = extract_queries()
    cur.execute(qs[9]); assert cur.fetchall() == []          # only 1 row w/ gap -> under HAVING 8
    for i in range(8):
        cur.execute("""INSERT INTO ipo_consolidated (company_name, brlm_names, listing_gap_pct)
            VALUES (%s, 'Lead One, Other', %s)""", (f"B{i} Ltd", 10 + i))
    cur.execute(qs[9])
    cols = [d[0] for d in cur.description]
    row = dict(zip(cols, cur.fetchone()))
    assert row["lead"] == "Lead One" and row["n"] >= 8
    assert row["pop_rate"] == 100                            # all gaps > 0
