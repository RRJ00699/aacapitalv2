"""
AACapital — Kite Access Token Generator
Run this ONCE each morning before market opens to get today's access token.

Usage:
  python _scripts/kite_login.py

Then copy the access token shown and set:
  $env:KITE_ACCESS_TOKEN = "your_token_here"

Or add to .env.local:
  KITE_ACCESS_TOKEN=your_token_here
"""

import os
import webbrowser
from kiteconnect import KiteConnect

API_KEY    = os.environ.get("KITE_API_KEY",    "br9m41pn8nvvywnl")
API_SECRET = os.environ.get("KITE_API_SECRET", "")

def main():
    kite = KiteConnect(api_key=API_KEY)
    login_url = kite.login_url()

    print("\n" + "="*60)
    print("  AACapital — Kite Login")
    print("="*60)
    print(f"\n1. Opening Kite login in browser...")
    print(f"   URL: {login_url}\n")
    webbrowser.open(login_url)

    print("2. After login, you'll be redirected to your redirect URL.")
    print("   Copy the 'request_token' from the URL.")
    print("   It looks like: ?request_token=XXXXXXXXXX&action=login\n")

    request_token = input("3. Paste request_token here: ").strip()

    if not API_SECRET:
        print("\nERROR: KITE_API_SECRET not set.")
        print("Set it with: $env:KITE_API_SECRET = 'your_secret'")
        print("Find it at: https://developers.kite.trade/apps")
        return

    try:
        data = kite.generate_session(request_token, api_secret=API_SECRET)
        access_token = data["access_token"]

        print(f"\n✓ Access token generated!")
        print(f"\n  Access Token: {access_token}")
        print(f"\n4. Set it in PowerShell:")
        print(f'   $env:KITE_ACCESS_TOKEN = "{access_token}"')
        print(f"\n   Or add to .env.local:")
        print(f'   KITE_ACCESS_TOKEN={access_token}')

        # Auto-save to a temp file
        with open("_scripts/.kite_token", "w") as f:
            f.write(access_token)
        print(f"\n   Also saved to _scripts/.kite_token")
        print("\n" + "="*60)
    except Exception as e:
        print(f"\nError generating session: {e}")
        print("Make sure your API secret is correct.")

if __name__ == "__main__":
    main()
