> ARCHIVED DOCUMENT
>
> This file is retained for historical reference only.
> It is not an implementation specification.
> Current product rules are defined in:
> `docs/specifications/AACAPITAL_PRODUCT_CONTRACT.md`

# AACapital — Target Architecture (evidence-first)

Written 2026-07-18 from the repo, not memory. Every claim below has a command
that reproduces it. Purpose: get from "equity platform with an IPO app inside"
to "simple, data-light IPO app" WITHOUT breaking what works.

---

## 1. TRUTH: what exists today (measured, not guessed)

| Fact | Evidence |
|---|---|
| `ipo_intelligence` has **230 distinct columns** referenced in code | `grep -rhoE "i\.[a-z_]+" _scripts app/api \| sort -u \| wc -l` |
| **113 file-references to 12 abandoned 1500-stock tables** | per-table grep, §4 below |
| The **live app reads only 6 IPO tables** | `grep -rhoE "FROM ([a-z_]+)" app/api/**/*.ts` |
| `ipo_consolidated` is the app's PRIMARY read (7 routes) | same |
| `ipo_intelligence` is read by only **1 route** — it is a STAGING table | same |
| RHP extraction dedupes by content SHA256 (no double-billing) | `rhp_sonnet.py` GUARDRAIL G |
| SBI Haiku has spent **$0.000 lifetime / 0 attempts** | `sbi_haiku_run_log` |

**The single most important finding:** the 230-column table is a *staging* surface
that the app barely reads. The app's real contract is `ipo_consolidated`. That
means we can clean the staging layer aggressively without touching the UI.

---

## 2. APPROVED SOURCES (owner-locked, 2026-07-18)

NSE · BSE · SEBI · Zerodha · IPOMatrix · Chittorgarh · Screener.
Nothing else enters the system.

**Commodity (INGEST — never rebuild):** issue details, price band, dates,
anchors, subscription, GMP, peer P/E, financials. IPOMatrix + Chittorgarh cover
~99% of this, cleaner than any bespoke scraper we can maintain.

**Moat (BUILD — nobody free provides it):**
1. **RHP governance forensics** (Sonnet on the prospectus) — auditor
   qualifications, SEBI actions, related-party, numbers integrity, concentration.
2. **Backtested win rates by factor** — "30+ anchors = 77%, n=X, era-consistent".
   Brokers publish ratings; we publish evidence.
3. **Exit discipline** (lock8/trail12) — nobody tells you when to sell.
4. **Owner's hard filters** — <₹200cr ruled out, SME excluded.

If a feature is not in the moat list, it should be a paste from a vendor, not a
pipeline we maintain.

---

## 3. TARGET DATA MODEL (6 tables + ops)

| Table | Role | Fed by | Read by |
|---|---|---|---|
| `ipo_master` | identity + issue facts (one row/IPO) | IPOMatrix, Chittorgarh, NSE | everything |
| `ipo_research` | RHP forensics + SBI note extraction | Sonnet, Haiku | Command |
| `ipo_scores` | ipo_score, quality_score, verdict, FV | our computes | Command, Live |
| `ipo_live` | listing-day ticks + pre-open book | Zerodha, NSE | Live, Journey |
| `ipo_outcomes` | listing gap, d10, d30 closes | price_candles | backtests only |
| `price_candles` | daily OHLC (already clean) | Zerodha | Journey, backtests |
| ops: `job_runs`, `pipeline_steps`, `pipeline_failures` | observability | pipeline | Settings |

**Everything else is archived.** No new table without a business case in
docs/specifications/IPO_BUSINESS_REQUIREMENTS.md.

---

## 4. THE ARCHIVE LIST (1500-stock residue — move, don't delete)

| Table | Files referencing | Why it exists | Action |
|---|---|---|---|
| stock_fundamentals | 16 | old equity screener | archive |
| delivery_data | 13 | secondary market | archive |
| **market_regimes** | **13** | **regime KILLED by owner** | archive |
| technical_signals | 12 | technicals, dropped | archive |
| management_commentary | 11 | secondary | archive |
| company_master | 10 | 1500-stock universe | archive |
| institutional_large_deals | 10 | secondary | archive |
| shareholding_history | 9 | secondary | archive |
| annual_financials | 9 | secondary | archive |
| mf_scheme_holdings | 5 | secondary | archive |
| distraction_log | 3 | **3 ROUTES READ IT — check first** | verify |
| stock_quality_flags | 2 | 1500-stock screen | archive |

**Rule: scripts move to `_scripts/archive/`, tables stay in the DB untouched.**
Nothing is dropped. If a screen breaks, `git revert` restores in one command.

---

## 5. MIGRATION PATH (phased, each reversible, app never breaks)

**Phase 0 — freeze the contract (no change).**
Snapshot exactly which tables/columns the app reads. That list is the invariant;
smoke_probe already enforces it (66 route-referenced columns across 5 tables).

**Phase 1 — archive dead scripts (zero risk).**
Move the ~113 legacy-table scripts to `_scripts/archive/`. They are not in cron
and not imported by lean. Verify: full test suite + tsc still green.

**Phase 2 — retire dead cron/compute paths.**
Anything writing only to archived tables comes out of the pipeline. Verify:
StepBoard shows fewer steps, all green.

**Phase 3 — screen consolidation (8 tabs → 3).**
Command (decide) · Live (execute) · Journey (hold/exit). The other 5 tabs are the
main consumers of legacy tables — retiring them removes the last reads.

**Phase 4 — schema slimming (LAST, only after 1-3 prove stable).**
Views with clean names over existing tables → routes point at views → unused
columns retired. Views mean the app never sees a rename.

---

## 6. WHAT WE FIX BEFORE ANY CLEANUP (correctness first)

1. **Dead MID-gap weight** — `ipo_score.py` still awards +2 for a factor the
   business doc declares DEAD (collapsed to coin-flip on clean data).
2. **₹200cr junk floor not enforced** — spec says "ruled out, don't touch";
   code only labels it AVOID and still shows it.
3. **SBI Haiku never runs** — filters on `i.close_date`; the route uses
   `c.ipo_close_date`. Suspected missing column → query throws → 0 attempts.
4. **Fuzzy SBI join** — `company ILIKE first-word` violates the strong-key rule
   and is why notes attach to some IPOs and not others.

**A smaller codebase computing the wrong number is worse than a big one
computing the right number. Correctness first, then size.**

---

## 7. ROLLBACK
Every phase is one `git revert`. Tables are never dropped. Archived scripts keep
full content under `_scripts/archive/`. If anything breaks: revert, re-run
smoke_probe, confirm the 66-column contract holds.

---

## 8. CLEANUP STATUS (folded in from CLEANUP_PROGRESS.md, 2026-07-18)

The "IPO-only, no equity residue" sweep is essentially complete. Delivered via:
- **#232** — dead `/api` fetches removed; orphan equity routes + hook, 53 equity/MF
  scripts archived; 2 dead pipeline steps removed; root hygiene. (Phases A–E)
- **#233 / #234** (parallel session) — 10 dead routes, `/today` page + today-screen,
  11 orphan components archived.
- **#235** — production deploy fix (lazy DB client; build no longer needs DATABASE_URL).
- **#236** — 3 parked planning docs archived.
- **this MR** — equity multibagger `.ts` engines + `sync-signals-to-neon.ts` archived
  (the last `.ts` residue); `similarity:multibagger` npm-script removed.

Every change moved to `_archive/` (nothing deleted); each has a fail-first guard test.

**Open (owner):** reconcile the #233-vs-directive contradiction on `ipo/monitor`
(kept by #233) vs `drhp`/`memo`/`tape` (archived by #233). **Separate lane
(correctness chat):** ₹200cr junk-floor exclusion, fuzzy `ILIKE` write-joins.
