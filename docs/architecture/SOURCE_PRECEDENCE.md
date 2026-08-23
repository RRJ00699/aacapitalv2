# Source precedence (5-table D1)

Status: **CURRENT** — the single rulebook for which writer wins when the
same field has two competing values.

This document turns Point 5 (Preserve source priority) into a set of
rules the ingest Worker and the pipeline’s Sonnet-driven passes must both
follow.

## The order

For every field of every table in `d1/migrations/`, when two writers land
different values, the following rank decides:

| Rank | Writer                                        | Examples of what it may write                                                                     | D1 mode allowed |
|---:|--------------------------------------------------|---------------------------------------------------------------------------------------------------|---|
| 1  | **Authoritative structured current source**       | NSE / SEBI / Kite (band, issue_price, listing_date, live LTP, live subscription)                  | `coalesce_empty` for fill-in; `upsert` for values the exchange re-issues (e.g. issue_price changed by SEBI update) |
| 2  | **RHP / DRHP structured facts (validated)**       | face value, fresh vs OFS split, financial history, promoter holding, BRLM/registrar               | `coalesce_empty`  |
| 3  | **Validated IPO Matrix bootstrap** (not yet loaded) | historical enrichment for fundamentals + financial history + validated subscription/anchor        | `coalesce_empty` **only**  — IPO Matrix never overwrites rank 1 or 2 |
| 4  | **Derived engine outputs**                        | `fundamentals.valuation_score`, `valuation_band`, `fundamental_verdict`, `listing_action`         | `upsert` (engine reruns are expected to replace prior engine outputs) |
| 5  | **AI interpretation — research findings only**    | `research_findings.finding`, `excerpt`, `severity`, `direction`, `category`                       | `append` only in `research_findings`; must **never** land in `fundamentals` or `ipo` |

## Non-negotiable rules

1. **Sonnet (or any AI) must NEVER silently overwrite structured numeric
   fundamentals.** AI extracts land in `research_findings`. If an AI
   extraction disagrees with a rank-1..3 value, the disagreement is
   surfaced by writing a `research_findings` row with
   `direction='negative'` and `category='data_conflict'` — not by
   changing `fundamentals`.
2. **Every important value must retain source/provenance in `source_facts`.**
   Every fundamentals/market write emits at least one `source_facts` row
   with `field`, `value`, `source`, `document_sha` (if applicable),
   `pipeline_version`, and `observation_hash`. The write is idempotent
   under `UNIQUE (ipo_id, field, observation_hash)` so retries with the
   same value collapse.
3. **`coalesce_empty` never overwrites a non-NULL cell.** A rank-2
   writer cannot clobber a rank-1 value. A rank-3 writer cannot clobber
   a rank-1 or rank-2 value.
4. **`upsert` mode is only allowed for ranks 1 and 4.** Ranks 2–3 are
   `coalesce_empty` only.
5. **`append` mode is only allowed for `market_observations` (any rank)
   and `research_findings` (rank 5).** `ipo` and `fundamentals` never
   accept `append`.

## What the ingest Worker enforces today

* `workers/ingest/src/schemas.ts:ALLOWED_MODES` restricts the modes
  each table accepts:

  | Table                 | Modes                                    |
  |---|---|
  | `ipo`                 | `coalesce_empty`                         |
  | `fundamentals`        | `coalesce_empty`, `upsert`               |
  | `market_observations` | `append`                                 |
  | `research_findings`   | `append`, `upsert`                       |

* `workers/ingest/src/db.ts:coalesceEmptyPatch` implements rule 3
  verbatim: only NULL cells are set from the patch, and every applied
  change is emitted as a `RowChange` so `source_facts` gains a row.
* `workers/ingest/src/index.ts` calls `factStatements(...)` for every
  successful non-`ipo` write, satisfying rule 2 by construction.

## Where the rulebook still needs code work

* **Rank enforcement is not yet cryptographic** — today, the source of a
  write is what the caller HTTP header says it is. Stage-D will add a
  per-source secret (`INGEST_KEY_NSE`, `INGEST_KEY_RHP`, ...) so a rank-5
  caller cannot pretend to be rank-1. Until then, deployment guards
  (single trusted VM writing to the Worker) provide the boundary.
* **IPO Matrix bootstrap** is authored but not yet loaded. When it is,
  its writer path must call the ingest Worker in `coalesce_empty` mode
  with `source='ipomatrix'`, and it must never call `mode=upsert` on
  `fundamentals`.
