# Owner nine-point pipeline contract

**Status:** Active owner contract checklist for PR #328.

Evidence status is explicit: **VERIFIED** means repository evidence was inspected;
**UNKNOWN** means owner configuration or external read-only evidence is unavailable.
This checklist is not production acceptance evidence.

| # | Requirement | producer / cron step | official source | canonical database home | snapshot / KV | UI consumer | retry / idempotency | proof | state |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Current/open/upcoming IPO discovery; missing V2-schema data is reported and retried on subsequent bounded runs. | `nse_lifecycle.py` / NSE discovery and V2 completeness plan | NSE | `ipo`, `ipo_issue` | command/index | Command Center | bounded resolution/upsert and progress-safe cohort | lifecycle, completeness, and cron tests | EXISTING (VERIFIED) |
| 2 | RHP, SBI, and official-NSE forward-only anchor allocation, retry-on-availability | downloads, SBI ingest, NSE lifecycle | SEBI, SBI, NSE | `documents`, `rhp_findings`, `source_facts` when a stable structured shape is proven | Details | Complete Details | SHA ledger, availability retry, and owner gates | document-ledger/lifecycle tests | BLOCKED: anchor allocation shape unproven |
| 3 | R2 storage/ledger/SHA | `document_ledger.store_document` | source document bytes | `documents` | Details evidence | Complete Details | R2-first SHA dedupe | document ledger tests | EXISTING; production handshake UNKNOWN |
| 4 | Kite to daily/15m/TOP levels | refresh, Daily candles, 15-min candles, TOP DISCOVERY | Kite | `market_candles`, `market_candles_15m`, `listing_observations` | `journey:isin:*:v1` | Journey | `(ipo_id,ts)` and `(ipo_id,obs_type,observed_at)` | detector/candle/snapshot tests | CHANGE_REQUIRED implemented; owner run pending |
| 5 | Listing pre-open | `capture_preopen.py` workflow | Kite | `listing_observations` (`preopen`) | `ipo-live-preopen:v2` | Command Center live | minute-key conflict no-op | capture tests | EXISTING (VERIFIED) |
| 6 | Complete Details | snapshot builder | canonical facts/documents | canonical joined homes | `ipo-details:isin:*:v1` | Complete Details | immutable versions/pointer | publication tests | EXISTING; production consumer proof UNKNOWN |
| 7 | junk filtering | drive decision engine | canonical facts | append-only `decisions` | `ipo-command:v6` | Command Center | effective latest decision | engine/command tests | EXISTING; live distribution UNKNOWN |
| 8 | listing rules | quarantined producer needs ownership decision | UNKNOWN | `rule_validation_results` shape exists | no verified snapshot field | Listing | UNKNOWN | repository trace | BLOCKED |
| 9 | Journey TOP/watch state (no bottom/entry interpretation in this PR) | TOP DISCOVERY + Journey builder | stored Kite candles | `listing_observations` (`level`) | `journey:isin:*:v1` | Journey | evaluated bar observation time | detector and snapshot contract tests | CHANGE_REQUIRED implemented; schema permission owner check pending |

## Workstream evidence and blockers

### W1 — formal 15-minute supply and Journey handshake

**VERIFIED:** `market_candles_15m` is defined with primary key `(ipo_id, ts)` in the
canonical V2 writer. The dedicated bounded lane reuses `kite_fetch.get_kite` and
`kite_fetch.fetch_candles_15m`, starts immediately after `max(ts)`, retries one
transient failure, throttles requests, and reports received/inserted/duplicate/no-data
counts. The promoted detector contains no Kite client and Journey receives its latest
level observation through the snapshot plane.

**UNKNOWN:** no repository migration or specification constrains allowed
`listing_observations.obs_type` values. The writer inspects live check constraints and
fails with an owner reason if `level` is not permitted. A real schema smoke and owner
Windows run remain required.

### W2 — anchor allocation

**UNKNOWN / BLOCKED:** an internet search attempt from the development environment
failed with HTTP 401 before the official NSE IPO-detail response's forward allocation
shape could be proven stable. Existing forward NSE anchor document capture is retained.
Cron reports `BLOCKER_ANCHOR_OFFICIAL_SOURCE_UNPROVEN`; no aggregator was scraped and
no parser or historical-backfill obligation was invented. Owner read-only PowerShell probe:
`Invoke-RestMethod -Headers @{'User-Agent'='Mozilla/5.0';'Referer'='https://www.nseindia.com/'} -Uri 'https://www.nseindia.com/api/ipo-detail?symbol=<EXACT_NSE_SYMBOL>&series=EQ' | ConvertTo-Json -Depth 20`.

### W3 — V2-schema completeness

**VERIFIED:** completeness is derived from the declared V2 schema map. The bounded
active cohort is measured before and after its single pass through existing lanes;
missing fields report their existing retry lanes without adding a fetcher.

### W4 — verdict and rules card

**UNKNOWN / BLOCKED:** no owner-authorized read-only database URL is present, so a
current verdict distribution and before/after comparison cannot be claimed. Repository
trace finds the historical rule-validation producer under `compatibility/` and marked
quarantined in the inventory, while no verified snapshot contract carries these rows.
Cron makes that missing production ownership visible. Verdict semantics and engine
version were not changed without the required diagnosis.

## Activation and operational impact

- **Paid calls:** 0 during development. Owner approval gates are unchanged.
- **Production, R2, Cloudflare calls/writes:** 0 during development.
- **Third-party scraping:** none. No third-party source was scraped.
- **Windows risk:** timezone-aware Python timestamps and repository-relative script
  constants are used; live PowerShell/schema parity remains owner evidence.
- **Rollback:** `git revert <merge-commit>`.
- **Owner activation:** provide read-only schema/database access; confirm `level` is an
  allowed observation type; run the exact NSE forward probe above; run both cron commands on
  a clean Windows checkout; attach publication payloads and browser screenshots.
