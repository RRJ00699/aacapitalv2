"""
_scripts/refresh_kite_token.py

Fully automated Kite token refresh using TOTP.
No Selenium, no browser — pure HTTP + pyotp.
Stores token in Neon platform_config table.
All other scripts read token from DB, not environment.

Run manually: python _scripts/refresh_kite_token.py
GitHub Actions: kite-token-refresh.yml at 8:00 AM IST Mon-Fri
"""

import os
import re
import sys
import time
import logging
import psycopg2
import pyotp
import requests
from kiteconnect import KiteConnect
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

API_KEY      = os.environ.get("KITE_API_KEY",      "br9m41pn8nvvywnl")
API_SECRET   = os.environ.get("KITE_API_SECRET",   "")
USER_ID      = os.environ.get("KITE_USER_ID",      "")
PASSWORD     = os.environ.get("KITE_PASSWORD",     "")
TOTP_SECRET  = os.environ.get("KITE_TOTP_SECRET",  "")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL", "")


def get_request_token() -> str:
    """Complete Kite login flow using TOTP — no browser needed."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    })

    # Step 1: Hit login URL to get cookies
    login_url = f"https://kite.trade/connect/login?v=3&api_key={API_KEY}"
    log.info("Opening login URL...")
    res = session.get(login_url, allow_redirects=True)
    log.info(f"Login page status: {res.status_code}")

    # Step 2: Submit credentials
    log.info(f"Submitting credentials for {USER_ID}...")
    login_res = session.post(
        "https://kite.zerodha.com/api/login",
        data={"user_id": USER_ID, "password": PASSWORD},
        timeout=30,
    ).json()

    if login_res.get("status") != "success":
        raise Exception(f"Login failed: {login_res.get('message', login_res)}")

    request_id = login_res["data"]["request_id"]
    log.info(f"Login OK — request_id: {request_id[:8]}...")

    # Step 3: Generate TOTP and submit 2FA
    totp = pyotp.TOTP(TOTP_SECRET)
    code = totp.now()
    log.info(f"Generated TOTP: {code}")

    twofa_res = session.post(
        "https://kite.zerodha.com/api/twofa",
        data={
            "user_id":     USER_ID,
            "request_id":  request_id,
            "twofa_value": code,
            "twofa_type":  "totp",
        },
        timeout=30,
    ).json()

    if twofa_res.get("status") != "success":
        raise Exception(f"2FA failed: {twofa_res.get('message', twofa_res)}")

    log.info("2FA OK")

    # Step 4: Follow the OAuth redirect to capture request_token
    time.sleep(1)
    final_url = ""
    try:
        # Disable redirect following so we can catch the redirect URL
        final_res = session.get(login_url, allow_redirects=False, timeout=15)
        final_url = final_res.headers.get("Location", final_res.url)
        log.info(f"Redirect location: {str(final_url)[:80]}...")
    except Exception as redirect_err:
        # Connection refused to 127.0.0.1 is EXPECTED — extract token from error URL
        err_str = str(redirect_err)
        log.info(f"Expected redirect caught: {err_str[:120]}")
        m = re.search(r"request_token=([a-zA-Z0-9]+)", err_str)
        if m:
            log.info("request_token extracted from error URL")
            return m.group(1)

    # Try to extract from redirect URL
    m = re.search(r"request_token=([a-zA-Z0-9]+)", str(final_url))
    if m:
        return m.group(1)

    # Last resort: try following with allow_redirects and catch connection error
    try:
        session.get(login_url, allow_redirects=True, timeout=5)
    except Exception as e:
        err_str = str(e)
        m = re.search(r"request_token=([a-zA-Z0-9]+)", err_str)
        if m:
            return m.group(1)

    raise Exception(f"request_token not found. Final URL: {final_url}")


def exchange_token(request_token: str) -> str:
    """Exchange request_token for access_token via Kite SDK."""
    kite = KiteConnect(api_key=API_KEY)
    data = kite.generate_session(request_token, api_secret=API_SECRET)
    return data["access_token"]


def save_to_db(access_token: str):
    """Save token to Neon platform_config table."""
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    # Ensure table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS platform_config (
            key        VARCHAR(255) PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Upsert token
    cur.execute("""
        INSERT INTO platform_config (key, value, updated_at)
        VALUES ('kite_access_token', %s, NOW())
        ON CONFLICT (key)
        DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, [access_token])

    # Also record last refresh time
    cur.execute("""
        INSERT INTO platform_config (key, value, updated_at)
        VALUES ('kite_token_refreshed_at', %s, NOW())
        ON CONFLICT (key)
        DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, [datetime.now().isoformat()])

    conn.commit()
    conn.close()
    log.info("Token saved to Neon platform_config")


def get_token_from_db() -> str:
    """Read current token from Neon. Used by all other scripts."""
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()
    cur.execute("SELECT value FROM platform_config WHERE key = 'kite_access_token'")
    row = cur.fetchone()
    conn.close()
    if not row:
        raise Exception("No kite_access_token in platform_config. Run refresh_kite_token.py first.")
    return row[0]


def verify_token(access_token: str) -> bool:
    """Verify the token works by calling Kite profile API."""
    try:
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        profile = kite.profile()
        log.info(f"Token verified — logged in as: {profile['user_name']} ({profile['user_id']})")
        return True
    except Exception as e:
        log.error(f"Token verification failed: {e}")
        return False


def main():
    log.info("=" * 50)
    log.info("AACapital — Kite Token Refresh")
    log.info("=" * 50)

    if not all([API_KEY, API_SECRET, USER_ID, PASSWORD, TOTP_SECRET, DATABASE_URL]):
        missing = [k for k, v in {
            "KITE_API_KEY": API_KEY, "KITE_API_SECRET": API_SECRET,
            "KITE_USER_ID": USER_ID, "KITE_PASSWORD": PASSWORD,
            "KITE_TOTP_SECRET": TOTP_SECRET, "DATABASE_URL": DATABASE_URL,
        }.items() if not v]
        log.error(f"Missing env vars: {missing}")
        sys.exit(1)

    try:
        request_token = get_request_token()
        log.info(f"request_token: {request_token[:8]}...")

        access_token = exchange_token(request_token)
        log.info(f"access_token:  {access_token[:8]}...")

        save_to_db(access_token)

        if verify_token(