"""
_scripts/debug-screener.py
Debugs what Screener.in returns for different URL patterns.
Run this first to find the correct download URL before running download-candles.py
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")

USERNAME = os.getenv("SCREENER_USERNAME")
PASSWORD = os.getenv("SCREENER_PASSWORD")
BASE_URL = "https://www.screener.in"
SYMBOL = "WABAG"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
})

# ── Login ─────────────────────────────────────────────────────────────────────
print("1. Getting CSRF token...")
r = session.get(f"{BASE_URL}/login/", timeout=15)
print(f"   Status: {r.status_code}")
csrf = session.cookies.get("csrftoken", "")
print(f"   CSRF: {csrf[:20]}..." if csrf else "   CSRF: MISSING")

print("\n2. Logging in...")
r = session.post(f"{BASE_URL}/login/", data={
    "username": USERNAME,
    "password": PASSWORD,
    "csrfmiddlewaretoken": csrf,
}, headers={"Referer": f"{BASE_URL}/login/"}, timeout=15)
print(f"   Status: {r.status_code}")
print(f"   Final URL: {r.url}")
print(f"   Cookies: {dict(session.cookies)}")
logged_in = "logout" in r.text.lower() or "dashboard" in r.url.lower() or r.url == f"{BASE_URL}/"
print(f"   Logged in: {logged_in}")

# ── Try different URL patterns ─────────────────────────────────────────────────
print(f"\n3. Testing download URLs for {SYMBOL}...")

urls = [
    f"{BASE_URL}/company/{SYMBOL}/consolidated/?format=csv",
    f"{BASE_URL}/company/{SYMBOL}/?format=csv",
    f"{BASE_URL}/api/company/{SYMBOL}/prices/?days_before=3650&format=csv",
    f"{BASE_URL}/company/{SYMBOL}/consolidated/",
    f"{BASE_URL}/company/{SYMBOL}/",
]

for url in urls:
    r = session.get(url, timeout=15)
    content_type = r.headers.get("Content-Type", "")
    first_100 = r.text[:100].replace("\n", "\\n")
    print(f"\n   URL: {url}")
    print(f"   Status: {r.status_code}  Content-Type: {content_type}")
    print(f"   First 100 chars: {first_100}")
    
    # Check if it's CSV
    if "text/csv" in content_type or (r.status_code == 200 and "Date" in r.text[:200] and "<html" not in r.text[:50].lower()):
        print("   ✅ THIS IS CSV DATA!")
