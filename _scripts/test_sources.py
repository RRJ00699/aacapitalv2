"""Test which financial data sources work"""
import requests, json

headers = {"User-Agent": "Mozilla/5.0"}

sources = [
    ("Stooq S&P",     "https://stooq.com/q/l/?s=^spx&f=sd2t2ohlcv&h&e=csv"),
    ("Stooq Gold",    "https://stooq.com/q/l/?s=gc.f&f=sd2t2ohlcv&h&e=csv"),
    ("Yahoo v7",      "https://query1.finance.yahoo.com/v7/finance/quote?symbols=^GSPC"),
    ("Yahoo v8",      "https://query2.finance.yahoo.com/v8/finance/chart/^GSPC?interval=1d&range=1d"),
    ("Alphavantage",  "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SPY&apikey=demo"),
    ("Marketstack",   "https://api.marketstack.com/v1/tickers/AAPL/eod/latest?access_key=test"),
    ("Coin Gecko BTC","https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"),
]

for name, url in sources:
    try:
        r = requests.get(url, headers=headers, timeout=6)
        print(f"  {name:25} → {r.status_code} ({len(r.text)} chars)")
        if r.status_code == 200 and len(r.text) > 20:
            print(f"    WORKS: {r.text[:80]}")
    except Exception as e:
        print(f"  {name:25} → ERROR: {str(e)[:50]}")
