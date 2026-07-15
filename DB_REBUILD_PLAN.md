# AACapital — Clean-DB Rebuild Plan (PARKED — execute when IPOMatrix is the reliable spine)

**Status:** Not now. Trigger = IPOMatrix JWT/JSON flowing reliably nightly for ≥2 weeks
with clean subscription + anchor data. Until then, the 2-line scraper fix + one dedupe
handles the only current problem (Kusumgar twin). This plan sits ready.

## Why wait for IPOMatrix
The whole point of a clean rebuild is to START clean. IPOMatrix is the cleanest source
(private JWT API → structured JSON, already filled 396 IPOs). Seeding the new schema from
it means no scraped twins/suffixes get inherited. Rebuilding while Chittorgarh scraping is
the primary source would just copy today's mess into a new DB.

## Design principles (the rules you asked for — baked into the schema, not hoped for)
1. **No duplicates, ever** — UNIQUE constraint on a normalized key so twins are IMPOSSIBLE
   at the DB level (an insert of "Kusumgar Ltd. LT" when "Kusumgar Ltd." exists → rejected,
   not duplicated).
2. **Strong-key identity** — ISIN as primary identity where available (globally unique),
   normalized company_name as fallback. Never fuzzy.
3. **One source of truth per column** — every field has ONE owning source (below). No
   column filled by two scrapers racing each other.
4. **Fill-empty-only enrichment** — secondary sources COALESCE into nulls only, never
   overwrite a strong-source value.
5. **Clean flow** — raw scrape → normalized staging → validated consolidated. The app only
   ever reads the validated layer.

## Target schema (from IPO_BUSINESS_REQUIREMENTS.md)
Three layers, not one sprawling table:

**Layer 1 — `ipo_master` (identity, immutable per IPO)**
  isin (PK where available) · company_name_normalized (UNIQUE) · company_name_display ·
  nse_symbol · listing_date · issue_size_cr · price_band_low/high
  → Source: IPOMatrix issue-details (primary), Chittorgarh (fallback, normalized before insert)

**Layer 2 — `ipo_signals` (the computed edges, refreshed nightly)**
  isin (FK) · ipo_score · score_band · verdict · why_trade/caution/avoid ·
  gmp_day_before_pct/max/min · anchor_count · ofs_pct · final_qib/nii/retail ·
  peer_median_pe · ipo_pe · fair_value · fair_mos
  → Source: ipo_score.py + compute_verdicts.py + compute_flags.py (computed, never scraped)

**Layer 3 — `ipo_rhp` (forensic read, one row per IPO)**
  isin (FK) · verdict · quality_gate · margin_of_safety · flag booleans · full_json
  → Source: rhp_sonnet_store.py (Claude Sonnet, unchanged)

Plus keep as-is (they're clean, high-volume, not the problem):
  price_candles · delivery_data · market_regimes · ipo_daily_levels

## Source→column ownership map (the "which source fills what" you asked for)
| Column group          | Primary source        | Fallback         | Rule            |
|-----------------------|-----------------------|------------------|-----------------|
| identity (isin/name)  | IPOMatrix issue-details | Chittorgarh    | normalize first |
| subscription (QIB/NII)| IPOMatrix             | Chittorgarh scrape | strong-key join |
| anchors               | IPOMatrix anchors     | —                | IPOMatrix only  |
| GMP                   | GMP scrape            | —                | day-before is the signal |
| RHP forensic          | rhp_sonnet_store      | —                | Sonnet only     |
| price/volume          | Kite/NSE bhavcopy     | —                | unchanged       |
| peer PE / notes       | SBI notes             | —                | peer_ps not pe  |

## Migration steps (when triggered)
1. New Neon PROJECT (not branch) — clean namespace
2. Create the 3-layer schema with all UNIQUE/FK constraints
3. Seed ipo_master from IPOMatrix (clean identities, no twins)
4. Backfill price_candles/delivery/regimes via COPY from old project (they're clean)
5. Re-run the compute scripts to fill ipo_signals fresh
6. Re-run RHP store to fill ipo_rhp
7. Point ONE env var (DATABASE_URL) at new project in a staging deploy
8. Verify every route returns data (the 9 API keys) on staging
9. Cut over prod env var · keep old project 30 days as rollback
10. Drop old project only after 30 clean days

## Guardrails
- Every step SELECT-previewed before write (your standing rule)
- Old project stays as the rollback parachute for 30 days minimum
- One env var switch = one cutover point (not "repoint everything")
- Staging verify BEFORE prod cutover
