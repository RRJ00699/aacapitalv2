#!/usr/bin/env python3
"""
build_ipo_consolidated.py — one wide IPO table from the scattered source tables.

Consolidates the data already in Neon (NO new scraping) into a single ipo_consolidated table:
  base   = ipo_intelligence (all 512 IPOs, richest table — 270 cols)
  + LEFT JOIN ipo_issue_details        ON nse_symbol   (financials, valuation, shareholding)
  + LEFT JOIN ipo_subscription_history ON nse_symbol   (final subscription by category)

Every column maps to a REAL, confirmed source column — wishlist names aliased to standard names.
Genuine-gap fields (1m tape, 60d OHLCV, auction price, kostak/sauda, objects-of-issue, risk tags,
3-year financial breakdown) are intentionally OMITTED — they have no source data (per design decision),
so we don't add empty columns.

Idempotent: DROP + CREATE each run, so it never drifts. Run after IPO refreshes (or cron it).
Run:  python build_ipo_consolidated.py
Env:  DATABASE_URL
"""
import os, sys
import psycopg2
URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

# (target_column, source_expression) — source is from i=ipo_intelligence, d=issue_details, s=subscription
# Only columns backed by real source data. COALESCE prefers the more reliable source where two exist.
MAP = [
  # ---- identity ----
  ("company_name",            "i.company_name"),
  ("nse_symbol",              "i.nse_symbol"),
  ("symbol",                  "i.symbol"),
  # unified resolved symbol — nse_symbol if present, else the verified symbol col
  ("symbol_final",            "COALESCE(NULLIF(UPPER(i.nse_symbol),''), NULLIF(UPPER(i.symbol),''))"),
  ("bse_code",                "i.bse_code"),
  ("isin",                    "COALESCE(i.isin, d.isin, s.isin)"),
  ("sector",                  "i.sector"),
  ("subsector",               "i.subsector"),
  ("industry",                "d.industry"),
  ("exchange",                "i.exchange"),
  ("listing_exchange",        "i.listing_exchange"),
  ("is_sme",                  "i.is_sme"),
  ("ipo_status",              "i.ipo_status"),
  ("ipo_open_date",           "COALESCE(i.open_date, i.issue_open_date, d.opening_date, s.opening_date)"),
  ("ipo_close_date",          "COALESCE(i.close_date, i.issue_close_date, d.closing_date, s.closing_date)"),
  ("listing_date",            "COALESCE(i.listing_date, d.listing_date, s.listing_date)"),
  # ---- issue structure ----
  ("issue_price",             "COALESCE(i.issue_price, d.issue_price)"),
  ("price_band_low",          "i.price_band_low"),
  ("price_band_high",         "i.price_band_high"),
  ("face_value",              "d.face_value"),
  ("lot_size",                "i.lot_size"),
  ("issue_size_cr",           "COALESCE(i.issue_size_cr, d.issue_amount_cr, s.issue_amount_cr)"),
  ("fresh_issue_cr",          "COALESCE(i.fresh_issue_cr, d.fresh_issue_cr)"),
  ("ofs_cr",                  "COALESCE(i.ofs_cr, d.ofs_cr)"),
  ("fresh_issue_ratio",       "i.fresh_issue_ratio"),
  ("ofs_pct",                 "COALESCE(i.ofs_pct, i.ofs_percentage)"),
  ("issue_category",          "COALESCE(d.issue_category, s.issue_category)"),
  ("issue_type",              "d.issue_type"),
  ("pricing_method",          "d.pricing_method"),
  ("greenshoe_price",         "i.greenshoe_price"),
  # ---- shareholding ----
  ("promoter_holding_before", "COALESCE(i.promoter_pre_equity, d.promoter_pre_pct)"),
  ("promoter_holding_after",  "COALESCE(i.promoter_post_equity, i.promoter_holding_post, d.promoter_post_pct)"),
  ("promoter_dilution_pct",   "i.promoter_dilution_pct"),
  ("promoter_pledge_pct",     "i.promoter_pledge_pct"),
  ("free_float_pct",          "i.free_float_pct"),
  ("pe_exit_flag",            "i.pe_exit_flag"),
  # ---- financials (latest year + CAGR; 3-year breakdown intentionally omitted) ----
  ("revenue_cr",              "COALESCE(i.revenue_cr, d.revenue_cr)"),
  ("pat_cr",                  "COALESCE(i.pat_cr, d.pat_cr)"),
  ("ebitda_cr",               "COALESCE(i.ebitda_cr, d.ebitda_cr)"),
  ("net_worth_cr",            "COALESCE(i.net_worth_cr, d.net_worth_cr)"),
  ("total_debt_cr",           "COALESCE(i.total_debt_cr, d.total_borrowing_cr)"),
  ("assets_cr",               "d.assets_cr"),
  ("reserves_cr",             "d.reserves_cr"),
  ("revenue_cagr_3y",         "COALESCE(i.revenue_cagr_3y, i.revenue_growth_3yr)"),
  ("profit_cagr_3y",          "COALESCE(i.profit_cagr_3y, i.pat_growth_3yr)"),
  ("roe",                     "COALESCE(i.roe, d.roe_pct)"),
  ("roce",                    "COALESCE(i.roce, d.roce_pct)"),
  ("ronw_pct",                "d.ronw_pct"),
  ("pat_margin",              "COALESCE(i.pat_margin, d.pat_margin_pct)"),
  ("ebitda_pct",              "i.ebitda_pct"),
  ("debt_equity",             "COALESCE(i.debt_equity, d.debt_equity)"),
  ("eps_pre",                 "COALESCE(i.eps_pre, d.eps_pre)"),
  ("eps_post",                "COALESCE(i.eps_post, d.eps_post)"),
  ("cash_flow_positive",      "i.cash_flow_positive"),
  ("operating_cf_growth",     "i.operating_cf_growth"),
  ("period_ended",            "d.period_ended"),
  # ---- valuation ----
  ("ipo_pe",                  "COALESCE(i.ipo_pe, i.pe_ratio)"),
  ("ipo_pe_pre",              "COALESCE(i.ipo_pe_pre, d.pe_pre)"),
  ("ipo_pe_post",             "COALESCE(i.ipo_pe_post, d.pe_post)"),
  ("ipo_pb",                  "COALESCE(i.ipo_pb, d.pbv)"),
  ("peer_median_pe",          "COALESCE(i.peer_median_pe, i.sector_pe_median)"),
  ("peer_pb",                 "i.peer_pb"),
  ("valuation_premium_pct",   "i.valuation_premium_pct"),
  ("peg_ratio",               "i.peg_ratio"),
  # ---- subscription (final) ----
  ("final_qib",               "COALESCE(s.qib_x, i.qib_subscription_x, i.qib_subscription)"),
  ("final_qib_ex_anchor",     "s.qib_ex_anchor_x"),
  ("final_anchor",            "s.anchor_x"),
  ("final_nii",               "COALESCE(s.nii_x, i.nii_subscription_x, i.nii_subscription)"),
  ("final_bnii",              "s.bnii_x"),
  ("final_snii",              "s.snii_x"),
  ("final_retail",            "COALESCE(s.retail_x, i.rii_subscription_x, i.retail_subscription)"),
  ("final_employee",          "s.employee_x"),
  ("final_total",             "COALESCE(s.total_x, i.total_subscription_x, i.total_subscription)"),
  ("qib_alloc_pct",           "COALESCE(s.qib_alloc_pct, i.retail_allocation_pct)"),
  ("nii_alloc_pct",           "s.nii_alloc_pct"),
  ("retail_alloc_pct",        "COALESCE(s.retail_alloc_pct, i.retail_allocation_pct)"),
  ("qib_to_retail_ratio",     "i.qib_to_retail_ratio"),
  ("structure_type",          "s.structure_type"),
  # ---- subscription day-by-day ----
  ("day1_qib",                "COALESCE(i.sub_day1_qib, i.qib_day1_x)"),
  ("day1_nii",                "COALESCE(i.sub_day1_nii, i.nii_day1_x)"),
  ("day1_retail",             "COALESCE(i.sub_day1_retail, i.retail_day1_x)"),
  ("day2_qib",                "COALESCE(i.sub_day2_qib, i.qib_day2_x)"),
  ("day2_nii",                "COALESCE(i.sub_day2_nii, i.nii_day2_x)"),
  ("day2_retail",             "i.sub_day2_retail"),
  ("day3_qib",                "COALESCE(i.sub_day3_qib, i.qib_day3_x)"),
  ("day3_nii",                "i.sub_day3_nii"),
  ("day3_retail",             "i.sub_day3_retail"),
  ("qib_backloaded",          "i.qib_backloaded"),
  ("hni_leverage_ratio",      "i.hni_leverage_ratio"),
  ("hni_breakeven_premium",   "i.hni_breakeven_premium"),
  # ---- GMP ----
  ("gmp_value",               "i.gmp_value"),
  ("gmp_pct",                 "COALESCE(i.gmp_percentage, i.gmp_pct_t1)"),
  ("gmp_t10",                 "i.gmp_pct_t10"),
  ("gmp_t7",                  "i.gmp_pct_t7"),
  ("gmp_t5",                  "i.gmp_pct_t5"),
  ("gmp_t3",                  "i.gmp_pct_t3"),
  ("gmp_t1",                  "i.gmp_pct_t1"),
  ("gmp_momentum",            "i.gmp_momentum"),
  ("gmp_volatility",          "i.gmp_volatility"),
  ("gmp_velocity",            "i.gmp_velocity"),
  ("gmp_max_pct",             "i.gmp_max_pct"),
  ("gmp_min_pct",             "i.gmp_min_pct"),
  ("gmp_day_before_pct",      "i.gmp_day_before_pct"),
  ("gmp_peak_date",           "i.gmp_peak_date"),
  ("gmp_breakdown_flag",      "i.gmp_breakdown_flag"),
  ("gmp_history",             "i.gmp_history"),
  # ---- anchor ----
  ("anchor_investors",        "i.anchor_investors"),
  ("anchor_names",            "i.anchor_names"),
  ("anchor_quality",          "i.anchor_quality"),
  ("anchor_classification",   "i.anchor_classification"),
  ("anchor_total_cr",         "COALESCE(i.anchor_total_cr, i.anchor_investment_cr)"),
  ("anchor_qib_alloc_cr",     "i.anchor_qib_alloc_cr"),
  ("anchor_alloc_pct",        "i.anchor_alloc_pct"),
  ("anchor_domestic_pct",     "i.anchor_domestic_pct"),
  ("anchor_foreign_pct",      "i.anchor_foreign_pct"),
  ("anchor_top5_pct",         "i.anchor_top5_pct"),
  ("anchor_count",            "i.anchor_count"),
  ("anchor_tier1_count",      "i.anchor_tier1_count"),
  ("anchor_flip_risk",        "i.anchor_flip_risk"),
  ("anchor_lock30_date",      "i.anchor_lock30_date"),
  ("anchor_lock90_date",      "i.anchor_lock90_date"),
  ("anchor_lockup_30d_shares","i.anchor_lockup_30d_shares"),
  ("anchor_lockup_90d_shares","i.anchor_lockup_90d_shares"),
  # ---- lead managers / registrar ----
  ("brlm_names",              "COALESCE(i.brlm_names, d.lead_managers)"),
  ("brlm_tier",               "i.brlm_tier"),
  ("brlm_score",              "i.brlm_score"),
  ("brlm_historical_win_rate","i.brlm_historical_win_rate"),
  ("brlm_avg_listing_gain",   "i.brlm_avg_listing_gain"),
  ("brlm_pct_negative",       "i.brlm_pct_negative"),
  ("registrar",               "d.registrar"),
  ("market_makers",           "d.market_makers"),
  # ---- listing performance ----
  ("listing_price",           "COALESCE(i.listing_price, i.listing_close_price)"),
  ("listing_open",            "i.listing_open"),
  ("listing_high",            "COALESCE(i.listing_high, i.listing_day_high)"),
  ("listing_low",             "COALESCE(i.listing_low, i.listing_day_low)"),
  ("listing_close",           "COALESCE(i.listing_day_close, i.listing_close_price)"),
  ("listing_vwap",            "COALESCE(i.listing_vwap, i.listing_day_vwap, i.vwap)"),
  ("listing_avwap",           "i.listing_avwap"),
  ("listing_volume",          "COALESCE(i.listing_volume, i.listing_volume_val)"),
  ("listing_delivery_pct",    "i.listing_delivery_pct"),
  ("listing_gap_pct",         "i.listing_gap_pct"),
  ("listing_vs_gmp_pct",      "i.listing_vs_gmp_pct"),
  ("above_vwap",              "i.above_vwap"),
  ("buy_qty",                 "i.buy_qty"),
  ("sell_qty",                "i.sell_qty"),
  ("day1_liquid_float",       "i.day1_liquid_float"),
  ("float_turnover_ratio",    "i.float_turnover_ratio"),
  ("hit_uc_day1",             "i.hit_uc_day1"),
  ("hit_lc_day1",             "i.hit_lc_day1"),
  ("hit_uc_day2",             "i.hit_uc_day2"),
  ("hit_lc_day2",             "i.hit_lc_day2"),
  ("ohlc_source",             "i.ohlc_source"),
  # ---- post-listing returns ----
  # NOTE: the stored return_day1..return_day365 columns are CORRUPTED (inconsistent
  # baseline — some issue-based, some neither). Per schema_v2 they are DROPPED here;
  # returns are computed live from price_candles instead. Only the two trustworthy
  # ones are kept: return_listing_open (listing gain) and return_current.
  ("return_listing_open",     "i.return_listing_open"),
  ("return_current",          "COALESCE(i.return_current, i.return_cmp)"),
  ("return_open_5d",          "i.return_open_5d"),
  ("return_open_20d",         "i.return_open_20d"),
  ("max_upside_pct",          "i.max_upside_pct"),
  ("max_upside_30d",          "i.max_upside_30d"),
  ("max_drawdown_day1",       "i.max_drawdown_day1"),
  ("max_drawdown_day30",      "COALESCE(i.max_drawdown_day30, i.max_drawdown_30d)"),
  ("nifty_alpha_day30",       "i.nifty_alpha_day30"),
  ("days_to_break_issue",     "i.days_to_break_issue"),
  ("days_to_new_high",        "i.days_to_new_high"),
  ("achieved_10pct",          "i.achieved_10pct"),
  # ---- market environment ----
  ("nifty_at_listing",        "i.nifty_at_listing"),
  ("nifty_above_ema200",      "i.nifty_above_ema200"),
  ("india_vix",               "COALESCE(i.india_vix, i.listing_vix_val)"),
  ("listing_pcr",             "i.listing_pcr"),
  ("listing_regime",          "i.listing_regime"),
  ("market_regime_score",     "i.market_regime_score"),
  ("fii_monthly_flow_cr",     "i.fii_monthly_flow_cr"),
  ("dii_monthly_flow_cr",     "i.dii_monthly_flow_cr"),
  ("sector_heat",             "i.sector_heat"),
  ("sector_3m_return",        "i.sector_3m_return"),
  ("sector_6m_return",        "i.sector_6m_return"),
  ("sector_ipo_success_rate", "i.sector_ipo_success_rate"),
  ("last10_ipo_avg_return",   "i.last10_ipo_avg_return"),
  # ---- derived scores (AACapital model) ----
  ("ipo_score",               "i.ipo_score"),
  ("raw_score",               "i.raw_score"),
  ("lqi_base",                "i.lqi_base"),
  ("lqi_final",               "i.lqi_final"),
  ("regime_multiplier",       "i.regime_multiplier"),
  ("archetype",               "i.archetype"),
  ("operator_risk_score",     "i.operator_risk_score"),
  ("operator_risk_flags",     "i.operator_risk_flags"),
  ("expected_return",         "i.expected_return"),
  ("prob_10pct_profit",       "i.prob_10pct_profit"),
  ("prob_gain_10_20",         "i.prob_gain_10_20"),
  ("prob_gain_20_50",         "i.prob_gain_20_50"),
  ("prob_gain_gt50",          "i.prob_gain_gt50"),
  ("prob_loss_0_10",          "i.prob_loss_0_10"),
  ("prob_loss_gt10",          "i.prob_loss_gt10"),
  ("confidence_level",        "i.confidence_level"),
  ("suggested_action",        "i.suggested_action"),
  ("position_size",           "i.position_size"),
  ("play_recommendation",     "i.play_recommendation"),
  ("play_confidence",         "i.play_confidence"),
  ("play_stop_loss_pct",      "i.play_stop_loss_pct"),
  ("play_target_pct",         "i.play_target_pct"),
  ("play_hold_window",        "i.play_hold_window"),
  ("buy_at_open_score",       "i.buy_at_open_score"),
  ("vwap_entry_score",        "i.vwap_entry_score"),
  ("post30_score",            "i.post30_score"),
  ("anchor_expiry_score",     "i.anchor_expiry_score"),
  ("risk_warning",            "i.risk_warning"),
  ("key_reasons",             "i.key_reasons"),
  ("similar_ipo_count",       "i.similar_ipo_count"),
  ("similar_ipos",            "i.similar_ipos"),
  # ---- provenance ----
  ("chittorgarh_imported",    "i.chittorgarh_imported"),
  ("enrichment_status",       "i.enrichment_status"),
  ("data_source",             "i.data_source"),
  ("is_backtest",             "i.is_backtest"),
  ("updated_at",              "i.updated_at"),
]

def main():
    if not URL: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(URL); conn.autocommit = False
    cur = conn.cursor()

    # SYM = the unified resolved symbol. Joining on this (not nse_symbol alone) lets the
    # 321 newly-resolved rows — where nse_symbol is null but symbol is verified — attach
    # their financials/subscription instead of silently missing.
    SYM = "COALESCE(NULLIF(UPPER(i.nse_symbol),''), NULLIF(UPPER(i.symbol),''))"
    select_sql = ",\n      ".join(f"{expr} AS {col}" for col, expr in MAP)
    build = f"""
      DROP TABLE IF EXISTS ipo_consolidated;
      CREATE TABLE ipo_consolidated AS
      SELECT
      {select_sql}
      FROM ipo_intelligence i
      LEFT JOIN ipo_issue_details        d ON UPPER(d.nse_symbol) = {SYM}
      LEFT JOIN ipo_subscription_history s ON UPPER(s.nse_symbol) = {SYM};
    """
    cur.execute(build)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ipocons_nse ON ipo_consolidated(nse_symbol)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ipocons_listing ON ipo_consolidated(listing_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ipocons_symfinal ON ipo_consolidated(symbol_final)")
    conn.commit()

    # ── schema_v2: empty jsonb enrichment columns (filled later by Phase C scraper) ──
    jsonb_cols = ["anchor_json", "gmp_history_json", "peer_json", "financial_history_json",
                  "selling_shareholder_json", "objects_json", "risk_tags_json",
                  "promoter_json", "market_snapshot_json"]
    for c in jsonb_cols:
        cur.execute(f"ALTER TABLE ipo_consolidated ADD COLUMN IF NOT EXISTS {c} jsonb")

    # ── schema_v2: the 7 evidence-backed signal columns ──
    cur.execute("""
      ALTER TABLE ipo_consolidated
        ADD COLUMN IF NOT EXISTS gap_bucket        text,
        ADD COLUMN IF NOT EXISTS is_profitable     boolean,
        ADD COLUMN IF NOT EXISTS valuation_premium numeric,
        ADD COLUMN IF NOT EXISTS regime_at_listing text,
        ADD COLUMN IF NOT EXISTS tp1_exit_note     text,
        ADD COLUMN IF NOT EXISTS operator_lock_flag boolean,
        ADD COLUMN IF NOT EXISTS brlm_tier         text,
        ADD COLUMN IF NOT EXISTS floor_price       numeric,
        ADD COLUMN IF NOT EXISTS ceiling_price     numeric,
        ADD COLUMN IF NOT EXISTS floor_defenses    int,
        ADD COLUMN IF NOT EXISTS level_verdict     text
    """)

    # gap_bucket: realized listing gap (listing_open - issue_price)/issue_price
    #   LOW <10% | MID 10-30% (the validated playable edge) | HIGH >30%
    cur.execute("""
      UPDATE ipo_consolidated SET gap_bucket = CASE
        WHEN issue_price IS NULL OR issue_price = 0 OR listing_open IS NULL THEN NULL
        WHEN (listing_open - issue_price) / issue_price * 100 < 10  THEN 'LOW'
        WHEN (listing_open - issue_price) / issue_price * 100 <= 30 THEN 'MID'
        ELSE 'HIGH' END
    """)

    # is_profitable: positive trailing PAT
    cur.execute("UPDATE ipo_consolidated SET is_profitable = (pat_cr IS NOT NULL AND pat_cr > 0)")

    # valuation_premium: IPO P/E relative to peer median. GOLDEN RULE — only write rows
    # where we can compute a real value; never blank an existing one to NULL.
    cur.execute("""
      UPDATE ipo_consolidated SET valuation_premium =
        round((ipo_pe - peer_median_pe) / peer_median_pe * 100, 1)
      WHERE ipo_pe IS NOT NULL AND peer_median_pe IS NOT NULL AND peer_median_pe > 0
        AND valuation_premium IS NULL
    """)

    # regime_at_listing: market regime on the listing date. market_regimes column names
    # differ across migrations (evaluation_date vs date; active_regime vs regime), so
    # discover them at runtime instead of assuming — skip gracefully if absent.
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name = 'market_regimes'""")
    mr_cols = {r[0] for r in cur.fetchall()}
    date_col = next((c for c in ("evaluation_date", "date", "regime_date", "trade_date") if c in mr_cols), None)
    reg_col  = next((c for c in ("active_regime", "regime") if c in mr_cols), None)
    if date_col and reg_col:
        cur.execute(f"""
          UPDATE ipo_consolidated c SET regime_at_listing = r.{reg_col}
          FROM market_regimes r WHERE r.{date_col} = c.listing_date
        """)
    else:
        print(f"  (regime: market_regimes missing date/regime cols {sorted(mr_cols)[:6]}… — skipped)")

    # india_vix: surface from market_regimes on the listing date — SAME source/pattern
    # as regime_at_listing above. The column-map (line ~210) reads i.india_vix, which is
    # always NULL; market_regimes is the real per-day source. FROM-join only touches rows
    # with a matching listing_date, so non-matching rows keep their build-time value.
    vix_col = next((c for c in ("india_vix", "vix", "vix_close", "india_vix_close") if c in mr_cols), None)
    if date_col and vix_col:
        cur.execute(f"""
          UPDATE ipo_consolidated c SET india_vix = r.{vix_col}
          FROM market_regimes r
          WHERE r.{date_col} = c.listing_date AND r.{vix_col} IS NOT NULL
            AND c.india_vix IS NULL
        """)  # GOLDEN RULE: fill empties only — never overwrite a populated cell
        print(f"  (vix: surfaced india_vix from market_regimes.{vix_col} on listing_date)")
    else:
        print(f"  (vix: market_regimes has no vix col {sorted(mr_cols)[:8]}… — skipped)")

    # tp1_exit_note: static research note (the validated MID-gap exit window)
    cur.execute("""
      UPDATE ipo_consolidated
      SET tp1_exit_note = 'Validated edge is MID-gap (10-30%); historical TP near listing+20td. Research signal, not a buy call.'
      WHERE gap_bucket = 'MID'
    """)

    # floor/ceiling from the listing-day ipo_level_analysis row (our tick-derived levels).
    # Guard: the table only exists once analyze_listing_day.py has run — skip if absent.
    cur.execute("SELECT to_regclass('public.ipo_level_analysis')")
    if cur.fetchone()[0]:
        cur.execute("""
          UPDATE ipo_consolidated c
          SET floor_price    = la.floor_price,
              ceiling_price  = la.ceiling_price,
              floor_defenses = la.floor_defenses,
              level_verdict  = la.verdict
          FROM ipo_level_analysis la
          WHERE UPPER(la.symbol) = c.symbol_final
            AND la.trade_date = c.listing_date
        """)
    else:
        print("  (floor/ceiling: ipo_level_analysis not found — skipped)")

    # NOTE (B2, deferred): operator_lock_flag needs a price_candles circuit-lock scan
    # (high==low across the first ~5 trading days); brlm_tier needs BRLM track-record
    # scoring. Columns exist (null) and will be computed in a verified follow-up pass.
    conn.commit()

    cur.execute("SELECT count(*) FROM ipo_consolidated")
    n = cur.fetchone()[0]
    cur.execute("""SELECT count(symbol_final), count(final_total), count(roe), count(lqi_final),
                          count(gap_bucket), count(*) FILTER (WHERE is_profitable),
                          count(regime_at_listing), count(floor_price)
                   FROM ipo_consolidated""")
    nsym, nsub, nroe, nlqi, ngap, nprof, nreg, nfloor = cur.fetchone()
    print(f"ipo_consolidated v2 built: {n} rows, {len(MAP)} base cols + signals/jsonb")
    print(f"  identity — symbol_final {nsym}/{n}")
    print(f"  joins    — subscription {nsub}/{n}, roe {nroe}/{n}, lqi_final {nlqi}/{n}")
    print(f"  signals  — gap_bucket {ngap}/{n}, profitable {nprof}, regime {nreg}/{n}, floor {nfloor}/{n}")
    print(f"  jsonb    — {len(jsonb_cols)} empty enrichment columns ready for Phase C")
    print(f"  deferred — operator_lock_flag, brlm_tier (columns added, computed in B2)")
    conn.close()

if __name__ == "__main__":
    main()
