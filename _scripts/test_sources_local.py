"""
Run this on your Windows machine to test which sources work:
python _scripts/test_sources_local.py
"""
import requests

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

sources = [
    ("BSE corporate filings", "https://www.bseindia.com/corporates/ann.aspx"),
    ("BSE API announcements", "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate=20260101&strScrip=500209&strSearch=P&strToDate=20260618&strType=C"),
    ("NSE concall",           "https://www.nseindia.com/api/corporates-concall?index=equities&symbol=INFY"),
    ("Screener INFY",         "https://www.screener.in/company/INFY/consolidated/"),
    ("Trendlyne INFY",        "https://trendlyne.com/fundamentals/quarterly-results/INFY/infosys-ltd/"),
    ("Economic Times",        "https://economictimes.indiatimes.com/infosys-ltd/earningscallanalysis/companyid-10960.cms"),
    ("Yahoo v8 INFY",         "https://query2.finance.yahoo.com/v8/finance/chart/INFY.NS?interval=3mo&range=1y"),
    ("Alpha Vantage",         "https://www.alphavantage.co/query?function=EARNINGS&symbol=INFY&apikey=demo"),
    ("Tijori INFY",           "https://tijorifinance.com/company/INFY"),
    ("Finology INFY",         "https://ticker.finology.in/company/INFY"),
]

for name, url in sources:
    try:
        r = requests.get(url, headers=headers, timeout=8)
        status = "✓ WORKS" if r.status_code == 200 and len(r.text) > 200 else f"✗ {r.status_code}"
        print(f"{status:12} {name}")
    except Exception as e:
        print(f"{'✗ ERROR':12} {name}: {str(e)[:50]}")
