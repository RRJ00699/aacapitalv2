"""
_scripts/kite-auth.py
Generates Zerodha Kite access token (must be run once each trading day).

Usage:
    python _scripts/kite-auth.py

Steps:
1. Opens Kite login URL in browser
2. You log in and get redirected to a URL with ?request_token=XXX
3. Paste that full URL here
4. Script exchanges it for access_token and writes to .env.local

Requirements:
    pip install kiteconnect python-dotenv
"""

import os
import re
import webbrowser
from dotenv import load_dotenv, set_key

load_dotenv(".env.local")

API_KEY    = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")

if not API_KEY or not API_SECRET:
    print("❌ Set KITE_API_KEY and KITE_API_SECRET in .env.local first")
    exit(1)

try:
    from kiteconnect import KiteConnect
except ImportError:
    print("❌ Run: pip install kiteconnect")
    exit(1)

kite = KiteConnect(api_key=API_KEY)
login_url = kite.login_url()

print("═══════════════════════════════════════════")
print("  Kite Auth — Daily Token Generator")
print("═══════════════════════════════════════════")
print(f"\n1. Opening login URL in browser...")
print(f"   {login_url}\n")
webbrowser.open(login_url)

print("2. Log in with your Zerodha credentials + 2FA")
print("3. After login you'll be redirected to your app's redirect URL")
print("   It looks like: https://yourapp.com/?request_token=XXXXXXXX&action=login&status=success")
print("\nPaste the full redirect URL here:")
redirect_url = input("> ").strip()

# Extract request_token
match = re.search(r"request_token=([^&]+)", redirect_url)
if not match:
    print("❌ Could not find request_token in URL")
    exit(1)

request_token = match.group(1)
print(f"\nExchanging request_token: {request_token[:10]}...")

try:
    session = kite.generate_session(request_token, api_secret=API_SECRET)
    access_token = session["access_token"]

    # Write to .env.local
    set_key(".env.local", "KITE_ACCESS_TOKEN", access_token)

    print(f"\n✅ Access token saved to .env.local")
    print(f"   Token: {access_token[:10]}...{access_token[-4:]}")
    print(f"\nNow run:")
    print(f"   python _scripts/kite-sync-candles.py --days 1")
except Exception as e:
    print(f"❌ Token exchange failed: {e}")
    exit(1)
