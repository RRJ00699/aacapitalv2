#!/usr/bin/env python3
"""
topout_online.py — ONLINE (live-decidable) top-out detector. At each bar t, judges
using ONLY stored bars 1..t. Production excludes the research-only hindsight scoring.

TIER 1 (USER ALERT): sharp climax-top. Fires at t+1 when at bar t:
  (1) new running high  high[t]==max(high[1..t])
  (2) volume climax     vol[t] >= CLIMAX_X * avg(vol[t-20..t-1])
  (3) rejection confirm  close[t+1] < high[t]*(1-REJECT/100)

TIER 2 (SILENT, never alerts): rounding-top WATCH, tracked two ways:
  A structural: >=LH_N consecutive lower highs after a prior local peak
  B ma-roll:    close < SMA(MA_N) AND SMA turning down, after a prior peak
  Watch only PROMOTES (if it later triggers Tier-1) or INVALIDATES (new high).

The separately researched bottom mirror is not promoted in this owner-approved scope.
"""
import os, argparse, datetime as dt, json, statistics as st
from zoneinfo import ZoneInfo
import psycopg2
def f(x):
    try: return float(x)
    except: return None
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
    for t in range(n):
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

        # Researched Tier-1 contract: decision is emitted only once the next real bar
        # supplies rejection confirmation. This is the sole permitted next-bar read.
        next_close = cs[t+1] if t + 1 < n else None
        if (is_new_high and climax and next_close is not None
                and next_close < hs[t]*(1-REJECT/100)):
            alert_bar=t+1; alert_px=next_close; fire_path="TIER1_REJECTION"
            trigger={"state":"SOW_FIRE", "path":fire_path, "climax_high":hs[t],
                     "climax_volume":vs[t], "confirmation_close":next_close}
            if t2_watch: promoted=True
            break

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
    # Production deliberately returns only live-decidable TOP state. The separately
    # researched bottom mirror and hindsight scoring remain out of owner-approved scope.
    state_name = "TOP" if alert_bar is not None else ("WATCH" if t2_watch else max_state)
    return {"state": state_name, "alert": alert_bar is not None,
            "alert_bar": alert_bar, "alert_price": alert_px, "watch_kind": t2_kind,
            "promoted": promoted, "invalidated": invalidated,
            "trigger": trigger, "max_state": max_state, "fire_path": fire_path}

DETECTOR_VERSION = "topout-online-researched-v1"
DEFAULTS = dict(CLIMAX=3.0, REJECT=1.0, LH_N=3, MA_N=10, ACCEL=1.5,
                NBAR=8, VOLWIN=50, RETEST=2.0)

def detect_top(bars):
    if not bars:
        return {"state": "IDLE", "alert": False, "trigger": None, "max_state": "IDLE"}
    tuples = [(b["ts"], b["o"], b["h"], b["l"], b["c"], b.get("v")) for b in bars]
    return run_ipo(tuples, **DEFAULTS)

def level_is_permitted(conn):
    cur=conn.cursor()
    cur.execute("""SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c
      JOIN pg_class t ON t.oid=c.conrelid WHERE t.relname='listing_observations' AND c.contype='c'""")
    definitions=" ".join(str(row[0]) for row in cur.fetchall()).lower()
    return not definitions or "obs_type" not in definitions or "level" in definitions

IST = ZoneInfo("Asia/Kolkata")

def input_is_fresh(evaluated, latest_completed_session, now=None):
    """Use the stored daily-session series as the holiday-aware session source."""
    now_ist = (now or dt.datetime.now(dt.timezone.utc)).astimezone(IST)
    evaluated_ist = evaluated.astimezone(IST)
    if evaluated_ist.date() == now_ist.date() and now_ist.time() < dt.time(15, 30):
        return False
    return latest_completed_session is not None and evaluated_ist.date() >= latest_completed_session

def run(conn, *, limit, dry_run, ids=None):
    from nse_fetch import CANONICAL_UNIVERSE_SQL
    cur=conn.cursor()
    clause="AND i.id = ANY(%s)" if ids is not None else ""
    params=([ids, limit] if ids is not None else [limit])
    cur.execute(f"""SELECT i.id,i.name_display FROM ipo i WHERE {CANONICAL_UNIVERSE_SQL} AND EXISTS
      (SELECT 1 FROM market_candles_15m c WHERE c.ipo_id=i.id) {clause}
      ORDER BY i.id LIMIT %s""", params)
    targets=cur.fetchall()
    if not dry_run and not level_is_permitted(conn):
        raise RuntimeError("owner: listing_observations schema does not permit obs_type='level'")
    states=[]; inserted_total=0; counts={}
    for ipo_id,name in targets:
        cur.execute("SELECT ts,o,h,l,c,v FROM market_candles_15m WHERE ipo_id=%s ORDER BY ts", (ipo_id,))
        bars=[dict(zip(("ts","o","h","l","c","v"), row)) for row in cur.fetchall()]
        result=detect_top(bars); evaluated=bars[-1]["ts"]
        # market_candles is the existing market-wide structured session source: it
        # represents weekends and exchange holidays without comparing an IPO to itself.
        cur.execute("""SELECT max(d) FROM market_candles WHERE
                       d <= CASE WHEN (now() AT TIME ZONE 'Asia/Kolkata')::time < time '15:30'
                         THEN (now() AT TIME ZONE 'Asia/Kolkata')::date-1
                         ELSE (now() AT TIME ZONE 'Asia/Kolkata')::date END""")
        latest_session=(cur.fetchone() or [None])[0]
        if not input_is_fresh(evaluated, latest_session):
            payload={"detector_version":DETECTOR_VERSION,
                     "evaluated_through_bar":evaluated.isoformat(), "label":"DISCOVERY",
                     "state":"STALE_INPUT", "alert":False, "trigger":None,
                     "max_state":"STALE_INPUT"}
            counts["STALE_INPUT"]=counts.get("STALE_INPUT",0)+1
            states.append({"ipo_id":ipo_id,"name":name,"inserted":0,**payload})
            continue
        payload={"detector_version":DETECTOR_VERSION,"evaluated_through_bar":evaluated.isoformat(),
                 "label":"DISCOVERY",**result}
        inserted=0
        if not dry_run:
            cur.execute("""INSERT INTO listing_observations(ipo_id,observed_at,obs_type,payload)
              VALUES(%s,%s,'level',%s::jsonb) ON CONFLICT (ipo_id,obs_type,observed_at) DO NOTHING""",
                        (ipo_id,evaluated,json.dumps(payload)))
            inserted=cur.rowcount; inserted_total += inserted
        counts[payload["state"]]=counts.get(payload["state"],0)+1
        states.append({"ipo_id":ipo_id,"name":name,"inserted":inserted,**payload})
    if not dry_run: conn.commit()
    return {"selected":len(targets),"state_counts":counts,"observations_inserted":inserted_total,
            "states":states,"label":"DISCOVERY"}

def parse_ids(value):
    return [int(x) for x in value.split(",") if x.strip()] if value else None

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument("--limit",type=int,default=10)
    ap.add_argument("--ids"); ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--write",action="store_true")
    a=ap.parse_args(argv)
    if not (a.dry_run or a.write): ap.error("choose --dry-run or --write")
    conn=psycopg2.connect(os.environ["DATABASE_URL"])
    try: result=run(conn,limit=max(1,a.limit),dry_run=a.dry_run,ids=parse_ids(a.ids))
    finally: conn.close()
    print("TOP_DETECTOR="+json.dumps(result,default=str,sort_keys=True))

if __name__=="__main__": main()
