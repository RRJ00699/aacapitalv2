#!/usr/bin/env python3
"""
compute_descriptors.py — Bucket A technical DESCRIPTORS (what IS, never a forecast).

Adds four honest context descriptors to technical_features (one row/symbol, latest snapshot):
  1. COMPRESSION / VCP STATE — is the stock coiling? (recent range vs prior range; tighter = coiling).
     Reports a 0-100 "tightness" + a state label. Says "coiling", NOT "will break out".
  2. SUPPORT / RESISTANCE — nearest support below + resistance above, from swing pivots (price levels
     the stock repeatedly turned at), with % distance. Descriptive levels, not targets.
  3. GAP — today's open vs prior close: UP/DOWN/NONE + size%; whether an open gap is still unfilled.
  4. DELIVERY CONTEXT — today's delivery% vs its own 60d norm (ratio). Killed as a SIGNAL; kept as
     honest context ("real buyers vs this stock's own normal"). Labeled context, never a buy tag.

All point-in-time on the latest bar. No prediction. Writes/updates technical_features columns.
Run:  python compute_descriptors.py [--symbol RELIANCE --diag]
Env:  DATABASE_URL
"""
import os, sys, argparse, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")

def compression(high, low, close, recent=10, prior=50):
    """Tightness 0-100: recent avg true-range% vs prior. Lower recent range -> higher tightness."""
    if len(close) < prior + recent: return None, None
    tr = np.maximum(high[1:]-low[1:], np.maximum(abs(high[1:]-close[:-1]), abs(low[1:]-close[:-1])))
    trp = tr / close[1:] * 100
    r = np.nanmean(trp[-recent:]); p = np.nanmean(trp[-(prior+recent):-recent])
    if not p or p <= 0: return None, None
    ratio = r / p                      # <1 = contracting
    tightness = float(max(0, min(100, (1 - ratio) * 100 + 50)))   # 50=neutral, >50 tighter
    state = ("Coiling (tight)" if ratio < 0.6 else
             "Contracting" if ratio < 0.85 else
             "Normal" if ratio < 1.15 else
             "Expanding (volatile)")
    return round(tightness, 1), state

def swing_levels(high, low, close, lookback=180, win=5):
    """Nearest support (below) + resistance (above) from local swing pivots in the lookback window."""
    if len(close) < 30: return None, None, None, None
    h = high[-lookback:]; l = low[-lookback:]; px = close[-1]
    piv_hi, piv_lo = [], []
    for i in range(win, len(h)-win):
        if h[i] == max(h[i-win:i+win+1]): piv_hi.append(h[i])
        if l[i] == min(l[i-win:i+win+1]): piv_lo.append(l[i])
    res = [p for p in piv_hi if p > px*1.005]
    sup = [p for p in piv_lo if p < px*0.995]
    nearest_res = min(res) if res else None
    nearest_sup = max(sup) if sup else None
    res_dist = round((nearest_res/px-1)*100, 2) if nearest_res else None
    sup_dist = round((nearest_sup/px-1)*100, 2) if nearest_sup else None
    return (round(nearest_sup,2) if nearest_sup else None, sup_dist,
            round(nearest_res,2) if nearest_res else None, res_dist)

def gap_state(open_, high, low, close):
    """Today's open vs yesterday close: classify gap + whether it's been filled intraday."""
    if len(close) < 2: return None, None, None
    prev_close = close[-2]; o = open_[-1]; hi = high[-1]; lo = low[-1]
    g = (o/prev_close - 1) * 100
    if abs(g) < 0.5: return "None", round(g,2), None
    if g > 0:   # gap up: filled if today's low came back to prev_close
        return "Up", round(g,2), bool(lo <= prev_close)
    else:
        return "Down", round(g,2), bool(hi >= prev_close)

def delivery_ctx(deliv_series):
    """Today's delivery% vs its own 60d norm. Context only (killed as a signal)."""
    s = pd.Series(deliv_series).dropna()
    if len(s) < 25: return None, None, None
    today = float(s.iloc[-1]); base = float(s.iloc[-61:-1].mean()) if len(s) > 61 else float(s.iloc[:-1].mean())
    if base <= 0: return round(today,1), None, None
    ratio = today / base
    label = ("Elevated" if ratio >= 1.5 else "Above norm" if ratio >= 1.2 else
             "Normal" if ratio >= 0.8 else "Light")
    return round(today,1), round(ratio,2), label

def per_symbol(c, d=None):
    o=c["open"].to_numpy(float); h=c["high"].to_numpy(float); l=c["low"].to_numpy(float)
    cl=c["close"].to_numpy(float)
    tight, cstate = compression(h,l,cl)
    sup, supd, res, resd = swing_levels(h,l,cl)
    gdir, gsize, gfill = gap_state(o,h,l,cl)
    dtoday=dratio=dlabel=None
    if d is not None and len(d):
        dtoday, dratio, dlabel = delivery_ctx(d["delivery_percentage"].to_numpy(float))
    return dict(compression_tightness=tight, compression_state=cstate,
                support=sup, support_dist=supd, resistance=res, resistance_dist=resd,
                gap_dir=gdir, gap_size=gsize, gap_filled=gfill,
                delivery_today=dtoday, delivery_ratio=dratio, delivery_state=dlabel)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--symbol"); ap.add_argument("--diag",action="store_true")
    a=ap.parse_args()
    if not URL: sys.exit("DATABASE_URL not set")
    import psycopg2; from psycopg2.extras import execute_values
    conn=psycopg2.connect(URL)

    if a.symbol:
        sym=a.symbol.upper()
        c=pd.read_sql("SELECT symbol,date,open,high,low,close FROM price_candles WHERE symbol=%(s)s AND close>0 ORDER BY date",
                      conn, params={"s":sym})
        d=pd.read_sql("SELECT symbol,date,delivery_percentage FROM delivery_data WHERE symbol=%(s)s ORDER BY date",
                      conn, params={"s":sym})
        conn.close()
        if c.empty: print("no candles."); return
        r=per_symbol(c, d if len(d) else None)
        print(f"\n{sym} descriptors (context, not forecasts):")
        for k,v in r.items(): print(f"  {k:24} {v}")
        return

    print("loading candles + delivery…")
    px=pd.read_sql("SELECT symbol,date,open,high,low,close FROM price_candles WHERE close>0 ORDER BY symbol,date", conn)
    dv=pd.read_sql("SELECT symbol,date,delivery_percentage FROM delivery_data ORDER BY symbol,date", conn)
    px["symbol"]=px["symbol"].str.upper()
    if len(dv): dv["symbol"]=dv["symbol"].str.upper()
    dvg={s:g for s,g in dv.groupby("symbol")} if len(dv) else {}

    rows=[]
    for sym,g in px.groupby("symbol", sort=False):
        r=per_symbol(g, dvg.get(sym)); r["symbol"]=sym; rows.append(r)
    F=pd.DataFrame(rows)

    cur=conn.cursor()
    for col,typ in [("compression_tightness","NUMERIC(5,1)"),("compression_state","TEXT"),
                    ("support","NUMERIC(14,2)"),("support_dist","NUMERIC(8,2)"),
                    ("resistance","NUMERIC(14,2)"),("resistance_dist","NUMERIC(8,2)"),
                    ("gap_dir","TEXT"),("gap_size","NUMERIC(8,2)"),("gap_filled","BOOLEAN"),
                    ("delivery_today","NUMERIC(6,1)"),("delivery_ratio","NUMERIC(6,2)"),("delivery_state","TEXT")]:
        cur.execute(f"ALTER TABLE technical_features ADD COLUMN IF NOT EXISTS {col} {typ}")
    conn.commit()

    cols=["symbol","compression_tightness","compression_state","support","support_dist","resistance",
          "resistance_dist","gap_dir","gap_size","gap_filled","delivery_today","delivery_ratio","delivery_state"]
    data=[tuple(None if pd.isna(r[c]) else r[c] for c in cols) for _,r in F.iterrows()]
    # symbol rows already exist (created by compute_technical_features); update descriptor cols
    execute_values(cur, f"""
        INSERT INTO technical_features ({','.join(cols)}) VALUES %s
        ON CONFLICT (symbol) DO UPDATE SET {', '.join(f'{c}=EXCLUDED.{c}' for c in cols[1:])}""",
        data, page_size=500)
    conn.commit()
    n_coil=int((F["compression_state"]=="Coiling (tight)").sum())
    n_gap=int(F["gap_dir"].isin(["Up","Down"]).sum())
    print(f"descriptors: updated {len(F):,} symbols ({n_coil} coiling, {n_gap} gapped today).")
    conn.close()

if __name__=="__main__":
    main()
