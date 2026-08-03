#!/usr/bin/env python3
"""
topout_online.py — ONLINE (live-decidable) top-out detector. At each bar t, judges
using ONLY bars 1..t. Hindsight (real 30d peak) used ONLY for scoring, never in the
rule. 15-min from Kite. Reuses fetch pattern from topout_research.py.

TIER 1 (USER ALERT): sharp climax-top. Fires at t+1 when at bar t:
  (1) new running high  high[t]==max(high[1..t])
  (2) volume climax     vol[t] >= CLIMAX_X * avg(vol[t-20..t-1])
  (3) rejection confirm  close[t+1] < high[t]*(1-REJECT/100)

TIER 2 (SILENT, never alerts): rounding-top WATCH, tracked two ways:
  A structural: >=LH_N consecutive lower highs after a prior local peak
  B ma-roll:    close < SMA(MA_N) AND SMA turning down, after a prior peak
  Watch only PROMOTES (if it later triggers Tier-1) or INVALIDATES (new high).

Scoring (hindsight OK here): gap between alert price and real 30d peak, drawdown
avoided vs hold-to-last, false-fire (price later made higher high after alert).

Usage: python topout_online.py [--limit N] [--climax 3] [--reject 1] [--lh 3] [--ma 10]
"""
import os, sys, io, argparse, datetime as dt, statistics as st
if __name__=="__main__":
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception: pass
import psycopg2
def f(x):
    try: return float(x)
    except: return None
def get_kite():
    sys.path.insert(0,"_scripts"); from kite_connect import get_kite as gk
    k=gk(); k.profile(); return k

def bearish_candle(b, t):
    """True if bar t is a bearish reversal candle (sourced defs):
       - bearish engulfing: red body engulfs prior green body
       - shooting star: upper wick >=2x body, small body at low of range
       - dark cloud cover: red opens above prior green high, closes below its midpoint
    """
    o,h,l,c = f(b[t][1]),f(b[t][2]),f(b[t][3]),f(b[t][4])
    if None in (o,h,l,c) or h==l: return False
    body=abs(c-o); rng=h-l; upper=h-max(o,c); lower=min(o,c)-l
    red = c<o
    # shooting star (single bar)
    if body>0 and upper>=2*body and lower<=body and (max(o,c)-l)<=0.4*rng:
        return True
    # two-bar patterns need a prior green
    if t>0:
        po,pc = f(b[t-1][1]), f(b[t-1][4])
        if po is not None and pc is not None and pc>po:      # prior green
            # bearish engulfing
            if red and o>=pc and c<=po and body>=abs(pc-po):
                return True
            # dark cloud cover
            midp=(po+pc)/2
            if red and o>pc and c<midp and c>po:
                return True
    return False

def _window(b, days):
    """Truncate bars to `days` CALENDAR days from the first (listing-day) bar. The trade
    horizon is 30 days = the first anchor lock-in (why the old table was intraday_30d);
    real_peak / gap_to_peak / later_high must be measured over the window actually traded,
    not the full ~257d Kite retention — otherwise a CLEAN 30-day top reads as EARLY_FIRE."""
    if not b or not days:
        return b
    cutoff = b[0][0] + dt.timedelta(days=days)
    return [x for x in b if x[0] <= cutoff]


def run_ipo(b, CLIMAX, REJECT, LH_N, MA_N, ACCEL, NBAR, VOLWIN, RETEST,
            BREAKDOWN=1.0, SOW_MARGIN=1.0, window_days=None):
    """b = list of (ts,o,h,l,c,v) chronological. Returns result dict. ONLINE: at bar
    t only bars<=t used for decisions; t+1 used ONLY for the confirm close (allowed,
    it's the next real bar you'd wait for live). window_days truncates b FIRST so the
    hindsight scoring (real_peak) is over the traded horizon, not all of Kite's retention."""
    if window_days:
        b = _window(b, window_days)
    n=len(b)
    hs=[f(x[2]) for x in b]; cs=[f(x[4]) for x in b]; vs=[f(x[5]) for x in b]
    b0=f(b[0][1])  # listing open, for run-up filter
    run_high=-1; alert_bar=None; alert_px=None
    t2_watch=False; t2_kind=None; promoted=False; invalidated=False
    # WYCKOFF 4-STATE machine (states across DIFFERENT bars, never same-bar):
    #   BC_ARMED -> AR_CONFIRMED -> FAILED_RETEST -> SOW_FIRE
    state="IDLE"; bc_high=None; bc_vol=None; bc_bar=None
    ar_low=None; ar_low_frozen=None; retest_high=None; retest_vol=None
    trigger=None; max_state="IDLE"; fire_path=None
    _order={"IDLE":0,"BC_ARMED":1,"AR_CONFIRMED":2,"FAILED_RETEST":3,"SOW_FIRE":4}
    for t in range(n-1):
        if hs[t] is None: continue
        # --- TIER 2 watch state (silent) ---
        if t>=LH_N:
            lh_seq=all(hs[t-k] is not None and hs[t-k]<hs[t-k-1] for k in range(LH_N))
        else: lh_seq=False
        if t>=MA_N:
            sma=st.mean([hs[k] for k in range(t-MA_N+1,t+1) if hs[k] is not None])
            sma_prev=st.mean([hs[k] for k in range(t-MA_N,t) if hs[k] is not None])
            ma_roll = cs[t] is not None and cs[t]<sma and sma<sma_prev
        else: ma_roll=False
        if (lh_seq or ma_roll) and not t2_watch:
            t2_watch=True; t2_kind="A" if lh_seq else "B"

        is_new_high = hs[t]==max(x for x in hs[:t+1] if x is not None)
        recent = (hs[t]-hs[t-NBAR])/hs[t-NBAR] if (t>=NBAR and hs[t-NBAR]) else None
        base   = (hs[t-NBAR]-hs[t-2*NBAR])/hs[t-2*NBAR] if (t>=2*NBAR and hs[t-2*NBAR]) else None
        accel_ok = (recent is not None and base is not None
                    and recent>0 and recent >= ACCEL*max(base,0.0001))
        vwin=[vs[k] for k in range(max(0,t-VOLWIN),t) if vs[k]]
        av=[vs[k] for k in range(max(0,t-20),t) if vs[k]]; av=st.mean(av) if av else None
        climax = (vs[t] is not None and av and vs[t]>=CLIMAX*av
                  and (not vwin or vs[t]>=max(vwin)))
        o0,c0 = f(b[t][1]), cs[t]; lo0=f(b[t][3])

        # --- NEW high above BC at any armed state = continuation: re-arm or invalidate
        if state!="IDLE" and bc_high is not None and hs[t] > bc_high*1.01:
            if is_new_high and climax and accel_ok:
                state="BC_ARMED"; bc_high=hs[t]; bc_vol=vs[t]; bc_bar=t
                ar_low=None; ar_low_frozen=None; retest_high=None
            else:
                state="IDLE"; bc_high=None; ar_low=None; ar_low_frozen=None
                invalidated=True
            continue

        # STATE 1 — BC_ARMED: new high + accel + volume climax (re-arm to higher BC)
        if state in ("IDLE","BC_ARMED") and is_new_high and climax and accel_ok:
            if bc_high is None or hs[t]>bc_high:
                state="BC_ARMED"; bc_high=hs[t]; bc_vol=vs[t]; bc_bar=t
                ar_low=None; ar_low_frozen=None; retest_high=None
            continue

        # STATE 2 — AR_CONFIRMED: track automatic-reaction low; freeze it once price
        # bounces back up off that low (the AR is complete).
        if state=="BC_ARMED" and bc_bar is not None and t>bc_bar and lo0 is not None:
            ar_low = lo0 if ar_low is None else min(ar_low, lo0)
            if ar_low is not None and c0 is not None and c0 > ar_low*1.01:
                ar_low_frozen=ar_low; state="AR_CONFIRMED"

        # STATE 3 — FAILED_RETEST: rally back near BC high, stays below, lower vol,
        # bearish candle. Records retest; does NOT fire.
        if state=="AR_CONFIRMED" and bc_high is not None:
            near = hs[t] >= bc_high*(1-RETEST/100)
            failed = hs[t] < bc_high
            lower_vol = vs[t] is not None and bc_vol and vs[t] < bc_vol
            candle = bearish_candle(b, t)
            if near and failed and lower_vol and candle:
                retest_high=hs[t]; retest_vol=vs[t]; state="FAILED_RETEST"
                continue
            # NO-RETEST BREAKDOWN (fix for 36 AR_CONFIRMED misses): the top fell away
            # WITHOUT a retest — price breaks decisively below the frozen AR low. Fire.
            if (ar_low_frozen is not None and c0 is not None
                    and c0 < ar_low_frozen*(1-BREAKDOWN/100) and alert_bar is None):
                alert_bar=t; alert_px=c0; fire_path="NO_RETEST"
                trigger=dict(state="SOW_FIRE", path="NO_RETEST", bc_high=bc_high,
                             ar_low=ar_low_frozen, retest_high=None,
                             volume_ratio=None,
                             bars_since_bc=(t-bc_bar if bc_bar is not None else None),
                             trigger_strength=(100*(bc_high-c0)/bc_high if bc_high else None))
                if t2_watch: promoted=True
                break

        # STATE 4 — SOW_FIRE: a LATER bar closes below the FROZEN ar_low (structure
        # break = distribution complete). LOOSER (fix for 17): close below ar_low, OR
        # below ar_low by SOW_MARGIN% (catches marginal breaks that were being missed).
        if state=="FAILED_RETEST" and ar_low_frozen is not None and alert_bar is None:
            broke = c0 is not None and c0 < ar_low_frozen*(1+SOW_MARGIN/100)
            if broke:
                alert_bar=t; alert_px=c0; fire_path="SOW"
                trigger=dict(state="SOW_FIRE", path="SOW", bc_high=bc_high, ar_low=ar_low_frozen,
                             retest_high=retest_high,
                             volume_ratio=(retest_vol/bc_vol if (retest_vol and bc_vol) else None),
                             bars_since_bc=(t-bc_bar if bc_bar is not None else None),
                             trigger_strength=(100*(bc_high-c0)/bc_high if bc_high else None))
                if t2_watch: promoted=True
                break

        # invalidate T2 watch if a new high forms while watching
        if t2_watch and is_new_high and alert_bar is None:
            t2_watch=False
        if _order.get(state,0) > _order.get(max_state,0): max_state=state
    if trigger: max_state="SOW_FIRE"
    # scoring (hindsight)
    real_peak=max(x for x in hs if x is not None)
    peak_i=max(range(n), key=lambda k: hs[k] if hs[k] else -1)
    last=cs[-1]
    res=dict(alert=alert_bar is not None, alert_bar=alert_bar, alert_px=alert_px,
             real_peak=real_peak, peak_i=peak_i, last=last,
             t2_kind=t2_kind, promoted=promoted, invalidated=invalidated, trigger=trigger,
             max_state=max_state, fire_path=fire_path)
    if alert_bar is not None:
        res["gap_to_peak"]=100*(alert_px-real_peak)/real_peak
        res["dd_avoided"]=100*(alert_px-last)/last if last else None
        ah=hs[alert_bar]
        res["false_fire"]=any(hs[k] is not None and hs[k]>ah*1.05 for k in range(alert_bar+1,n))

    # ===== MIRROR: BOTTOM-OUT (new running low + selling climax + decisive bounce) =====
    ls=[f(x[3]) for x in b]
    b_alert=None; b_px=None
    sc_armed=False; sc_low=None; sc_vol=None
    for t in range(n-1):
        if ls[t] is None: continue
        is_new_low = ls[t]==min(x for x in ls[:t+1] if x is not None)
        rec = (ls[t-NBAR]-ls[t])/ls[t-NBAR] if (t>=NBAR and ls[t-NBAR]) else None
        bas = (ls[t-2*NBAR]-ls[t-NBAR])/ls[t-2*NBAR] if (t>=2*NBAR and ls[t-2*NBAR]) else None
        accel_dn = (rec is not None and bas is not None and rec>0 and rec>=ACCEL*max(bas,0.0001))
        vwin=[vs[k] for k in range(max(0,t-VOLWIN),t) if vs[k]]
        av=[vs[k] for k in range(max(0,t-20),t) if vs[k]]; av=st.mean(av) if av else None
        sell_climax = (vs[t] is not None and av and vs[t]>=CLIMAX*av
                       and (not vwin or vs[t]>=max(vwin)))
        # STEP 1 — ARM on Selling Climax (capitulation new low + accel-down + vol climax)
        if is_new_low and sell_climax and accel_dn:
            sc_armed=True; sc_low=ls[t]; sc_vol=vs[t]; continue
        # STEP 2 — FIRE on FAILED RETEST of the low (secondary test):
        #   price revisits near sc_low but HOLDS above it (higher low) on LOWER volume,
        #   and this bar is green (buyers stepping in).
        if sc_armed and sc_low is not None and b_alert is None:
            near = ls[t] <= sc_low*(1+RETEST/100)
            held = ls[t] > sc_low                       # higher low
            lower_vol = vs[t] is not None and sc_vol and vs[t] < sc_vol
            o0,c0=f(b[t][1]), cs[t]
            green = c0 is not None and o0 is not None and c0>o0
            if near and held and lower_vol and green:
                b_alert=t; b_px=c0; break
            if ls[t] < sc_low*0.99:                     # new low = invalidate arm
                sc_armed=False; sc_low=None
    real_bot=min(x for x in ls if x is not None)
    res["b_alert"]=b_alert is not None; res["b_px"]=b_px; res["real_bot"]=real_bot
    if b_alert is not None:
        res["b_gap"]=100*(b_px-real_bot)/real_bot
        bl=ls[b_alert]
        res["b_false"]=any(ls[k] is not None and ls[k]<bl*0.95 for k in range(b_alert+1,n))
    return res

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=10)
    ap.add_argument("--climax",type=float,default=3.0); ap.add_argument("--reject",type=float,default=1.0)
    ap.add_argument("--lh",type=int,default=3); ap.add_argument("--ma",type=int,default=10)
    ap.add_argument("--accel",type=float,default=1.5)    # recent leg >= ACCEL x prior leg
    ap.add_argument("--nbar",type=int,default=8)         # leg length in bars (~2hr)
    ap.add_argument("--volwin",type=int,default=50)
    ap.add_argument("--retest",type=float,default=2.0)   # retest within X% of climax level
    ap.add_argument("--window-days",dest="window_days",type=int,default=30,
                    help="truncate bars to N calendar days from listing before scoring (30 = anchor lock-in horizon)")
    ap.add_argument("--full",action="store_true")       # tradable 269 (band10/20+MF>0)
    ap.add_argument("--all",action="store_true")         # ALL 531 IPOs 2016+ (no band/MF)
    a=ap.parse_args()
    conn=psycopg2.connect(os.environ["DATABASE_URL"]); cur=conn.cursor()
    if a.all:
        cur.execute("""SELECT i.id,i.kite_token,i.name_display,i.listing_date
                       FROM ipo i
                       WHERE date_part('year',i.listing_date)>=2016
                         AND i.kite_token IS NOT NULL AND i.isin IS NOT NULL
                       ORDER BY i.listing_date DESC""")
        rows=cur.fetchall()
    elif a.full:
        cur.execute("""SELECT i.id,i.kite_token,i.name_display,i.listing_date
                       FROM ipo i
                       WHERE i.in_backtest_universe=TRUE AND i.kite_token IS NOT NULL
                         AND i.isin IS NOT NULL
                         AND date_part('year',i.listing_date)>=2016
                         AND EXISTS (SELECT 1 FROM ipo_listing_band b
                                     WHERE b.ipo_id=i.id AND b.band_pct IN (10,20))
                         AND EXISTS (SELECT 1 FROM subscription_snapshots ss
                                     WHERE ss.ipo_id=i.id AND ss.mf_shares_bid>0)
                       ORDER BY i.listing_date DESC""")
        rows=cur.fetchall()
    else:
        cur.execute("""SELECT i.id,i.kite_token,i.name_display,i.listing_date
                       FROM ipo i
                       WHERE i.in_backtest_universe=TRUE AND i.kite_token IS NOT NULL
                         AND i.isin IS NOT NULL
                         AND date_part('year',i.listing_date)>=2025
                         AND EXISTS (SELECT 1 FROM ipo_listing_band b
                                     WHERE b.ipo_id=i.id AND b.band_pct IN (10,20))
                         AND EXISTS (SELECT 1 FROM subscription_snapshots ss
                                     WHERE ss.ipo_id=i.id AND ss.mf_shares_bid>0)
                       ORDER BY i.listing_date DESC""")
        rows=cur.fetchall()[:a.limit]
    kite=get_kite()
    print(f"ONLINE top-out — {len(rows)} IPOs, 15-min live. climax>={a.climax}x + highest-in-{a.volwin} + accel>={a.accel}x(leg{a.nbar}) + decisive-reject\n")
    if a.full or a.all: print(f"running {len(rows)} IPOs — progress every 25...")
    else: print(f"{'IPO':22}{'TOP@px':>10}{'realpk':>9}{'gap%':>6}{'BOT@px':>10}{'realbot':>9}{'bgap%':>6}")
    fires=0; falses=0; bfires=0; bfalses=0; done=0; skipped=0
    tgaps=[]; bgaps=[]; ddsaved=[]; states={}
    for iid,tok,name,ld in rows:
        done+=1
        try:
            end=min(ld+dt.timedelta(days=60), dt.date.today())
            bars=kite.historical_data(tok,ld,end,"15minute")
        except Exception as e:
            if not (a.full or a.all): print(f"  {name[:20]:20} kite fail {str(e)[:22]}")
            skipped+=1; continue
        if not bars or len(bars)<25: skipped+=1; continue
        b=[(x["date"],x["open"],x["high"],x["low"],x["close"],x.get("volume")) for x in bars]
        r=run_ipo(b,a.climax,a.reject,a.lh,a.ma,a.accel,a.nbar,a.volwin,a.retest,window_days=a.window_days)
        if r["alert"]:
            fires+=1; tgaps.append(r["gap_to_peak"])
            if r.get("dd_avoided") is not None: ddsaved.append(r["dd_avoided"])
            if r.get("false_fire"): falses+=1
        if r["b_alert"]:
            bfires+=1; bgaps.append(r["b_gap"])
            if r.get("b_false"): bfalses+=1
        states[r["max_state"]]=states.get(r["max_state"],0)+1
        if not (a.full or a.all):
            top=f"{r['alert_px']:.1f}" if r["alert"] else "—"
            bot=f"{r['b_px']:.1f}" if r["b_alert"] else "—"
            tgap=f"{r['gap_to_peak']:+.1f}" if r["alert"] else ""
            bgap=f"{r['b_gap']:+.1f}" if r["b_alert"] else ""
            print(f"{name[:21]:22}{top:>10}{r['real_peak']:>9.1f}{tgap:>6}{bot:>10}{r['real_bot']:>9.1f}{bgap:>6}  {r['max_state']}")
        elif done%25==0:
            print(f"  ...{done}/{len(rows)} processed (fired {fires}, skipped {skipped})")
    print(f"\nTOP fired {fires}/{len(rows)} (false {falses})   BOTTOM fired {bfires}/{len(rows)} (false {bfalses})   skipped {skipped}")
    if tgaps:
        import statistics as _s
        tgaps_s=sorted(tgaps)
        print(f"TOP gap-to-peak: median {_s.median(tgaps):+.1f}%  best {max(tgaps):+.1f}%  worst {min(tgaps):+.1f}%")
        good=100*sum(1 for g in tgaps if g>=-8)/len(tgaps)
        print(f"  within 8% of real peak: {good:.0f}% of fires")
        if ddsaved: print(f"  drawdown saved vs last close: median {_s.median(ddsaved):+.1f}%")
    if bgaps:
        import statistics as _s
        goodb=100*sum(1 for g in bgaps if 0<=g<=10)/len(bgaps)
        print(f"BOTTOM gap-above-low: median {_s.median(bgaps):+.1f}%  within 0-10% of real bottom: {goodb:.0f}%")
    print("gap%<0 = TOP alert below real peak (good). bgap%>0 = BOTTOM alert above real bottom (good). [DISCOVERY]")
    print("TOP state distribution:", " ".join(f"{k}={states.get(k,0)}" for k in
          ["IDLE","BC_ARMED","AR_CONFIRMED","FAILED_RETEST","SOW_FIRE"]))
    cur.close(); conn.close()

if __name__=="__main__": main()
