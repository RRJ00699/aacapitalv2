#!/usr/bin/env python3
"""
forensic.py â€” PER-IPO forensic for the top/bottom detector. NOT an aggregate score.
One row per tradable IPO: what the detector did, the real top/bottom, and the
MEASURABLE reason it hit / missed / fired-early â€” so we read the WHY case by case.

Reuses run_ipo() from topout_online.py (no logic duplication). 15-min from Kite.
Adds per-case:
  - furthest Wyckoff state, alert price, real peak/bottom, gap%
  - clean@2/3/5/8%  (is the TOP alert within X% of real peak â€” 4 tolerance columns)
  - later_high%  = how much higher price went AFTER the alert (early-fire size)
  - reason  = plain classification: CLEAN / EARLY_FIRE / LATE / SILENT_OK / MISSED
  - chart facts at the alert bar: vol_ratio (retest/BC), bars_since_BC, trigger_strength

Universe = tradable (band 10/20 + MF>0), all 2016+, token+ISIN (ISIN spine).
Output: terminal + CSV (forensic.csv). Batched 25, progress. NO blind run.
Cost: ~ tradable-count Kite calls, 6-9 min. Fresh Kite token.

Usage: python forensic.py [--limit N] [--out forensic.csv]
"""
import os, sys, io, argparse, datetime as dt, csv
if __name__=="__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2
sys.path.insert(0,".")
from topout_online import run_ipo, get_kite, f, _window

def stage2_confirm(r, bars, N=8):
    """After a CAUTION fire, decide PARABOLIC vs CONFIRMED two ways.
    Method A (fixed window N bars): price reclaims BC high within N bars -> PARABOLIC.
    Method B (structure): whichever happens first after alert â€” reclaim BC high
      (-> PARABOLIC) or break below alert-bar low by 2% (-> CONFIRMED)."""
    if not r["alert"] or not (r.get("trigger") or {}).get("bc_high"):
        return (None, None)
    hs=[f(x[2]) for x in bars]; ls=[f(x[3]) for x in bars]
    ab=r["alert_bar"]; bc=r["trigger"]["bc_high"]; alo=ls[ab]
    win=[hs[k] for k in range(ab+1, min(ab+1+N, len(bars))) if hs[k] is not None]
    a_label = "PARABOLIC" if (win and max(win) >= bc) else "CONFIRMED"
    b_label="CONFIRMED"
    for k in range(ab+1, len(bars)):
        if hs[k] is not None and hs[k] >= bc: b_label="PARABOLIC"; break
        if ls[k] is not None and alo is not None and ls[k] < alo*0.98: b_label="CONFIRMED"; break
    return (a_label, b_label)

def classify(r, bars):
    """Return (reason, later_high_pct, clean_flags dict)."""
    hs=[f(x[2]) for x in bars]
    if not r["alert"]:
        # did it have a real top it should have caught? (peak not at the very start/end)
        pk=r["peak_i"]; n=len(bars)
        had_top = 3 < pk < n-3
        return ("MISSED" if had_top and r["max_state"] in ("FAILED_RETEST","AR_CONFIRMED")
                else "SILENT_OK"), None, {}
    gap=abs(r["gap_to_peak"])          # % below real peak (0 = perfect)
    ab=r["alert_bar"]; ah=hs[ab]
    later=[hs[k] for k in range(ab+1,len(bars)) if hs[k] is not None]
    later_high = (100*(max(later)-ah)/ah) if later else 0.0
    clean={t: gap<=t for t in (2,3,5,8)}
    if later_high>8: reason="EARLY_FIRE"      # price ran >8% higher after alert
    elif gap<=5: reason="CLEAN"
    else: reason="LATE"                        # fired but well below peak, didn't run higher
    return reason, later_high, clean

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=0)
    ap.add_argument("--out",default="forensic.csv")
    ap.add_argument("--era",default="",help="early=2016-2020, late=2021-2026, blank=all")
    ap.add_argument("--all-ipos",dest="all_ipos",action="store_true",help="drop tradable filter (band/MF) â€” use ALL IPOs with 15-min")
    ap.add_argument("--climax",type=float,default=3.0); ap.add_argument("--reject",type=float,default=1.0)
    ap.add_argument("--lh",type=int,default=3); ap.add_argument("--ma",type=int,default=10)
    ap.add_argument("--accel",type=float,default=1.5); ap.add_argument("--nbar",type=int,default=8)
    ap.add_argument("--volwin",type=int,default=50); ap.add_argument("--retest",type=float,default=2.0)
    ap.add_argument("--window-days",dest="window_days",type=int,default=30,
                    help="truncate each IPO's bars to N calendar days from listing BEFORE scoring "
                         "(30 = anchor lock-in trade horizon; why the old table was intraday_30d)")
    a=ap.parse_args()
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    era_clause=""
    if a.era=="early": era_clause=" AND date_part('year',i.listing_date) BETWEEN 2016 AND 2020"
    elif a.era=="late": era_clause=" AND date_part('year',i.listing_date) BETWEEN 2021 AND 2026"
    tradable_clause="" if a.all_ipos else """
                     AND EXISTS (SELECT 1 FROM ipo_listing_band b
                                 WHERE b.ipo_id=i.id AND b.band_pct IN (10,20))
                     AND EXISTS (SELECT 1 FROM subscription_snapshots ss
                                 WHERE ss.ipo_id=i.id AND ss.mf_shares_bid>0)"""
    cur.execute("""SELECT i.id,i.name_display,i.listing_date
                   FROM ipo i
                   WHERE date_part('year',i.listing_date)>=2016"""+era_clause+"""
                     AND EXISTS (SELECT 1 FROM market_candles_15m x WHERE x.ipo_id=i.id)"""+tradable_clause+"""
                   ORDER BY i.listing_date DESC""")
    rows=cur.fetchall()
    if a.limit: rows=rows[:a.limit]
    print(f"FORENSIC â€” {len(rows)} IPOs {'[ALL, no tradable filter]' if a.all_ipos else '(tradable band10/20+MF>0)'}{' ['+a.era.upper()+' era]' if a.era else ''}, 15-min from STORED market_candles_15m")
    print("reason: CLEAN=within5% | EARLY_FIRE=ran>8% higher after | LATE=fired far below | MISSED | SILENT_OK\n")
    out=[]
    done=0; skipped=0
    counts={}
    curb=conn.cursor()
    for iid,name,ld in rows:
        done+=1
        curb.execute("""SELECT ts,o,h,l,c,v FROM market_candles_15m
                        WHERE ipo_id=%s ORDER BY ts""",(iid,))
        recs=curb.fetchall()
        if not recs or len(recs)<25: skipped+=1; continue
        b=[(x[0],x[1],x[2],x[3],x[4],x[5]) for x in recs]
        # 30-day trade horizon: truncate BEFORE scoring so real_peak / gap / later_high are
        # measured over what we'd actually hold (listing -> first anchor lock-in), not the
        # full ~257d Kite retention that reclassifies a clean 30-day top as EARLY_FIRE.
        if a.window_days: b=_window(b,a.window_days)
        r=run_ipo(b,a.climax,a.reject,a.lh,a.ma,a.accel,a.nbar,a.volwin,a.retest)
        reason,later_high,clean=classify(r,b)
        s2a,s2b=stage2_confirm(r,b)
        counts[reason]=counts.get(reason,0)+1
        trig=r.get("trigger") or {}
        row=dict(ipo=name, listed=str(ld), state=r["max_state"], reason=reason,
                 fire_path=r.get("fire_path"),
                 stage2_A=s2a, stage2_B=s2b,
                 alert_px=round(r["alert_px"],1) if r["alert"] else None,
                 real_peak=round(r["real_peak"],1),
                 gap_pct=round(r["gap_to_peak"],1) if r["alert"] else None,
                 later_high_pct=round(later_high,1) if later_high is not None else None,
                 clean2=clean.get(2), clean3=clean.get(3), clean5=clean.get(5), clean8=clean.get(8),
                 vol_ratio=round(trig.get("volume_ratio"),2) if trig.get("volume_ratio") else None,
                 bars_since_bc=trig.get("bars_since_bc"),
                 trig_strength=round(trig.get("trigger_strength"),1) if trig.get("trigger_strength") else None,
                 bot_alert=round(r["b_px"],1) if r["b_alert"] else None,
                 real_bot=round(r["real_bot"],1),
                 bot_gap=round(r["b_gap"],1) if r["b_alert"] else None)
        out.append(row)
        if done%25==0: print(f"  ...{done}/{len(rows)} (skipped {skipped})  so far: {counts}")
    # write CSV
    if out:
        with open(a.out,"w",newline="") as fh:
            w=csv.DictWriter(fh, fieldnames=list(out[0].keys())); w.writeheader()
            for row in out: w.writerow(row)
    print(f"\n=== REASON BREAKDOWN ({len(out)} IPOs) ===")
    for k in ("CLEAN","EARLY_FIRE","LATE","MISSED","SILENT_OK"):
        print(f"  {k:12} {counts.get(k,0)}")
    # clean-tolerance sensitivity across fires
    fired=[r for r in out if r["alert_px"] is not None]
    if fired:
        print(f"\nof {len(fired)} TOP fires, within tolerance:")
        for t in ("clean2","clean3","clean5","clean8"):
            c=sum(1 for r in fired if r[t]); print(f"  {t.replace('clean','')}%: {100*c//len(fired)}% ({c})")
    print(f"\nâœ“ CSV: {a.out}  â€” sort by 'reason' and 'later_high_pct' to read the misses. [DISCOVERY]")

    # ===== STAGE-2 COMPARISON: which method labels EARLY_FIRE as PARABOLIC correctly? =====
    # Truth: EARLY_FIRE should be PARABOLIC; CLEAN/LATE should be CONFIRMED.
    def score(method_key):
        ef=[r for r in out if r["reason"]=="EARLY_FIRE" and r[method_key]]
        good=[r for r in out if r["reason"] in ("CLEAN","LATE") and r[method_key]]
        ef_para=sum(1 for r in ef if r[method_key]=="PARABOLIC")
        good_conf=sum(1 for r in good if r[method_key]=="CONFIRMED")
        return (ef_para, len(ef), good_conf, len(good))
    print("\n=== STAGE-2 PARABOLIC CONFIRMATION â€” method comparison ===")
    print("(EARLY_FIRE should label PARABOLIC; CLEAN/LATE should label CONFIRMED)")
    for mk,name in [("stage2_A","Method A (fixed 8-bar window)"),("stage2_B","Method B (structure-first)")]:
        efp,efn,gc,gn=score(mk)
        print(f"  {name}")
        print(f"     EARLY_FIRE caught as PARABOLIC: {100*efp//max(efn,1)}% ({efp}/{efn})")
        print(f"     CLEAN/LATE kept as CONFIRMED:   {100*gc//max(gn,1)}% ({gc}/{gn})")
    cur.close(); conn.close()

if __name__=="__main__": main()

