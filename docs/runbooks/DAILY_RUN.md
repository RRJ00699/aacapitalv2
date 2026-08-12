# Daily Windows Pipeline

> **Status: Active** — Owner's supported daily production command.

**Working directory:** `C:\aacapital-v2`  
**Run at:** 8:00 AM IST / 9:30 PM US Central on the previous day during CDT, or 8:30 PM during CST.

## Configuration

Required: `DATABASE_URL`.

Optional, by lane: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
`R2_DOCUMENT_BUCKET`, `SBI_OWNER_APPROVED`, `ANTHROPIC_API_KEY`, `KITE_API_KEY`,
`SBI_SONNET_OWNER_APPROVED`, `SBI_SONNET_INPUT_USD_PER_MTOK`,
`SBI_SONNET_OUTPUT_USD_PER_MTOK`, `SBI_SONNET_OUTPUT_CAP`, `SBI_SONNET_RUN_CAP_USD`,
`RHP_EXTRACTION_OWNER_APPROVED`,
`KITE_API_SECRET`, `KITE_USER_ID`, `KITE_PASSWORD`, `KITE_TOTP_SECRET`,
`ALLOW_LEGACY_KITE_DB_TOKEN_WRITE`, `KITE_REFRESH_VALIDATE_ONLY`,
`EXECUTE_CLOUDFLARE_SECRET_ROTATION`, `KITE_BROKER_PROXY_URL`,
`KITE_BROKER_PROXY_AUTH_SECRET`, `SNAPSHOT_PUBLISH_URL`,
`SNAPSHOT_PUBLISH_KEY`, and `NTFY_TOPIC`. Never paste values into logs or the PR.
Paid lanes require explicit owner gating: `SBI_SONNET_OWNER_APPROVED=YES` and
`RHP_EXTRACTION_OWNER_APPROVED=YES`; SBI ingest separately uses `SBI_OWNER_APPROVED=YES`.
The owner Kite handoff requires both `ALLOW_LEGACY_KITE_DB_TOKEN_WRITE=1` and
`KITE_REFRESH_VALIDATE_ONLY=1`.

## Run (PowerShell)

```powershell
python pipeline\cron.py --dry-run
python pipeline\cron.py
```

The one-screen **END-OF-RUN REPORT** is at the bottom of each command's console output.

## Five likely failures

1. `DATABASE_URL` absent — set it in the current PowerShell environment, then rerun.
2. `required script absent` — run `git fetch origin; git switch main; git pull --ff-only origin main`.
3. Python module missing — run `python -m pip install -r pipeline\requirements.txt`.
4. Snapshot lane skipped — configure `SNAPSHOT_PUBLISH_URL` and `SNAPSHOT_PUBLISH_KEY`.
5. Kite/SBI lane skipped — configure the names shown by Step 0; approve paid/SBI lanes explicitly.
