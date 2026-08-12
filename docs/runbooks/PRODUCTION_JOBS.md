# Production job map

Status: CURRENT — verified static production caller map.

Evidence status is repository-static unless explicitly stated; installed VM crontab
state remains **UNKNOWN** pending the owner read-only probe in the lean decision register.

| Job/caller | Entrypoint | Schedule | DB | Network / paid API | R2 / KV | Output / consumer |
|---|---|---|---|---|---|---|
| GitHub pipeline | `pipeline/cron.py --run` | manual dispatch | `DATABASE_URL` writer; read-only smoke separately | SEBI, NSE, SBI, Kite; Anthropic paid extraction capped | document R2; snapshot publication KV | canonical facts, extraction, snapshots; all four public products |
| Snapshot publication | `pipeline/publish_snapshot_with_ledger.py` | pipeline workflow | canonical reads | publication HTTP | CACHE version/pointers | Command, Details, Live, Journey |
| NSE pre-open | `pipeline/capture_preopen.py` | GitHub cron | writer | NSE | publication path may use KV | Listing Day Live |
| SBI notes | workflow + pipeline scripts | GitHub cron | writer | SBI; configured extraction may be paid | R2 document contract | verified extraction inputs |
| VM job runner | `_scripts/job_runner.py` | installer exists; actual VM crontab UNKNOWN | `DATABASE_URL` queue and selected job writes | varies by selected job | reads/deletes `admin:jobs-pending` | Admin repairs and bounded recomputation |
| npm prod modes | `_scripts/prod/kite_sync_and_predict.py` | explicit operator | writer | Kite | none | market/IPO operational records |

Admin catalogs contain the same 14 keys: `pipeline`, `pipeline_weekly`, `ipo_lifecycle`, `news`, `peer_pe_notes`, `peer_pe`, `vm_verify`, `token`, `gmp`, `ipomatrix`, `breadth`, `sync`, `schema`, and `smoke`. The contract test enforces equality.
Schema provisioning remains an explicit `schema` operator job; web requests and the VM
queue poller no longer create tables.
