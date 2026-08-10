# SBI R6 strict extraction transport

Status: code contract for PR #323. No production activation is implied by this document.

## Why R6 exists

The historical SBI pilot exposed four boundary defects: free-form JSON drift, two
inconsistent definitions of "extracted", source-fact provenance arguments that were not
persisted, and item-drop diagnostics that disappeared on later evidence/write failures.
R6 fixes those boundaries before another paid Messages call.

## Model boundary

The production SBI Messages request uses one client tool, `record_sbi_extraction`, with
`strict: true`, a closed JSON schema, and forced single-tool choice with parallel tool
use disabled. Temperature is zero. The paid path accepts only one correctly named
`tool_use` block and never falls back to parsing assistant prose. `max_tokens` remains a
truncation result and never enters parsing or writers.

`PROMPT_VERSION` is `sbi-v1.3`. Excerpts target 8-12 words while the server hard limit
remains 15. `page_number` is the number from the synthetic `--- PAGE N ---` marker, not
printed report pagination.

## Evidence and canonical writes

Unicode normalization is comparison-only; the model excerpt is stored unchanged.
Surviving claims/facts must still match the asserted PDF page. Item-level schema/bound
violations are recorded in `dropped_items`; after parsing, those diagnostics are kept on
successful, evidence-rejected, and write-error records.

SBI scalar facts write the live `source_facts.doc_id` foreign key plus the supplied model
confidence. The existing fact change-detection identity remains `(ipo_id, field, source)`;
`doc_id` and confidence are provenance, not a new dedup key.

Extraction completion has one SQL predicate shared by the runner and migration verifier:
a matching SBI insight OR a matching SBI source-fact row for the same document/model/
prompt version is complete. This allows a legitimate scalar-only extraction to reach
`EXTRACTION_MISSING=0`.

## Cost boundary

The old chars/4 total is retained only as a diagnostic approximation and is not an owner
authorization ceiling after strict tools were added. Before every default production paid call, the lane asks Anthropic
`/v1/messages/count_tokens` for the matching input context. Anthropic documents that
count as an estimate that may differ slightly from actual Messages usage, so AACapital
budgets the greater of count+1,024 tokens or count+10% before adding the configured
maximum output tokens. This reserve is an engineering guardrail, not a vendor-guaranteed
error bound; an observed reserve/cap breach is surfaced and blocks approval.

`--count-tokens-only` is the owner-gated no-generation checkpoint for the frozen 198
resolved, SHA-verified historical notes. It writes a local manifest containing per-note
counts, min/max/total input tokens, the guarded input budget, the delta from the legacy
approximation, owner price inputs, and the guarded maximum. It makes zero Messages generation calls and zero
canonical extraction writes.

## Live schema evidence

Read-only inspection of the AACapitalPvtLtd Neon branch on 2026-08-09 verified
`source_facts` contains nullable `doc_id bigint` with a foreign key to `documents(id)`
`ON DELETE SET NULL`, and `confidence numeric NOT NULL DEFAULT 1.0` constrained to 0..1.
The existing unique index remains `(ipo_id, field, source, fetched_at)`, with a separate
index on `(ipo_id, field)`. No schema migration is part of R6.

## Activation gate

Do not merge or run a paid pilot merely because unit tests pass. First review the remote
PR code, then run the owner-approved count-only checkpoint, review its exact total and
choose a new ceiling. The next two-note pilot is acceptable only with two `EXTRACTED`
results, zero drops, zero failure categories, and `full_run_approval_blocked=false`.

## Count-only authorization boundary

`--count-tokens-only` requires the owner gate plus input/output prices and output cap, but no spend-cap environment value. It performs read-only Neon/R2 verification and Anthropic token-count requests only, writes a local review manifest, and makes zero Messages-generation or canonical-write calls. The owner chooses the spend ceiling only after reviewing that manifest.
