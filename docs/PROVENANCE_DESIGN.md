Status: FOLDED INTO CONTRACT §9-11 (2026-07-21) — historical design record, not a spec
Authority: docs/AACAPITAL_PRODUCT_CONTRACT.md (this design folds into the
contract as a new §9 "Evidence & provenance" only after owner approval;
per directive 2026-07-21 no second product contract is created)

# PROVENANCE & FOUR-STATE DESIGN (design only — zero migrations in this PR)

Goal: every qualitative UI statement carries machine-readable provenance, and
completeness is expressed as CONFIRMED / PARTIAL / PENDING / FAILED — never
collapsed to null/false. This document is the reviewable design; code lands
in the small PRs listed in §6.

## 1 · What already exists (build on, don't duplicate)

| Need | Existing asset | Gap |
|---|---|---|
| RHP evidence | `ipo_rhp_intel.full_json` — Sonnet output with quoted lines per claim (`rhp_sonnet.py` SYSTEM prompt mandates quotes) | evidence embedded in one JSON blob; no per-insight rows, no page numbers |
| SBI evidence | `ipo_research_notes.full_json` | same shape issue |
| Run identity | `rhp_run_log` (spend, processed, deferred) | no per-IPO attempt state, no fingerprints |
| Failure events | `pipeline_failures`, `pipeline_steps` | step-level, not IPO-stage-level |
| PDF identity | files on VM; sha256 computable (`vm_verify.py`) | checksum not persisted → can't gate re-billing on change |

## 2 · New tables (additive only — no ALTER of existing tables, no drops)

```sql
CREATE TABLE IF NOT EXISTS ipo_insights (
  insight_id      BIGSERIAL PRIMARY KEY,
  ipo_id          INT  NOT NULL,             -- FK ipo_intelligence.id
  category        TEXT NOT NULL,             -- structure|governance|financial|valuation|sbi|risk
  statement       TEXT NOT NULL,
  direction       TEXT NOT NULL CHECK (direction IN ('positive','negative','neutral','incomplete')),
  source_type     TEXT NOT NULL,             -- RHP|SBI|NSE|SEBI|CHITTORGARH|SCREENER|BACKTEST|HOUSE_RULE|STRUCTURED
  source_name     TEXT,
  source_document_id TEXT,                   -- pdf sha256 or note filename
  source_url      TEXT,
  source_locator  TEXT,                      -- page/section when the model reports it
  source_excerpt  TEXT,                      -- the quoted line (Sonnet already produces it)
  extraction_model TEXT, analysis_model TEXT, analysis_run_id TEXT,
  confidence      TEXT,
  created_at      TIMESTAMPTZ DEFAULT now(),
  source_published_at TIMESTAMPTZ, source_downloaded_at TIMESTAMPTZ,
  is_current      BOOLEAN DEFAULT true
);
CREATE TABLE IF NOT EXISTS ipo_stage_state (
  ipo_id INT NOT NULL, stage TEXT NOT NULL,  -- DISCOVERED..READY_FOR_LIVE (contract list)
  status TEXT NOT NULL CHECK (status IN ('CONFIRMED','PARTIAL','PENDING','FAILED')),
  attempt_count INT DEFAULT 0,
  started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ,
  last_error TEXT, next_retry_at TIMESTAMPTZ,
  input_fingerprint TEXT,                    -- pdf sha256 + prompt_version + model
  output_fingerprint TEXT, pipeline_version TEXT,
  PRIMARY KEY (ipo_id, stage)
);
```

Writer rules: fill-empty never applies here — both tables are derived/event
tables (Rule-1 exempt like `pipeline_failures`). `is_current=false` supersedes
rather than deletes (no destructive migration, contract §8).

## 3 · State semantics (locked wording from the directive)

| Example | State |
|---|---|
| RHP downloaded, Sonnet not run | PARTIAL |
| RHP not yet published on SEBI | PENDING |
| SBI note not published | PENDING |
| SBI parser crashed | FAILED |
| RHP analysis completed + row written | CONFIRMED |

Rendering rule: a **negative or positive insight renders only when its
`ipo_insights` row exists with `source_excerpt` (or `source_type IN
('STRUCTURED','BACKTEST','HOUSE_RULE')` for numeric facts)**; otherwise the UI
shows the category's PENDING sentence. The #262 OFS fix is the hand-built
prototype of exactly this rule; this design generalizes it to every clause in
the IpoCard reason builder (P/E premium, leverage, ROE, growth, RHP risks…).

## 4 · Population path (no new model spend)

`rhp_sonnet_store.py` gains a fan-out step: after upserting `ipo_rhp_intel`,
explode `full_json` fields that already carry quotes (structure, use_of_
proceeds, promoter_pledge, top_3_material_risks, …) into `ipo_insights` rows
with `analysis_run_id` + pdf sha256. Same for the SBI store. **Zero extra
Anthropic calls** — we mine what the caps already paid for. Cost impact:
Neon rows only (~20–40 rows/IPO).

## 5 · Cost/dedup gating (fingerprints)

Before any Sonnet call: `input_fingerprint = sha256(pdf) + prompt_version +
model`. If `ipo_stage_state` has that fingerprint CONFIRMED → skip (no
re-bill). Changed pdf → new fingerprint → prior insights `is_current=false`,
stage back to PENDING. This also gives the $3/IPO cap a per-IPO ledger
(today's cap is per-day via `rhp_run_log`; per-IPO tracking becomes possible
without changing the cap value).

## 6 · Small-PR sequence (post VM-baseline, per directive)

1. **PR-A** migrations via `schema_sync.py` (additive DDL above) + fan-out in
   the two store scripts + unit tests on fixture JSON. No UI change.
2. **PR-B** ipo-command joins `ipo_insights` (KV-cached as today); IpoCard
   reason builder switches clause-by-clause to insight rows with source
   badges; per-clause tests (fail-before/pass-after).
3. **PR-C** `ipo_stage_state` writers inside the lean pipeline steps +
   `vm_verify.py` reads it instead of inferring from files; retry/`next_retry_at`
   honored by `rhp_auto.py`.
4. **PR-D** Live screen readiness banner from stage state
   (READY_FOR_LIVE gate; INCOMPLETE never renders as SKIP/BUY).

Open questions for owner sign-off (recorded, not guessed): page-number
fidelity from Sonnet (prompt asks for quotes, not page numbers — adding
locators may need a prompt_version bump, which re-fingerprints old IPOs; we
propose grandfathering old runs as locator-less), and whether SBI counts as
verdict input or context (contract conflict #5 — needs an owner line).
