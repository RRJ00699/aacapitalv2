from yahooquery import search
import time

funds = [
    "HDFC Mid Cap Opportunities Direct Growth",
    "SBI Bluechip Fund Direct Growth",
    "Mirae Asset Large Cap Fund Direct",
    "Axis Small Cap Fund Direct Growth",
    "Nippon India Small Cap Fund Direct",
    "Kotak Flexi Cap Fund Direct",
    "ICICI Prudential Bluechip Fund Direct",
    "DSP Small Cap Fund Direct Growth",
    "360 ONE Focused Equity Fund Direct",
]

for f in funds:
    try:
        r = search(f)
        mf = [q for q in r.get("quotes", []) if q.get("quoteType") == "MUTUALFUND"]
        if mf:
            print(f"{mf[0]['symbol']} | {mf[0].get('shortname','?')} | {f}")
        else:
            print(f"NOT FOUND | {f}")
    except Exception as e:
        print(f"ERROR: {e} | {f}")
    time.sleep(1)
