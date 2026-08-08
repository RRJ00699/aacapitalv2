"""
_scripts/seed_global_cache.py
Uses Yahoo Finance v8 (works) + CoinGecko for BTC/ETH
Saves to Neon platform_config.global_cache for Vercel fallback
"""
import os, json, time, psycopg2, requests

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

META = {
    "^GSPC":    {"label": "S&P 500",    "flag": "🇺🇸", "region": "us"},
    "^NDX":     {"label": "Nasdaq 100", "flag": "🇺🇸", "region": "us"},
    "^DJI":     {"label": "Dow Jones",  "flag": "🇺🇸", "region": "us"},
    "DX-Y.NYB": {"label": "DXY",        "flag": "💵", "region": "fx"},
    "USDINR=X": {"label": "USD/INR",    "flag": "₹",  "region": "fx"},
    "GC=F":     {"label": "Gold",       "flag": "🥇", "region": "commodity"},
    "CL=F":     {"label": "Crude Oil",  "flag": "🛢", "region": "commodity"},
    "^N225":    {"label": "Nikkei",     "flag": "🇯🇵", "region": "asia"},
    "^HSI":     {"label": "Hang Seng",  "flag": "🇭🇰", "region": "asia"},
    "^FTSE":    {"label": "FTSE 100",   "flag": "🇬🇧", "region": "europe"},
    "^GDAXI":   {"label": "DAX",        "flag": "🇩🇪", "region": "europe"},
    "BTC-USD":  {"label": "Bitcoin",    "flag": "₿",  "region": "crypto"},
}

global_data = {}

# ── Yahoo v8 for each symbol ──────────────────────────────────────────────────
YF_SYMS = ["^GSPC","^NDX","^DJI","DX-Y.NYB","USDINR=X","GC=F","CL=F","^N225","^HSI","^FTSE","^GDAXI"]

print("Fetching from Yahoo Finance v8...")
for sym in YF_SYMS:
    try:
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d"
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            print(f"  {sym}: {r.status_code}")
            continue
        d = r.json()
        meta_yf = d["chart"]["result"][0]["meta"]
        price    = meta_yf.get("regularMarketPrice")
        prev     = meta_yf.get("previousClose") or meta_yf.get("chartPreviousClose")
        if not price:
            continue
        chg_pct  = round((price - prev) / prev * 100, 2) if prev else 0
        chg      = round(price - prev, 2) if prev else 0
        m        = META.get(sym, {"label": sym, "flag": "🌍", "region": "global"})
        global_data[sym] = {**m, "symbol": sym, "price": price, "changePct": chg_pct, "change": chg}
        print(f"  {m['label']:15} {price:>12.2f}  {chg_pct:+.2f}%")
        time.sleep(0.2)
    except Exception as e:
        print(f"  {sym}: error — {e}")

# ── CoinGecko for BTC ─────────────────────────────────────────────────────────
print("\nFetching BTC from CoinGecko...")
try:
    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true",
        headers=headers, timeout=8
    )
    btc = r.json().get("bitcoin", {})
    price   = btc.get("usd")
    chg_pct = round(btc.get("usd_24h_change", 0), 2)
    if price:
        global_data["BTC-USD"] = {
            "label": "Bitcoin", "flag": "₿", "region": "crypto",
            "symbol": "BTC-USD", "price": price,
            "changePct": chg_pct, "change": round(price * chg_pct / 100, 2),
        }
        print(f"  Bitcoin         {price:>12,.0f}  {chg_pct:+.2f}%")
except Exception as e:
    print(f"  BTC error: {e}")

# ── Save to Neon ──────────────────────────────────────────────────────────────
print(f"\nTotal: {len(global_data)} symbols")

if global_data:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO platform_config(key,value,updated_at) VALUES(%s,%s,NOW()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()",
        ["global_cache", json.dumps(global_data)]
    )
    conn.commit()
    conn.close()
    print(f"✅ Saved {len(global_data)} symbols to Neon global_cache")
else:
    print("❌ No data retrieved")
