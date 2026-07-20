Status: CURRENT
Authority: docs/AACAPITAL_PRODUCT_CONTRACT.md
Last verified against code: 2026-07-21
Verified commit: PR #265 head

# PIPELINE RUNTIME AUDIT

Runtime truth comes from `vm_verify.py` runs, never from code existing.

## Baseline (owner-run, 2026-07-21 01:25 IST, exit 0)

- VM TZ `Asia/Kolkata` confirmed; crontab times are true IST; every entry
  dual-rendered IST + US-Central.
- Cron execution CONFIRMED: 74 pipeline_steps in 36h; logs all fresh.
- Recurring failures (root-caused & fixed in this PR): `compute journal
  outcomes` (missing pnl_pct/outcome/thesis DDL) · `SBI Haiku extract`
  (hand-run 2026-07-21 = green, $0.044, 4 notes; 5 SKIPs were Windows
  backslash pdf_path rows — normalize+repair shipped). `freshness monitor` /
  `date sanity gate` entries are alert-gates by design (reclassify later).
- Two production-discovered IPOs (both list 2026-07-21): SBIFUNDS (₹11,693cr,
  129 anchors, 100% OFS, SBI note parsed, peerPE NULL ⇒ fair value
  unavailable ⇒ Live shows RESEARCH INCOMPLETE) · Alpine Texworld (₹126cr ⇒
  hard-excluded from feeds by the LOCKED <₹200cr rule; visible in the audit
  matrix by design).
- Stale-verdict class observed live: Sonnet verdicts in DB with zero PDF +
  zero summary ⇒ now machine-marked (NULL pdf_sha256 ⇒ PARTIAL legacy/stale).
- RHP dirs: all EMPTY + 6 SUSPECT junk slugs ⇒ target-hygiene + matcher +
  prune fixes shipped.

## Incident 2026-07-21 · deploy raced the schema run (RESOLVED in code)

#265 deployed a route querying `ipo_insights` while the DDL ships via
`schema_sync.py`; the owner's pipeline attempt hit the RETIRED stub (exit 1)
so schema never synced → screen degraded (`relation "ipo_insights" does not
exist`). Immediate recovery: Admin → Schema sync. Permanent fix: the route
self-heals the table on the rebuild path with DDL kept byte-equivalent to
schema_sync by test, plus an EXECUTED reproduction test (fresh DB without
the table → self-heal → real cards query → green). Audit gap admitted: SQL
was validated against a schema that already contained the table; deploy-
order is now part of the test surface.

## Post-merge expectations (next vm_verify run)

§2 journal & Haiku green or self-naming stderr · §3 Sonnet rows labeled
legacy/stale until a NEW RHP lands end-to-end (then: fan-out rows, UI badges)
· §4 zero SUSPECT dirs after the next fetch · §5 UI payload live (env vars
added 2026-07-21) with OFS-pending line attested for SBIFUNDS.

## NOT_VERIFIED (genuine environment limits — the exact owner commands)

| Item | Why | One command |
|---|---|---|
| Post-merge pipeline behavior | needs deploy + VM run | Admin→Sync, then `cd /root/aac && set -a && . ./.env && set +a && venv/bin/python _scripts/run_ipo_pipeline_lean.py` (off-window) |
| Full runtime matrix refresh | same | the vm_verify one-liner (runbook) |
| Live-day UI states | needs a listing morning | watch /dashboard/ipo2 Live 09:00–10:00 IST |
| p95/error-rate under load | would wake Neon + spend request budget | `k6 run -e BASE=https://aacapitalprivatelimited.com _scripts/loadtest_k6.js` from PC (asserts x-cache≠MISS: Neon stays asleep) |
| Cross-browser/mobile UAT | human eyes | Chrome/Safari/Firefox + one mobile: cards render, SBI section, pending lanes, Live chip, journey chart |
