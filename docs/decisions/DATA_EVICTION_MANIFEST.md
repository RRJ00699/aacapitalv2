# Phase 3 data-eviction manifest

**Status:** **EXECUTED — 2026-08-07**

Inventory captured on 2026-08-07 from commit `0cc02f5`. Counts exclude CSV header rows. Byte counts are exact filesystem sizes, not allocated disk sizes. “IPO-universe” means an IPO observation or IPO document; the sector-map split uses exact `nse_symbol` membership in `ipo_backtest_export/ipo_meta.csv`. No Neon query or write was made.

## Inventory and proposed disposition

| Target | Files | Bytes | Rows / records | Observed date range | Caller grep result | IPO-universe | Non-IPO | Destination | Disposition |
|---|---:|---:|---:|---|---|---:|---:|---|---|
| `data/` | 262 | 150,668,409 | 124,476 CSV rows + 241 PDF documents | bulk/block filenames: 2016-06-09–2026-06-09; SBI note dates not reliably machine-readable | **BLOCKED:** live callers exist (below) | 241 IPO PDFs | 124,476 market-deal rows | `C:\aacapital-exports\2026-08-07\data.zip`; PDFs may remain in the current canonical `documents`/`ipo_research_notes` flow only after owner validation | Export only. Do not evict while live SBI callers use this tree. Bulk/block rows are owner-archive candidates. |
| `ipo_backtest_export/` | 3 | 2,885,594 | 34,155 | 2010-01-18–2026-09-27 | no live exact-path caller | 32,052 | 2,103 market-index rows | `C:\aacapital-exports\2026-08-07\ipo_backtest_export.zip` | Owner archive; canonical DB already owns production IPO facts, subject to owner confirmation. |
| `_output/` | 1 | 650,489 | N/A (`enricher_v2.log`) | not structured | no live exact-path caller | 0 | 0 | `C:\aacapital-exports\2026-08-07\_output.zip` | Owner archive. |
| `dip_defense.csv` | 1 | 12,308 | 84 | 2021-01-29–2026-04-02 | no live caller | 84 | 0 | owner export directory | Owner archive; research output, not a production input. |
| `factor_report.csv` | 1 | 1,361 | 30 aggregate rows | no date column | no live caller | 30 derived IPO aggregates | 0 | owner export directory | Owner archive; research output. |
| `forensic.csv` | 1 | 10,272 | 97 | 2025-08-05–2026-07-31 | no live caller | 97 | 0 | owner export directory | Owner archive; research output. |
| `ipo_factors.csv` | 1 | 78,473 | 359 | no date column | output option documented by `_scripts/ipo/ipo_factor_dump.py`; no read caller | 359 | 0 | owner export directory | Owner archive; reproducible research output. |
| `sector_map.csv` | 1 | 35,969 | 1,051 | no date column | written by `_scripts/dump_sector_map.py`; no read caller | 168 exact IPO-symbol matches | 883 unmatched symbols | owner export directory | Owner archive; do not create a new Neon table. |
| `ipo_master.xlsx` | 1 | 75,182 | 0 worksheet rows (template-only workbook) | no populated dates | fallback read candidate in `_scripts/sync_ipo_master.py`; no caller evidence for that script in enabled workflows, package scripts, pipeline, or Admin jobs | 0 | 0 | owner export directory | Owner archive after approval. |

Totals before execution: **274 files, 154,418,057 bytes, 160,252 CSV rows, and 241 PDF documents**. The approved archive-only targets were removed after the owner export was verified. `data/research_notes/` was retained.

## Caller verification

The required statement “no live production caller reads `data/` trees” is **not verified and is currently false**:

- `pipeline/cron.py` reads/writes `data/research_notes` for the canonical `--rhp`/SBI path.
- `_scripts/job_runner.py` exposes `sbi_download` and `sbi_parse` with `data/research_notes` arguments.
- `.github/workflows/sbi-notes.yml` downloads, parses, and commits `data/research_notes`.
- `_scripts/run_ipo_pipeline_lean.py` invokes the SBI scripts, whose defaults and explicit arguments use `data/research_notes`.

Therefore `data/research_notes/` is **not approved for deletion** in the post-export commit unless those live paths are deliberately migrated in a separately reviewed change. The other listed targets have no production read caller; generator/output mentions are recorded in the table rather than treated as reads.

## Owner export and verification

**Verified export destination:** `C:\aacapital-exports\2026-08-07`

The owner reported these individually verified SHA256 values:

| Exported file | SHA256 |
|---|---|
| `data.zip` | `11E9FB68C3A6B10DA5109F02A463AF854A975605719392DF7ECA67E0BB436ED7` |
| `ipo_backtest_export.zip` | `4CB13E1A46FF1375EF2B30C59DAE19A991B14A704A7374E31CF92600A0E2089B` |
| `_output.zip` | `8AD2C677235E333557C6483056893D1770B08CE99AADF4E3ABF4BBEFCF6DEA14` |
| `dip_defense.csv` | `5624342BB19D20C253D5121F3047FF24191C6DC457438C44EB876DA9303A5C83` |
| `factor_report.csv` | `34E2F744CA6E3DA53ED819F85EEC62A2E30CB29B3510B4F332BE6C017F12A7C5` |
| `forensic.csv` | `ECFBC4688B08FE7F5C52DEF512ABD00A4302254898C87A04BEFFEDBF7E524B2C` |
| `ipo_factors.csv` | `7ABA4C6A3C897188EFC5B72D2DE471F612EC5DA262D72572B9083A3ACC190716` |
| `sector_map.csv` | `80E84ECF82A880A419BFCC1F71EA5904F65ECA035FF2FF1BD99120C76C6ED3B8` |
| `ipo_master.xlsx` | `0E2D51B6A82479542A357D6C88C94DF0F1185E39119F3D33528E00943D9EF867` |

From a Windows PowerShell prompt at the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\_scripts\export_phase3_data.ps1 -Destination C:\aacapital-exports\2026-08-07
```

The script creates the destination, archives directories, copies standalone reports, compares exported file counts and uncompressed bytes with the sources, prints CSV row counts, and prints SHA256 for every output. Any verification mismatch exits non-zero.

## Retained live lane and follow-up

**`data/research_notes/` status:** **BLOCKED-LIVE**

**Reason:** active SBI/cron callers.

**Open follow-up:** migrate the SBI/research-note lane before removal. This execution did not propose a new Neon table or change or delete an R2 object.
