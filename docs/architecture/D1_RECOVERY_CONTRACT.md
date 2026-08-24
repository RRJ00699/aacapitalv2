# D1 recovery and physical-model contract

Status: PROPOSED — PR #343 owner review

The model is functional rather than a Neon mirror. Identity is ISIN, then the repository canonical `name_norm`; symbols are nullable routing metadata. Long narratives are outside `ipo`. Canonical decimal facts use exact decimal-string `TEXT`, counts/shares use `INTEGER`, time-series retain time, and interpretive AI output cannot overwrite authoritative facts. Serving/KV publication is intentionally outside this migration.

Lifecycle: **discovery** → **document** → **issue** → **subscription** → **anchor** → **listing/pre-open** → **post-listing** → **calculation/publication**.

| Table | Why / principal columns | Primary producer | Consumer | DUE | Recovery source | Tier |
|---|---|---|---|---|---|---|
| `ipo` | permanent identity: ISIN, normalized name, symbols, Matrix ID | NSE discovery; migration identity mapper | every downstream relation | discovery | NSE + raw Matrix; manual collision review | B |
| `ipo_issue` | one current authoritative issue: schedule, generated lock30/lock90 dates, ₹/share, shares, ₹ crore, registrar/BRLM | NSE issue lane; validated bootstrap | research/calculation/KV builder | issue | NSE/RHP/raw Matrix | B |
| `company_profile` | long description and structured company profile | RHP extractor | company-quality/KV builder | document | RHP/DRHP | B |
| `ownership` | one row/category for pre/post holdings and dilution | RHP extractor | company-quality/valuation | document | RHP/DRHP | B |
| `objects_of_issue` | one source row/use of proceeds | RHP extractor | company-quality/KV builder | document | RHP/DRHP | B |
| `financial_statements` | period+basis accounts in ₹ crore | RHP extractor; validated Matrix bootstrap | KPI/valuation/quality | document | RHP/DRHP/raw Matrix | B |
| `reservations` | row/category allocation structure | NSE issue lane | subscription context/KV | issue opens | NSE raw response | B |
| `subscription_snapshots` | category time-series; shares, x, final flag, stable fingerprint | NSE subscription lane | demand/trade setup | subscription | NSE/raw observations | B |
| `anchor_summary` | issue-level anchor totals | future official anchor parser | quality/KV | anchor report | report PDF | B |
| `anchor_allocations` | immutable document row/order and raw investor name | future official anchor parser | anchor research/classifier | anchor report | report PDF | B (PDF is A) |
| `peer_comparisons` | row/peer sourced metrics and as-of date | RHP extractor | valuation/quality | document | RHP/SBI evidence | B |
| `documents` | SHA identity and URL/size/pages/R2 metadata (not bytes) | SEBI/SBI/NSE fetchers | all evidence lanes | document published | original bytes/R2/source refetch | A metadata; bytes A |
| `research_findings` | strengths/risks/litigation/auditor/opinion with evidence/model/prompt | RHP/SBI/anchor extraction | company quality/KV | document analyzed | document + versioned re-extraction | C (documents A) |
| `gmp_observations` | explicitly unofficial time-series | approved GMP scraper | contextual display only | pre-listing | captured observation | B; non-official |
| `market_bars` | coherent `1d`/`15m`; schema permits future `5m` but no backfill claim | Kite | Journey/backtests/market calculations | listing/post | Kite where retained | B |
| `listing_observations` | pre-open/listing tape and raw fields | NSE/Kite capture | live action/listing outcome | listing day | captured payload; pre-open not historically replaceable | **A for pre-open**, B otherwise |
| `valuation_runs` | versioned inputs, ratios, range, MoS, missing inputs | valuation engine | KV snapshot/audit | calculation | recompute from facts | C |
| `decision_history` | append-only company/trade/live layer decisions | layer-specific engines | KV snapshot/audit | respective lifecycle layer | recompute where inputs preserved | C |
| `source_facts` | field-level raw/normalized/unit/source/parser provenance | every mapper | audit/reconciliation | every write | raw objects/documents/source | B |
| `raw_objects` | deferred D1 payload home; schema protections remain for a later archive phase | future archive/R2 ingest | recovery/migration audit | deferred after core cutover | owner Tier-A archive/backups | **A** |
| `migration_quarantine` | anomalies/unmapped/ambiguous records, never silent loss | migration mapper | reconciliation/owner review | migration | rerun after explicit resolution | A audit record |
| `migration_checkpoints` | deterministic resume key and counts | migration mapper | migration operator | migration | rerun from prior stable key | C |

`fundamental_metrics` was removed: sourced metrics have one provenance home in `source_facts`; AACapital-computed metrics have one versioned home in `valuation_runs`.

## Lifecycle DUE contract

`ANNOUNCED`: identity and initial issue record. `UPCOMING`: documents/profile/financial extraction. `OPEN`: live issue/reservation facts. `CLOSED`: final subscription. `ALLOTTED`: issue price/ISIN/allotment facts. `LISTED`: pre-open/listing observations and market bars. `WITHDRAWN`: no later facts become due. `ipo_lifecycle_due` derives these flags; 0 is `NOT_DUE`, not missing, failed, or numeric zero.

## Raw storage decision and sizing gate

Core D1 does not store IPO Matrix payload bodies. The owner-held 968-file archive remains
Tier-A recovery evidence, while the migration report records file path, SHA256, and byte
size and normalized provenance retains archive SHA references. R2/archive ingestion is a
later phase and does not block core cutover; the existing `raw_objects` schema is preserved.

## Recovery order

Restore Tier A bytes/observations and verify SHA256; rebuild Tier B normalized facts with the pinned parser and unit contract; recompute Tier C; reconcile; only then publish a new versioned KV snapshot. Neon remains read-only throughout and is not a recovery write target.
