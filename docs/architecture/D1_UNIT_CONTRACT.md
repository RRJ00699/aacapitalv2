# D1 source-to-normalized unit contract

**Blocking rule:** a row with an anomaly is reported to `migration_quarantine`; migration never guesses, rescales, or turns missing values into zero. Values in D1 have units in their column names or an explicit `unit` column. IPO Matrix `*_amt_cr` is known in current code to sometimes contain raw rupees, so its historical magnitude heuristic is not accepted as proof for bulk migration.

| Source | Source field | Raw example | Meaning | Raw unit | Normalized unit | Validation |
|---|---|---:|---|---|---|---|
| NSE | price band lower/upper | `95`, `100` | offer range | ₹/share | `band_lo_rs`, `band_hi_rs` ₹/share | non-negative; low ≤ high; compare face value |
| NSE | final issue price | `100` | allotment price | ₹/share | `issue_price_rs` | within band when all present |
| NSE/RHP | face value | `10` | nominal value | ₹/share | `face_value_rs` | >0; band below 0.5× face quarantined |
| NSE | lot size | `150` | minimum lot | shares | `lot_size_shares` | positive integer |
| NSE/RHP | issue/fresh/OFS amount | `500.25` | issue components | ₹ crore | `*_cr` | ≥0; components reconcile within max(₹1cr, 2%) or quarantine |
| IPO Matrix | `ttl_fresh_issue_amt_cr`, `ttl_ofs_amt_cr` | `11961618350.29` | issue component | UNKNOWN per record (key can hold ₹) | ₹ crore only after source-specific proof | magnitude/unit evidence required; Shreeji-like values quarantine |
| IPO Matrix | `market_cap.at_offer_price` / `kpi.market_cap_cr` | field survey required | market cap | `SOURCE_GAP` until surveyed | `market_cap_cr` | must exceed zero; cross-check price × post shares |
| NSE | reservation shares/% | `1500000`, `35` | category allocation | shares / percent | `shares_reserved`, `reservation_pct` | shares integer ≥0; percent 0–100; totals tolerance documented per issue |
| NSE | bid shares / no. of times | `6000000`, `4` | demand | shares / x | `shares_bid`, `subscription_x` | ≥0; missing remains NULL; if both shares exist recompute and compare |
| IPO Matrix | subscription summary | `23.4` | final subscription | x | `subscription_x` | ≥0; zero is retained only when explicitly observed |
| RHP/IPOMatrix | revenue/income/EBITDA/PAT/net worth/reserves/debt/assets/cash | field survey required | period accounts | ₹ or ₹ lakh/crore as document labels | `*_cr` | document label mandatory; no magnitude guessing; accounting cross-checks reported |
| RHP | EPS/NAV | `12.40` | per-share metric | ₹/share | metric `rs_per_share` | basis/period required |
| RHP/calculation | PE/PB/debt-equity | `18.2` | ratio | x | metric `x` | ≥0; calculated rows carry version |
| RHP/calculation | ROE/ROCE/RoNW/margins/CAGR | `14.5` | percentage | percent, not fraction | metric `pct` | plausible range reported; values outside -100–1000 quarantined pending evidence |
| Anchor report | shares/price/amount/% | `100000`, `100`, `1`, `2.5` | allocation row | shares, ₹/share, ₹ crore, percent | explicit respective columns | shares×price/1e7 ≈ amount; percent 0–100 |
| Kite | OHLC | `101.25` | traded price | ₹/share | `*_rs` | low ≤ open/close ≤ high; all >0 |
| Kite | volume | `10000` | traded volume | shares | `volume_shares` | integer ≥0 |
| NSE pre-open | quantities/IEQ | `10000` | order/equilibrium quantity | shares | `*_qty_shares`, `ieq_shares` | integer ≥0; Tier-A raw payload retained |
| GMP provider | GMP | `25` | unofficial premium | ₹/share | `gmp_rs` | source/time required; never authoritative |
| Derived | fair value/MoS | `90–110`, `-5` | valuation output | ₹/share, percent | explicit columns | inputs + engine version + missing inputs required |

## Anomaly codes

`BAND_REVERSED`, `PRICE_OUTSIDE_BAND`, `BAND_FACE_MAGNITUDE`, `ISSUE_COMPONENT_MISMATCH`, `NEGATIVE_MONEY`, `PERCENT_RANGE`, `OHLC_INVALID`, `UNIT_UNPROVEN`, `IDENTITY_COLLISION`, and `MALFORMED_SOURCE`. `tools/d1_migration.validate_issue` implements the issue gate. Tolerance exceptions require an evidence reference; they are never silent repairs.
