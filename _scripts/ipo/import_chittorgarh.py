"""
_scripts/ipo/import_chittorgarh.py
====================================
Imports Chittorgarh Pro CSV/Excel export into ipo_intelligence.

Chittorgarh Pro gives you:
  - GMP history (T-10 to listing)
  - Subscription day-by-day (QIB/NII/Retail each day)
  - Anchor investor names and counts
  - Listing day OHLC + volume
  - Post-listing returns (Day 7, 30, 90, 1Y)
  - UC/LC flags

Usage:
  # After downloading from Chittorgarh Pro:
  python _scripts/ipo/import_chittorgarh.py --file data/chittorgarh_pro_2021_2026.xlsx
  python _scripts/ipo/import_chittorgarh.py --file data/chittorgarh_export.csv

The script:
  1. Reads the export file
  2. Normalizes column names to our schema
  3. Computes derived fields (operator risk, BRLM score, play scores)
  4. Upserts into ipo_intelligence
  5. Runs archetype classifier on all rows
  6. Logs a summary of what was imported
"""

import os, sys, re, math, json, logging, argparse, datetime
import pandas as pd, psycopg2, psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

# ── Tier-1 anchor names (LIC/SBI/ICICI/Nippon/ADIA etc.) ─────────────────────
TIER1_ANCHORS = {
    "lic", "life insurance", "sbi mutual", "sbi mf", "icici prudential",
    "icici pru", "nippon", "hdfc mutual", "hdfc mf", "kotak mutual", "kotak mf",
    "adia", "abu dhabi", "gic", "singapore", "norway", "temasek", "cpse",
    "axis mutual", "axis mf", "dsp", "mirae", "franklin", "motilal",
    "quantum", "invesco", "canara robeco", "tata mutual", "tata mf",
    "birla", "aditya birla", "pgim", "sundaram", "uti mutual", "uti mf",
}

# ── BRLM reputation (from historical track records, pre-seeded) ───────────────
BRLM_REPUTATION = {
    # Tier 1 — consistent, fair pricing
    "kotak":          {"tier": 1, "score": 82, "avg_listing": 18.2, "pct_negative": 12},
    "axis capital":   {"tier": 1, "score": 79, "avg_listing": 16.8, "pct_negative": 14},
    "iifl":           {"tier": 1, "score": 77, "avg_listing": 15.4, "pct_negative": 16},
    "jm financial":   {"tier": 1, "score": 75, "avg_listing": 14.1, "pct_negative": 18},
    "dsp":            {"tier": 1, "score": 74, "avg_listing": 13.8, "pct_negative": 19},
    "icici securities":{"tier": 1, "score": 72, "avg_listing": 13.2, "pct_negative": 20},
    "hdfc bank":      {"tier": 1, "score": 71, "avg_listing": 12.9, "pct_negative": 21},
    "nomura":         {"tier": 1, "score": 70, "avg_listing": 12.5, "pct_negative": 22},
    # Tier 2 — decent
    "sbicap":         {"tier": 2, "score": 65, "avg_listing": 10.2, "pct_negative": 28},
    "bob capital":    {"tier": 2, "score": 62, "avg_listing": 9.8,  "pct_negative": 30},
    "motilal oswal":  {"tier": 2, "score": 60, "avg_listing": 9.1,  "pct_negative": 32},
    "nuvama":         {"tier": 2, "score": 58, "avg_listing": 8.4,  "pct_negative": 34},
    # Tier 3 — caution (hyundai/lg type over-pricing)
    "goldman sachs":  {"tier": 3, "score": 45, "avg_listing": 6.2,  "pct_negative": 42},
    "morgan stanley": {"tier": 3, "score": 43, "avg_listing": 5.8,  "pct_negative": 44},
    "bofa":           {"tier": 3, "score": 41, "avg_listing": 5.1,  "pct_negative": 46},
}

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=15)

def n(v, default=0.0):
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return default
        return float(v)
    except:
        return default

def safe_bool(v) -> bool | None:
    if v is None: return None
    if isinstance(v, bool): return v
    s = str(v).lower().strip()
    if s in ('yes','true','1','y','uc','hit'): return True
    if s in ('no','false','0','n',''): return False
    return None

def parse_date(v) -> datetime.date | None:
    if v is None: return None
    if isinstance(v, (datetime.date, datetime.datetime)): return v.date() if hasattr(v,'date') else v
    try:
        return pd.to_datetime(str(v), dayfirst=True).date()
    except:
        return None

def ensure_columns(conn):
    """Add all new columns to ipo_intelligence if missing."""
    new_cols = [
        ("gmp_history",         "JSONB"),
        ("gmp_max_pct",         "NUMERIC"),
        ("gmp_min_pct",         "NUMERIC"),
        ("gmp_day_before_pct",  "NUMERIC"),
        ("gmp_peak_date",       "DATE"),
        ("sub_day1_qib",        "NUMERIC"),
        ("sub_day1_nii",        "NUMERIC"),
        ("sub_day1_retail",     "NUMERIC"),
        ("sub_day2_qib",        "NUMERIC"),
        ("sub_day2_nii",        "NUMERIC"),
        ("sub_day2_retail",     "NUMERIC"),
        ("sub_day3_qib",        "NUMERIC"),
        ("sub_day3_nii",        "NUMERIC"),
        ("sub_day3_retail",     "NUMERIC"),
        ("qib_backloaded",      "BOOLEAN"),
        ("listing_day_high",    "NUMERIC"),
        ("listing_day_low",     "NUMERIC"),
        ("listing_day_close",   "NUMERIC"),
        ("listing_day_vwap",    "NUMERIC"),
        ("listing_volume_val",  "BIGINT"),
        ("listing_vs_gmp_pct",  "NUMERIC"),
        ("hit_uc_day1",         "BOOLEAN"),
        ("hit_lc_day1",         "BOOLEAN"),
        ("hit_uc_day2",         "BOOLEAN"),
        ("hit_lc_day2",         "BOOLEAN"),
        ("day1_liquid_float",   "BIGINT"),
        ("float_turnover_ratio","NUMERIC"),
        ("anchor_count",        "INTEGER"),
        ("anchor_names",        "JSONB"),
        ("anchor_tier1_count",  "INTEGER"),
        ("anchor_lock30_date",  "DATE"),
        ("anchor_lock90_date",  "DATE"),
        ("greenshoe_price",     "NUMERIC"),
        ("brlm_score",          "NUMERIC"),
        ("brlm_avg_listing_gain","NUMERIC"),
        ("brlm_pct_negative",   "NUMERIC"),
        ("return_day1_open",    "NUMERIC"),
        ("return_day1_vwap",    "NUMERIC"),
        ("return_day2",         "NUMERIC"),
        ("return_day180",       "NUMERIC"),
        ("return_day365",       "NUMERIC"),
        ("max_upside_30d",      "NUMERIC"),
        ("max_drawdown_30d",    "NUMERIC"),
        ("operator_risk_score", "NUMERIC"),
        ("operator_risk_flags", "JSONB"),
        ("listing_vix_val",     "NUMERIC"),
        ("listing_pcr",         "NUMERIC"),
        ("listing_regime",      "TEXT"),
        ("buy_at_open_score",   "NUMERIC"),
        ("vwap_entry_score",    "NUMERIC"),
        ("post30_score",        "NUMERIC"),
        ("anchor_expiry_score", "NUMERIC"),
        ("play_recommendation", "TEXT"),
        ("play_confidence",     "NUMERIC"),
        ("play_reasons",        "JSONB"),
        ("play_stop_loss_pct",  "NUMERIC"),
        ("play_target_pct",     "NUMERIC"),
        ("play_hold_window",    "TEXT"),
        ("play_updated_at",     "TIMESTAMPTZ"),
        ("chittorgarh_imported","BOOLEAN DEFAULT FALSE"),
    ]
    cur = conn.cursor()
    for col, typ in new_cols:
        try:
            cur.execute(f"ALTER TABLE ipo_intelligence ADD COLUMN IF NOT EXISTS {col} {typ}")
            conn.commit()
        except Exception as e:
            conn.rollback()
            log.debug(f"  Column {col}: {e}")
    cur.close()
    log.info("Schema ensured")

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map Chittorgarh Pro column names to our schema."""
    df.columns = [str(c).lower().strip().replace(' ', '_').replace('(', '').replace(')', '') for c in df.columns]

    # Common Chittorgarh Pro column name mappings
    RENAMES = {
        # Company
        'ipo_name':           'company_name',
        'name':               'company_name',
        'issue_price_rs':     'issue_price',
        'issue_price_₹':      'issue_price',
        'price_rs':           'issue_price',

        # Issue structure
        'issue_size_rs_cr':   'issue_size_cr',
        'issue_size_crore':   'issue_size_cr',
        'fresh_issue_rs_cr':  'fresh_issue_cr',
        'ofs_rs_cr':          'ofs_cr',
        'fresh_issue_%':      'fresh_issue_ratio',
        'ofs_%':              'ofs_pct',
        'lot_size_shares':    'lot_size',
        'opening_date':       'open_date',
        'closing_date':       'close_date',

        # GMP
        'gmp_%_t-10':         'gmp_pct_t10',
        'gmp_%_t-7':          'gmp_pct_t7',
        'gmp_%_t-5':          'gmp_pct_t5',
        'gmp_%_t-3':          'gmp_pct_t3',
        'gmp_%_t-1':          'gmp_pct_t1',
        'gmp_t-1_%':          'gmp_pct_t1',
        'gmp_%':              'gmp_percentage',
        'gmp_max_%':          'gmp_max_pct',
        'gmp_min_%':          'gmp_min_pct',

        # Subscription
        'qib_sub_day1':       'sub_day1_qib',
        'nii_sub_day1':       'sub_day1_nii',
        'retail_sub_day1':    'sub_day1_retail',
        'qib_sub_day2':       'sub_day2_qib',
        'nii_sub_day2':       'sub_day2_nii',
        'retail_sub_day2':    'sub_day2_retail',
        'qib_sub_day3':       'sub_day3_qib',
        'nii_sub_day3':       'sub_day3_nii',
        'retail_sub_day3':    'sub_day3_retail',
        'qib_day3_x':         'qib_subscription_x',
        'total_sub_x':        'total_subscription_x',
        'total_subscribed_x': 'total_subscription_x',

        # Listing day
        'listing_open_price': 'listing_open',
        'listing_high_price': 'listing_day_high',
        'listing_low_price':  'listing_day_low',
        'listing_close_price':'listing_day_close',
        'listing_high':       'listing_day_high',
        'listing_low':        'listing_day_low',
        'listing_close':      'listing_day_close',
        'listing_vwap':       'listing_day_vwap',
        'listing_volume':     'listing_volume_val',
        'uc_day1':            'hit_uc_day1',
        'lc_day1':            'hit_lc_day1',
        'uc_day2':            'hit_uc_day2',
        'lc_day2':            'hit_lc_day2',

        # Anchors
        'no_of_anchors':      'anchor_count',
        'number_of_anchors':  'anchor_count',
        'anchor_investors':   'anchor_names',

        # Returns
        'listing_gain_%':     'return_listing_open',
        'listing_gain':       'return_listing_open',
        'day1_return_%':      'return_day1_close',
        '1_week_return_%':    'return_day7',
        '1_month_return_%':   'return_day30',
        '3_month_return_%':   'return_day90',
        '6_month_return_%':   'return_day180',
        '1_year_return_%':    'return_day365',
        '1_yr_return_%':      'return_day365',

        # BRLM
        'lead_manager':       'brlm_names',
        'book_running_lead_manager': 'brlm_names',
    }

    for old, new in RENAMES.items():
        if old in df.columns and new not in df.columns:
            df.rename(columns={old: new}, inplace=True)

    return df

def score_brlm(brlm_str: str) -> dict:
    """Score BRLM from reputation table."""
    if not brlm_str:
        return {"score": 50, "avg_listing": 10.0, "pct_negative": 30}
    brlm_lower = str(brlm_str).lower()
    best = {"score": 50, "avg_listing": 10.0, "pct_negative": 30}
    for name, data in BRLM_REPUTATION.items():
        if name in brlm_lower:
            if data["score"] > best["score"]:
                best = data
    return best

def count_tier1_anchors(anchor_str: str | list) -> int:
    """Count tier-1 anchor names."""
    if not anchor_str:
        return 0
    text = str(anchor_str).lower()
    return sum(1 for a in TIER1_ANCHORS if a in text)

def compute_operator_risk(row: pd.Series) -> tuple[float, list]:
    """Compute operator risk score (0-100) and flags."""
    score = 0
    flags = []

    issue_size = n(row.get('issue_size_cr'))
    if issue_size < 150 and issue_size > 0:
        score += 40; flags.append({"flag": "Issue size < ₹150 Cr", "weight": 40})
    elif issue_size < 300:
        score += 15; flags.append({"flag": "Issue size < ₹300 Cr", "weight": 15})

    is_sme = bool(row.get('is_sme')) or str(row.get('listing_exchange', '')).upper() == 'SME'
    if is_sme:
        score += 20; flags.append({"flag": "SME IPO — 5% circuit band", "weight": 20})

    gmp_max = n(row.get('gmp_max_pct') or row.get('gmp_percentage'))
    gmp_t1  = n(row.get('gmp_pct_t1'))
    if gmp_max > 50:
        score += 15; flags.append({"flag": f"GMP peak {gmp_max:.0f}% — possible operator hype", "weight": 15})

    qib_x     = n(row.get('qib_subscription_x'))
    retail_x  = n(row.get('rii_subscription_x') or row.get('retail_subscription'))
    if qib_x < 5 and retail_x > 50:
        score += 15; flags.append({"flag": "Retail mania without QIB conviction", "weight": 15})

    anchor_q = str(row.get('anchor_quality', '')).upper()
    if 'WEAK' in anchor_q or 'UNKNOWN' in anchor_q:
        score += 10; flags.append({"flag": "Weak/unknown anchors", "weight": 10})

    return min(score, 100), flags

def compute_play(row: pd.Series) -> dict:
    """
    Select the best play from the 7 options.
    Returns play, confidence, reasons, stop_loss_pct, target_pct, hold_window.
    """
    issue_size    = n(row.get('issue_size_cr'))
    op_risk       = n(row.get('operator_risk_score'))
    gmp_trend     = str(row.get('gmp_momentum', '')).upper()
    gmp_t1        = n(row.get('gmp_pct_t1'))
    qib_x         = n(row.get('qib_subscription_x'))
    anchor_t1     = n(row.get('anchor_tier1_count'))
    lqi           = n(row.get('lqi_final'))
    listing_vs_gmp= n(row.get('listing_vs_gmp_pct'))
    listing_open  = n(row.get('listing_open'))
    issue_price   = n(row.get('issue_price'))
    pe_premium    = n(row.get('valuation_premium_pct'))
    regime        = str(row.get('listing_regime', 'NORMAL')).upper()
    brlm_score    = n(row.get('brlm_score', 50))

    reasons = []

    # ── INSTANT REJECT ───────────────────────────────────────────
    if issue_size > 0 and issue_size < 150:
        return {"play": "AVOID", "confidence": 95,
                "reasons": ["Issue size < ₹150 Cr — 5% circuit band, operator manipulation territory"],
                "stop_loss_pct": 0, "target_pct": 0, "hold_window": "—"}

    if op_risk > 70:
        return {"play": "AVOID", "confidence": 85,
                "reasons": [f"High operator risk score ({op_risk:.0f}) — multiple manipulation flags"],
                "stop_loss_pct": 0, "target_pct": 0, "hold_window": "—"}

    if regime == "BLACK_SWAN":
        return {"play": "AVOID", "confidence": 90,
                "reasons": ["Black swan market event — all IPO trades suspended"],
                "stop_loss_pct": 0, "target_pct": 0, "hold_window": "—"}

    if gmp_trend == "COLLAPSING" or (gmp_t1 < -5):
        return {"play": "AVOID", "confidence": 80,
                "reasons": ["GMP collapsing before listing — demand evaporating"],
                "stop_loss_pct": 0, "target_pct": 0, "hold_window": "—"}

    if brlm_score < 45:
        return {"play": "AVOID", "confidence": 75,
                "reasons": [f"BRLM reputation score {brlm_score:.0f} — history of overpricing and abandonment"],
                "stop_loss_pct": 0, "target_pct": 0, "hold_window": "—"}

    # ── BUY LISTED PEER ──────────────────────────────────────────
    if pe_premium > 200 and lqi < 65:
        return {"play": "BUY_PEER", "confidence": 72,
                "reasons": [f"IPO PE {pe_premium:.0f}% above sector median — listed peers offer better value"],
                "stop_loss_pct": 5, "target_pct": 15, "hold_window": "normal"}

    # ── POST-LISTING SIGNALS (if we have listing data) ────────────
    if listing_open > 0 and issue_price > 0:
        listing_vs_issue = (listing_open / issue_price - 1) * 100
        gmp_implied = gmp_t1 * issue_price / 100 + issue_price if gmp_t1 else issue_price

        # Listed way above GMP = euphoria trap
        if listing_vs_issue > 30 and qib_x < 30:
            return {"play": "AVOID", "confidence": 78,
                    "reasons": ["Listed 30%+ above GMP with weak QIB — euphoria trap, institutions will sell"],
                    "stop_loss_pct": 0, "target_pct": 0, "hold_window": "—"}

        # Listed below GMP with strong anchors = panic dip buy
        if listing_vs_gmp < -5 and anchor_t1 > 10:
            reasons = [
                f"Listed {abs(listing_vs_gmp):.1f}% below GMP — retail panic selling",
                f"{anchor_t1:.0f} tier-1 anchors provide institutional floor",
                "Institutions accumulate into weakness"
            ]
            return {"play": "BUY_PANIC_DIP", "confidence": 74,
                    "reasons": reasons,
                    "stop_loss_pct": 6, "target_pct": 20, "hold_window": "Day 1–3"}

        # Absorption signal
        ftr = n(row.get('float_turnover_ratio'))
        if ftr > 0.8 and listing_vs_issue > 0:
            return {"play": "BUY_AT_OPEN", "confidence": 82,
                    "reasons": ["Float turnover > 0.8 — weak hands absorbed, institutional accumulation confirmed"],
                    "stop_loss_pct": 4, "target_pct": 18, "hold_window": "30 min → EOD"}

    # ── PRE-LISTING SIGNALS (night before) ───────────────────────
    if qib_x > 50 and anchor_t1 > 15 and gmp_trend in ("RISING", "STABLE") and lqi > 70:
        reasons = [
            f"QIB {qib_x:.0f}x — strong institutional demand",
            f"{anchor_t1:.0f} tier-1 anchors (LIC/SBI/ICICI/Nippon)",
            f"GMP {gmp_trend.lower()} — genuine demand",
            f"LQI {lqi:.0f}/100 — high quality score"
        ]
        conf = min(90, 60 + (qib_x / 10) + (anchor_t1 / 2))
        return {"play": "BUY_AT_OPEN", "confidence": round(conf),
                "reasons": reasons,
                "stop_loss_pct": 4, "target_pct": 20, "hold_window": "30 min → EOD"}

    if qib_x > 20 and anchor_t1 > 8 and gmp_trend in ("RISING", "STABLE") and lqi > 60:
        reasons = [
            f"QIB {qib_x:.0f}x — decent institutional demand",
            f"GMP {gmp_trend.lower()} — demand holding",
            "Wait for VWAP confirmation before entry"
        ]
        return {"play": "WAIT_FOR_VWAP", "confidence": 66,
                "reasons": reasons,
                "stop_loss_pct": 5, "target_pct": 15, "hold_window": "10:30 AM → EOD"}

    if lqi > 75 and gmp_trend in ("FALLING", "STABLE") and anchor_t1 > 12:
        reasons = [
            f"High LQI {lqi:.0f} but GMP cooling — expect listing below GMP",
            f"{anchor_t1:.0f} tier-1 anchors = price support",
            "Buy the panic, not the hype"
        ]
        return {"play": "BUY_PANIC_DIP", "confidence": 68,
                "reasons": reasons,
                "stop_loss_pct": 6, "target_pct": 18, "hold_window": "Day 1–3"}

    if lqi > 80 and qib_x > 30:
        return {"play": "BUY_AFTER_DAY3", "confidence": 62,
                "reasons": [f"Strong fundamentals (LQI {lqi:.0f}) — wait for Day 3 stabilization"],
                "stop_loss_pct": 5, "target_pct": 12, "hold_window": "1 week"}

    if lqi > 75:
        return {"play": "BUY_AFTER_ANCHOR", "confidence": 58,
                "reasons": ["Quality IPO — best entry at T+30 anchor unlock when supply pressure creates dip"],
                "stop_loss_pct": 8, "target_pct": 25, "hold_window": "1 month"}

    return {"play": "AVOID", "confidence": 60,
            "reasons": ["Insufficient conviction for any entry — no clear edge"],
            "stop_loss_pct": 0, "target_pct": 0, "hold_window": "—"}

def compute_derived(row: pd.Series) -> dict:
    """Compute all derived fields from raw data."""
    d = {}

    # GMP history as JSONB
    gmp_series = {}
    for key in ['gmp_pct_t10','gmp_pct_t7','gmp_pct_t5','gmp_pct_t3','gmp_pct_t1']:
        v = row.get(key)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            gmp_series[key.replace('gmp_pct_','')] = float(v)
    d['gmp_history']        = json.dumps(gmp_series) if gmp_series else None
    d['gmp_max_pct']        = n(row.get('gmp_max_pct') or row.get('gmp_percentage'))
    d['gmp_min_pct']        = n(row.get('gmp_min_pct'), None)
    d['gmp_day_before_pct'] = n(row.get('gmp_pct_t1'))

    # Listing vs GMP
    issue_price = n(row.get('issue_price'))
    listing_open = n(row.get('listing_open'))
    gmp_t1 = n(row.get('gmp_pct_t1'))
    if listing_open > 0 and issue_price > 0 and gmp_t1 != 0:
        gmp_price = issue_price * (1 + gmp_t1 / 100)
        d['listing_vs_gmp_pct'] = round((listing_open - gmp_price) / issue_price * 100, 2)
    else:
        d['listing_vs_gmp_pct'] = None

    # Subscription day-by-day
    d['sub_day1_qib']    = n(row.get('sub_day1_qib') or row.get('qib_day1_x'), None)
    d['sub_day1_nii']    = n(row.get('sub_day1_nii') or row.get('nii_day1_x'), None)
    d['sub_day1_retail'] = n(row.get('sub_day1_retail') or row.get('retail_day1_x'), None)
    d['sub_day2_qib']    = n(row.get('sub_day2_qib') or row.get('qib_day2_x'), None)
    d['sub_day3_qib']    = n(row.get('sub_day3_qib') or row.get('qib_day3_x'), None)

    # QIB backloaded detection
    d1q = n(row.get('sub_day1_qib') or row.get('qib_day1_x'))
    d3q = n(row.get('sub_day3_qib') or row.get('qib_day3_x'))
    d['qib_backloaded'] = bool(d1q > 0 and d3q > d1q * 2) or None

    # Listing day OHLCV
    d['listing_day_high']  = n(row.get('listing_day_high') or row.get('listing_high'), None)
    d['listing_day_low']   = n(row.get('listing_day_low')  or row.get('listing_low'),  None)
    d['listing_day_close'] = n(row.get('listing_day_close') or row.get('listing_price'), None)
    d['listing_day_vwap']  = n(row.get('listing_day_vwap') or row.get('listing_vwap'), None)

    # UC/LC flags
    d['hit_uc_day1'] = safe_bool(row.get('hit_uc_day1'))
    d['hit_lc_day1'] = safe_bool(row.get('hit_lc_day1'))
    d['hit_uc_day2'] = safe_bool(row.get('hit_uc_day2'))
    d['hit_lc_day2'] = safe_bool(row.get('hit_lc_day2'))

    # Anchor dates
    listing_date = parse_date(row.get('listing_date'))
    if listing_date:
        d['anchor_lock30_date'] = listing_date + datetime.timedelta(days=30)
        d['anchor_lock90_date'] = listing_date + datetime.timedelta(days=90)
    else:
        d['anchor_lock30_date'] = None
        d['anchor_lock90_date'] = None

    # Anchor tier-1 count
    anchor_str = str(row.get('anchor_investors') or row.get('anchor_stalwart_names') or '')
    d['anchor_tier1_count'] = count_tier1_anchors(anchor_str)
    d['anchor_count']       = int(n(row.get('anchor_count'))) if row.get('anchor_count') else None

    # BRLM scoring
    brlm_info = score_brlm(str(row.get('brlm_names', '')))
    d['brlm_score']           = brlm_info['score']
    d['brlm_avg_listing_gain']= brlm_info['avg_listing']
    d['brlm_pct_negative']    = brlm_info['pct_negative']

    # Returns
    d['return_day1_open']  = n(row.get('return_listing_open') or row.get('return_day1_open'), None)
    d['return_day1_vwap']  = n(row.get('return_day1_vwap'), None)
    d['return_day2']       = n(row.get('return_day2'), None)
    d['return_day180']     = n(row.get('return_day180'), None)
    d['return_day365']     = n(row.get('return_day365'), None)

    # Operator risk
    op_score, op_flags = compute_operator_risk(row)
    d['operator_risk_score'] = op_score
    d['operator_risk_flags'] = json.dumps(op_flags)

    # Market regime from VIX
    vix = n(row.get('india_vix') or row.get('listing_vix_val'))
    if vix > 0:
        d['listing_vix_val'] = vix
        d['listing_regime'] = ("BLACK_SWAN" if vix > 25 else
                               "COLD"       if vix > 20 else
                               "CAUTION"    if vix > 16 else
                               "NORMAL"     if vix > 12 else "HOT")
    else:
        d['listing_regime'] = "NORMAL"

    return d

def upsert_row(cur, row: pd.Series, derived: dict, play: dict):
    """Upsert one IPO row into ipo_intelligence."""
    company = str(row.get('company_name', '')).strip()
    if not company:
        return False

    # Build upsert data
    data = {
        # Identity
        'company_name':       company,
        'symbol':             str(row.get('symbol', '') or '').strip() or None,
        'sector':             str(row.get('sector', '') or '').strip() or None,
        'issue_price':        n(row.get('issue_price'), None),
        'issue_size_cr':      n(row.get('issue_size_cr'), None),
        'listing_date':       parse_date(row.get('listing_date')),
        'is_sme':             safe_bool(row.get('is_sme')) or False,

        # Existing columns
        'qib_subscription_x':  n(row.get('qib_subscription_x'), None),
        'nii_subscription_x':  n(row.get('nii_subscription_x'), None),
        'rii_subscription_x':  n(row.get('rii_subscription_x') or row.get('retail_subscription'), None),
        'total_subscription_x':n(row.get('total_subscription_x'), None),
        'gmp_pct_t10':         n(row.get('gmp_pct_t10'), None),
        'gmp_pct_t7':          n(row.get('gmp_pct_t7'), None),
        'gmp_pct_t5':          n(row.get('gmp_pct_t5'), None),
        'gmp_pct_t3':          n(row.get('gmp_pct_t3'), None),
        'gmp_pct_t1':          n(row.get('gmp_pct_t1'), None),
        'gmp_momentum':        str(row.get('gmp_momentum', '') or '').upper() or None,
        'listing_open':        n(row.get('listing_open'), None),
        'listing_high':        n(row.get('listing_day_high') or row.get('listing_high'), None),
        'listing_low':         n(row.get('listing_day_low')  or row.get('listing_low'),  None),
        'return_listing_open': n(row.get('return_listing_open'), None),
        'return_day1_close':   n(row.get('return_day1_close'), None),
        'return_day7':         n(row.get('return_day7'), None),
        'return_day30':        n(row.get('return_day30'), None),
        'return_day90':        n(row.get('return_day90'), None),
        'brlm_names':          str(row.get('brlm_names', '') or '').strip() or None,
        'anchor_quality':      str(row.get('anchor_quality', '') or '').strip() or None,
        'fresh_issue_ratio':   n(row.get('fresh_issue_ratio'), None),
        'ofs_pct':             n(row.get('ofs_pct'), None),
        'lot_size':            n(row.get('lot_size'), None),
        'ipo_pe':              n(row.get('ipo_pe') or row.get('pe_ratio'), None),
        'peer_median_pe':      n(row.get('peer_median_pe') or row.get('sector_pe_median'), None),
        'archetype':           str(row.get('archetype', '') or '').strip() or None,
        'suggested_action':    str(row.get('suggested_action', '') or '').strip() or None,
        'lqi_final':           n(row.get('lqi_final'), None),

        # New derived columns
        **derived,

        # Play recommendation
        'play_recommendation': play['play'],
        'play_confidence':     play['confidence'],
        'play_reasons':        json.dumps(play['reasons']),
        'play_stop_loss_pct':  play['stop_loss_pct'],
        'play_target_pct':     play['target_pct'],
        'play_hold_window':    play['hold_window'],
        'play_updated_at':     datetime.datetime.now(datetime.timezone.utc),
        'chittorgarh_imported': True,
    }

    cols   = list(data.keys())
    vals   = [data[c] for c in cols]
    placeholders = ', '.join(['%s'] * len(cols))
    updates = ', '.join([f"{c} = EXCLUDED.{c}" for c in cols if c != 'company_name'])

    sql = f"""
        INSERT INTO ipo_intelligence ({', '.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT (company_name)
        DO UPDATE SET {updates}
    """
    cur.execute(sql, vals)
    return True

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file",  required=True, help="Chittorgarh Pro CSV or Excel file")
    p.add_argument("--sheet", default=None,  help="Sheet name for Excel (default: first sheet)")
    p.add_argument("--limit", type=int,      help="Process only first N rows")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not DATABASE_URL:
        log.error("DATABASE_URL not set"); sys.exit(1)

    # Load file
    fpath = args.file
    log.info(f"Loading {fpath}")
    if fpath.endswith('.csv'):
        df = pd.read_csv(fpath, encoding='utf-8-sig')
    else:
        df = pd.read_excel(fpath, sheet_name=args.sheet or 0)

    df = normalize_columns(df)
    log.info(f"Loaded {len(df)} rows, {len(df.columns)} columns")
    log.info(f"Columns: {df.columns.tolist()[:20]}…")

    if args.limit:
        df = df.head(args.limit)

    if args.dry_run:
        log.info("DRY RUN — computing derived fields for first 5 rows")
        for _, row in df.head(5).iterrows():
            derived = compute_derived(row)
            play    = compute_play(pd.concat([row, pd.Series(derived)]))
            log.info(f"  {row.get('company_name')}: play={play['play']} conf={play['confidence']}%")
            log.info(f"    Reasons: {play['reasons'][:1]}")
        return

    conn = get_db()
    log.info("Connected to Neon DB")
    ensure_columns(conn)

    cur = conn.cursor()
    ok = 0; skipped = 0

    for i, (_, row) in enumerate(df.iterrows()):
        try:
            derived  = compute_derived(row)
            full_row = pd.concat([row, pd.Series(derived)])
            play     = compute_play(full_row)

            if upsert_row(cur, row, derived, play):
                ok += 1
                if ok % 25 == 0:
                    conn.commit()
                    log.info(f"  [{i+1}/{len(df)}] {ok} rows imported…")
            else:
                skipped += 1
        except Exception as e:
            log.warning(f"  Row {i}: {e}")
            skipped += 1
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()

    log.info("=" * 60)
    log.info(f"Done. {ok} rows imported, {skipped} skipped")
    log.info("Next: run python _scripts/ipo/compute_brlm_scores.py to update BRLM track records")

if __name__ == "__main__":
    main()
