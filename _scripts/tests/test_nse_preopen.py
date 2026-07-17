#!/usr/bin/env python3
"""Offline tests for nse_preopen_capture — fixtures only, NSE never contacted."""
import importlib.util, json, os, sys, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("cap", os.path.join(HERE, "..", "nse_preopen_capture.py"))
cap = importlib.util.module_from_spec(spec); spec.loader.exec_module(cap)
fx = json.load(open(os.path.join(HERE, "fixture_nse_preopen.json")))

def t(name, ok): print(f"  {'PASS' if ok else 'FAIL'} — {name}"); return ok

results = []
# 1. shape validation
results.append(t("shape: fixture valid", cap.validate_shape(fx) is None))
results.append(t("shape: broken payload rejected", cap.validate_shape({"x": 1}) is not None))
# 2. parser + symbol filter
recs = cap.parse_rows(fx, {"ALPINE"})
r = recs[0]
results.append(t("parser: filters to wanted symbols", len(recs) == 1 and r["symbol"] == "ALPINE"))
results.append(t("parser: IEP/IEQ/totals", r["iep"] == 142.5 and r["ieq"] == 385000
                 and r["buy_qty"] == 981030 and r["sell_qty"] == 822634))
results.append(t("parser: lean % computed", r["lean_pct"] == 19.3))
results.append(t("parser: best bid = highest buy level", r["best_bid"] == 142.5 and r["best_bid_qty"] == 12000))
results.append(t("parser: best ask = lowest sell level", r["best_ask"] == 142.5 and r["best_ask_qty"] == 9000))
results.append(t("parser: cancelled None when unexposed", r["cancelled_qty"] is None))
# 3. dedupe: hash stable on same state, changes on new state
r2 = cap.parse_rows(fx, {"ALPINE"})[0]
results.append(t("dedupe: identical state -> identical hash", r["state_hash"] == r2["state_hash"]))
fx2 = json.loads(json.dumps(fx)); fx2["data"][0]["metadata"]["totalBuyQuantity"] = 999999
r3 = cap.parse_rows(fx2, {"ALPINE"})[0]
results.append(t("dedupe: changed qty -> new hash", r["state_hash"] != r3["state_hash"]))
# 4. window logic (IST boundaries)
mk = lambda h, m, s2: dt.datetime(2026, 7, 20, h, m, s2)
results.append(t("window: 08:59:29 out", not cap.in_window(mk(8, 59, 29))))
results.append(t("window: 09:00:00 in", cap.in_window(mk(9, 0, 0))))
results.append(t("window: 09:58:00 in", cap.in_window(mk(9, 58, 0))))
results.append(t("window: 10:00:31 out", not cap.in_window(mk(10, 0, 31))))
n = sum(results)
print(f"\n{n}/{len(results)} PASS")
assert n == len(results), f'{n}/{len(results)} offline checks passed'


def test_nse_preopen_offline():
    assert True  # checks executed + asserted at import
