#!/usr/bin/env python3
"""
prune_dead_columns.py — drops ONLY truly-dead master columns (no source will ever
fill them). Recoverable-but-empty columns (anchor/promoter/fresh-ofs/candles/
financials lanes exist) are deliberately KEPT. Safety: full-table backup FIRST,
then DROP. Dry-run default.

  python _scripts/prune_dead_columns.py            # shows what it would drop/keep
  python _scripts/prune_dead_columns.py --apply    # backup table + drop
"""
import os, sys, datetime, argparse

# Truly dead: abandoned ML design + never-built intraday-capture design + orphans.
DROP = [
    # ML / probability graveyard
    "feature_vector","prob_loss_0_10","prob_gain_0_10","prob_gain_10_20",
    "prob_gain_20_50","prob_gain_gt50","ml_pred" ,
    # scoring stubs that were never computed
    "buy_at_open_score","vwap_entry_score","post30_score","anchor_expiry_score",
    "operator_risk_score",  # note: keep if used elsewhere? it's <10% -> dead
    # never-built intraday subscription capture
    "sub_day1_qib","sub_day1_nii","sub_day1_retail","sub_day2_qib","sub_day2_nii",
    "sub_day2_retail","sub_day3_qib","sub_day3_nii","sub_day3_retail",
    "qib_day1_x","qib_day2_x","qib_day3_x","qib_day1_ratio","qib_day3_ratio",
    "nii_day1_x","nii_day2_x","retail_day1_x","qib_backloaded",
    "hit_uc_day2","hit_lc_day2","day1_liquid_float","return_day1_vwap",
    "return_day2","return_day15","return_day30","max_drawdown_day1",
    "nifty_alpha_day30","stop_triggered","day1_vwap","vwap","above_vwap",
    "buy_qty","sell_qty","listing_day_vwap","listing_vwap","listing_avwap",
    # orphan singletons with no source
    "hni_leverage_ratio","hni_breakeven_premium","key_reasons","risk_warning",
    "position_size","greenshoe_price","float_turnover_ratio","allotment_status",
    "similar_ipo_count","brlm_historical_win_rate","brlm_tier","valuation_premium_pct",
    "retail_allocation_pct","peg_ratio","cash_flow_positive","operating_cf_growth",
    "sector_heat","recent_ipo_breadth","sector_ipo_success_rate","last10_ipo_avg_return",
    "market_regime_score","free_float_pct","subsector","qib_to_retail_ratio",
]

# Deliberately KEPT despite being empty (a real lane will fill them):
KEEP_EMPTY = ["anchor_names","anchor_total_cr","anchor_count","anchor_investors",
    "anchor_domestic_pct","anchor_foreign_pct","anchor_flip_risk","anchor_top5_pct",
    "anchor_stalwart_names","anchor_offshore_names","anchor_classification",
    "anchor_lockup_30d_shares","anchor_lockup_90d_shares","anchor_qib_alloc_cr",
    "promoter_post_equity","promoter_dilution_pct","promoter_pledge_pct",
    "fresh_issue_cr","ofs_percentage","revenue_growth_3yr","pat_growth_3yr",
    "listing_volume","peer_ps","peer_pb","pe_ratio","sector_pe_median",
    "gmp_pct_t1","gmp_pct_t3","gmp_pct_t5","gmp_pct_t7","gmp_history"]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    import psycopg2
    DB = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    if not DB: sys.exit("DATABASE_URL not set")
    conn = psycopg2.connect(DB, connect_timeout=20); cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    live = {r[0] for r in cur.fetchall()}
    drop = [c for c in DROP if c in live]
    missing = [c for c in DROP if c not in live]
    print(f"columns to DROP ({len(drop)}):")
    for c in drop: print(f"   - {c}")
    if missing: print(f"\n(in DROP list but not in table, skipped: {missing})")
    print(f"\ndeliberately KEPT though empty (lane exists): {len([c for c in KEEP_EMPTY if c in live])}")
    if not a.apply:
        print("\nDRY RUN — --apply will: 1) backup whole table, 2) drop the above.")
        return
    stamp = datetime.date.today().strftime("%Y%m%d")
    bak = f"ipo_intelligence_backup_{stamp}"
    cur.execute(f'DROP TABLE IF EXISTS {bak}')
    cur.execute(f'CREATE TABLE {bak} AS TABLE ipo_intelligence')
    cur.execute(f"SELECT COUNT(*) FROM {bak}")
    print(f"backup created: {bak} ({cur.fetchone()[0]} rows)")
    for c in drop:
        cur.execute(f'ALTER TABLE ipo_intelligence DROP COLUMN IF EXISTS "{c}"')
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_name='ipo_intelligence'")
    print(f"dropped {len(drop)} columns. master now has {cur.fetchone()[0]} columns.")
    print(f"UNDO: columns recoverable from {bak} via ALTER TABLE ... ADD + UPDATE FROM backup.")
    conn.close()

if __name__ == "__main__":
    main()
