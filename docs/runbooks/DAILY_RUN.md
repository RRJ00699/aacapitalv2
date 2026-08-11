# Daily Windows Pipeline

**Working directory:** `C:\aacapital-v2`  
**Run at:** 8:00 AM IST / 9:30 PM US Central on the previous day during CDT, or 8:30 PM during CST.

## Configuration

Required: `DATABASE_URL`.

Optional, by lane: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
`R2_DOCUMENT_BUCKET`, `SBI_OWNER_APPROVED`, `ANTHROPIC_API_KEY`, `KITE_API_KEY`,
`KITE_API_SECRET`, `KITE_USER_ID`, `KITE_PASSWORD`, `KITE_TOTP_SECRET`,
`KITE_BROKER_PROXY_URL`, `KITE_BROKER_PROXY_AUTH_SECRET`, `SNAPSHOT_PUBLISH_URL`,
`SNAPSHOT_PUBLISH_KEY`, and `NTFY_TOPIC`. Never paste values into logs or the PR.
Paid lanes require explicit owner gating (`SBI_OWNER_APPROVED=YES` and/or paid API configuration).

## Run (PowerShell)

```powershell
python pipeline\cron.py --dry-run
python pipeline\cron.py
```

The one-screen **END-OF-RUN REPORT** is at the bottom of each command's console output.

## Five likely failures

1. `DATABASE_URL` absent — set it in the current PowerShell environment, then rerun.
2. `required script absent` — restore the clean checkout (`git reset --hard origin/codex/windows-pipeline-end-to-end`).
3. Python module missing — run `python -m pip install -r pipeline\requirements.txt`.
4. Snapshot lane skipped — configure `SNAPSHOT_PUBLISH_URL` and `SNAPSHOT_PUBLISH_KEY`.
5. Kite/SBI lane skipped — configure the names shown by Step 0; approve paid/SBI lanes explicitly.
