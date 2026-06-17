"""
_scripts/kite_connect.py

Shared Kite connection helper.
All scripts import this instead of reading KITE_ACCESS_TOKEN from env.
Token is read from Neon platform_config table.

Usage in any script:
    from _scripts.kite_connect import get_kite
    kite = get_kite()
    data = kite.ltp(["NSE:RELIANCE"])
"""

import os
import logging
import psycopg2
from kiteconnect import KiteConnect

log = logging.getLogger(__name__)

API_KEY      = os.environ.get("KITE_API_KEY", "br9m41pn8nvvywnl")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL", "")


def get_token_from_db() -> str:
    """Read active Kite access token from Neon platform_config."""
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not set")

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()
    cur.execute("SELECT value, updated_at FROM platform_config WHERE key = 'kite_access_token'")
    row = cur.fetchone()
    conn.close()

    if not row:
        raise Exception(
            "No kite_access_token in Neon platform_config.\n"
            "Run: python _scripts/refresh_kite_token.py"
        )

    token, updated_at = row
    log.info(f"Token from DB (updated: {str(updated_at)[:16]})")
    return token


def get_token() -> str:
    """
    Get Kite access token.
    Priority: 1) Neon DB  2) KITE_ACCESS_TOKEN env var
    """
    # Try DB first
    try:
        if DATABASE_URL:
            return get_token_from_db()
    except Exception as e:
        log.warning(f"DB token fetch failed: {e}")

    # Fall back to env var
    token = os.environ.get("KITE_ACCESS_TOKEN", "")
    if token:
        log.info("Using KITE_ACCESS_TOKEN from environment")
        return token

    raise Exception(
        "No Kite access token available.\n"
        "Run: python _scripts/refresh_kite_token.py"
    )


def get_kite() -> KiteConnect:
    """Return an authenticated KiteConnect instance."""
    token = get_token()
    kite  = KiteConnect(api_key=API_KEY)
    kite.set_access_token(token)
    return kite
