"""
_scripts/kite-auth-auto.py
Automated Kite token refresh with TOTP support.

Two modes:
  Manual (default): Opens browser, you complete login, paste redirect URL
  Auto (--auto):    Uses stored TOTP secret to complete 2FA without human input

Setup for --auto mode:
  1. Get your TOTP secret from Zerodha:
     - Login to zerodha.com → My Profile → Security → 2FA
     - Click "Can't scan? Enter manually" to get the secret key
  2. Add to .env.local:
     KITE_TOTP_SECRET=YOUR_32_CHARACTER_SECRET

Usage:
  python _scripts/kite-auth-auto.py           # manual mode
  python _scripts/kite-auth-auto.py --auto    # fully automated

For GitHub Actions (daily token refresh):
  - Store KITE_TOTP_SECRET, KITE_USER_ID, KITE_PASSWORD as GitHub Secrets
  - The kite-token-refresh.yml workflow runs this at 8 AM IST daily
  - Writes fresh KITE_ACCESS_TOKEN back to GitHub Secrets via API

Requirements:
  pip install kiteconnect python-dotenv pyotp selenium webdriver-manager
"""

import os
import sys
import re
import time
import argparse
import webbrowser
from dotenv import load_dotenv, set_key

load_dotenv(".env.local")
load_dotenv(".env")

API_KEY    = os.getenv("KITE_API_KEY")
API_SECRET = os.getenv("KITE_API_SECRET")
USER_ID    = os.getenv("KITE_USER_ID")       # your Zerodha client ID e.g. AB1234
PASSWORD   = os.getenv("KITE_PASSWORD")       # your Zerodha password
TOTP_SECRET= os.getenv("KITE_TOTP_SECRET")   # 32-char TOTP secret from Zerodha

parser = argparse.ArgumentParser()
parser.add_argument("--auto", action="store_true", help="Fully automated login using TOTP secret")
args = parser.parse_args()

if not API_KEY or not API_SECRET:
    print("❌ KITE_API_KEY and KITE_API_SECRET must be set in .env.local")
    sys.exit(1)

try:
    from kiteconnect import KiteConnect
except ImportError:
    print("❌ Run: pip install kiteconnect")
    sys.exit(1)

kite = KiteConnect(api_key=API_KEY)

def save_token(access_token: str):
    """Save token to .env.local"""
    set_key(".env.local", "KITE_ACCESS_TOKEN", access_token)
    print(f"✅ Access token saved to .env.local")
    print(f"   Token: {access_token[:8]}...{access_token[-4:]}")

def manual_auth():
    """Original manual flow — open browser, paste URL"""
    login_url = kite.login_url()
    print("═══════════════════════════════════════════")
    print("  Kite Auth — Manual Mode")
    print("═══════════════════════════════════════════")
    print(f"\n1. Opening login URL...")
    print(f"   {login_url}\n")
    webbrowser.open(login_url)
    print("2. Log in → complete 2FA → you'll be redirected")
    print("   URL will look like: http://127.0.0.1/?request_token=XXXX...")
    print("\nPaste the full redirect URL here:")
    redirect_url = input("> ").strip()
    m = re.search(r"request_token=([^&]+)", redirect_url)
    if not m:
        print("❌ No request_token found in URL")
        sys.exit(1)
    return m.group(1)

def auto_auth():
    """Fully automated flow using Selenium + TOTP"""
    if not all([USER_ID, PASSWORD, TOTP_SECRET]):
        print("❌ For --auto mode, set these in .env.local:")
        print("   KITE_USER_ID=AB1234")
        print("   KITE_PASSWORD=yourpassword")
        print("   KITE_TOTP_SECRET=your32chartotp secret")
        sys.exit(1)

    try:
        import pyotp
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        print("❌ Run: pip install pyotp selenium webdriver-manager")
        sys.exit(1)

    print("═══════════════════════════════════════════")
    print("  Kite Auth — Automated Mode")
    print("═══════════════════════════════════════════\n")

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    wait = WebDriverWait(driver, 15)

    try:
        login_url = kite.login_url()
        print(f"  Opening: {login_url}")
        driver.get(login_url)

        # Enter user ID
        wait.until(EC.presence_of_element_located((By.ID, "userid"))).send_keys(USER_ID)
        driver.find_element(By.ID, "password").send_keys(PASSWORD)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        print("  ✓ Credentials submitted")

        # Wait for TOTP screen
        time.sleep(2)

        # Generate TOTP
        totp   = pyotp.TOTP(TOTP_SECRET)
        code   = totp.now()
        print(f"  ✓ TOTP generated: {code}")

        # Try multiple selectors — Zerodha changes field IDs periodically
        totp_input = None
        for selector in [
            (By.ID, "totp"),
            (By.NAME, "totp"),
            (By.XPATH, "//input[@type='number']"),
            (By.XPATH, "//input[@placeholder='6-digit code']"),
            (By.XPATH, "//input[contains(@class,'totp')]"),
            (By.CSS_SELECTOR, "input[type='number']"),
        ]:
            try:
                totp_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located(selector)
                )
                if totp_input:
                    break
            except:
                continue

        if not totp_input:
            # Take screenshot for debugging
            driver.save_screenshot("/tmp/kite_totp_debug.png")
            print(f"  Page source snippet: {driver.page_source[:500]}")
            raise Exception("TOTP input field not found — Zerodha may have changed UI")

        totp_input.clear()
        totp_input.send_keys(code)
        time.sleep(0.5)
        # Try submit button variations
        for submit_xpath in ["//button[@type='submit']", "//button[contains(text(),'Continue')]", "//input[@type='submit']"]:
            try:
                driver.find_element(By.XPATH, submit_xpath).click()
                break
            except:
                continue

        # Wait for redirect to 127.0.0.1
        time.sleep(3)
        current_url = driver.current_url
        print(f"  Redirected to: {current_url[:80]}...")

        m = re.search(r"request_token=([^&]+)", current_url)
        if not m:
            print(f"❌ No request_token in redirect URL: {current_url}")
            sys.exit(1)

        print("  ✓ request_token captured")
        return m.group(1)

    finally:
        driver.quit()

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    request_token = auto_auth() if args.auto else manual_auth()
    print(f"\nExchanging request_token...")

    try:
        session      = kite.generate_session(request_token, api_secret=API_SECRET)
        access_token = session["access_token"]
        save_token(access_token)

        print(f"\nNow run:")
        print(f"  python _scripts/kite-sync-candles.py --days 1")
    except Exception as e:
        print(f"❌ Token exchange failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
