# IPO Matrix field coverage contract

**Status: VERIFIED against repository code; archive coverage remains UNKNOWN.** The repository contains no raw IPO Matrix fixture/archive. The only executable shape evidence is `_scripts/ipomatrix_ingest.py` and `pipeline/ipomatrix_fallback.py`; therefore a field not read there is not claimed to exist. Before normalization, `tools/d1_migration.py` inventories bytes, hashes, JSON validity and IDs. A real field survey remains blocked until the owner supplies the immutable archive.

Legend: `PIPELINE_GAP` means no current forward producer was found; `SOURCE_GAP` means the approved forward source/path cannot be proven from repository evidence. “Required” means required to reproduce the investor information contract, not necessarily a UI field today.

| IPO Matrix field/section (observed key where proven) | Needed by AACapital? | Forward official source | Existing producer | New producer required? | Normalized destination | Recovery path |
|---|---:|---|---|---|---|---|
| About Company | Yes | SEBI RHP/DRHP | RHP document/extraction lane (narrative shape not proven) | `PIPELINE_GAP` structured profile mapper | `company_profile.business_description` | Tier-A PDF → re-extract |
| Strengths | Yes | SEBI RHP; SBI as external opinion | RHP/SBI extraction | No schema work; producer mapping must be verified | `research_findings(category=strength)` | Tier-A document → versioned extraction |
| Promoters | Yes | SEBI RHP/DRHP | RHP extraction (exact output unproven) | `PIPELINE_GAP` normalized mapper | `company_profile.promoters_json`; evidence in `source_facts` | PDF → re-extract |
| Selling Shareholders | Yes | SEBI RHP | No proven normalized producer | `PIPELINE_GAP` | `source_facts` initially; normalized ownership extension after field survey | PDF; preserve evidence |
| Objects of Issue | Yes | SEBI RHP | No proven row producer | `PIPELINE_GAP` | `objects_of_issue` | PDF → re-extract rows |
| Lead Managers (`issue_details.lead_managers`) | Yes | NSE issue information / RHP | `ipomatrix_ingest.extract` bootstrap; NSE issue producer | Verify row/evidence mapper | `ipo_issue.brlm_json` | NSE refetch or PDF |
| Registrar (`issue_details.registrar.name`) | Yes | NSE issue information / RHP | IPO Matrix and NSE issue producer | No | `ipo_issue.registrar_name` | NSE refetch or PDF |
| Issue Overview (`issue_details`) | Yes | NSE | IPO Matrix bootstrap and `pipeline/nse_fetch.py` | D1 mapper | `ipo_issue` | NSE refetch; bootstrap raw archive |
| Schedule | Yes | NSE | NSE issue producer | D1 mapper | `ipo_issue.*_date` | NSE refetch |
| Pre/Post holding (`pre_post_holding`) | Yes | SEBI RHP | IPO Matrix mapper only proves promoter post | `PIPELINE_GAP` complete categories | `ownership` | PDF → re-extract |
| Market Cap (`market_cap.at_offer_price`, `kpi.market_cap_cr`) | Yes | NSE/RHP arithmetic inputs | IPO Matrix bootstrap | Official/recomputed mapper | `ipo_issue.market_cap_cr`; metric provenance | NSE/RHP → recompute when safe |
| Reservation | Yes | NSE | `pipeline/nse_fetch.py` subscription shape; reservation rows not proven | `PIPELINE_GAP` row producer | `reservations` | NSE response/raw capture |
| Subscription (`subscription.summary.{qib,nii,rii,total}`) | Yes | NSE | NSE producer and IPO Matrix final bootstrap | D1 category mapper | `subscription_snapshots` | NSE raw/refetch where available |
| Anchor summary (`anchor`) | Yes | NSE Anchor Allocation Report | IPO Matrix bootstrap | `PIPELINE_GAP` official report parser | `anchor_summary` | Tier-A report → parse |
| Anchor investors (`anchor.investors[].investor_name`) | Yes | NSE Anchor Allocation Report | IPO Matrix names-only producer | `PIPELINE_GAP` row-preserving parser | `anchor_allocations` | Tier-A report → parse |
| GMP | Context only | `SOURCE_GAP` (non-official market intelligence) | InvestorGain scraper exists | D1 time-series mapper | `gmp_observations` (`is_official=0`) | Source observations; not authoritative |
| Financial statements (nested list located by fallback mapper) | Yes | SEBI RHP/DRHP | RHP writer; IPO Matrix fallback | D1 migration mapper | `financial_statements` period/basis rows | Tier-A PDF/raw JSON → parse |
| KPIs (`kpi.pe_ratio`, `price_to_book`, `roe`, `ronw`, `roce`, margins, NAV) | Yes where used | RHP; otherwise recompute | IPO Matrix mapper/RHP findings | Versioned mapper/calculator | sourced values in `source_facts`; computed values in `valuation_runs` | Sourced evidence or recompute |
| pre/post EPS (`kpi.eps_pre`, `eps_post`) | Yes | SEBI RHP | IPO Matrix mapper | Official extraction/recompute mapper | sourced `source_facts`; calculation inputs/output in `valuation_runs` | PDF/raw JSON |
| pre/post PE (`kpi.pe_ratio`, `post_pe_ratio`) | Yes | RHP inputs + issue price | IPO Matrix mapper | Versioned calculation producer | sourced `source_facts`; computed `valuation_runs` | Recompute from preserved inputs |
| Peer Comparison (`peer_analysis`) | Yes | SEBI RHP; SBI commentary separately | IPO Matrix stored opaque JSON; RHP writer evidence | `PIPELINE_GAP` row mapper | `peer_comparisons`; opinions in `research_findings` | PDF/raw JSON → parse |
| Documents | Yes | SEBI/NSE/SBI | RHP and SBI fetch lanes | Anchor report fetch gap | `documents` metadata; bytes later in R2 | Tier-A source bytes by SHA256 |
| Company sector/industry/incorporation/office/website | Yes | SEBI RHP | `SOURCE_GAP` exact IPO Matrix keys; no proven mapper | `PIPELINE_GAP` | `company_profile` | PDF → re-extract |
| Issue size/fresh/OFS (`ttl_*_amt_cr`) | Yes | NSE/RHP | IPO Matrix mapper contains magnitude heuristic; NSE producer | Unit-gated D1 mapper | `ipo_issue.*_cr` | NSE/RHP/raw; quarantine anomaly |
| Listing exchange prices (`listing.exchanges[]`) | Yes | Kite | IPO Matrix bootstrap; Kite producer | D1 mapper | `listing_observations`; `market_bars` | Kite history where available |

## Blocking survey output

Run `python tools/d1_migration.py --ipomatrix PATH --survey artifacts/ipomatrix-field-survey.json` before loading. The survey contains JSON path, occurrence count, primitive type frequencies, null frequency, and representative values—never an inferred unit. `files=0` is not acceptance: it is an explicit archive blocker. No key absent from the proven code paths above may be mapped until the field survey records its real path and examples and an owner-reviewed identity path map is supplied.
