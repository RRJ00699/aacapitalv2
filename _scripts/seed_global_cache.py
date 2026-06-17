"""
Seed global markets cache in Neon using multiple free sources.
Run locally: python _scripts/seed_global_cache.py
"""
import os, json, time, psycopg2, requests

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://finance.yahoo.com/",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

SYMBOLS = [
    "^GSPC","^NDX","^DJI",
    "DX-Y.NYB","USDINR=X",
    "GC=F","CL=F",
    "BTC-USD",
    "^N225","^HSI",
    "^FTSE","^GDAXI",
]

META = {
    "^GSPC":    {"label":"S&P 500",    "flag":"🇺🇸"},
    "^NDX":     {"label":"Nasdaq 100", "flag":"🇺🇸"},
    "^DJI":     {"label":"Dow Jones",  "flag":"🇺🇸"},
    "DX-Y.NYB": {"label":"DXY",        "flag":"💵"},
    "USDINR=X": {"label":"USD/INR",    "flag":"₹"},
    "GC=F":     {"label":"Gold",       "flag":"🥇"},
    "CL=F":     {"label":"Crude Oil",  "flag":"🛢"},
    "BTC-USD":  {"label":"Bitcoin",    "flag":"₿"},
    "^N225":    {"label":"Nikkei",     "flag":"🇯🇵"},
    "^HSI":     {"label":"Hang Seng",  "flag":"🇭🇰"},
    "^FTSE":    {"label":"FTSE 100",   "flag":"🇬🇧"},
    "^GDAXI":   {"label":"DAX",        "flag":"🇩🇪"},
}

global_data = {}

# Try Yahoo Finance v8 (different endpoint)
for base in ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]:
    try:
        url = f"{base}/v8/finance/spark?symbols={','.join(SYMBOLS)}&range=1d&interval=1d"
        r = requests.get(url, headers=headers, timeout=10)
        print(f"[spark] {base}: {r.status_code}")
        if r.status_code == 200 and r.text:
            data = r.json()
            for sym, info in data.get("spark", {}).get("result", {}).items() if isinstance(data.get("spark",{}).get("result"), dict) else []:
                meta = META.get(sym, {})
                global_data[sym] = {**meta, "symbol": sym, "price": None, "changePct": None}
    except Exception as e:
        print(f"[spark] error: {e}")

# Try Yahoo v7 with cookies
if len(global_data) < 3:
    try:
        session = requests.Session()
        # Get crumb first
        cookie_res = session.get("https://fc.yahoo.com", headers=headers, timeout=5)
        crumb_res = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", headers=headers, timeout=5)
        crumb = crumb_res.text.strip()
        print(f"[crumb] '{crumb}'")

        if crumb and crumb != "":
            syms_str = "%2C".join(SYMBOLS)
            url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms_str}&crumb={crumb}"
            r = session.get(url, headers=headers, timeout=10)
            print(f"[v7+crumb] status: {r.status_code}, len: {len(r.text)}")
            if r.status_code == 200:
                results = r.json().get("quoteResponse", {}).get("result", [])
                print(f"[v7+crumb] got {len(results)} results")
                for q in results:
                    meta = META.get(q["symbol"], {})
                    global_data[q["symbol"]] = {
                        **meta,
                        "symbol": q["symbol"],
                        "price": q.get("regularMarketPrice"),
                        "changePct": round(q.get("regularMarketChangePercent", 0), 2),
                        "change": round(q.get("regularMarketChange", 0), 2),
                    }
    except Exception as e:
        print(f"[crumb] error: {e}")

print(f"\nGot {len(global_data)} symbols: {list(global_data.keys())[:5]}")

if global_data:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO platform_config(key,value,updated_at) VALUES(%s,%s,NOW()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()",
        ["global_cache", json.dumps(global_data)]
    )
    conn.commit()
    conn.close()
    print(f"✅ Saved {len(global_data)} symbols to Neon cache")
    for k, v in list(global_data.items())[:4]:
        print(f"  {k}: {v.get('price')} ({v.get('changePct')}%)")
else:
    print("❌ No data from Yahoo — will use placeholder cache")
    # Save placeholders so UI shows something
    placeholders = {
        sym: {**META.get(sym, {"label": sym, "flag": "🌍"}), "symbol": sym, "price": None, "changePct": None}
        for sym in SYMBOLS
    }
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO platform_config(key,value,updated_at) VALUES(%s,%s,NOW()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()",
        ["global_cache", json.dumps(placeholders)]
    )
    conn.commit()
    conn.close()
    print("Saved placeholder cache — prices will show when Yahoo accessible")
