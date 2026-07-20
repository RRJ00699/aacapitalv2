Status: CURRENT
Authority: docs/AACAPITAL_PRODUCT_CONTRACT.md
Last verified against code: 2026-07-21
Verified commit: PR #265 head (branch feat/provenance-pr-a)

# CURRENT PR IMPLEMENTATION AUDIT — PR #265

Baseline before Phase 8: 642 passed / 2 skipped (full DB tier via pgserver),
tsc clean, `npm run build` compiles. Base = main @ 295a623.

| Requirement | Implementation | File (anchor) | Test | Runtime | Remaining |
|---|---|---|---|---|---|
| Bare OFS never "promoter cash-out" | pending-lane ladder | components/ipo/IpoCard.tsx (Phase-7 OFS repair block) | test_evidence_and_filters (5 OFS tests) | UI: pending vm_verify §5 post-merge | — |
| OFS negative needs RHP evidence | insight→fj0→pending ladder | IpoCard.tsx (stIns ladder) | test_ofs_negative_requires_structure_evidence | same | — |
| Strengths ≠ negative heading | "…and in its favour" divider | IpoCard.tsx render | test_strengths_divided… | same | — |
| SME/<₹200cr excluded, NULL visible | one WHERE rule ×3 feeds | ipo-command, ipo, live-preopen routes | 4 filter tests + SQL executes | DB: CONFIRMED (query runs on pg fixture) | — |
| SBI exact-key joins | normalized equality ×6 + ×1 | ipo-command, live-preopen | test_sbi_join_is_exact_key_not_fuzzy | same | — |
| OFS fair-value weight unchanged | −0.08 untouched | lib/fair-value.ts:47 | test_quantitative_ofs_weight_unchanged | — | — |
| Provenance store | ipo_insights + fan-out (no excerpt, no row; supersede) | schema_sync.py, insights_fanout.py, rhp_sonnet_store.py | test_provenance_pr_a (10, real-pg supersede) | DB: NOT_VERIFIED until post-merge pipeline | run pipeline, re-run vm_verify |
| Checksum invalidation | pdf_sha256 at store; NULL = legacy/stale | rhp_sonnet_store.py; vm_verify PARTIAL flag | test_vm_verify_flags…, test_store_script_persists… | VM: baseline showed the stale class | fingerprint-skip pre-call = follow-up (rhp_sonnet already skips done bases) |
| Four states end-to-end | stage_state lib + writers + vm_verify + Live chip | lib/stage_state.py; fetch/sonnet-store/haiku; live-preopen | test_phase7_stage_live (real-pg attempts/backoff) | DB: NOT_VERIFIED until first run | — |
| Retry: bounded, per-IPO isolation | next_retry_at gates only itself | fetch_new_rhps target NOT EXISTS | test_fetch_honors_backoff… | same | — |
| One orchestrator | run_ipo_pipeline_lean.py remains the single cron path | crontab (runbook) | test_no_dead_pipeline_steps | VM: CONFIRMED (74 steps/36h baseline) | — |
| $3/IPO + $0.50 caps | pre-existing (rhp_auto, sbi_haiku) | _scripts/rhp_auto.py, sbi_haiku_extract.py | existing cap tests | VM: CONFIRMED ($0.044 hand run) | per-IPO ledger view = follow-up |
| Layer C readiness gate | research_ready/_missing server-attested; UI chip | live-preopen route; ipo2 page | test_live_preopen_attests…, test_live_ui_shows… | UI: NOT_VERIFIED until listing morning | watch SBIFUNDS |
| Fair-value gating | inputs-missing ⇒ unavailable (blocks readiness) | live-preopen researchMissing; fair-value lib | test_live_preopen_attests… | — | — |
| SBI text in UI | full SBI section + exact pending sentence | IpoCard.tsx SBI block | test_sbi_section_renders… | UI: NOT_VERIFIED until deploy | — |
| RHP text in UI | quoted-evidence list + badges | IpoCard.tsx | test_rhp_evidence_list…, test_quoted_badge… | same | — |
| RHP over-match fix | target hygiene + matcher tighten + prune + persist-on-success | fetch_new_rhps.py | test_phase5 (7) | VM: NOT_VERIFIED until next fetch run | expect 0 SUSPECT dirs |
| Nightly failures | journal DDL (pnl_pct/outcome/thesis); Haiku preflight + Win-path fix | schema_sync.py; sbi_haiku_extract.py | journal DDL proven on real pg | VM: hand-run green 2026-07-21 | cron run confirm |
| vm_verify tooling | 5-state, 5-column, discovery-driven, exit-1 criticals | _scripts/vm_verify.py | test_vm_verify (10) | VM: CONFIRMED (baseline run, exit 0) | re-run post-merge |
| Docs authority | contract §9-11; UI_EVIDENCE_CONTRACT; runbook; this audit; PROVENANCE_DESIGN folded | docs/ | test_docs_contract | — | — |

## Overlap/duplication check
One provenance schema (schema_sync), one stage lib, one normalization per
matcher family, one eligibility rule text reused verbatim ×3. No competing
contract docs (PROVENANCE_DESIGN folded). No earlier fix overwritten —
regression tests for Phases 1-7 all green at head.

## Security audit (2026-07-21)
- `npm audit`: 11 → **9 moderate** after `npm audit fix` (lockfile-only).
  Remaining 9 = `postcss<8.5.10` + `uuid` via `apollo-server-*` inside
  `stock-nse-india` (transitive; no direct import of apollo; `--force` is
  breaking — deferred with owner sign-off, not hidden).
- `pip-audit` (sandbox env, best-effort): urllib3 2.6.3 → advisories
  PYSEC-2026-141/142, fix 2.7.0. VM: `venv/bin/pip install -U urllib3`.
- ESLint: repo baseline 129 pre-existing problems (untouched — unrelated
  cleanup is out of scope pre-listing); **my changed files: 2 errors were
  mine, fixed**; the rest on those files pre-date this PR.
- Secrets: `.env*` untracked ✓. **Found & redacted at HEAD**: a real
  password (`Ashrith@2820` / URL-encoded variant) in 4 _archive scripts,
  including `SCREENER_PASSWORD`. **Owner action: rotate the Screener.in
  password and the local Postgres password** — git history retains them.

## Load/perf (owner targets: p95<200ms, err<0.1%)
NOT_VERIFIED by design from this environment: driving load would wake Neon
and burn the Cloudflare request budget. Delivered `_scripts/loadtest_k6.js`
(PC-run): asserts p95<200ms, err<0.1%, and **x-cache ≠ MISS** so the test
itself proves Neon stayed asleep. Zero-idle is test-proven instead:
STALE-path 0-query (test_A2b), KV keys on every hot read (A3 allow-list
down to market/global, ipo, playbook).
