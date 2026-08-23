# IPO Matrix bootstrap sequence

Status: **CURRENT** — planning-only doc; nothing is ingested yet.

Owner has raw IPO Matrix archive covering 2004–2026 (≈60 for 2026,
≈103 for 2025, + long tail earlier years). Combined validation of the
archive is happening independently of this PR.

## Load order (Point 4 of the owner brief)

1. **A. Lock final 5-table D1 schema** — done: `d1/migrations/*.sql`.
2. **B. Lock field/unit mapping** — pending owner-signed field map (see
   §Unit rules below). Values must be verified per-field before any
   normalisation.
3. **C. Complete local Neon→D1 rehearsal** — done for the current Neon
   dataset. Sizing + copy + reconciliation reports in
   `_migrate/*.md`.
4. **D. Load IPO Matrix bootstrap into LOCAL / STAGING D1** — use IPO
   Matrix as an ENRICHMENT source per
   `docs/architecture/SOURCE_PRECEDENCE.md`. Write via the ingest Worker
   in `mode=coalesce_empty` with `source='ipomatrix'`.
5. **E. Reconcile the IPO Matrix + Neon combined result** —
   `tools/migrate/reconcile.py` grows a per-source column so operators
   can see how many cells landed from Neon vs IPO Matrix vs anywhere
   else.

Only then may we consider **remote-staging D1**.

## What IPO Matrix may fill (rank 3 in source-precedence)

| D1 target             | Field(s) that IPO Matrix may fill                                                                     |
|---|---|
| `ipo`                 | `symbol`, `sector`, `industry`, `ipomatrix_id`, `bse_code`, `is_mainboard`, `listing_date` (only if Neon has NULL) |
| `fundamentals`        | `open_date`, `close_date`, `allotment_date`, `band_lo`, `band_hi`, `issue_price`, `face_value`, `lot_size`, `issue_size_cr`, `fresh_cr`, `ofs_cr`, `market_cap_cr`, `registrar`, `brlm_count`, `allocation_qib_pct`, `allocation_nii_pct`, `allocation_retail_pct`, financial history, subscription (if validated), anchor (if validated), listing outcomes (if validated) |
| `research_findings`   | `finding_type='ipomatrix_note'` (**new type; needs schema whitelist expansion in a follow-up migration**) if IPO Matrix carries human-authored commentary |

IPO Matrix **must never**:

* overwrite non-NULL `ipo.isin` or `ipo.name_norm` — identity is
  managed by `resolveIpoIdentity`.
* write `fundamentals.fundamental_verdict` or `listing_action` — those
  are rank-4 engine outputs.
* write `market_observations` — IPO Matrix is a batch/derived source,
  not a live market feed.

## Unit rules (LOCKED)

All IPO Matrix monetary fields **must be verified against a known
reference issue** before the whole archive is normalised. The Point 4
rule ("do not infer units from field names such as `_cr`") is enforced
as follows:

1. Every incoming IPO Matrix monetary field is annotated with an
   explicit `unit` in the loader mapping (`inr_per_share`,
   `inr_crore`, `inr_lakh`, `usd`, `percent`, `multiplier`).
2. A field name suffix of `_cr` does NOT imply the value is in crore.
   The loader has an override table that documents the actual measured
   unit per column, validated against a golden IPO.
3. Any field for which the unit cannot be verified is written to
   `source_facts` with the raw value + `pipeline_version='ipomatrix-
   bootstrap-unverified-YYYYMMDD'` and NOT written to `fundamentals`.

## Raw JSON immutability

* Raw IPO Matrix captures are stored in R2 under
  `r2://aacapital-source/ipomatrix/<year>/<sha256>.json` (Stage-D
  action; not yet provisioned).
* No loader or engine ever mutates these blobs.
* Every `fundamentals` cell landed from IPO Matrix cites the
  corresponding R2 blob's `document_sha` in `source_facts`, so the
  provenance path is `fundamentals.field → source_facts row →
  document_sha → R2 immutable blob`.

## Progression gate

Before step D above starts, the owner must sign off on:

1. A per-field unit table (Google Sheet or Markdown) proving the
   measured unit of every IPO Matrix column against a known reference
   IPO (e.g. Shreeji Shipping precedent).
2. This document (`IPO_MATRIX_BOOTSTRAP.md`) reflecting any last-
   minute deviations.

Only then can `tools/migrate/ipomatrix_to_d1.py` (to be authored)
start writing into local D1 via the ingest Worker.
