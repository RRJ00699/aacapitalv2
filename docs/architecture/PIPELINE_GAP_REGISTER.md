# Forward pipeline gap register

This register describes missing work; it does **not** implement the forward pipeline. `SOURCE_GAP` means the exact official source/shape is unproven. `PIPELINE_GAP` means the source is identified but no complete normalized producer was found.

| Information contract | Current producer/evidence | Missing producer | Forward source | Lifecycle DUE |
|---|---|---|---|---|
| IPO identity/lifecycle | `pipeline/nse_lifecycle.py` | D1 writer + collision queue | NSE | discovery |
| issue schedule/band/face/lot/size/fresh/OFS/registrar/BRLM | `pipeline/nse_fetch.py` | D1 unit-gated mapper | NSE; RHP evidence | issue |
| company profile/promoters/selling shareholders | document/RHP lane exists | `PIPELINE_GAP` normalized mapper | SEBI RHP/DRHP | document |
| objects of issue | no row producer proven | `PIPELINE_GAP` row/evidence extractor | SEBI RHP | document |
| ownership | only promoter-post Matrix mapper proven | `PIPELINE_GAP` complete category mapper | SEBI RHP | document |
| financial periods | `pipeline/rhp_writer.py`; Matrix fallback | D1 adapter + per-field unit evidence | SEBI RHP; bootstrap archive | document |
| sourced/recomputed KPIs | partial RHP/Matrix mappings | versioned metric calculator with provenance | RHP inputs | calculation |
| reservation categories | NSE subscription producer evidence | `PIPELINE_GAP` reservation row mapper | NSE | issue opens |
| subscription snapshots | NSE fetch exists; current V2 shape differs | D1 category time-series adapter | NSE | during/final subscription |
| anchor report discovery/download | quarantined `compatibility/scripts/nse_anchor_backfill.py` proves session pattern | `PIPELINE_GAP` supported fetch lane | NSE issue page/report | anchor report |
| anchor summary/allocation rows | names-only Matrix bootstrap | `PIPELINE_GAP` deterministic row-preserving parser; Sonnet only fallback | official NSE Anchor Allocation Report | anchor report |
| peers | Matrix opaque `peer_analysis`; RHP evidence lane | `PIPELINE_GAP` row mapper | SEBI RHP; SBI commentary separate | document |
| RHP/DRHP documents | SEBI fetch/RHP lane | D1 metadata adapter; R2 activation later | SEBI | document published |
| SBI document/opinion | SBI pipeline exists | D1 evidence adapter | approved SBI document | broker note published |
| research findings | RHP/SBI extractors exist | D1 category adapter and version supersession | documents; Sonnet extraction only | after document |
| GMP | InvestorGain scraper exists | D1 observation adapter | `SOURCE_GAP` official source; retain as non-official | pre-listing |
| daily/15m candles | `pipeline/kite_fetch.py` | D1 market-bar adapter | Kite | listing/post |
| historical 5m | none proven | none authorized; do not backfill | `SOURCE_GAP` | future only |
| pre-open | NSE capture exists | D1 Tier-A adapter + raw preservation | NSE live capture | listing morning |
| listing outcome/Journey | Kite/calculation lanes exist | versioned D1 calculation adapters | Kite bars | listing/post |
| valuation | application fair-value logic exists | D1 versioned-run writer | normalized facts | calculation |
| three decision layers | existing rule/decision code is split across V2 | append-only layer writers and lifecycle gate | normalized facts + live tape | respective stage |
| versioned KV publication | existing KV publication architecture | future D1→calculation→KV publisher; out of scope | D1 | after validation |
