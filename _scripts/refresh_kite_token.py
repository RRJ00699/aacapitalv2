"""
_scripts/refresh_kite_token.py

Fully automated Kite token refresh using TOTP.
No Selenium, no browser — pure HTTP + pyotp.
Rotates token into the dedicated Cloudflare Kite broker Worker Secret.
The public Next.js Worker never receives or reads the Kite access token.

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
from dotenv import load_dotenv

# TEST MODE MUST NOT INHERIT AMBIENT CONFIGURATION.
#
# load_dotenv() injects the developer's .env into os.environ at IMPORT time — that is,
# after a test fixture has already cleared those names. The control tests load this
# module to exercise main(), so on any machine with a populated .env the fixture's
# isolation was undone the moment the module executed: EXECUTE_CLOUDFLARE_SECRET_ROTATION,
# ALLOW_LEGACY_KITE_DB_TOKEN_WRITE, KITE_REFRESH_VALIDATE_ONLY and the broker URL/secret
# all came back. That is why the suite fails on the owner's PC and passes in CI, and it
# is not merely a wrong verdict: with the rotation flags ambient, running the tests
# attempted a real `wrangler secret put` and a real broker verification against
# production.
#
# Under KITE_REFRESH_TEST_MODE the process believes exactly what the test told it and
# nothing else. Production is unaffected: the flag is set only by tests and CI.
if os.environ.get("KITE_REFRESH_TEST_MODE") != "1":
    load_dotenv(".env.local")
    load_dotenv(".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()

API_KEY      = os.environ.get("KITE_API_KEY", "")  # env or platform_config only — no hardcoded fallback (audit 2026-07-17)
API_SECRET   = os.environ.get("KITE_API_SECRET",   "")
USER_ID      = os.environ.get("KITE_USER_ID",      "")
PASSWORD     = os.environ.get("KITE_PASSWORD",      "")
TOTP_SECRET  = os.environ.get("KITE_TOTP_SECRET",  "")
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL", "")


def _require_key():
    if not API_KEY:
        sys.exit("KITE_API_KEY missing — set it in .env or Settings (platform_config kite_api_key).")
def _db_overrides():
    """platform_config beats .env when set — lets Rakesh rotate Zerodha creds
    from Settings on his phone (Build plan #4) without SSH. Keys:
    kite_api_key / kite_api_secret / kite_user_id / kite_password /
    kite_totp_secret. Failure here falls back silently to env values."""
    global API_KEY, API_SECRET, USER_ID, PASSWORD, TOTP_SECRET
    try:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("""SELECT key, value FROM platform_config
                       WHERE key IN ('kite_api_key','kite_api_secret',
                                     'kite_user_id','kite_password',
                                     'kite_totp_secret','zerodha_totp_secret')
                         AND COALESCE(value,'') <> ''""")
        m = dict(cur.fetchall()); conn.close()
        API_KEY     = m.get("kite_api_key", API_KEY)
        API_SECRET  = m.get("kite_api_secret", API_SECRET)
        USER_ID     = m.get("kite_user_id", USER_ID)
        PASSWORD    = m.get("kite_password", PASSWORD)
        TOTP_SECRET = m.get("zerodha_totp_secret") or m.get("kite_totp_secret") or TOTP_SECRET
    except Exception:
        pass

def get_request_token() -> str:
    """Complete Kite login flow using TOTP — no browser needed."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    })

    # Step 1: Hit login URL to get cookies
    login_url = f"https://kite.trade/connect/login?v=3&api_key={API_KEY}"
    log.info(f"Opening login URL...")
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
    log.info("Login credentials accepted")

    # Step 3: Generate TOTP and submit 2FA
    totp = pyotp.TOTP(TOTP_SECRET)
    code = totp.now()
    log.info("Generated TOTP")

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

    # Step 4: Follow OAuth redirect — try multiple strategies to get request_token
    time.sleep(1)

    # Strategy 1: allow_redirects=False — check Location header
    try:
        final_res = session.get(login_url, allow_redirects=False, timeout=15)
        location = final_res.headers.get("Location", "")
        m = re.search(r"request_token=([a-zA-Z0-9]+)", location)
        if m:
            return m.group(1)
    except Exception as e:
        m = re.search(r"request_token=([a-zA-Z0-9]+)", str(e))
        if m:
            return m.group(1)

    # Strategy 2: allow_redirects=True — catch connection refused to 127.0.0.1
    try:
        final_res = session.get(login_url, allow_redirects=True, timeout=5)
        m = re.search(r"request_token=([a-zA-Z0-9]+)", final_res.url)
        if m:
            return m.group(1)
    except Exception as e:
        err_str = str(e)
        m = re.search(r"request_token=([a-zA-Z0-9]+)", err_str)
        if m:
            return m.group(1)

    # Strategy 3: check all response history
    try:
        s2 = requests.Session()
        s2.headers.update(session.headers)
        s2.cookies.update(session.cookies)
        resp = s2.get(login_url, allow_redirects=True, timeout=10)
        for r in resp.history:
            m = re.search(r"request_token=([a-zA-Z0-9]+)", r.url)
            if m:
                return m.group(1)
        m = re.search(r"request_token=([a-zA-Z0-9]+)", resp.url)
        if m:
            return m.group(1)
    except Exception as e:
        m = re.search(r"request_token=([a-zA-Z0-9]+)", str(e))
        if m:
            return m.group(1)

    raise Exception(f"request_token not found. Final URL: {final_url}")


def exchange_token(request_token: str) -> str:
    """Exchange request_token for access_token via Kite SDK."""
    kite = KiteConnect(api_key=API_KEY)
    data = kite.generate_session(request_token, api_secret=API_SECRET)
    return data["access_token"]


def legacy_save_to_db(api_key: str, access_token: str) -> bool:
    """Atomically hand off one complete credential pair for owner-PC candle jobs.

    TODO/ADR Stage 2: delete this function and its call immediately after all
    three owner proofs are complete: broker Worker Secret rotation succeeds,
    broker verification succeeds, and rollback drill succeeds.
    """
    if not (os.environ.get("ALLOW_LEGACY_KITE_DB_TOKEN_WRITE") == "1"
            and os.environ.get("KITE_REFRESH_VALIDATE_ONLY") == "1"):
        log.info("legacy platform_config token write skipped")
        return False
    log.warning("LEGACY development-only platform_config token write enabled")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        cur = conn.cursor()

        # Ensure table exists
        cur.execute("""
        CREATE TABLE IF NOT EXISTS platform_config (
            key        VARCHAR(255) PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

        # API key and access token are committed in the same transaction. Downstream
        # resolution therefore reads a pair from one source, never a mixed pair.
        cur.execute("""
        INSERT INTO platform_config (key, value, updated_at)
        VALUES ('kite_api_key', %s, NOW())
        ON CONFLICT (key)
        DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
    """, [api_key])
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

    # ── BRIDGE: the Cloudflare worker (lib/brokers/zerodha.ts getToken) reads
    # kite_session, NOT platform_config. Missing this bridge left the worker
    # bookless on the 2026-07-16 listing morning (last web login was June 13).
    # Upsert the same fresh token there so both stores refresh together.
        cur.execute("""
        UPDATE kite_session
           SET access_token = %s, created_at = NOW(),
               expires_at = NOW() + interval '20 hours'
         WHERE user_id = 'owner'
    """, (access_token,))
        if cur.rowcount == 0:
            cur.execute("""
            INSERT INTO kite_session (access_token, user_id, created_at, expires_at)
            VALUES (%s, 'owner', NOW(), NOW() + interval '20 hours')
        """, (access_token,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    log.info("Complete Kite credential pair handed off to database")
    return True


def rotate_worker_secret(access_token: str) -> None:
    """Update the dedicated broker Worker Secret without printing the token.

    This uses wrangler only when explicitly enabled by the operator. CI and dry-runs
    must not mutate Cloudflare.
    """
    test_result = os.environ.get("KITE_REFRESH_TEST_ROTATION")
    if test_result:
        if test_result != "success":
            raise RuntimeError("mock rotation failure")
        return
    import subprocess
    worker = os.environ.get("KITE_BROKER_WORKER_NAME", "aacapital-kite-broker-proxy")
    cmd = ["npx", "wrangler", "secret", "put", "KITE_ACCESS_TOKEN", "--name", worker]
    subprocess.run(cmd, input=access_token, text=True, check=True)


def verify_broker() -> bool:
    """Verify broker /health and one bounded /quotes call; never includes token."""
    test_result = os.environ.get("KITE_REFRESH_TEST_VERIFICATION")
    if test_result:
        return test_result == "success"
    url = os.environ.get("KITE_BROKER_PROXY_URL", "").rstrip("/")
    secret = os.environ.get("KITE_BROKER_PROXY_AUTH_SECRET", "")
    symbol = os.environ.get("KITE_ROTATION_VERIFY_SYMBOL", "NIFTYBEES").strip().upper()
    if not url or not secret:
        log.error("Broker verification missing URL/auth secret")
        return False
    headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
    try:
        h = requests.get(f"{url}/health", headers=headers, timeout=8)
        if h.status_code != 200:
            return False
        q = requests.post(f"{url}/quotes", headers=headers, json={"symbols": [symbol], "allowed_symbols": [symbol]}, timeout=8)
        return q.status_code == 200 and bool(q.json().get("ok"))
    except Exception as e:
        log.error(f"Broker verification failed: {type(e).__name__}")
        return False


def last_snapshot_timestamp() -> str:
    try:
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("SELECT updated_at::text FROM platform_config WHERE key = 'ipo-live-preopen:v2'")
        row = cur.fetchone(); conn.close()
        return row[0] if row else "unknown"
    except Exception:
        return "unknown"


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
    test_result = os.environ.get("KITE_REFRESH_TEST_VERIFICATION")
    if test_result:
        return test_result == "success"
    try:
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        profile = kite.profile()
        log.info(f"Token verified — logged in as: {profile['user_name']} ({profile['user_id']})")
        return True
    except Exception as e:
        log.error("Token verification failed: %s", type(e).__name__)
        return False


def _alert(msg: str):
    """Phase-3: token failure is the single worst silent failure (listing-day
    ticker + candles all die). URGENT push; never raises."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from lib.notify import notify
        notify("Kite token refresh FAILED", msg, priority="urgent", tags=["rotating_light"])
    except Exception:
        pass


STATUSES = {
    "SUCCESS_ROTATED", "SUCCESS_VALIDATED_ONLY", "SUCCESS_VALIDATED_HANDED_OFF",
    "SKIPPED_NOT_ACTIVATED", "FAILED_LOGIN", "FAILED_ROTATION", "FAILED_VERIFICATION",
}


def _finish(status: str) -> int:
    """Emit the sole machine-readable result without ever including token material."""
    if status not in STATUSES:
        raise ValueError(f"unknown Kite refresh status: {status}")
    print(f"KITE_REFRESH_STATUS={status}")
    return 0 if not status.startswith("FAILED_") else 1


def _obtain_access_token() -> str:
    """Authenticate, with an explicit offline mode used only by tests/CI."""
    if os.environ.get("KITE_REFRESH_TEST_MODE") == "1":
        log.info("Kite authentication completed (test mode)")
        return "test-only-sensitive-access-token"
    request_token = get_request_token()
    access_token = exchange_token(request_token)
    log.info("Kite authentication completed")
    return access_token


def main():
    log.info("=" * 50)
    log.info("AACapital — Kite Token Refresh")
    log.info("=" * 50)

    test_mode = os.environ.get("KITE_REFRESH_TEST_MODE") == "1"
    if not test_mode:
        _db_overrides()

    if not test_mode and not all([API_KEY, API_SECRET, USER_ID, PASSWORD, TOTP_SECRET, DATABASE_URL]):
        missing = [k for k, v in {
            "KITE_API_KEY": API_KEY, "KITE_API_SECRET": API_SECRET,
            "KITE_USER_ID": USER_ID, "KITE_PASSWORD": PASSWORD,
            "KITE_TOTP_SECRET": TOTP_SECRET, "DATABASE_URL": DATABASE_URL,
        }.items() if not v]
        log.error(f"Missing env vars: {missing}")
        _alert(f"Missing credentials: {', '.join(missing)}. Fix env / Settings then re-run.")
        return _finish("FAILED_LOGIN")

    try:
        access_token = _obtain_access_token()
    except Exception as exc:
        log.error("Kite login/token exchange failed: %s", type(exc).__name__)
        _alert("Kite login/token exchange failed. Listing-day ticker and candle sync will skip until fixed.")
        return _finish("FAILED_LOGIN")

    if os.environ.get("EXECUTE_CLOUDFLARE_SECRET_ROTATION") != "1":
        if os.environ.get("KITE_REFRESH_VALIDATE_ONLY") == "1":
            if verify_token(access_token):
                if os.environ.get("ALLOW_LEGACY_KITE_DB_TOKEN_WRITE") == "1":
                    try:
                        legacy_save_to_db(API_KEY, access_token)
                    except Exception as exc:
                        log.error("Kite credential handoff failed: %s", type(exc).__name__)
                        _alert("Validated Kite credential pair could not be handed off.")
                        return _finish("FAILED_ROTATION")
                    return _finish("SUCCESS_VALIDATED_HANDED_OFF")
                log.info("Kite token validated in-process; downstream handoff disabled")
                return _finish("SUCCESS_VALIDATED_ONLY")
            log.error("Kite token validation failed; live overlay remains disabled")
            _alert("Kite token validation failed. Live overlay remains disabled.")
            return _finish("FAILED_VERIFICATION")
        log.info("Broker secret rotation skipped because Stage 2 is not activated")
        return _finish("SKIPPED_NOT_ACTIVATED")

    if not os.environ.get("KITE_BROKER_PROXY_URL", "").strip() or not os.environ.get("KITE_BROKER_PROXY_AUTH_SECRET", "").strip():
        log.error("Activated broker rotation requires URL and auth secret")
        _alert("Activated Kite broker rotation is missing broker URL or auth secret. Live overlay remains disabled.")
        return _finish("FAILED_ROTATION")

    try:
        rotate_worker_secret(access_token)
    except Exception as exc:
        log.error("Broker Worker secret rotation failed: %s", type(exc).__name__)
        _alert("Kite broker Worker secret rotation failed. Live overlay remains disabled.")
        return _finish("FAILED_ROTATION")

    if not verify_broker():
        log.error("Broker verification failed; live overlay remains disabled")
        _alert(f"Broker verification failed. Live overlay remains disabled; static snapshot fallback retained. Last snapshot: {last_snapshot_timestamp()}")
        return _finish("FAILED_VERIFICATION")

    log.info("Broker Worker token rotation and bounded verification complete; overlay activation remains separate")
    return _finish("SUCCESS_ROTATED")


if __name__ == "__main__":
    sys.exit(main())
