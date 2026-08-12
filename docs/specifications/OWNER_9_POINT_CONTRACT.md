# Owner nine-point pipeline contract

Evidence status is explicit: **VERIFIED** means repository evidence was inspected;
**UNKNOWN** means owner configuration or external read-only evidence is unavailable.
This checklist is not production acceptance evidence.

| # | Requirement | producer / cron step | official source | canonical database home | snapshot / KV | UI consumer | retry / idempotency | proof | state |
|---|---|---|---|---|---|---|---|---|---|
| 1 | IPO discovery and retry | `nse_lifecycle.py` / NSE discovery | NSE | `ipo`, `ipo_issue` | command/index | Command Center | bounded resolution/upsert | lifecycle and cron tests | EXISTING (VERIFIED) |
| 2 | RHP, SBI, anchor documents | downloads, SBI ingest, NSE lifecycle | SEBI, SBI, NSE | `documents`, `rhp_findings` | Details | Complete Details | SHA ledger and owner gates | document-ledger/lifecycle tests | BLOCKED: anchor allocation source unproven |
| 3 | R2 storage/ledger/SHA | `document_ledger.store_document` | source document bytes | `documents` | Details evidence | Complete Details | R2-first SHA dedupe | document ledger tests | EXISTING; production handshake UNKNOWN |
| 4 | Kite to daily/15m/levels | refresh, Daily candles, 15-min candles, Top/bottom DISCOVERY | Kite | `market_candles`, `market_candles_15m`, `listing_observations` | `journey:isin:*:v1` | Journey | `(ipo_id,ts)` and `(ipo_id,obs_type,observed_at)` | detector/candle/snapshot tests | CHANGE_REQUIRED implemented; owner run pending |
| 5 | Listing pre-open | `capture_preopen.py` workflow | Kite | `listing_observations` (`preopen`) | `ipo-live-preopen:v2` | Command Center live | minute-key conflict no-op | capture tests | EXISTING (VERIFIED) |
| 6 | Complete Details | snapshot builder | canonical facts/documents | canonical joined homes | `ipo-details:isin:*:v1` | Complete Details | immutable versions/pointer | publication tests | EXISTING; production consumer proof UNKNOWN |
| 7 | junk filtering | drive decision engine | canonical facts | append-only `decisions` | `ipo-command:v6` | Command Center | effective latest decision | engine/command tests | EXISTING; live distribution UNKNOWN |
| 8 | listing rules | quarantined producer needs ownership decision | UNKNOWN | `rule_validation_results` shape exists | no verified snapshot field | Listing | UNKNOWN | repository trace | BLOCKED |
| 9 | journey signals | Top/bottom DISCOVERY + Journey builder | stored Kite candles | `listing_observations` (`level`) | `journey:isin:*:v1` | Journey | evaluated bar observation time | detector and snapshot contract tests | CHANGE_REQUIRED implemented; schema permission owner check pending |

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
failed with HTTP 401 before an official NSE index/API, stable attachment pattern, and
historical circular could be proven. Existing NSE anchor document capture is retained.
Cron reports `BLOCKER_ANCHOR_OFFICIAL_SOURCE_UNPROVEN`; no aggregator was scraped and
no parser was invented from an unsupported fixture.

### W3 — IPO record contract

**UNKNOWN / BLOCKED:** no authorized ledger export, R2 credentials, or immutable
historical payload inventory is present. The claimed count is **UNKNOWN**, not 641.
Creating a reviewed path union and field classification without that evidence would
fabricate the contract. Cron reports
`BLOCKER_IPO_RECORD_CONTRACT_EVIDENCE_UNAVAILABLE`. Vendor-only field list is UNKNOWN
pending the evidence-backed analyzer; no IPOMatrix client, token, call, or scrape was
added.

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
  allowed observation type; provide a SHA-verifiable historical JSON export or authorize
  R2 reads; prove the official NSE allocation circular source; run both cron commands on
  a clean Windows checkout; attach publication payloads and browser screenshots.
