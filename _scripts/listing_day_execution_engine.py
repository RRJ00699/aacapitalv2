"""
AACapital IPO Alpha Engine V3
_scripts/listing_day_execution_engine.py

Real Kite WebSocket listing day monitor.
Replaces simulation with live call-auction market depth from Kite.

Usage:
  python _scripts/listing_day_execution_engine.py --ipo "BLS E-Services"
  python _scripts/listing_day_execution_engine.py --symbol BLSE --issue-price 135 --lqi 96
  python _scripts/listing_day_execution_engine.py --simulate --scenario BULLISH
  python _scripts/listing_day_execution_engine.py --ipo "Carraro India" --simulate --scenario BEARISH
"""

import os
import sys
import time
import json
import logging
import argparse
import threading
import psycopg2
from datetime import datetime, date
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger()

DATABASE_URL      = os.environ.get("DATABASE_URL", "")
KITE_API_KEY      = os.environ.get("KITE_API_KEY",      "br9m41pn8nvvywnl")
KITE_API_SECRET   = os.environ.get("KITE_API_SECRET",   "")
KITE_ACCESS_TOKEN = os.environ.get("KITE_ACCESS_TOKEN", "")
if not KITE_ACCESS_TOKEN:
    try:
        import psycopg2 as _pg
        _db = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL", "")
        if _db:
            _c = _pg.connect(_db); _cur = _c.cursor()
            _cur.execute("SELECT value FROM platform_config WHERE key = 'kite_access_token'")
            _r = _cur.fetchone(); _cur.close(); _c.close()
            if _r and _r[0]: KITE_ACCESS_TOKEN = str(_r[0]).strip()
    except Exception:
        pass

OI_HOLD_THRESHOLD = 65.0
OI_NEUTRAL_LOW    = 50.0
OI_EXIT_THRESHOLD = 40.0
POLL_INTERVAL_SEC = 60


# ── Kite WebSocket ─────────────────────────────────────────────────────────────

class KiteLiveMonitor:
    def __init__(self, api_key, access_token, instrument_token):
        self.api_key      = api_key
        self.access_token = access_token
        self.token        = instrument_token
        self.latest_tick  = {}
        self._connected   = False

    def start(self):
        try:
            from kiteconnect import KiteTicker
        except ImportError:
            log.error("kiteconnect not installed. Run: pip install kiteconnect")
            sys.exit(1)

        self.ticker = KiteTicker(self.api_key, self.access_token)

        def on_ticks(ws, ticks):
            for tick in ticks:
                if tick["instrument_token"] == self.token:
                    self.latest_tick = tick

        def on_connect(ws, response):
            log.info("Kite WebSocket connected")
            ws.subscribe([self.token])
            ws.set_mode(ws.MODE_FULL, [self.token])
            self._connected = True

        def on_error(ws, code, reason):
            log.error(f"WebSocket error {code}: {reason}")

        def on_close(ws, code, reason):
            log.warning(f"WebSocket closed: {reason}")
            self._connected = False

        self.ticker.on_ticks   = on_ticks
        self.ticker.on_connect = on_connect
        self.ticker.on_error   = on_error
        self.ticker.on_close   = on_close

        t = threading.Thread(target=self.ticker.connect, kwargs={"threaded": True})
        t.daemon = True
        t.start()
        time.sleep(3)

    def get_depth_signal(self) -> dict:
        tick = self.latest_tick
        if not tick:
            return {"ready": False}
        depth      = tick.get("depth", {})
        buy_levels = depth.get("buy",  [])
        sel_levels = depth.get("sell", [])
        total_buy  = sum(l.get("quantity", 0) for l in buy_levels)
        total_sell = sum(l.get("quantity", 0) for l in sel_levels)
        total      = total_buy + total_sell
        return {
            "ready":         True,
            "live_price":    tick.get("last_price", 0),
            "buy_qty":       total_buy,
            "sell_qty":      total_sell,
            "total_qty":     total,
            "oi_buy_pct":    round(total_buy  / total * 100, 2) if total > 0 else 50.0,
            "oi_sell_pct":   round(total_sell / total * 100, 2) if total > 0 else 50.0,
            "volume":        tick.get("volume_traded", 0),
            "average_price": tick.get("average_traded_price", 0),
        }

    def stop(self):
        if hasattr(self, "ticker"):
            self.ticker.close()


# ── Kite REST quote fallback ───────────────────────────────────────────────────

class KiteQuoteMonitor:
    def __init__(self, api_key, access_token, exchange_symbol):
        self.exchange_symbol = exchange_symbol
        self.kite = None
        try:
            from kiteconnect import KiteConnect
            self.kite = KiteConnect(api_key=api_key)
            self.kite.set_access_token(access_token)
        except ImportError:
            log.error("kiteconnect not installed.")

    def get_depth_signal(self) -> dict:
        if not self.kite:
            return {"ready": False}
        try:
            data       = self.kite.quote([self.exchange_symbol])
            q          = data.get(self.exchange_symbol, {})
            depth      = q.get("depth", {})
            buy_levels = depth.get("buy",  [])
            sel_levels = depth.get("sell", [])
            total_buy  = sum(l.get("quantity", 0) for l in buy_levels)
            total_sell = sum(l.get("quantity", 0) for l in sel_levels)
            total      = total_buy + total_sell
            return {
                "ready":         True,
                "live_price":    q.get("last_price", 0),
                "buy_qty":       total_buy,
                "sell_qty":      total_sell,
                "total_qty":     total,
                "oi_buy_pct":    round(total_buy  / total * 100, 2) if total > 0 else 50.0,
                "oi_sell_pct":   round(total_sell / total * 100, 2) if total > 0 else 50.0,
                "volume":        q.get("volume", 0),
                "average_price": q.get("average_price", 0),
            }
        except Exception as e:
            log.error(f"Quote error: {e}")
            return {"ready": False}

    def stop(self): pass


# ── Simulation ─────────────────────────────────────────────────────────────────

class SimulatedMonitor:
    def __init__(self, issue_price, scenario="BULLISH"):
        self.issue_price = issue_price
        self.scenario    = scenario

    def get_depth_signal(self) -> dict:
        if self.scenario == "BULLISH":
            buy_vol  = float(os.getenv("SIM_BUY_VOL",   720000))
            sell_vol = float(os.getenv("SIM_SELL_VOL",  280000))
            price    = float(os.getenv("SIM_LIVE_PRICE", self.issue_price * 1.35))
        elif self.scenario == "BEARISH":
            buy_vol  = 310000
            sell_vol = 690000
            price    = self.issue_price * 0.93
        else:
            buy_vol  = 510000
            sell_vol = 490000
            price    = self.issue_price * 1.08

        total = buy_vol + sell_vol
        return {
            "ready":         True,
            "live_price":    round(price, 2),
            "buy_qty":       int(buy_vol),
            "sell_qty":      int(sell_vol),
            "total_qty":     int(total),
            "oi_buy_pct":    round(buy_vol  / total * 100, 2),
            "oi_sell_pct":   round(sell_vol / total * 100, 2),
            "volume":        int(total),
            "average_price": round(price * 0.99, 2),
        }

    def stop(self): pass


# ── Decision engine ────────────────────────────────────────────────────────────

def compute_signal(tick: dict, issue_price: float, gmp_price: float,
                   lqi: int, phase: str) -> dict:
    if not tick.get("ready"):
        return {"signal": "WAIT", "reason": "No live data yet",
                "color": "YELLOW", "premium": 0, "gmp_gap": 0, "warnings": []}

    oi_buy  = tick["oi_buy_pct"]
    oi_sell = tick["oi_sell_pct"]
    price   = tick["live_price"]
    premium = round((price - issue_price) / issue_price * 100, 2) if issue_price > 0 else 0
    gmp_gap = round((price - gmp_price)   / gmp_price   * 100, 2) if gmp_price  > 0 else 0
    warnings = []

    if phase in ("AUCTION", "FINAL"):
        if price < issue_price:
            signal = "EXIT IMMEDIATELY"
            reason = f"Listing below issue price (₹{price} vs ₹{issue_price}). Exit without hesitation."
            color  = "RED"
        elif oi_buy >= 70 and premium > 0:
            signal = "STRONG HOLD / MOMENTUM CHASE"
            reason = f"Auction heavily skewed to buyers ({oi_buy}%). Strong institutional demand."
            color  = "GREEN"
        elif oi_buy >= OI_HOLD_THRESHOLD:
            signal = "HOLD"
            reason = f"Buy depth {oi_buy}% — bulls in control."
            color  = "GREEN"
        elif oi_buy >= OI_NEUTRAL_LOW:
            if lqi >= 65:
                signal = "HOLD WITH STOP"
                reason = f"Neutral auction ({oi_buy}% buy). LQI {lqi} provides structural support."
            else:
                signal = "WATCH"
                reason = f"Neutral auction ({oi_buy}% buy). LQI {lqi} low — proceed with caution."
            color = "YELLOW"
        elif oi_buy <= OI_EXIT_THRESHOLD:
            signal = "EXIT ON CREDIT" if phase == "FINAL" else "CAUTION / LIKELY EXIT"
            reason = f"Sell pressure dominating ({oi_sell}% sell). Avoid holding."
            color  = "RED"
        else:
            signal = "WATCH"
            reason = f"Mixed signals. OI buy {oi_buy}%."
            color  = "YELLOW"

        if gmp_price > 0 and gmp_gap < -15:
            warnings.append(
                f"GMP disconnect: live ₹{price} vs GMP ₹{gmp_price:.0f} (gap {gmp_gap}%)"
            )

    elif phase == "EXECUTION":
        if price < issue_price:
            signal = "EXIT IMMEDIATELY"
            reason = "Price below issue price. No debate — exit."
            color  = "RED"
        elif oi_buy >= 65 and premium > 50:
            signal = "PARTIAL EXIT + TRAIL"
            reason = f"Gain {premium}% — bank 50%, trail rest with VWAP stop."
            color  = "GREEN"
        elif oi_buy >= 65:
            signal = "HOLD / MOMENTUM CHASE"
            reason = f"OI {oi_buy}% bullish. Price up {premium}%. Hold above VWAP."
            color  = "GREEN"
        elif oi_buy >= 50:
            signal = "HOLD WITH STOP"
            reason = "Neutral order book. Hold if price > listing VWAP. Exit on 2 candles below VWAP."
            color  = "YELLOW"
        elif oi_buy <= OI_EXIT_THRESHOLD:
            signal = "EXIT"
            reason = f"Sell pressure {oi_sell}%. Fading fast. Exit at best available price."
            color  = "RED"
        else:
            signal = "WAIT"
            reason = "Mixed signals. Watch VWAP for 15 min before deciding."
            color  = "YELLOW"

    else:
        signal   = "MONITORING"
        reason   = "Watching auction develop."
        color    = "BLUE"

    return {
        "signal":   signal,
        "reason":   reason,
        "color":    color,
        "premium":  premium,
        "gmp_gap":  gmp_gap,
        "warnings": warnings,
    }


# ── Display ────────────────────────────────────────────────────────────────────

COLOR = {
    "GREEN":  "\033[92m",
    "YELLOW": "\033[93m",
    "RED":    "\033[91m",
    "BLUE":   "\033[94m",
    "RESET":  "\033[0m",
    "BOLD":   "\033[1m",
}

def print_header(company, lqi, issue_price, gmp_price, p10, p_loss, similar, pre_signal):
    print("\n" + "="*70)
    print(f"{COLOR['BOLD']}  AACAPITAL IPO ALPHA ENGINE V3 — LISTING DAY MONITOR{COLOR['RESET']}")
    print(f"  {company.upper()}")
    print("="*70)
    print(f"  Issue Price    : ₹{issue_price}")
    print(f"  LQI            : {lqi}/100")
    print(f"  P(>10% gain)   : {p10}%")
    print(f"  P(loss)        : {p_loss}%")
    if gmp_price:
        prem = round((gmp_price - issue_price) / issue_price * 100, 1)
        print(f"  GMP            : ₹{gmp_price:.0f} ({prem}% premium)")
    if similar:
        print(f"  Similar IPOs   : {', '.join(str(s) for s in similar[:3])}")
    print(f"  Pre-market     : {pre_signal}")
    print("="*70 + "\n")


def print_tick(ts, tick, decision):
    c   = COLOR.get(decision["color"], "")
    r   = COLOR["RESET"]
    b   = COLOR["BOLD"]
    oi  = tick.get("oi_buy_pct", 0)
    bar = f"[{'█' * int(oi/5)}{'░' * (20 - int(oi/5))}]"
    print(
        f"  {b}[{ts}]{r}  "
        f"₹{tick.get('live_price', 0):<8.2f}  "
        f"{decision.get('premium', 0):+.1f}%  "
        f"OI buy: {c}{oi:5.1f}%{r} {bar}  "
        f"→ {c}{b}{decision.get('signal', '—')}{r}"
    )
    for w in decision.get("warnings", []):
        print(f"  {COLOR['YELLOW']}  ⚠ {w}{COLOR['RESET']}")


def print_final_card(company, issue_price, gmp_price, tick, decision, pre_signal, final_signal):
    c = COLOR.get(decision["color"], "")
    r = COLOR["RESET"]
    b = COLOR["BOLD"]
    print("\n" + "═"*70)
    print(f"{b}  AACAPITAL LISTING DAY FINAL DECISION{r}")
    print("═"*70)
    print(f"  IPO              : {company}")
    print(f"  Issue Price      : ₹{issue_price}")
    if gmp_price:
        print(f"  GMP Expected     : ₹{gmp_price:.0f}")
    print(f"  Final Listing    : ₹{tick.get('live_price', 0):.2f}")
    print(f"  Listing Gain     : {decision.get('premium', 0):+.1f}%")
    print(f"  OI Buy           : {tick.get('oi_buy_pct', 0):.1f}%")
    print(f"  OI Sell          : {tick.get('oi_sell_pct', 0):.1f}%")
    print(f"  Buy Qty          : {tick.get('buy_qty', 0):,.0f}")
    print(f"  Sell Qty         : {tick.get('sell_qty', 0):,.0f}")
    print(f"  Pre-market       : {pre_signal}")
    print(f"  Auction Signal   : {final_signal}")
    print(f"\n  {b}RECOMMENDED ACTION : {c}{decision.get('signal', '—')}{r}")
    print(f"  {decision.get('reason', '')}")
    for w in decision.get("warnings", []):
        print(f"\n  {COLOR['YELLOW']}⚠ {w}{r}")
    print("═"*70 + "\n")


# ── Neon helpers ───────────────────────────────────────────────────────────────

def load_ipo_from_neon(company_name: str) -> Optional[dict]:
    if not DATABASE_URL:
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute("""
            SELECT company_name, symbol, issue_price, lqi_final,
                   prob_10pct_profit, prob_loss_gt10, expected_return,
                   gmp_percentage, gmp_value, similar_ipos, suggested_action,
                   sector, archetype
            FROM ipo_intelligence
            WHERE company_name ILIKE %s
            LIMIT 1
        """, [f"%{company_name}%"])
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        cols = ["company_name", "symbol", "issue_price", "lqi", "p10", "p_loss",
                "exp_return", "gmp_pct", "gmp_value", "similar_ipos",
                "pre_action", "sector", "archetype"]
        return dict(zip(cols, row))
    except Exception as e:
        log.error(f"Neon load error: {e}")
        return None


def get_instrument_token(symbol: str) -> Optional[int]:
    if not DATABASE_URL or not symbol:
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute("""
            SELECT instrument_token FROM instrument_master
            WHERE tradingsymbol = %s AND exchange = 'NSE'
            LIMIT 1
        """, [symbol.upper()])
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        log.error(f"Token lookup error: {e}")
        return None


def save_listing_signal(company_name, symbol, tick, final_dec, exec_dec):
    if not DATABASE_URL:
        return
    try:
        # Map signal text to a short code for signal_quality column
        signal_map = {
            "STRONG HOLD / MOMENTUM CHASE": "STRONG_HOLD",
            "HOLD / MOMENTUM CHASE":        "HOLD",
            "HOLD WITH STOP":               "HOLD_STOP",
            "PARTIAL EXIT + TRAIL":         "PARTIAL_EXIT",
            "EXIT ON CREDIT":               "EXIT",
            "EXIT IMMEDIATELY":             "EXIT",
            "EXIT":                         "EXIT",
            "WATCH":                        "WATCH",
            "WAIT":                         "WAIT",
            "CAUTION / LIKELY EXIT":        "CAUTION",
        }
        sig_code = signal_map.get(exec_dec.get("signal", ""), "WATCH")

        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO ipo_listing_signals
              (symbol, listing_date, listing_open,
               oi_buy_pct, oi_sell_pct, oi_total,
               signal_quality, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (symbol, listing_date)
            DO UPDATE SET
              listing_open   = EXCLUDED.listing_open,
              oi_buy_pct     = EXCLUDED.oi_buy_pct,
              oi_sell_pct    = EXCLUDED.oi_sell_pct,
              oi_total       = EXCLUDED.oi_total,
              signal_quality = EXCLUDED.signal_quality
        """, [
            symbol or company_name[:10].upper().replace(" ", ""),
            date.today().isoformat(),
            tick.get("live_price"),
            tick.get("oi_buy_pct"),
            tick.get("oi_sell_pct"),
            tick.get("total_qty"),
            sig_code,
        ])
        conn.commit()
        conn.close()
        log.info(f"Signal saved: {company_name} ({symbol}) → {sig_code}")
    except Exception as e:
        log.error(f"Save error: {e}")


# ── Main orchestration ─────────────────────────────────────────────────────────

def run(company_name, symbol, issue_price, lqi, gmp_value, p10, p_loss,
        similar, pre_signal, simulate=False, sim_scenario="BULLISH"):

    gmp_price = issue_price * (1 + gmp_value / 100) if gmp_value else 0

    print_header(company_name, lqi, issue_price, gmp_price,
                 p10, p_loss, similar, pre_signal)

    # Setup data source
    if simulate:
        log.info("Running in SIMULATION mode")
        monitor = SimulatedMonitor(issue_price, scenario=sim_scenario)
    elif KITE_ACCESS_TOKEN:
        token = get_instrument_token(symbol)
        if token:
            log.info(f"Using Kite WebSocket (token {token})")
            monitor = KiteLiveMonitor(KITE_API_KEY, KITE_ACCESS_TOKEN, token)
            monitor.start()
        else:
            log.warning(f"No instrument token for {symbol} — using REST quote")
            monitor = KiteQuoteMonitor(KITE_API_KEY, KITE_ACCESS_TOKEN, f"NSE:{symbol}")
    else:
        log.warning("KITE_ACCESS_TOKEN not set — simulation mode")
        monitor = SimulatedMonitor(issue_price, scenario=sim_scenario)

    # Phase 1: Auction window
    print(f"  {'─'*66}")
    print(f"  PHASE 1 — CALL AUCTION (9:30 AM – 10:15 AM)")
    print(f"  {'─'*66}")

    auction_end = datetime.now().replace(hour=10, minute=15, second=0, microsecond=0)
    history     = []

    if simulate:
        for ts in ["09:30", "09:45", "10:00", "10:15"]:
            tick = monitor.get_depth_signal()
            dec  = compute_signal(tick, issue_price, gmp_price, lqi, "AUCTION")
            print_tick(ts, tick, dec)
            history.append((ts, tick, dec))
            time.sleep(0.5)
    else:
        while datetime.now() < auction_end:
            tick = monitor.get_depth_signal()
            dec  = compute_signal(tick, issue_price, gmp_price, lqi, "AUCTION")
            ts   = datetime.now().strftime("%H:%M")
            print_tick(ts, tick, dec)
            history.append((ts, tick, dec))
            time.sleep(POLL_INTERVAL_SEC)

    # Phase 2: Final lock
    print(f"\n  {'─'*66}")
    print(f"  PHASE 2 — LISTING PRICE LOCKED (10:15 AM)")
    print(f"  {'─'*66}")
    final_tick = monitor.get_depth_signal()
    final_dec  = compute_signal(final_tick, issue_price, gmp_price, lqi, "FINAL")
    print_tick("10:15", final_tick, final_dec)

    if not simulate:
        log.info("Waiting 10 minutes for share credit (10:25 AM)...")
        time.sleep(600)

    # Phase 3: Execution
    print(f"\n  {'─'*66}")
    print(f"  PHASE 3 — EXECUTION DECISION (10:25 AM)")
    print(f"  {'─'*66}")
    exec_tick = monitor.get_depth_signal()
    exec_dec  = compute_signal(exec_tick, issue_price, gmp_price, lqi, "EXECUTION")

    print_final_card(company_name, issue_price, gmp_price,
                     exec_tick, exec_dec,
                     pre_signal or "—", final_dec.get("signal", "—"))

    save_listing_signal(company_name, symbol, exec_tick, final_dec, exec_dec)
    monitor.stop()


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AACapital IPO Listing Day Engine V3")
    parser.add_argument("--ipo",         type=str,   help="IPO company name (auto-loads from Neon)")
    parser.add_argument("--symbol",      type=str,   help="NSE symbol e.g. BLSE")
    parser.add_argument("--issue-price", type=float, help="Issue price")
    parser.add_argument("--lqi",         type=int,   default=50)
    parser.add_argument("--gmp",         type=float, default=0, help="GMP pct over issue")
    parser.add_argument("--simulate",    action="store_true")
    parser.add_argument("--scenario",    type=str,   default="BULLISH",
                        choices=["BULLISH", "BEARISH", "NEUTRAL"])
    args = parser.parse_args()

    ipo_data = {}
    if args.ipo and DATABASE_URL:
        ipo_data = load_ipo_from_neon(args.ipo) or {}
        if ipo_data:
            log.info(f"Loaded from Neon: {ipo_data['company_name']}")

    company     = ipo_data.get("company_name") or args.ipo     or "Test IPO"
    symbol      = ipo_data.get("symbol")       or args.symbol  or ""
    issue_price = float(ipo_data.get("issue_price") or args.issue_price or 100)
    lqi         = int(float(ipo_data.get("lqi")     or args.lqi          or 50))
    gmp         = float(ipo_data.get("gmp_pct")     or args.gmp          or 0)
    p10         = float(ipo_data.get("p10")          or 0)
    p_loss      = float(ipo_data.get("p_loss")       or 0)
    pre_signal  = ipo_data.get("pre_action")         or "—"

    similar = []
    raw = ipo_data.get("similar_ipos")
    if raw:
        try:
            similar = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            similar = []

    simulate = args.simulate or not KITE_ACCESS_TOKEN

    run(company, symbol, issue_price, lqi, gmp, p10, p_loss,
        similar, pre_signal,
        simulate=simulate, sim_scenario=args.scenario)


if __name__ == "__main__":
    main()
