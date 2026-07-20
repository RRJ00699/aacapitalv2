/**
 * watchlist.ts
 * AACapital top 200 tracked universe — Indian equities.
 * Covers: Capital Goods, Defence, EMS, Water, Specialty Chemicals,
 *         Hospitals, Diagnostics, NBFC, Infra, Consumer, IT Midcap
 *
 * Edit this file to add/remove symbols. All loaders and extractors
 * reference this list automatically.
 */

export const WATCHLIST_200: string[] = [
  // ── Capital Goods & Engineering ──────────────────────────────────
  'ABB', 'SIEMENS', 'BHEL', 'BEL', 'HAL', 'BEML',
  'CUMMINSIND', 'THERMAX', 'AIAENG', 'GRINDWELL',
  'KAYNES', 'SYRMA', 'AVALON', 'ZENTEC', 'IDEAFORGE',
  'DATAPATTNS', 'MTAR', 'MTARTECH', 'PARAS',

  // ── Water & Environment ───────────────────────────────────────────
  'WABAG', 'WABAGLTD', 'IONEXCHANG', 'PNCINFRA',

  // ── Defence & Aerospace ───────────────────────────────────────────
  'COCHINSHIP', 'MAZAGON', 'GRSE', 'MIDHANI',
  'ASTRA', 'ZENTEC', 'PARAS', 'DYNAMATECH',

  // ── EMS / Electronics Manufacturing ──────────────────────────────
  'NETWEB', 'DIXON', 'AMBER', 'PGEL', 'VISI',

  // ── Specialty Chemicals ───────────────────────────────────────────
  'PIIND', 'NAVINFLUOR', 'FLUOROCHEM', 'CLEAN', 'AAVAS',
  'TATACHEM', 'DEEPAKNTR', 'LXCHEM', 'FINEORG',
  'ALKYLAMINE', 'BALRAMCHIN', 'ATUL',

  // ── Hospitals & Healthcare ────────────────────────────────────────
  'APOLLOHOSP', 'MAXHEALTH', 'FORTIS', 'RAINBOW',
  'KRSNAA', 'VIJAYA', 'HEALTHCARE', 'MEDANTA',

  // ── Diagnostics & Pharma ─────────────────────────────────────────
  'METROPOLIS', 'LALPATHLAB', 'THYROCARE',
  'SUNPHARMA', 'DRREDDY', 'CIPLA', 'ALKEM',
  'IPCALAB', 'GRANULES', 'SUVEN', 'SEQUENT',

  // ── NBFC & Fintech ────────────────────────────────────────────────
  'BAJFINANCE', 'BAJAJFINSV', 'CHOLAFIN', 'MUTHOOTFIN',
  'MANAPPURAM', 'CREDITACC', 'SPANDANA', 'IIFL',
  'PNBHOUSING', 'HOMEFIRST', 'APTUS',

  // ── Banks (select midcap) ─────────────────────────────────────────
  'FEDERALBNK', 'SOUTHBANK', 'KARURVYSYA',
  'DCBBANK', 'RBLBANK', 'EQUITASBNK',

  // ── IT Midcap ─────────────────────────────────────────────────────
  'PERSISTENT', 'COFORGE', 'LTIM', 'MPHASIS',
  'KPITTECH', 'TATAELXSI', 'CYIENT', 'BIRLASOFT',
  'MASTEK', 'HEXAWARE', 'ZENSAR',

  // ── Infrastructure & Construction ─────────────────────────────────
  'KNRCON', 'HGINFRA', 'GPPL', 'ASHOKA',
  'IRB', 'GASFIN', 'NCC', 'PNCINFRA',
  'JKCEMENT', 'RAMCOCEM', 'HEIDELBERG',

  // ── Consumer & Retail ─────────────────────────────────────────────
  'DMART', 'TRENT', 'VSTIND', 'CAMPUS',
  'MANYAVAR', 'VEDANT', 'RELAXO', 'BATA',
  'TITAN', 'KAJARIACER', 'CERA',

  // ── Renewable Energy ──────────────────────────────────────────────
  'SUZLON', 'INOXWIND', 'GREENKO', 'NTPC',
  'CESC', 'TORNTPOWER', 'ADANIGREEN',

  // ── Real Estate ───────────────────────────────────────────────────
  'ANANTRAJ', 'SOBHA', 'MAHLIFE', 'GODREJPROP',
  'BRIGADE', 'PHOENIXLTD',

  // ── Metals & Mining ───────────────────────────────────────────────
  'GRAVITA', 'HINDZINC', 'NMDC', 'MOIL',
  'NALCO', 'RATNAMANI',

  // ── Logistics & Supply Chain ──────────────────────────────────────
  'DELHIVERY', 'BLUEDART', 'MAHLOG', 'GATI',
  'ALLCARGO', 'CONCOR',

  // ── Auto & Auto Ancillary ─────────────────────────────────────────
  'MOTHERSON', 'SUNDRMFAST', 'SCHAEFFLER',
  'EXIDEIND', 'AMARA', 'BOSCHLTD',
  'MINDAIND', 'SUBROS',

  // ── Telecom & Media ───────────────────────────────────────────────
  'INDIAMART', 'JUSTDIAL', 'ZOMATO', 'NYKAA',

  // ── Miscellaneous / Multibagger Watchlist ─────────────────────────
  'ELID', 'INOX', 'GENESYS', 'CARTRADE',
  'EASEMYTRIP', 'IRCTC', 'RVNL', 'RAILTEL',
  'CDSL', 'BSE', 'MCX', 'CAMS',
];

export const WATCHLIST_CORE_50: string[] = WATCHLIST_200.slice(0, 50);
