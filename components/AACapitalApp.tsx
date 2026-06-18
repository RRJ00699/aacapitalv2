"use client"
import { TrendingUp, BarChart2, Zap, Home, RefreshCw, Activity, Briefcase, Settings2, Users } from "lucide-react"
import {
  calcConviction, calcEV, allocPct,
  ConvictionPanel, CapitalGoalEngine, ModeTracker, CompoundTab,
  WealthBuilderTab, MarketEnginePanel, BacktestingLab,
  StocksUploadPanel, PostListingScanner, CapProtBadge,
  SubscriptionTracker
} from "./features/sprint-features"
import { SettingsTab } from "./features/settings-tab"
import { PortfolioTab } from "./features/portfolio-tab"
import { IpoCalendar } from "./features/ipo-calendar"
import { AnchorLockupTracker }  from "./features/anchor-lockup"
import { GlobalMacroScreen } from "./features/market-global-screen"
import { CommandCenter } from "./features/command-center"
import { StockResearchWorkspace } from "./features/stock-research-workspace"
import { InvestmentCommandCenter } from "./features/investment-command-center"
import { SectorRotationScreen } from "./features/sector-rotation"
import { TradeJournalScreen, CapitalDeploymentOptimizer, MultibaggerDiscoveryEngine } from "./features/sprint8-features"
import { DNALabScreen } from "./features/dna-lab"
import { EarningsScreen } from "./features/earnings-screen"
import { StockSearch } from "./features/stock-search"
import { CronMonitor } from "./features/cron-monitor"
import { IntelligenceDashboard } from "./features/intelligence-dashboard"
import { TodayScreen } from "./features/today-screen"
import { TechnicalScreener } from "./features/technical-screener"
import { MultibaggerDiscovery } from "./features/multibagger-discovery"
import { PortfolioDoctor } from "./features/portfolio-doctor"
import { IpoCommandCenter } from "./ipo/IpoCommandCenter"
import React, { useState, useEffect, useCallback, useRef } from "react";
/* eslint-disable */

/* ═══════════════════════════════════════════════════════════════
   AACapital — Institutional Research Platform
   Tabs: Stocks · Screener · IPO · Calculator
   Live prices · Tier 1A/1/2/Avoid · Guru screener
   Nightly stored procedure logic · All frameworks encoded
   ═══════════════════════════════════════════════════════════════ */

// ─── STOCK MASTER LIST (symbol + company name) ───────────────────
const NSE_STOCKS = [
  {sym:"RELIANCE",name:"Reliance Industries"},{sym:"HDFCBANK",name:"HDFC Bank"},
  {sym:"ICICIBANK",name:"ICICI Bank"},{sym:"INFY",name:"Infosys"},
  {sym:"TCS",name:"Tata Consultancy Services"},{sym:"WIPRO",name:"Wipro"},
  {sym:"AXISBANK",name:"Axis Bank"},{sym:"KOTAKBANK",name:"Kotak Mahindra Bank"},
  {sym:"LT",name:"Larsen & Toubro"},{sym:"BAJFINANCE",name:"Bajaj Finance"},
  {sym:"SUNPHARMA",name:"Sun Pharmaceutical"},{sym:"TITAN",name:"Titan Company"},
  {sym:"ASIANPAINT",name:"Asian Paints"},{sym:"PIDILITIND",name:"Pidilite Industries"},
  {sym:"TATAMOTORS",name:"Tata Motors"},{sym:"POWERGRID",name:"Power Grid Corp"},
  {sym:"NTPC",name:"NTPC"},{sym:"COALINDIA",name:"Coal India"},
  {sym:"ONGC",name:"ONGC"},{sym:"BPCL",name:"BPCL"},
  {sym:"DRREDDY",name:"Dr Reddy's"},{sym:"CIPLA",name:"Cipla"},
  {sym:"DIVISLAB",name:"Divi's Laboratories"},{sym:"ADANIPORTS",name:"Adani Ports"},
  {sym:"HCLTECH",name:"HCL Technologies"},{sym:"BAJAJFINSV",name:"Bajaj Finserv"},
  {sym:"SBILIFE",name:"SBI Life Insurance"},{sym:"HDFCLIFE",name:"HDFC Life"},
  {sym:"NESTLEIND",name:"Nestle India"},{sym:"BRITANNIA",name:"Britannia Industries"},
  {sym:"HINDUNILVR",name:"Hindustan Unilever"},{sym:"ITC",name:"ITC"},
  {sym:"MARUTI",name:"Maruti Suzuki"},{sym:"HEROMOTOCO",name:"Hero MotoCorp"},
  {sym:"TATASTEEL",name:"Tata Steel"},{sym:"JSWSTEEL",name:"JSW Steel"},
  {sym:"HINDALCO",name:"Hindalco"},{sym:"ULTRACEMCO",name:"UltraTech Cement"},
  {sym:"GRASIM",name:"Grasim Industries"},{sym:"ADANIENT",name:"Adani Enterprises"},
  {sym:"BHARTIARTL",name:"Bharti Airtel"},{sym:"TECHM",name:"Tech Mahindra"},
  {sym:"LTIM",name:"LTIMindtree"},{sym:"INDUSINDBK",name:"IndusInd Bank"},
  {sym:"SBIN",name:"State Bank of India"},{sym:"EICHERMOT",name:"Eicher Motors"},
  {sym:"M&M",name:"Mahindra & Mahindra"},{sym:"BAJAJ-AUTO",name:"Bajaj Auto"},
  {sym:"TATACONSUM",name:"Tata Consumer Products"},{sym:"APOLLOHOSP",name:"Apollo Hospitals"},
  // Nifty Next 50
  {sym:"ABCAPITAL",name:"Aditya Birla Capital"},{sym:"HBLENGINE",name:"HBL Engineering"},
  {sym:"BEL",name:"Bharat Electronics"},{sym:"HAL",name:"Hindustan Aeronautics"},
  {sym:"GRSE",name:"Garden Reach Shipbuilders"},{sym:"BDL",name:"Bharat Dynamics"},
  {sym:"MAZDOCK",name:"Mazagon Dock"},{sym:"COCHINSHIP",name:"Cochin Shipyard"},
  {sym:"SIEMENS",name:"Siemens India"},{sym:"ABB",name:"ABB India"},
  {sym:"CUMMINSIND",name:"Cummins India"},{sym:"THERMAX",name:"Thermax"},
  {sym:"HAVELLS",name:"Havells India"},{sym:"CROMPTON",name:"Crompton Greaves Consumer"},
  {sym:"VOLTAS",name:"Voltas"},{sym:"TRENT",name:"Trent"},
  {sym:"PAGEIND",name:"Page Industries"},{sym:"MUTHOOTFIN",name:"Muthoot Finance"},
  {sym:"CHOLAFIN",name:"Cholamandalam Finance"},{sym:"MARICO",name:"Marico"},
  {sym:"DABUR",name:"Dabur India"},{sym:"COLPAL",name:"Colgate-Palmolive India"},
  {sym:"GODREJCP",name:"Godrej Consumer Products"},{sym:"VBL",name:"Varun Beverages"},
  {sym:"RADICO",name:"Radico Khaitan"},{sym:"TATAPOWER",name:"Tata Power"},
  {sym:"TORNTPOWER",name:"Torrent Power"},{sym:"ADANIGREEN",name:"Adani Green Energy"},
  {sym:"GAIL",name:"GAIL India"},{sym:"ZOMATO",name:"Zomato"},
  {sym:"NYKAA",name:"Nykaa"},{sym:"DMART",name:"Avenue Supermarts"},
  {sym:"BAJAJHFL",name:"Bajaj Housing Finance"},{sym:"SHREECEM",name:"Shree Cement"},
  {sym:"AMBUJACEM",name:"Ambuja Cements"},{sym:"LUPIN",name:"Lupin"},
  {sym:"BIOCON",name:"Biocon"},{sym:"AUROPHARMA",name:"Aurobindo Pharma"},
  {sym:"ALKEM",name:"Alkem Laboratories"},{sym:"IPCA",name:"IPCA Laboratories"},
  {sym:"CONCOR",name:"Container Corp"},{sym:"IRCTC",name:"IRCTC"},
  {sym:"RECLTD",name:"REC"},{sym:"PFC",name:"Power Finance Corp"},
  {sym:"IREDA",name:"IREDA"},{sym:"NHPC",name:"NHPC"},{sym:"SJVN",name:"SJVN"},
  // Midcap
  {sym:"POLYCAB",name:"Polycab India"},{sym:"PERSISTENT",name:"Persistent Systems"},
  {sym:"MPHASIS",name:"Mphasis"},{sym:"COFORGE",name:"Coforge"},
  {sym:"KAYNES",name:"Kaynes Technology"},{sym:"SYRMA",name:"Syrma SGS Technology"},
  {sym:"DATAPATTERNS",name:"Data Patterns India"},{sym:"DIXON",name:"Dixon Technologies"},
  {sym:"AMBER",name:"Amber Enterprises"},{sym:"IDEAFORGE",name:"ideaForge Technology"},
  {sym:"CAMS",name:"CAMS"},{sym:"CDSL",name:"CDSL"},
  {sym:"MCX",name:"MCX"},{sym:"BSE",name:"BSE"},
  {sym:"AAVAS",name:"Aavas Financiers"},{sym:"HOMEFIRST",name:"Home First Finance"},
  {sym:"APTUS",name:"Aptus Value Housing"},{sym:"CANFINHOME",name:"Can Fin Homes"},
  {sym:"ENDURANCE",name:"Endurance Technologies"},{sym:"MOTHERSON",name:"Samvardhana Motherson"},
  {sym:"BALKRISHNA",name:"Balkrishna Industries"},{sym:"APOLLOTYRE",name:"Apollo Tyres"},
  {sym:"CEATLTD",name:"CEAT"},{sym:"MINDA",name:"Uno Minda"},
  {sym:"APLAPOLLO",name:"APL Apollo Tubes"},{sym:"RATNAMANI",name:"Ratnamani Metals"},
  {sym:"GRINDWELL",name:"Grindwell Norton"},{sym:"TIMKEN",name:"Timken India"},
  {sym:"SCHAEFFLER",name:"Schaeffler India"},{sym:"ELGIEQUIP",name:"Elgi Equipments"},
  {sym:"DEEPAKNTR",name:"Deepak Nitrite"},{sym:"AARTI",name:"Aarti Industries"},
  {sym:"VINATI",name:"Vinati Organics"},{sym:"SRF",name:"SRF"},
  {sym:"NAVINFLUOR",name:"Navin Fluorine"},{sym:"PIIND",name:"PI Industries"},
  {sym:"COROMANDEL",name:"Coromandel International"},{sym:"KPRMILL",name:"KPR Mill"},
  {sym:"ZYDUSLIFE",name:"Zydus Lifesciences"},{sym:"TATAELXSI",name:"Tata Elxsi"},
  {sym:"KPITTECH",name:"KPIT Technologies"},{sym:"CYIENT",name:"Cyient"},
  {sym:"INTELLECT",name:"Intellect Design Arena"},{sym:"INDIAMART",name:"IndiaMart"},
  {sym:"LICI",name:"LIC India"},{sym:"MANAPPURAM",name:"Manappuram Finance"},
  {sym:"CREDITACC",name:"CreditAccess Grameen"},{sym:"UJJIVAN",name:"Ujjivan SFB"},
  // Smallcap
  {sym:"TITAGARH",name:"Titagarh Rail Systems"},{sym:"RVNL",name:"Rail Vikas Nigam"},
  {sym:"IRCON",name:"IRCON International"},{sym:"RAILTEL",name:"RailTel Corp"},
  {sym:"NBCC",name:"NBCC India"},{sym:"HUDCO",name:"HUDCO"},
  {sym:"KNRCON",name:"KNR Constructions"},{sym:"HGINFRA",name:"H.G. Infra Engineering"},
  {sym:"ASTRAL",name:"Astral"},{sym:"SUPREMEIND",name:"Supreme Industries"},
  {sym:"FINOLEX",name:"Finolex Cables"},{sym:"KEI",name:"KEI Industries"},
  {sym:"BHARATFORG",name:"Bharat Forge"},{sym:"SUNDRMFAST",name:"Sundram Fasteners"},
  {sym:"CRAFTSMAN",name:"Craftsman Automation"},{sym:"KALYANKJIL",name:"Kalyan Jewellers"},
  {sym:"SENCO",name:"Senco Gold"},{sym:"VEDANT",name:"Vedant Fashions"},
  {sym:"METRO",name:"Metro Brands"},{sym:"BATA",name:"Bata India"},
  {sym:"TTKPRESTIG",name:"TTK Prestige"},{sym:"WONDERLA",name:"Wonderla Holidays"},
  {sym:"CHALET",name:"Chalet Hotels"},{sym:"TIINDIA",name:"Tube Investments"},
  {sym:"POONAWALLA",name:"Poonawalla Fincorp"},{sym:"JYOTHYLAB",name:"Jyothy Labs"},
  {sym:"EMAMILTD",name:"Emami"},{sym:"CLEAN",name:"Clean Science & Tech"},
  {sym:"AETHER",name:"Aether Industries"},{sym:"GHCL",name:"GHCL"},
  {sym:"DHANUKA",name:"Dhanuka Agritech"},{sym:"UPL",name:"UPL"},
  {sym:"SAIL",name:"Steel Authority of India"},{sym:"NMDC",name:"NMDC"},
  {sym:"BHEL",name:"BHEL"},{sym:"HPCL",name:"HPCL"},
  {sym:"GLENMARK",name:"Glenmark Pharma"},{sym:"GRANULES",name:"Granules India"},
  {sym:"NEULANDLAB",name:"Neuland Laboratories"},{sym:"ALKYLAMINE",name:"Alkyl Amines"},
  {sym:"SRF",name:"SRF"},{sym:"ATUL",name:"Atul"},
  {sym:"TATACHEM",name:"Tata Chemicals"},{sym:"VEDL",name:"Vedanta"},
  {sym:"NATIONALUM",name:"National Aluminium"},{sym:"HINDALCO",name:"Hindalco"},
  {sym:"IRFC",name:"Indian Railway Finance Corp"},{sym:"NSDL",name:"NSDL"},
  {sym:"PAYTM",name:"Paytm"},{sym:"DELHIVERY",name:"Delhivery"},
  {sym:"MAPMYINDIA",name:"MapMyIndia"},{sym:"JUSTDIAL",name:"Just Dial"},
  {sym:"LTTS",name:"L&T Technology Services"},{sym:"TATACOMM",name:"Tata Communications"},
  {sym:"RAYMOND",name:"Raymond"},{sym:"VGUARD",name:"V-Guard Industries"},
  {sym:"BLUESTAR",name:"Blue Star"},{sym:"SYMPHONY",name:"Symphony"},
  {sym:"MMFIN",name:"M&M Financial Services"},{sym:"LEMON",name:"Lemon Tree Hotels"},
  {sym:"MAHINDCIE",name:"Mahindra CIE"},{sym:"GABRIEL",name:"Gabriel India"},
  {sym:"SPANDANA",name:"Spandana Sphoorty"},{sym:"FUSION",name:"Fusion Micro Finance"},
  {sym:"GPPL",name:"Gujarat Pipavav Port"},{sym:"WELSPUNLIV",name:"Welspun Living"},
  {sym:"MASTEK",name:"Mastek"},{sym:"ROUTE",name:"Route Mobile"},
  {sym:"TANLA",name:"Tanla Platforms"},{sym:"BALRAMCHIN",name:"Balrampur Chini"},
  {sym:"TRIVENI",name:"Triveni Engineering"},{sym:"RENUKA",name:"Shree Renuka Sugars"},
  {sym:"DCMSHRIRAM",name:"DCM Shriram"},{sym:"VARDHMAN",name:"Vardhman Textiles"},
  {sym:"SHOPERSTOP",name:"Shoppers Stop"},{sym:"RELAXO",name:"Relaxo Footwears"},
  {sym:"VMART",name:"V-Mart Retail"},{sym:"CARTRADE",name:"CarTrade Tech"},
  {sym:"EASEMYTRIP",name:"EaseMyTrip"},{sym:"FSL",name:"Firstsource Solutions"},
  {sym:"WHIRLPOOL",name:"Whirlpool of India"},{sym:"VOLTAS",name:"Voltas"},
  {sym:"PETRONET",name:"Petronet LNG"},{sym:"SUNTV",name:"Sun TV Network"},
  {sym:"MOIL",name:"MOIL"},{sym:"CASTROLIND",name:"Castrol India"},
  {sym:"NOCIL",name:"NOCIL"},{sym:"GALAXYSURF",name:"Galaxy Surfactants"},
  {sym:"PIIND",name:"PI Industries"},{sym:"ELECON",name:"Elecon Engineering"},
  {sym:"ISGEC",name:"ISGEC Heavy Engineering"},{sym:"MAHSEAMLES",name:"Maharashtra Seamless"},
];

// ─── NSE UNIVERSE (screener runs over these) ──────────────────────
const UNIVERSE = [
  // Nifty 50
  "RELIANCE","HDFCBANK","ICICIBANK","INFY","TCS","WIPRO","AXISBANK","KOTAKBANK",
  "LT","BAJFINANCE","SUNPHARMA","TITAN","ASIANPAINT","PIDILITIND","POLYCAB",
  "TATAMOTORS","POWERGRID","NTPC","COALINDIA","ONGC","BPCL","DRREDDY","CIPLA",
  "DIVISLAB","ADANIPORTS","HCLTECH","BAJAJFINSV","SBILIFE","HDFCLIFE","NESTLEIND",
  "BRITANNIA","HINDUNILVR","ITC","MARUTI","BAJAJ-AUTO","HEROMOTOCO","M&M",
  "TATASTEEL","JSWSTEEL","HINDALCO","ULTRACEMCO","GRASIM","ADANIENT","BHARTIARTL",
  "TECHM","LTIM","INDUSINDBK","SBIN","EICHERMOT",
  // Nifty Next 50
  "ABCAPITAL","HBLENGINE","BEL","HAL","GRSE","BDL","MAZDOCK","COCHINSHIP",
  "SIEMENS","ABB","CUMMINSIND","THERMAX","HAVELLS","CROMPTON","VOLTAS","BLUESTAR",
  "TRENT","ABFRL","PAGEIND","MUTHOOTFIN","CHOLAFIN","BAJAJCON","MARICO","DABUR",
  "COLPAL","GODREJCP","EMAMILTD","VBL","RADICO","MCDOWELL","TATAPOWER","TORNTPOWER",
  "ADANIGREEN","ADANITRANS","GAIL","PETRONET","CONCOR","IRCTC","ZOMATO","NYKAA",
  "DMART","BAJAJHFL","SHREECEM","AMBUJACEM","AUROPHARMA","LUPIN","BIOCON","GLENMARK",
  "ALKEM","IPCA",
  // Nifty Midcap 150
  "PERSISTENT","MPHASIS","COFORGE","KAYNES","SYRMA","DATAPATTERNS","DIXON","AMBER",
  "IDEAFORGE","AVALON","AETHER","CLEAN","LICI","CAMS","CDSL","MCX","BSE","NSDL",
  "AAVAS","HOMEFIRST","APTUS","REPCO","CANFINHOME","CREDITACC","UJJIVAN","EQUITASBNK",
  "SURYODAY","FINOPB","VEDL","NATIONALUM","APLAPOLLO","WELCORP","RATNAMANI",
  "KALYANKJIL","SENCO","TITAN","ENDURANCE","MOTHERSON","BALKRISHNA","APOLLOTYRE",
  "CEATLTD","MINDA","FIEM","SUPRAJIT","SUNDRMFAST","SANSERA","CRAFTSMAN",
  "LAXMIMACH","GRINDWELL","TIMKEN","SCHAEFFLER","NRB","SKFINDIA","ELGIEQUIP",
  "JYOTHYLAB","TATACONSUM","ZYDUSLIFE","ABBOTINDIA","GLAXO","PFIZER","SANOFI",
  "IOLCP","NAVINFLUOR","DEEPAKNTR","AARTI","VINATI","ALKYLAMINE","GALAXYSURF",
  "PIDILITIND","SRF","ATUL","NOCIL","GHCL","TATACHEM","GNFC","GSFC","COROMANDEL",
  "PIIND","DHANUKA","RALLIS","BAYER","SUMICHEM","BAYERCROP","UPL","INSECTICID",
  "KPRMILL","VARDHMAN","PAGEIND","GOKEX","WELSPUNLIV","RAYMOND","VEDANT","MANYAVAR",
  "SHOPERSTOP","METRO","BATA","RELAXO","VMART","TRENT","NYKAA","MAPMYINDIA",
  "CARTRADE","EASEMYTRIP","IRFC","RVNL","RAILTEL","IRCON","NBCC","HUDCO","NHPC",
  "SJVN","RECLTD","PFC","IREDA","GPPL","MAHSEAMLES","MANAPPURAM","POONAWALLA",
  // Nifty Smallcap 250 sample
  "HBLENGINE","GRSE","BDL","COCHINSHIP","MAZDOCK","ELECON","TEXRAIL","TITAGARH",
  "KERNEX","IRCON","RVNL","NBCC","AHLUCONT","CAPACITE","KNR","HGINFRA","PNC",
  "SADBHAV","DILIPBUILDCON","GPPL","ESABINDIA","ISGEC","THERMAX","GMRINFRA",
  "ADANIPORTS","SUNTV","ZEEL","NETWORK18","TV18BRDCST","JAGRAN","DBCORP","HMVL",
  "ASTRAL","SUPREMEIND","NILKAMAL","GHCL","ORIENTELEC","HAVELLS","VGUARD","FINOLEX",
  "POLYCAB","KEI","HLEGLAS","ASAHIINDIA","GAEL","KRBL","LT","LTTS","LTIM",
  "INTELLECT","KPITTECH","TATAELXSI","CYIENT","MASTEK","NIITTECH","RATEGAIN",
  "ROUTE","TANLA","INDIAMART","JUSTDIAL","MATRIMONY","INFO","FSL","SASKEN",
  // MSCI India smallcap/midcap additions
  "SUNDARAM","WABCOINDIA","GABRIEL","JAMNAUTO","BHARATFORG","RAMKRISHN",
  "MANINFRA","ITI","BHEL","SAIL","MOIL","NMDC","GMDC","HINDCOPPER","MTNL",
  "BPCL","MRPL","HPCL","CPCL","CHENNPETRO","GULFOILLUB","CASTROLIND",
  "AARTIDRUGS","DISHMAN","GRANULES","SOLARA","SHILPAMED","POLYMED","SUVENPHAR",
  "NEULANDLAB","HIKAL","BALRAMCHIN","DHAMPUR","RENUKA","TRIVENI","BAJAJHIND",
  "DCMSHRIRAM","DHARAMSI","TTKPRESTIG","HAWKINS","WONDERLA","CHALET","LEMON",
  "MAHINDCIE","TIINDIA","MMFIN","CREDITACC","SPANDANA","AROHAN","FUSION",
].filter((v,i,a)=>a.indexOf(v)===i); // deduplicate

// ─── GURU FILTER DEFINITIONS ──────────────────────────────────────
const GURU_FILTERS = {
  buffett: {
    name:"Warren Buffett", emoji:"🏦", color:"#1d4ed8", bg:"#eff6ff",
    desc:"Quality moat businesses. High ROCE, owner-operator, low debt, durable competitive advantage.",
    criteria: d => d.roce>=18 && d.roe>=15 && d.debt<1.0 && d.promoter>=50 && d.pledge<10 && d.pat3>=12,
    sort: d => d.roce*0.4 + d.roe*0.3 + (d.promoter/10)*0.3,
    badges:["ROCE ≥18%","ROE ≥15%","D/E <1x","Promoter ≥50%","Pledge <10%"],
  },
  lynch: {
    name:"Peter Lynch", emoji:"📈", color:"#059669", bg:"#f0fdf4",
    desc:"Growth at reasonable price. 20%+ growers, PEG below 2, small-mid caps. Early multibagger setup.",
    criteria: d => d.rev3>=15 && d.pat3>=15 && d.peg<2.0 && d.mcap<50000,
    sort: d => d.rev3*0.35 + d.pat3*0.35 + (2.5-Math.min(d.peg,2.5))*10*0.3,
    badges:["Rev CAGR ≥15%","PAT CAGR ≥15%","PEG <2x","MCap <₹50kCr"],
  },
  kutumba: {
    name:"Kutumbarao", emoji:"🏛️", color:"#92400e", bg:"#fffbeb",
    desc:"Essential-need businesses. Pricing power, debt-free, clean promoter, industry tailwind.",
    criteria: d => d.roce>=15 && d.debt<0.8 && d.promoter>=55 && d.pledge<5 && d.roe>=15,
    sort: d => d.roce*0.3 + (d.promoter/10)*0.3 + d.roe*0.2 + (1-Math.min(d.debt,1))*10*0.2,
    badges:["ROCE ≥15%","D/E <0.8x","Promoter ≥55%","Pledge <5%","ROE ≥15%"],
  },
  graham: {
    name:"Benjamin Graham", emoji:"📖", color:"#6d28d9", bg:"#faf5ff",
    desc:"Margin of safety. Low PE, low PB, strong balance sheet. Buy ₹1 of value for 50 paise.",
    criteria: d => d.pe<30 && d.pb<4 && d.debt<0.7 && d.piotroski>=6 && d.altman>2.5,
    sort: d => (50-Math.min(d.pe,50))*0.3 + (6-Math.min(d.pb,6))*5*0.3 + d.piotroski*5*0.2 + d.altman*5*0.2,
    badges:["P/E <30x","P/B <4x","D/E <0.7x","Piotroski ≥6","Altman Z >2.5"],
  },
  mayer: {
    name:"Chris Mayer 100x", emoji:"🚀", color:"#7c3aed", bg:"#faf5ff",
    desc:"100-bagger setup: small-mid cap, owner-operator, high ROCE, 20%+ growth, reinvestment runway.",
    criteria: d => d.mcap<25000 && d.promoter>=55 && d.roce>=20 && d.rev3>=20 && d.pat3>=18,
    sort: d => d.mbScore,
    badges:["MCap <₹25kCr","Promoter ≥55%","ROCE ≥20%","Rev CAGR ≥20%","PAT ≥18%"],
  },
  agrawal: {
    name:"Raamdeo QGLP", emoji:"🇮🇳", color:"#dc2626", bg:"#fef2f2",
    desc:"Quality + Growth + Longevity + Price. High quality Indian businesses at reasonable valuation.",
    criteria: d => d.overall>=65 && d.roce>=18 && d.rev3>=15 && d.pe<50 && d.pledge<8,
    sort: d => d.overall*0.5 + d.roce*0.3 + d.rev3*0.2,
    badges:["Score ≥65","ROCE ≥18%","Rev CAGR ≥15%","P/E <50x","Pledge <8%"],
  },
  buyzone: {
    name:"In Buy Zone Now", emoji:"🎯", color:"#16a34a", bg:"#f0fdf4",
    desc:"Stocks currently in their trading zone. Updated at 8:45 AM and 4:15 PM IST nightly.",
    criteria: d => d.buyZone>=61 && d.cmp>d.ema200,
    sort: d => d.buyZone,
    badges:["Buy Zone ≥61","Above 200 EMA","FII/DII buying","Delivery >avg","RSI 40-70"],
  },
};

// ─── NIGHTLY SQL PROCEDURES (shown in modal) ──────────────────────
const BACKEND_SQL = `-- ═══════════════════════════════════════════════════
-- AACapital Nightly Stored Procedures
-- Deploy: Postgres on Railway / Supabase / AWS RDS
-- Cron:   Vercel Cron Jobs (vercel.json)
-- ═══════════════════════════════════════════════════

-- SCHEMA
CREATE TABLE daily_scores (
  symbol TEXT,
  date DATE DEFAULT CURRENT_DATE,
  cmp NUMERIC, pe NUMERIC, pb NUMERIC,
  roe NUMERIC, roce NUMERIC,
  rev3 NUMERIC, pat3 NUMERIC,
  debt NUMERIC, promoter NUMERIC, pledge NUMERIC,
  rsi NUMERIC, delivery_pct NUMERIC,
  fii_now NUMERIC, dii_now NUMERIC,
  buy_zone_score INTEGER,
  overall_score INTEGER,
  mb_score INTEGER,
  tier TEXT, verdict TEXT,
  sl NUMERIC, t1 NUMERIC, t2 NUMERIC, t3 NUMERIC,
  PRIMARY KEY (symbol, date)
);

CREATE TABLE guru_signals (
  symbol TEXT,
  date DATE DEFAULT CURRENT_DATE,
  buffett_pass BOOLEAN,
  lynch_pass BOOLEAN,
  kutumba_pass BOOLEAN,
  graham_pass BOOLEAN,
  mayer_pass BOOLEAN,
  agrawal_pass BOOLEAN,
  in_buy_zone BOOLEAN,
  PRIMARY KEY (symbol, date)
);

-- NIGHTLY PROCEDURE (runs at 8:45 AM + 4:15 PM IST)
CREATE OR REPLACE PROCEDURE run_nightly_scores()
LANGUAGE plpgsql AS $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT * FROM daily_scores
           WHERE date = CURRENT_DATE LOOP

    -- Guru signal computation
    INSERT INTO guru_signals (symbol, date,
      buffett_pass, lynch_pass, kutumba_pass,
      graham_pass, mayer_pass, agrawal_pass, in_buy_zone)
    VALUES (
      r.symbol, CURRENT_DATE,
      (r.roce>=18 AND r.roe>=15 AND r.debt<1.0 AND r.promoter>=50 AND r.pledge<10),
      (r.rev3>=15 AND r.pat3>=15 AND r.pe/NULLIF(r.rev3,0)<2.0),
      (r.roce>=15 AND r.debt<0.8 AND r.promoter>=55 AND r.pledge<5 AND r.roe>=15),
      (r.pe<30 AND r.pb<4 AND r.debt<0.7),
      (r.roce>=20 AND r.promoter>=55 AND r.rev3>=20 AND r.pat3>=18),
      (r.overall_score>=65 AND r.roce>=18 AND r.rev3>=15 AND r.pe<50),
      (r.buy_zone_score>=61)
    )
    ON CONFLICT (symbol, date) DO UPDATE SET
      buffett_pass=EXCLUDED.buffett_pass,
      lynch_pass=EXCLUDED.lynch_pass,
      kutumba_pass=EXCLUDED.kutumba_pass,
      graham_pass=EXCLUDED.graham_pass,
      mayer_pass=EXCLUDED.mayer_pass,
      agrawal_pass=EXCLUDED.agrawal_pass,
      in_buy_zone=EXCLUDED.in_buy_zone;

  END LOOP;
END; $$;

-- QUERY: Buffett stocks in buy zone today
SELECT s.symbol, d.cmp, d.roce, d.roe,
       d.buy_zone_score, d.tier, d.t1, d.sl
FROM guru_signals g
JOIN daily_scores d USING (symbol)
WHERE g.date = CURRENT_DATE
  AND g.buffett_pass = TRUE
  AND g.in_buy_zone = TRUE
ORDER BY d.buy_zone_score DESC;

-- QUERY: Lynch multibaggers
SELECT symbol, cmp, rev3, pat3, buy_zone_score
FROM guru_signals g JOIN daily_scores d USING (symbol)
WHERE g.date=CURRENT_DATE AND g.lynch_pass=TRUE
ORDER BY d.mb_score DESC LIMIT 20;

-- Vercel Cron (add to vercel.json):
-- "crons": [
--   { "path": "/api/cron/morning", "schedule": "15 3 * * 1-5" },
--   { "path": "/api/cron/evening", "schedule": "45 10 * * 1-5" }
-- ]
-- (8:45 AM IST = 3:15 AM UTC | 4:15 PM IST = 10:45 AM UTC)

-- ══════════════════════════════════════════════
-- WEBHOOK ALERTS: Telegram / WhatsApp
-- ══════════════════════════════════════════════

-- /api/cron/morning.ts (Next.js Vercel handler)
-- const db = new Pool({ connectionString: process.env.DATABASE_URL });
--
-- export default async function handler(req, res) {
--   await db.query('CALL run_nightly_scores()');
--
--   // Fetch buy zone + guru signals
--   const { rows } = await db.query(\`
--     SELECT symbol, cmp, buy_zone_score, tier, t1, sl
--     FROM guru_signals g JOIN daily_scores d USING(symbol)
--     WHERE g.date = CURRENT_DATE
--       AND g.in_buy_zone = TRUE
--       AND (g.buffett_pass OR g.agrawal_pass)
--     ORDER BY buy_zone_score DESC LIMIT 5
--   \`);
--
--   // Send Telegram alert
--   if (rows.length > 0) {
--     const msg = rows.map(r =>
--       \`🟢 \${r.symbol} | BZ:\${r.buy_zone_score} | ₹\${r.cmp} | T1:₹\${r.t1} | SL:₹\${r.sl}\`
--     ).join('\n');
--
--     await fetch(\`https://api.telegram.org/bot\${process.env.TELEGRAM_BOT_TOKEN}/sendMessage\`, {
--       method: 'POST',
--       headers: { 'Content-Type': 'application/json' },
--       body: JSON.stringify({
--         chat_id: process.env.TELEGRAM_CHAT_ID,
--         text: \`🚨 AACapital Morning Scan\n\${msg}\`,
--         parse_mode: 'Markdown'
--       })
--     });
--   }
--
--   // WhatsApp via Twilio (alternative)
--   // POST https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json
--   // From: whatsapp:+14155238886 (Twilio sandbox)
--   // To:   whatsapp:+91XXXXXXXXXX
--   // Body: same msg string
--
--   res.json({ ok: true, alerts: rows.length });
-- }
--
-- ENV VARIABLES to set in Vercel dashboard:
--   DATABASE_URL = postgres://...
--   TELEGRAM_BOT_TOKEN = your bot token from @BotFather
--   TELEGRAM_CHAT_ID = your personal chat ID
--   TWILIO_ACCOUNT_SID = optional for WhatsApp
--   TWILIO_AUTH_TOKEN = optional for WhatsApp`

// ─── ANCHOR SCORING MODEL (2Y IPO history) ───────────────────────
const ANCHOR_SCORES = {
  "BlackRock":10,"Vanguard":10,"GIC Singapore":9.8,"Temasek":9.8,
  "Fidelity":9.7,"Nomura":9.4,"Morgan Stanley":9.4,"Goldman Sachs":9.4,
  "Abu Dhabi":9.6,"SBI MF":9.2,"HDFC MF":9.0,"ICICI Pru MF":8.8,
  "Mirae Asset":8.7,"Franklin Templeton":8.8,"Nippon MF":8.5,
  "Axis MF":8.3,"DSP MF":8.2,"Kotak MF":8.0,"UTI MF":8.0,
  "Invesco":8.4,"LIC MF":7.5,"Tata MF":7.3,"Aditya Birla MF":7.2,
  "Motilal Oswal MF":7.5,"Steadview Capital":7.8,"Tiger Global":7.5,
  "Accel":6.5,"Matrix Partners":6.8,"Sequoia India":7.2,
};

const anchorScore = (anchors) => {
  if (!anchors?.length) return 5;
  const scores = anchors.map(a => {
    const m = Object.entries(ANCHOR_SCORES).find(([k]) => a.toLowerCase().includes(k.toLowerCase().split(" ")[0]));
    return m ? m[1] : 6.0;
  });
  const avg = scores.reduce((a,b)=>a+b,0)/scores.length;
  const hasGlobal = anchors.some(a => ["BlackRock","Vanguard","GIC","Fidelity","Nomura","Morgan","Goldman","Abu Dhabi","Temasek"].some(g=>a.includes(g)));
  return Math.min(10, +(avg+(hasGlobal?0.4:0)).toFixed(1));
};

const predictGain = (aScore, qibX) => {
  const q = parseFloat(qibX)||10;
  return Math.max(-10, Math.min(200, +((aScore-5)*8 + Math.min(q,200)*0.15).toFixed(0)));
};

// ─── IPO PIPELINE ─────────────────────────────────────────────────
const DEFAULT_IPOS = [
  // Recently listed — June 2026
  {name:"CMR Green Technologies",sector:"Metals - Recycling",size:631,band:"₹182–192",listing:"10-Jun-2026",status:"LISTED",gmp:"+30%",qib:"—",hni:"—",retail:"—",anchor:[],drhp:true,ofsP:0},
  {name:"Hexagon Nutrition",sector:"FMCG / Nutrition",size:180,band:"₹42–45",listing:"12-Jun-2026",status:"LISTED",gmp:"+8%",qib:"—",hni:"—",retail:"—",anchor:[],drhp:false,ofsP:0},
  {name:"Onemi Technology (Kissht)",sector:"Fintech / NBFC",size:850,band:"₹162–171",listing:"08-May-2026",status:"LISTED",gmp:"+22%",qib:"—",hni:"—",retail:"—",anchor:[],drhp:true,ofsP:30},
  {name:"Powerica Limited",sector:"Power / Gensets",size:1200,band:"₹375–395",listing:"02-Apr-2026",status:"LISTED",gmp:"+15%",qib:"—",hni:"—",retail:"—",anchor:[],drhp:true,ofsP:20},
  {name:"Sai Parenterals",sector:"Pharma / CDMO",size:600,band:"₹372–392",listing:"02-Apr-2026",status:"LISTED",gmp:"+12%",qib:"—",hni:"—",retail:"—",anchor:[],drhp:true,ofsP:25},
  {name:"GSP Crop Science",sector:"Agrochemicals",size:400,band:"₹304–320",listing:"24-Mar-2026",status:"LISTED",gmp:"+18%",qib:"—",hni:"—",retail:"—",anchor:[],drhp:true,ofsP:15},
  {name:"Innovision Limited",sector:"IT Services",size:350,band:"₹494–519",listing:"23-Mar-2026",status:"LISTED",gmp:"+25%",qib:"—",hni:"—",retail:"—",anchor:[],drhp:true,ofsP:10},
];

const IPO_HISTORY = [
  {name:"Bajaj Housing Finance",anchor:["BlackRock","Mirae Asset","HDFC MF"],gain:114},
  {name:"Premier Energies",anchor:["BlackRock","GIC Singapore","Nomura"],gain:120},
  {name:"Waaree Energies",anchor:["GIC Singapore","Fidelity","SBI MF"],gain:70},
  {name:"Tata Technologies",anchor:["SBI MF","HDFC MF","BlackRock"],gain:140},
  {name:"Ola Electric",anchor:["SBI MF","HDFC MF","Fidelity"],gain:76},
  {name:"TBO Tek",anchor:["Goldman Sachs","Fidelity","Mirae Asset"],gain:55},
  {name:"IREDA",anchor:["SBI MF","LIC MF","UTI MF"],gain:56},
  {name:"Vibhor Steel",anchor:["Axis MF","LIC MF","DSP MF"],gain:194},
  {name:"Swiggy",anchor:["BlackRock","Fidelity","Nomura"],gain:7},
  {name:"Hyundai India",anchor:["BlackRock","GIC Singapore","Fidelity"],gain:-1.5},
  {name:"NTPC Green",anchor:["SBI MF","LIC MF","HDFC MF"],gain:3},
  {name:"Mankind Pharma",anchor:["BlackRock","Fidelity","Morgan Stanley"],gain:20},
];

// ─── TIER CLASSIFICATION ──────────────────────────────────────────
const classifyTier = (d) => {
  const flags=[], greens=[];
  // ── CRITICAL HARD STOPS ──
  if(d.pledge>15) flags.push({sev:"CRITICAL",msg:`Pledge ${d.pledge.toFixed(1)}% — HARD STOP: Margin-call spiral risk regardless of score`});
  if(d.promoter<40) flags.push({sev:"CRITICAL",msg:`Promoter ${d.promoter.toFixed(1)}% — dangerously low`});
  if(d.debt>2.0) flags.push({sev:"CRITICAL",msg:`D/E ${d.debt.toFixed(2)}x — balance sheet stress`});
  if(d.auditorResigned) flags.push({sev:"CRITICAL",msg:`Auditor Resignation — faster sell signal than Beneish. Exit immediately.`});
  if(d.beneish>-1.78) flags.push({sev:"HIGH",msg:`Beneish ${d.beneish.toFixed(2)} — earnings manipulation pattern`});
  if(d.altman<1.8) flags.push({sev:"HIGH",msg:`Altman Z ${d.altman.toFixed(2)} — financial distress territory`});
  if(d.fcfPatDivergence) flags.push({sev:"HIGH",msg:`PAT growing but CFO stagnant — non-cash profits, quality penalised`});
  if(d.rev3>20&&d.pat3<8) flags.push({sev:"HIGH",msg:"Revenue up but profits flat — margin compression"});
  if(d.emaExtended) flags.push({sev:"MEDIUM",msg:`CMP ${Number(d.emaExtPct).toFixed(1)}% above 20-EMA — Extended. Downgraded to Hold/Wait for retest.`});
  if(d.pledge>5&&d.pledge<=15) flags.push({sev:"MEDIUM",msg:`Pledge ${d.pledge.toFixed(1)}% — watch for further pledging`});
  if(d.promoter<50) flags.push({sev:"MEDIUM",msg:`Promoter ${d.promoter.toFixed(1)}% — below 50% comfort`});
  if(d.debt>1.0) flags.push({sev:"MEDIUM",msg:`D/E ${d.debt.toFixed(2)}x — elevated leverage`});
  if(d.pe>70) flags.push({sev:"MEDIUM",msg:`P/E ${d.pe.toFixed(0)}x — priced for perfection`});
  if(d.adtv<5) flags.push({sev:"MEDIUM",msg:`ADTV ₹${Number(d.adtv).toFixed(1)}Cr — illiquid. Building position will move price.`});
  if(d.deliverySpike) flags.push({sev:"INFO",msg:`Delivery spike ${Number(d.deliverySpikePct).toFixed(0)}% above 10D avg — Institutional block accumulation 🟢`});
  // ── GREEN FLAGS ──
  if(d.roce>=20) greens.push(`ROCE ${d.roce.toFixed(1)}%`);
  if(d.roe>=20) greens.push(`ROE ${d.roe.toFixed(1)}%`);
  if(d.rev3>=20) greens.push(`Rev CAGR ${d.rev3.toFixed(1)}%`);
  if(d.pledge<2) greens.push(`Zero pledge`);
  if(d.promoter>=60) greens.push(`Promoter ${d.promoter.toFixed(1)}%`);
  if(d.debt<0.5) greens.push(`Low debt ${d.debt.toFixed(2)}x`);
  if(d.piotroski>=7) greens.push(`Piotroski ${d.piotroski}/9`);
  if(d.fii&&d.fii[7]>d.fii[0]) greens.push(`FII accumulating`);
  if(d.topTierAuditor) greens.push(`Top-tier auditor`);
  if(d.adtv>=10) greens.push(`ADTV ₹${Number(d.adtv).toFixed(0)}Cr liquid`);
  const crits=flags.filter(f=>f.sev==="CRITICAL").length;
  const highs=flags.filter(f=>f.sev==="HIGH").length;
  const s=d.overall;
  if(d.pledge>15)
    return{tier:"HIGH_RISK",label:"🔴 High Risk / Speculative",color:"#dc2626",bg:"#fef2f2",border:"#fecaca",desc:"Pledge >15% — hard stop. Margin-call spiral risk overrides all other signals.",flags,greens};
  if(crits>=1||highs>=2||s<50)
    return{tier:"AVOID",label:"⛔ AVOID",color:"#dc2626",bg:"#fef2f2",border:"#fecaca",desc:"Hard eliminate. Critical red flags override any technical setup.",flags,greens};
  if(d.emaExtended&&s>=80)
    return{tier:"1A_WAIT",label:"🏆 1A — Wait/Retest",color:"#7c3aed",bg:"#faf5ff",border:"#e9d5ff",desc:"Elite fundamentals but extended >15% above 20-EMA. Wait for retest.",flags,greens};
  if(s>=80&&d.roce>=20&&d.promoter>=55&&d.pledge<5&&d.rev3>=15)
    return{tier:"1A",label:"🏆 Tier 1A — Elite",color:"#1d4ed8",bg:"#eff6ff",border:"#bfdbfe",desc:"Institutional grade. Full conviction buy on VCP+NR7 setup.",flags,greens};
  if(s>=65&&d.roce>=15&&d.promoter>=50&&d.pledge<10)
    return{tier:"1",label:"⭐ Tier 1 — Strong",color:"#059669",bg:"#f0fdf4",border:"#bbf7d0",desc:"Strong business. Buy on setup with conviction.",flags,greens};
  if(s>=50)
    return{tier:"2",label:"🟡 Tier 2 — Conditional",color:"#d97706",bg:"#fffbeb",border:"#fde68a",desc:"Decent business, 1-2 concerns. Trade only. Strict SL.",flags,greens};
  return{tier:"AVOID",label:"⛔ AVOID",color:"#dc2626",bg:"#fef2f2",border:"#fecaca",desc:"Below threshold.",flags,greens};
};

// ─── STOCK DATA ENGINE ────────────────────────────────────────────
const makeStock = (sym) => {
  const seed=sym.split("").reduce((a,c)=>a+c.charCodeAt(0),0);
  const r=(min,max,o=0)=>+(min+(((seed*17+o*31)%100)/100)*(max-min)).toFixed(2);
  const ri=(min,max,o=0)=>Math.round(r(min,max,o));
  const cmp=r(80,8500,1),pe=r(6,90,2),pb=r(0.6,15,3);
  const roe=r(6,52,4),roce=r(8,55,5);
  const rev3=r(8,42,6),pat3=r(10,55,7),debt=r(0.02,2.2,8);
  const promoter=r(38,79,9),pledge=r(0,20,10);
  const rsi=r(30,78,11),del=r(25,74,12);
  const ema20=+(cmp*r(0.93,1.05,13)).toFixed(0);
  const ema50=+(cmp*r(0.87,1.01,14)).toFixed(0);
  const ema200=+(cmp*r(0.76,0.96,15)).toFixed(0);
  const fii=Array.from({length:8},(_,i)=>+r(5,24,20+i));
  const dii=Array.from({length:8},(_,i)=>+r(3,18,30+i));
  const mf=Array.from({length:8},(_,i)=>+r(2,15,40+i));
  const rev=Array.from({length:8},(_,i)=>+r(400,9000,50+i));
  const pat=Array.from({length:8},(_,i)=>+r(40,1400,60+i));
  const fcf=Array.from({length:8},(_,i)=>+r(-80,900,70+i));
  const delH=Array.from({length:20},(_,i)=>+r(25,74,80+i));
  const qs=["Q1'24","Q2'24","Q3'24","Q4'24","Q1'25","Q2'25","Q3'25","Q4'25"];
  const mcap=+(cmp*r(150,90000,90)).toFixed(0);
  const piotroski=ri(3,9,91);
  const beneish=r(-3.8,-1.0,92);
  const altman=r(1.2,6.5,93);
  const evEb=r(5,38,94),peg=r(0.3,4.2,95);
  const opMarg=r(6,38,96),intCov=r(1.5,18,97);
  const pcr=r(0.4,1.8,98),adx=r(15,55,99);
  const gS=Math.min(10,Math.round((rev3>20?3:rev3>15?2:1)+(pat3>25?3:pat3>15?2:1)+4));
  const qS=Math.min(10,Math.round((roe>20?3:2)+(roce>20?3:2)+4));
  const govS=Math.min(10,Math.round((promoter>60?3:promoter>50?2:1)+(pledge<2?3:pledge<5?2:0)+4));
  const valS=Math.min(10,Math.round((pe<20?4:pe<35?3:pe<50?2:1)+(pb<3?3:pb<6?2:1)+3));
  const techS=Math.min(10,Math.round((rsi>50&&rsi<70?4:2)+(cmp>ema50?3:1)+3));
  const ownS=Math.min(10,Math.round((fii[7]>fii[0]?4:2)+(dii[7]>dii[0]?3:1)+3));
  const overall=Math.round(gS*2.5+qS*2.0+govS*2.0+valS*1.5+techS*1.0+ownS*1.0);
  const mbScore=Math.min(100,Math.round(
    (rev3>=20?14:rev3>=15?9:4)+(roe>=20?14:roe>=15?9:4)+
    (roce>=20?12:roce>=15?7:3)+(promoter>=55?11:promoter>=50?7:3)+
    (pledge<2?10:pledge<5?5:0)+(debt<0.5?10:debt<1?5:1)+
    (mcap<20000?10:mcap<50000?5:2)+(pat3>=20?10:pat3>=15?6:3)+
    (piotroski>=7?6:piotroski>=5?3:1)
  ));
  const buyZone=Math.min(100,
    (roe>20&&roce>20?20:0)+(fii[7]>fii[0]&&dii[7]>dii[0]?15:0)+
    (cmp>ema50&&cmp>ema200&&ema50>ema200?15:0)+
    (del>(delH.reduce((a,b)=>a+b,0)/20)?10:0)+
    (rev3>15&&pat3>15?10:0)+(promoter>60&&pledge<3?20:0)+
    (cmp>ema20&&del>55?15:0)+(rsi>50&&rsi<70?10:0)+
    (piotroski>7&&altman>3?10:0)+(fii[7]>fii[5]&&dii[7]>dii[5]&&del>50?15:0)
  );
  const verd=overall>=80?"STRONG BUY":overall>=70?"ACCUMULATE":overall>=60?"HOLD":overall>=50?"WATCHLIST":"AVOID";
  const verdC=overall>=80?"#16a34a":overall>=70?"#1d4ed8":overall>=60?"#d97706":overall>=50?"#ea580c":"#dc2626";
  const rr=(mn,mx,o=0)=>+(mn+(((seed*13+o*29)%100)/100)*(mx-mn)).toFixed(0);
  const cT=+rr(cmp*1.1,cmp*1.45,100);
  const bullT=+rr(cmp*1.25,cmp*1.6,101);
  const bearT=+rr(cmp*0.88,cmp*1.08,102);
  const analystCount=ri(6,30,103);
  const buyPct=ri(42,85,104);
  const holdPct=ri(8,32,105);
  const sellPct=Math.max(0,100-buyPct-holdPct);
  const brokers=[
    {name:"Motilal Oswal",target:+rr(cmp*1.08,cmp*1.5,110),rating:"Buy"},
    {name:"HDFC Securities",target:+rr(cmp*1.06,cmp*1.45,111),rating:"Buy"},
    {name:"Kotak Securities",target:+rr(cmp*1.04,cmp*1.42,112),rating:"Accumulate"},
    {name:"ICICI Direct",target:+rr(cmp*1.02,cmp*1.38,113),rating:buyPct>60?"Buy":"Hold"},
    {name:"Axis Capital",target:+rr(cmp*1.06,cmp*1.48,114),rating:"Buy"},
  ];
  const guruScores={
    buffett:Math.min(100,Math.round((roce>=20?25:15)+(roe>=20?20:10)+(debt<0.5?20:10)+(promoter>=55?20:10)+(pledge<5?15:5))),
    lynch:Math.min(100,Math.round((rev3>=20?20:12)+(pat3>=20?20:12)+(peg<1.5?25:15)+(mcap<20000?20:10)+(pat3>rev3*0.8?15:5))),
    graham:Math.min(100,Math.round((pe<20?25:pe<35?15:5)+(pb<2?25:15)+(debt<0.5?20:10)+(intCov>4?20:10))),
    agrawal:Math.min(100,Math.round((qS>=8?20:12)+(gS>=8?20:12)+(overall>=70?20:10)+(pe<35?20:10)+(roce>=20?20:10))),
    kutumba:Math.min(100,Math.round((roce>=15?20:10)+(promoter>=55?20:10)+(debt<0.8?20:10)+(roe>=18?20:10)+(rev3>=15?20:10))),
    mayer:Math.min(100,Math.round((promoter>=55?20:10)+(roe>=20?20:10)+(roce>=20?15:8)+(mcap<20000?15:5)+(rev3>=20?15:8)+(pat3>=20?15:8))),
    marks:Math.min(100,Math.round((debt<0.5?25:15)+(beneish<-1.78?25:10)+(intCov>5?20:10)+(altman>3?20:10)+(piotroski>=7?10:5))),
  };
  const {tier,label:tierLabel,color:tierColor,bg:tierBg,border:tierBorder,desc:tierDesc,flags,greens}=classifyTier({pledge,promoter,debt,beneish,altman,rev3,pat3,pe,roce,roe,piotroski,fii,overall,govS});
  const intVal=+(Math.sqrt(22.5*(cmp/pe)*(cmp/pb))).toFixed(0);
  const moS=+(((intVal-cmp)/Math.max(intVal,1))*100).toFixed(1);
  // ── NEW ENGINES ──────────────────────────────────────────────────
  // ADTV (30-day avg daily traded value in ₹Cr)
  const adtv=+(cmp*r(0.5,120,135)*r(0.1,0.8,136)).toFixed(1);
  const adtvFlag=adtv<5;
  // Delivery spike: today vs 10D avg
  const del10Avg=+(delH.slice(10,20).reduce((a,b)=>a+b,0)/10).toFixed(1);
  const deliverySpike=del>(del10Avg*1.5);
  const deliverySpikePct=+(del/del10Avg*100-100).toFixed(1);
  // EMA extension: how far CMP is above 20-EMA
  const emaExtPct=+(((cmp-ema20)/ema20)*100).toFixed(1);
  const emaExtended=emaExtPct>15;
  // Dynamic buy zone spread: penalise if extended
  const buyZoneAdj=emaExtended?Math.max(0,buyZone-20):buyZone;
  // FCF vs PAT divergence: PAT growing but FCF flat/negative
  const patGrowing=pat3>15;
  const fcfAvg=fcf.reduce((a,b)=>a+b,0)/fcf.length;
  const fcfPatDivergence=patGrowing&&fcfAvg<(pat[pat.length-1]*0.3);
  // Governance flags (simulated deterministically)
  const auditorResigned=(seed%7===0);
  const topTierAuditor=!auditorResigned&&(seed%3!==0);
  const cfoResigned=(seed%11===0);
  const rptRisk=(seed%5===0);
  const equityDilution=(seed%9===0);
  // RSI multi-timeframe
  const rsiW=+(rsi*r(0.88,1.12,140)).toFixed(1);  // weekly RSI proxy
  const rsiM=+(rsi*r(0.80,1.08,141)).toFixed(1);  // monthly RSI proxy
  const rsiAligned=rsi>55&&rsiW>55&&rsiM>60;
  // Smart money score
  const smartMoney=Math.min(100,Math.round(
    (fii[7]>fii[5]?25:fii[7]>fii[0]?15:5)+
    (dii[7]>dii[5]?20:dii[7]>dii[0]?12:4)+
    (del>del10Avg*1.3?20:del>del10Avg?10:3)+
    (deliverySpike?15:0)+
    (r(0,1,142)>0.6?20:8)  // block/bulk deal proxy
  ));
  // Governance risk score (0=clean, 100=dangerous)
  const govRisk=Math.min(100,Math.round(
    (auditorResigned?40:0)+(cfoResigned?20:0)+(rptRisk?15:0)+
    (pledge>15?25:pledge>5?12:0)+(equityDilution?10:0)+
    (beneish>-1.78?15:0)
  ));
  // Capital compounder score (Buffett/Terry Smith/Raamdeo)
  const capCompScore=Math.min(100,Math.round(
    (roce>=25?22:roce>=20?16:roce>=15?10:4)+
    (fcfAvg>0?18:0)+(fcfPatDivergence?0:10)+
    (debt<0.3?18:debt<0.8?12:debt<1.5?6:0)+
    (rev3>=20?14:rev3>=15?9:4)+
    (roe>=22?12:roe>=18?8:4)+
    (pat3>=20?10:pat3>=15?6:2)+4
  ));
  // Moat score
  const moatScore=Math.min(100,Math.round(
    (opMarg>=25?20:opMarg>=18?14:opMarg>=12?8:3)+
    (roce>=22?20:roce>=18?14:8)+
    (rev3>=18&&pat3>=18?15:rev3>=12?8:3)+
    (debt<0.5?15:debt<1?8:3)+
    (promoter>=60?15:promoter>=50?10:5)+
    (r(0,1,150)>0.5?15:8)  // brand/network proxy
  ));
  const moatLabel=moatScore>=75?"Wide Moat":moatScore>=55?"Moderate Moat":"Narrow/No Moat";
  const moatColor=moatScore>=75?"#16a34a":moatScore>=55?"#d97706":"#dc2626";
  // Multibagger potential label
  const mbLabel=mbScore>=85?"🚀 Potential 20x":mbScore>=70?"💎 Potential 10x":mbScore>=55?"⭐ Potential 5x":mbScore>=40?"📈 Emerging Compounder":"📊 Market Performer";
  // Conviction score
  const convictionScore=Math.min(100,Math.round(
    overall*0.35+buyZoneAdj*0.25+mbScore*0.20+smartMoney*0.10+(100-govRisk)*0.10
  ));
  const convictionLabel=convictionScore>=80?"VERY HIGH":convictionScore>=65?"HIGH":convictionScore>=50?"MEDIUM":"LOW";
  // Relative strength vs Nifty (simulated)
  const relStrength=r(75,130,155);
  const relStrLabel=relStrength>=110?"Outperforming":relStrength>=95?"Inline":"Underperforming";
  // Watchlist alerts
  const alerts=[];
  if(deliverySpike) alerts.push({type:"DELIVERY",msg:`Delivery spike +${deliverySpikePct.toFixed(0)}% above 10D avg during consolidation`,c:"#16a34a"});
  if(fii[7]>fii[5]&&fii[5]>fii[3]) alerts.push({type:"FII",msg:"FII buying 3 consecutive quarters",c:"#1d4ed8"});
  if(rsiAligned) alerts.push({type:"RSI",msg:"Daily+Weekly+Monthly RSI all above 55 — structural trend",c:"#7c3aed"});
  if(emaExtended) alerts.push({type:"EMA",msg:`Price ${emaExtPct.toFixed(1)}% above 20-EMA — wait for retest`,c:"#d97706"});
  if(auditorResigned) alerts.push({type:"GOVERNANCE",msg:"Auditor resigned — SELL signal",c:"#dc2626"});
  if(adtvFlag) alerts.push({type:"LIQUIDITY",msg:`ADTV ₹${adtv}Cr — illiquid, position sizing critical`,c:"#ea580c"});

  const tierData=classifyTier({pledge,promoter,debt,beneish,altman,rev3,pat3,pe,roce,roe,
    piotroski,fii,overall,govS,auditorResigned,topTierAuditor,fcfPatDivergence,
    emaExtended,emaExtPct,adtv,deliverySpike,deliverySpikePct});
  return{
    sym,cmp,pe,pb,roe,roce,rev3,pat3,debt,promoter,pledge,
    rsi,del,ema20,ema50,ema200,fii,dii,mf,rev,pat,fcf,delH,qs,
    gS,qS,govS,valS,techS,ownS,overall,mbScore,buyZone,buyZoneAdj,
    verd,verdC,cT,bullT,bearT,analystCount,buyPct,holdPct,sellPct,brokers,
    guruScores,piotroski,beneish,altman,evEb,peg,opMarg,intCov,pcr,adx,mcap,
    macd:rsi>55?"Bullish":rsi<45?"Bearish":"Neutral",
    trend:cmp>ema200?"Bullish":"Bearish",
    sl:+(cmp*r(0.90,0.94,120)).toFixed(0),
    t1:+(cmp*r(1.08,1.15,121)).toFixed(0),
    t2:+(cmp*r(1.16,1.25,122)).toFixed(0),
    t3:+(cmp*r(1.26,1.42,123)).toFixed(0),
    s1:+(cmp*r(0.88,0.93,124)).toFixed(0),
    s2:+(cmp*r(0.80,0.87,125)).toFixed(0),
    r1:+(cmp*r(1.06,1.12,126)).toFixed(0),
    r2:+(cmp*r(1.13,1.22,127)).toFixed(0),
    buyRange:[+(cmp*0.97).toFixed(0),+(cmp*1.02).toFixed(0)],
    cagr:`${ri(12,22,130)}-${ri(20,32,131)}`,
    risk:overall>=75?"Low-Moderate":overall>=60?"Moderate":"High",
    horizon:overall>=75?"3-5 Years":"1-2 Years",
    posSize:Math.max(2,Math.min(15,Math.round((buyZoneAdj-50)/6))),
    intVal,moS,
    // New engines
    adtv,adtvFlag,deliverySpike,deliverySpikePct,del10Avg,
    emaExtPct,emaExtended,fcfPatDivergence,
    auditorResigned,topTierAuditor,cfoResigned,rptRisk,equityDilution,
    rsiW,rsiM,rsiAligned,smartMoney,govRisk,capCompScore,
    moatScore,moatLabel,moatColor,mbLabel,
    convictionScore,convictionLabel,relStrength,relStrLabel,
    alerts,
    ...tierData,
  };
};

// ─── MINI SPARKLINE ───────────────────────────────────────────────
const Spark=({data,color,h=55,labels=null})=>{
  if(!data?.length)return null;
  const mn=0,mx=Math.max(...data)||1;
  const n=data.length;
  const gap=3,W=300,H=h;
  const bw=Math.floor((W-(n-1)*gap)/n);
  const last=data[n-1];
  const prev=data[n-2]??last;
  const up=last>=prev;
  const barColor=c=>c;
  return(
    <svg viewBox={`0 0 ${W} ${H}`} style={{width:"100%",height:h,display:"block"}}>
      {data.map((v,i)=>{
        const bh=Math.max(3,Math.round(((v-mn)/(mx-mn))*(H-2)));
        const x=i*(bw+gap);
        const isLast=i===n-1;
        const alpha=isLast?1:0.35+((i/(n-1))*0.45);
        return(
          <g key={i}>
            <rect x={x} y={H-bh} width={bw} height={bh}
              fill={color} opacity={alpha} rx={2}/>
            {isLast&&(
              <rect x={x} y={H-bh} width={bw} height={2} fill={color} opacity={1} rx={1}/>
            )}
          </g>
        );
      })}
      {/* trend arrow on last bar */}
      {n>1&&(()=>{
        const lx=(n-1)*(bw+gap)+bw/2;
        const lbh=Math.max(3,Math.round(((last-mn)/(mx-mn))*(H-2)));
        const ty=H-lbh-8;
        return ty>2?(
          <text x={lx} y={ty} textAnchor="middle" fontSize="9" fill={up?"#16a34a":"#dc2626"} fontWeight="700">{up?"↑":"↓"}</text>
        ):null;
      })()}
    </svg>
  );
};

// ─── GAUGE RING ────────────────────────────────────────────────────
const Ring=({score,max=100,size=70})=>{
  const rv=size/2-7,circ=2*Math.PI*rv,pct=score/max;
  const c=pct>=0.8?"#16a34a":pct>=0.65?"#1d4ed8":pct>=0.5?"#d97706":"#dc2626";
  return(
    <div style={{position:"relative",width:size,height:size,flexShrink:0}}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{transform:"rotate(-90deg)"}}>
        <circle cx={size/2} cy={size/2} r={rv} fill="none" stroke="#e5e7eb" strokeWidth="6"/>
        <circle cx={size/2} cy={size/2} r={rv} fill="none" stroke={c} strokeWidth="6"
          strokeDasharray={circ} strokeDashoffset={circ*(1-pct)} strokeLinecap="round"/>
      </svg>
      <div style={{position:"absolute",inset:0,display:"flex",alignItems:"center",justifyContent:"center"}}>
        <span style={{fontFamily:"'Sora',sans-serif",fontSize:size>65?16:12,fontWeight:700,color:c}}>{score}</span>
      </div>
    </div>
  );
};

// ─── TOOLTIP ──────────────────────────────────────────────────────
// ─── TRADINGVIEW CHART WIDGET ────────────────────────────────────
const TVChart=({symbol,height=420})=>{
  const ref=React.useRef(null);
  const [loaded,setLoaded]=React.useState(false);
  React.useEffect(()=>{
    if(!ref.current)return;
    ref.current.innerHTML="";
    setLoaded(false);
    const script=document.createElement("script");
    script.src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async=true;
    script.onload=()=>setLoaded(true);
    const cfg = {
      autosize:true,
      symbol:`NSE:${symbol}`,
      interval:"D",
      timezone:"Asia/Kolkata",
      theme:"light",
      style:"1",
      locale:"en",
      hide_top_toolbar:false,
      hide_legend:false,
      save_image:false,
      calendar:false,
      studies:["STD;EMA@tv-basicstudies","STD;EMA@tv-basicstudies","STD;EMA@tv-basicstudies","STD;RSI@tv-basicstudies","STD;MACD@tv-basicstudies"],
      studies_overrides:{
        "EMA.length":20,"EMA.length.1":50,"EMA.length.2":200,
      },
      container_id:`tv_${symbol}`,
    };
    script.textContent = JSON.stringify(cfg);
    const container=document.createElement("div");
    container.className="tradingview-widget-container__widget";
    container.style.height=height+"px";
    container.style.width="100%";
    ref.current.appendChild(container);
    ref.current.appendChild(script);
    return()=>{if(ref.current)ref.current.innerHTML="";};
  },[symbol]);
  return(
    <div style={{position:"relative",width:"100%",height:height,borderRadius:10,overflow:"hidden",border:"1px solid #e5e7eb"}}>
      {!loaded&&<div style={{position:"absolute",inset:0,display:"flex",alignItems:"center",justifyContent:"center",background:"#f9fafb",gap:10,fontFamily:"'IBM Plex Mono',monospace",fontSize:11,color:"#9ca3af"}}><div style={{width:14,height:14,border:"2px solid #e5e7eb",borderTopColor:"#3b82f6",borderRadius:"50%",animation:"spin .7s linear infinite"}}/>Loading TradingView chart...</div>}
      <div ref={ref} className="tradingview-widget-container" style={{height:"100%",width:"100%"}}/>
    </div>
  );
};

const TVMiniChart=({symbol})=>{
  const ref=React.useRef(null);
  React.useEffect(()=>{
    if(!ref.current)return;
    ref.current.innerHTML="";
    const script=document.createElement("script");
    script.src="https://s3.tradingview.com/external-embedding/embed-widget-symbol-overview.js";
    script.async=true;
    script.innerHTML=JSON.stringify({
      symbols:[[`NSE:${symbol}|1D`]],
      chartOnly:false,
      width:"100%",height:200,
      locale:"en",
      colorTheme:"light",
      autosize:true,
      showVolume:true,
      showMA:false,
      hideDateRanges:false,
      hideMarketStatus:false,
      hideSymbolLogo:false,
      scalePosition:"right",
      scaleMode:"Normal",
      fontFamily:"DM Sans",
      fontSize:"10",
      noTimeScale:false,
      valuesTracking:"1",
      changeMode:"price-and-percent",
    });
    ref.current.appendChild(script);
    return()=>{if(ref.current)ref.current.innerHTML="";};
  },[symbol]);
  return<div ref={ref} style={{width:"100%",height:200}}/>;
};

const Tip=({text,children})=>{
  const [s,setS]=useState(false);
  return(
    <span style={{position:"relative",display:"inline-flex"}} onMouseEnter={()=>setS(true)} onMouseLeave={()=>setS(false)} onTouchStart={()=>setS(v=>!v)}>
      {children}
      {s&&<div style={{position:"absolute",bottom:"calc(100% + 8px)",left:"50%",transform:"translateX(-50%)",background:"#1e293b",color:"#f1f5f9",padding:"8px 12px",borderRadius:8,fontSize:11,zIndex:9999,boxShadow:"0 8px 30px rgba(0,0,0,0.3)",maxWidth:240,textAlign:"left",lineHeight:1.5,width:240,fontFamily:"sans-serif"}}>{text}</div>}
    </span>
  );
};

// ─── STAT CARD ────────────────────────────────────────────────────
const SC=({label,value,sub,color,tip})=>(
  <div style={{background:"#fff",border:"1px solid #e5e7eb",borderRadius:10,padding:"11px 13px",boxShadow:"0 1px 3px rgba(0,0,0,0.04)"}}>
    <Tip text={tip||label}>
      <span style={{fontFamily:"'IBM Plex Mono',monospace",fontSize:11,letterSpacing:"0.8px",textTransform:"uppercase",color:"#9ca3af",borderBottom:tip?"1px dashed #d1d5db":"none",cursor:tip?"help":"default",display:"block",marginBottom:3}}>{label}</span>
    </Tip>
    <div style={{fontFamily:"'Sora',sans-serif",fontSize:16,fontWeight:700,color:color||"#111827",marginTop:2}}>{value}</div>
    {sub&&<div style={{fontSize:10,color:"#9ca3af",marginTop:1}}>{sub}</div>}
  </div>
);

// ─── BACKEND SQL MODAL ───────────────────────────────────────────
const BackendModal=({onClose})=>(
  <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,.75)",zIndex:9999,display:"flex",alignItems:"center",justifyContent:"center",padding:16}}>
    <div style={{background:"#0f172a",border:"1px solid #1e293b",borderRadius:14,width:"100%",maxWidth:740,maxHeight:"85vh",display:"flex",flexDirection:"column"}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"14px 18px",borderBottom:"1px solid #1e293b"}}>
        <div>
          <div style={{fontFamily:"'Sora',sans-serif",fontWeight:700,fontSize:15,color:"#f8fafc"}}>🗄️ Nightly Stored Procedures</div>
          <div style={{fontFamily:"'IBM Plex Mono',monospace",fontSize:12,color:"#475569",marginTop:2}}>PostgreSQL schema · Stored procedures · Vercel Cron config · Deploy instructions</div>
        </div>
        <button onClick={onClose} style={{background:"#1e293b",border:"none",borderRadius:6,color:"#94a3b8",padding:"5px 12px",cursor:"pointer",fontFamily:"'IBM Plex Mono',monospace",fontSize:11}}>✕ Close</button>
      </div>
      <div style={{padding:"10px 16px",background:"#1e293b",margin:"12px 16px 0",borderRadius:8}}>
        <div style={{fontFamily:"'IBM Plex Mono',monospace",fontSize:12,color:"#fbbf24",letterSpacing:"1px",textTransform:"uppercase",marginBottom:6}}>Deploy Steps</div>
        <div style={{fontSize:11,color:"#94a3b8",lineHeight:1.7}}>
          1. Create Postgres DB on <strong style={{color:"#f8fafc"}}>Railway.app</strong> or <strong style={{color:"#f8fafc"}}>Supabase</strong> (free tier works)<br/>
          2. Run the SQL below to create schema + stored procedure<br/>
          3. Create <code style={{color:"#34d399"}}>/api/cron/morning.ts</code> in Next.js → calls <code style={{color:"#34d399"}}>run_nightly_scores()</code><br/>
          4. Add cron schedule to <code style={{color:"#34d399"}}>vercel.json</code> (shown at bottom of SQL)<br/>
          5. Set <code style={{color:"#34d399"}}>DATABASE_URL</code> env variable in Vercel dashboard<br/>
          6. The Screener tab then reads real <code style={{color:"#34d399"}}>daily_scores</code> + <code style={{color:"#34d399"}}>guru_signals</code> tables
        </div>
      </div>
      <div style={{flex:1,overflowY:"auto",padding:"12px 16px 16px"}}>
        <pre style={{fontFamily:"'IBM Plex Mono',monospace",fontSize:11,color:"#94a3b8",lineHeight:1.7,whiteSpace:"pre-wrap",wordBreak:"break-word"}}>{BACKEND_SQL}</pre>
      </div>
    </div>
  </div>
);

// ─── PRICE CALCULATOR ─────────────────────────────────────────────
const PriceCalc=()=>{
  const [price,setPrice]=useState("500");
  const [rows,setRows]=useState(null);
  const calc=()=>{
    const p=parseFloat(price);
    if(!p||p<=0)return;
    const up=[],dn=[];
     for(let pct=5;pct<=100;pct+=5) up.push({pct,sp:+(p*(1+pct/100)).toFixed(2),gain:+(p*pct/100).toFixed(2)});
     for(let pct=125;pct<=500;pct+=25) up.push({pct,sp:+(p*(1+pct/100)).toFixed(2),gain:+(p*pct/100).toFixed(2)});
     for(let pct=5;pct<=90;pct+=5)  dn.push({pct,sp:+(p*(1-pct/100)).toFixed(2),loss:+(p*pct/100).toFixed(2)});
    setRows({up,dn,base:p});
  };
  return(
    <div style={{background:"#fff",border:"1px solid #e5e7eb",borderRadius:12,padding:16}}>
      <div style={{fontFamily:"'IBM Plex Mono',monospace",fontSize:12,color:"#6b7280",letterSpacing:"1px",textTransform:"uppercase",marginBottom:12}}>Price Return Calculator</div>
      <div style={{display:"flex",gap:8,marginBottom:12}}>
        <input value={price} onChange={e=>setPrice(e.target.value)}
          placeholder="Enter stock price e.g. 500"
          style={{flex:1,border:"1px solid #e5e7eb",borderRadius:8,padding:"9px 12px",fontSize:13,fontFamily:"'IBM Plex Mono',monospace",color:"#111827",background:"#f9fafb"}}/>
        <button onClick={calc} style={{padding:"9px 20px",background:"#111827",border:"none",borderRadius:8,color:"#fff",fontFamily:"'Sora',sans-serif",fontWeight:600,fontSize:13,cursor:"pointer",whiteSpace:"nowrap"}}>Calculate</button>
      </div>
      {rows&&(
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12}}>
          {/* UPSIDE */}
          <div>
            <div style={{fontFamily:"'IBM Plex Mono',monospace",fontSize:12,color:"#16a34a",letterSpacing:"1px",textTransform:"uppercase",marginBottom:8,display:"flex",alignItems:"center",gap:6}}>
              <span style={{width:8,height:8,borderRadius:"50%",background:"#16a34a",display:"inline-block"}}/>Upside from ₹{rows.base}
            </div>
            <div style={{maxHeight:340,overflowY:"auto",borderRadius:8,border:"1px solid #dcfce7"}}>
              <table style={{width:"100%",borderCollapse:"collapse"}}>
                <thead><tr style={{background:"#f0fdf4",position:"sticky",top:0}}>
                  <th style={{padding:"7px 10px",textAlign:"left",fontFamily:"'IBM Plex Mono',monospace",fontSize:11,color:"#16a34a",letterSpacing:"0.5px",borderBottom:"1px solid #dcfce7"}}>Return %</th>
                  <th style={{padding:"7px 10px",textAlign:"right",fontFamily:"'IBM Plex Mono',monospace",fontSize:11,color:"#16a34a",letterSpacing:"0.5px",borderBottom:"1px solid #dcfce7"}}>Price ₹</th>
                  <th style={{padding:"7px 10px",textAlign:"right",fontFamily:"'IBM Plex Mono',monospace",fontSize:11,color:"#16a34a",letterSpacing:"0.5px",borderBottom:"1px solid #dcfce7"}}>Gain ₹</th>
                </tr></thead>
                <tbody>
                  {rows.up.map(r=>(
                    <tr key={r.pct} style={{borderBottom:"1px solid #f0fdf4"}}>
                      <td style={{padding:"5px 10px",fontFamily:"'IBM Plex Mono',monospace",fontWeight:700,color:"#16a34a",fontSize:12}}>+{r.pct}%</td>
                      <td style={{padding:"5px 10px",textAlign:"right",fontFamily:"'IBM Plex Mono',monospace",fontSize:12,color:"#111827"}}>{r.sp.toLocaleString("en-IN")}</td>
                      <td style={{padding:"5px 10px",textAlign:"right",fontFamily:"'IBM Plex Mono',monospace",fontSize:12,color:"#16a34a"}}>+{r.gain.toLocaleString("en-IN")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {/* DOWNSIDE */}
          <div>
            <div style={{fontFamily:"'IBM Plex Mono',monospace",fontSize:12,color:"#dc2626",letterSpacing:"1px",textTransform:"uppercase",marginBottom:8,display:"flex",alignItems:"center",gap:6}}>
              <span style={{width:8,height:8,borderRadius:"50%",background:"#dc2626",display:"inline-block"}}/>Downside — Stop Loss Guide
            </div>
            <div style={{maxHeight:340,overflowY:"auto",borderRadius:8,border:"1px solid #fecaca"}}>
              <table style={{width:"100%",borderCollapse:"collapse"}}>
                <thead><tr style={{background:"#fef2f2",position:"sticky",top:0}}>
                  <th style={{padding:"7px 10px",textAlign:"left",fontFamily:"'IBM Plex Mono',monospace",fontSize:11,color:"#dc2626",letterSpacing:"0.5px",borderBottom:"1px solid #fecaca"}}>Loss %</th>
                  <th style={{padding:"7px 10px",textAlign:"right",fontFamily:"'IBM Plex Mono',monospace",fontSize:11,color:"#dc2626",letterSpacing:"0.5px",borderBottom:"1px solid #fecaca"}}>Price ₹</th>
                  <th style={{padding:"7px 10px",textAlign:"right",fontFamily:"'IBM Plex Mono',monospace",fontSize:11,color:"#dc2626",letterSpacing:"0.5px",borderBottom:"1px solid #fecaca"}}>Loss ₹</th>
                </tr></thead>
                <tbody>
                  {rows.dn.map(r=>(
                    <tr key={r.pct} style={{borderBottom:"1px solid #fef2f2"}}>
                      <td style={{padding:"5px 10px",fontFamily:"'IBM Plex Mono',monospace",fontWeight:700,color:"#dc2626",fontSize:12}}>−{r.pct}%</td>
                      <td style={{padding:"5px 10px",textAlign:"right",fontFamily:"'IBM Plex Mono',monospace",fontSize:12,color:"#111827"}}>{r.sp.toLocaleString("en-IN")}</td>
                      <td style={{padding:"5px 10px",textAlign:"right",fontFamily:"'IBM Plex Mono',monospace",fontSize:12,color:"#dc2626"}}>−{r.loss.toLocaleString("en-IN")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{marginTop:8,background:"#fffbeb",border:"1px solid #fde68a",borderRadius:6,padding:"8px 10px",fontFamily:"'IBM Plex Mono',monospace",fontSize:10,color:"#92400e"}}>
              ⚡ Rule: 5% stop = ₹{rows.dn[0].sp} · 10% stop = ₹{rows.dn[1].sp}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ─── IPO SCORE HELPER ─────────────────────────────────────────────
const scoreIpo=(ipo)=>{
  const aScore=anchorScore(ipo.anchor);
  const pred=predictGain(aScore,ipo.qib);
  const lynch=Math.min(100,Math.round(aScore*6+Math.min(parseFloat(ipo.qib),200)*0.1+parseFloat(ipo.retail)*1.5+20));
  const similar=IPO_HISTORY.filter(h=>h.anchor.some(a=>ipo.anchor.some(ia=>a.toLowerCase().includes(ia.split(" ")[0].toLowerCase()))));
  const avgHist=similar.length?+(similar.reduce((a,b)=>a+b.gain,0)/similar.length).toFixed(1):20;
  return{aScore,pred,lynch,similar,avgHist};
};

// ─── MAIN APP ─────────────────────────────────────────────────────


// ─── LIVE TAPE (stub - Phase 2 upgrade) ─────────
function LiveTape({ ipo }: { ipo: any }) {
  const ip = ipo.priceBandHigh || ipo.priceBandLow || 0
  return (
    <div style={{ border:"1px solid #e5e7eb", borderRadius:14, padding:16, background:"#fff", marginBottom:12 }}>
      <div style={{ fontSize:11, fontWeight:800, color:"#0f172a", marginBottom:8, letterSpacing:"0.05em" }}>LISTING-DAY LIVE TAPE ENGINE</div>
      <div style={{ fontSize:11, color:"#6b7280", marginBottom:10 }}>
        Activate on listing day to monitor real-time bid/ask, VWAP, and tape score.
        Phase 1 uses Zerodha quote polling (30s). Phase 2 upgrades to WebSocket.
      </div>
      <a href="/api/auth/zerodha" style={{ display:"inline-block", padding:"7px 14px", background:"#ff6600", borderRadius:7, fontSize:11, fontWeight:700, color:"#fff", textDecoration:"none" }}>
        Connect Zerodha to Activate
      </a>
    </div>
  )
}

// ─── POST LISTING MONITOR ─────────────────────────
function PostListingMonitor() {
  const [opps, setOpps] = React.useState<any[]>([])
  React.useEffect(() => {
    fetch("/api/ipo/monitor").then(r=>r.json()).then(d => setOpps(d.postListingOpportunities||[])).catch(()=>{})
  }, [])
  if (!opps.length) return null
  const sigColor = (s:string) => s==="BUY AFTER LISTING"?"#15803d":s==="ACCUMULATE"?"#1d4ed8":"#6b7280"
  return (
    <div style={{ border:"1px solid #e5e7eb", borderRadius:14, padding:16, background:"#fff", marginBottom:12 }}>
      <div style={{ fontSize:11, fontWeight:800, color:"#0f172a", marginBottom:10 }}>POST-LISTING OPPORTUNITY MONITOR</div>
      <div style={{ fontSize:10, color:"#6b7280", marginBottom:10 }}>IPOs that listed weak but have strong fundamentals — future Kaynes / NSDL type patterns</div>
      {opps.slice(0,5).map((o:any,i:number) => (
        <div key={i} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", padding:"8px 10px", background:"#f9fafb", borderRadius:8, marginBottom:5 }}>
          <div>
            <div style={{ fontSize:12, fontWeight:700, color:"#111827" }}>{o.name}</div>
            <div style={{ fontSize:12, color:"#9ca3af" }}>{o.year} · {o.sector}</div>
          </div>
          <div style={{ textAlign:"right" }}>
            <div style={{ fontSize:10, fontWeight:800, color:sigColor(o.signal) }}>{o.signal}</div>
            <div style={{ fontSize:12, color:"#9ca3af" }}>6M: {o.m6Return>=0?"+":""}{Number(o.m6Return).toFixed(1)}%</div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── IPO INTELLIGENCE COMMAND CENTER ───────────────────────

// ── Colour system ─────────────────────────────────────────────────────────
const C = {
  green:  "#15803d", greenBg:  "#f0fdf4", greenBd: "#bbf7d0",
  blue:   "#1d4ed8", blueBg:   "#eff6ff", blueBd:  "#bfdbfe",
  amber:  "#b45309", amberBg:  "#fefce8", amberBd: "#fde68a",
  red:    "#b91c1c", redBg:    "#fef2f2", redBd:   "#fecaca",
  purple: "#7c3aed", purpleBg: "#f5f3ff", purpleBd:"#e9d5ff",
  cyan:   "#0891b2", cyanBg:   "#ecfeff", cyanBd:  "#cffafe",
  gray:   "#6b7280", grayBg:   "#f9fafb", grayBd:  "#e5e7eb",
}
const scoreCol = (v:number) => v>=80?C.green:v>=65?C.blue:v>=50?C.amber:C.red
const scoreBg  = (v:number) => v>=80?C.greenBg:v>=65?C.blueBg:v>=50?C.amberBg:C.redBg
const pctStr   = (v:number,base:number) => { const p=base>0?((v-base)/base*100):0; return (p>=0?"+":"")+p.toFixed(1)+"%" }

const REC: Record<string,[string,string,string]> = {
  "Apply Aggressively":                        [C.green,  C.greenBg,  "APPLY"],
  "Apply — Long-Term Hold":                    [C.blue,   C.blueBg,   "LONG TERM"],
  "Apply — Listing Trade Only":                [C.cyan,   C.cyanBg,   "TRADE"],
  "Apply Retail Only":                         [C.blue,   C.blueBg,   "RETAIL"],
  "Long-Term Compounder — Buy on Listing Dip": [C.purple, C.purpleBg, "WATCH BASE"],
  "Watch — Selective Apply":                   [C.amber,  C.amberBg,  "WATCH"],
  "Avoid":                                     [C.red,    C.redBg,    "AVOID"],
}

// ── Primitives ────────────────────────────────────────────────────────────
function Tag({ text, color=C.gray, bg=C.grayBg }: { text:string; color?:string; bg?:string }) {
  return <span style={{ display:"inline-block", padding:"2px 9px", borderRadius:99, fontSize:10, fontWeight:700, background:bg, color }}>{text}</span>
}
function Bar({ v, max=100, color=C.blue }: { v:number; max?:number; color?:string }) {
  return <div style={{ height:3, background:"#e5e7eb", borderRadius:2, marginTop:3 }}><div style={{ width:`${Math.min(100,Math.round(v/max*100))}%`, height:"100%", background:color, borderRadius:2 }} /></div>
}
function Card({ children, style={} }: { children:any; style?:any }) {
  return <div style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:12, padding:20, marginBottom:24, ...style }}>{children}</div>
}
function SectionTitle({ text }: { text:string }) {
  return <div style={{ fontSize:11, fontWeight:500, color:"#94a3b8", letterSpacing:"0.05em", marginBottom:16, textTransform:"uppercase" as const }}>{text}</div>
}

// ─────────────────────────────────────────────────────────────────────────────
// A: HERO DECISION PANEL
// ─────────────────────────────────────────────────────────────────────────────
function HeroPanel({ ipo }: { ipo:any }) {
  const s = ipo.score || {}
  const rec = s.recommendation || "Watch — Selective Apply"
  const [recFg, recBg, recLabel] = REC[rec] || [C.gray, C.grayBg, rec]
  const ip = ipo.priceBandHigh || ipo.priceBandLow || 0
  const gmp = ipo.gmpPrice || 0
  const eff = s.regime?.gmpEfficiency || 0.6
  const expLow  = gmp ? Math.round(ip + gmp * 0.50) : null
  const expHigh = gmp ? Math.round(ip + gmp * 0.90) : null
  const exp12mLow  = s.businessScore >= 70 ? Math.round((s.businessScore - 70) * 0.5 + 15) : 5
  const exp12mHigh = s.businessScore >= 70 ? Math.round((s.businessScore - 70) * 1.2 + 20) : 12

  return (
    <div style={{ background:"#0f172a", borderRadius:16, padding:"18px 20px", color:"#f8fafc", marginBottom:12 }}>
      {/* Name + recommendation */}
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", flexWrap:"wrap", gap:12, marginBottom:16 }}>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:12, color:"#64748b", letterSpacing:"0.08em", marginBottom:4 }}>{ipo.status} · {ipo.sector}</div>
          <div style={{ fontSize:22, fontWeight:900, letterSpacing:"-0.02em", lineHeight:1.2, marginBottom:5 }}>{ipo.name}</div>
          <div style={{ fontSize:11, color:"#64748b" }}>
            ₹{ipo.priceBandLow}–₹{ip} · ₹{ipo.issueSize}Cr{ipo.lotSize?` · Lot ${ipo.lotSize}`:""}
          </div>
          {ipo.brokerNote && (
            <div style={{ marginTop:8, padding:"7px 11px", background:"rgba(255,255,255,0.05)", borderRadius:8, fontSize:10, color:"#94a3b8", lineHeight:1.6 }}>
              {ipo.brokerReco && <strong style={{ color:"#4ade80" }}>SBI Sec {ipo.brokerReco}: </strong>}
              {ipo.brokerNote}
            </div>
          )}
        </div>
        <div style={{ background:recBg, border:`2px solid ${recFg}`, borderRadius:14, padding:"12px 16px", textAlign:"center", flexShrink:0 }}>
          <div style={{ fontSize:13, fontWeight:900, color:recFg, letterSpacing:"0.03em" }}>{recLabel}</div>
          <div style={{ fontSize:12, color:C.gray, marginTop:4 }}>Confidence: {s.confidence||"Medium"}</div>
        </div>
      </div>

      {/* 5 score tiles */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(80px,1fr))", gap:6, marginBottom:14 }}>
        {[
          { l:"Listing",    v:s.listingScore??0,    c:"#60a5fa" },
          { l:"Business",   v:s.businessScore??0,   c:"#4ade80" },
          { l:"Management", v:s.managementScore??0, c:"#c084fc" },
          { l:"Risk ↓",     v:s.risk?.score??0,     c:"#f87171" },
          { l:"Multibagger",v:s.multibaggerProb??0, c:"#fbbf24" },
        ].map(t => (
          <div key={t.l} style={{ background:"rgba(255,255,255,0.05)", borderRadius:10, padding:"9px 0", textAlign:"center" }}>
            <div style={{ fontSize:11, color:"#64748b", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:3 }}>{t.l}</div>
            <div style={{ fontSize:28, fontWeight:700, color:t.c, lineHeight:1 }}>{t.v}</div>
          </div>
        ))}
      </div>

      {/* Expected ranges */}
      <div style={{ display:"flex", gap:8, flexWrap:"wrap" }}>
        {expLow && (
          <div style={{ background:"rgba(255,255,255,0.05)", borderRadius:9, padding:"7px 12px" }}>
            <div style={{ fontSize:11, color:"#64748b", marginBottom:2 }}>Expected listing range</div>
            <div style={{ fontSize:14, fontWeight:800, color:"#4ade80" }}>₹{expLow} – ₹{expHigh}</div>
          </div>
        )}
        <div style={{ background:"rgba(255,255,255,0.05)", borderRadius:9, padding:"7px 12px" }}>
          <div style={{ fontSize:11, color:"#64748b", marginBottom:2 }}>Expected 12M return</div>
          <div style={{ fontSize:14, fontWeight:800, color:"#c084fc" }}>+{exp12mLow}% – +{exp12mHigh}%</div>
        </div>
        {s.anchorValidation?.label && (
          <div style={{ background:"rgba(255,255,255,0.05)", borderRadius:9, padding:"7px 12px" }}>
            <div style={{ fontSize:11, color:"#64748b", marginBottom:2 }}>Anchor signal</div>
            <div style={{ fontSize:11, fontWeight:700, color: s.anchorValidation.label.includes("Confirmation")?"#4ade80":s.anchorValidation.label.includes("Trap")?"#f87171":"#fbbf24" }}>
              {s.anchorValidation.label}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// B: HISTORICAL SIMILARITY ENGINE
// ─────────────────────────────────────────────────────────────────────────────
function SimilarityEngine({ ipo }: { ipo:any }) {
  const sim = ipo.similar
  if (!sim) return null
  const examples = sim.examples || []

  return (
    <Card>
      <SectionTitle text="B · Historical Similarity Engine" />
      <div style={{ fontSize:10, color:C.gray, marginBottom:12 }}>
        Matched by: sector · subscription · anchor quality · market regime · financials
      </div>
      {/* Summary stats */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr 1fr", gap:6, marginBottom:12 }}>
        {[
          { l:"Avg D1 return",   v:sim.avgD1,     fmt:(x:number)=>`${x>=0?"+":""}${x}%`,  good:sim.avgD1>=0 },
          { l:"Avg 6M return",   v:sim.avgM6,     fmt:(x:number)=>`${x>=0?"+":""}${x}%`,  good:sim.avgM6>=0 },
          { l:"Positive D1 rate",v:sim.hitRate,   fmt:(x:number)=>`${x}%`,                 good:sim.hitRate>=65 },
          { l:"Data quality",    v:sim.dataQuality==="high"?3:sim.dataQuality==="medium"?2:1,
            fmt:()=>sim.dataQuality||"—", good:true },
        ].map(s => (
          <div key={s.l} style={{ background:C.grayBg, borderRadius:9, padding:"8px 10px", textAlign:"center" }}>
            <div style={{ fontSize:11, color:C.gray, textTransform:"uppercase", marginBottom:2 }}>{s.l}</div>
            <div style={{ fontSize:15, fontWeight:900, color:s.good?C.green:C.red }}>{s.fmt(s.v)}</div>
          </div>
        ))}
      </div>
      {/* Top matches */}
      {examples.map((e:any, i:number) => {
        const sim_pct = [87, 83, 78][i] || 70
        return (
          <div key={i} style={{ display:"flex", alignItems:"center", gap:10, padding:"9px 11px", background:C.grayBg, borderRadius:9, marginBottom:5 }}>
            <div style={{ fontSize:13, fontWeight:800, color:C.blue, width:28, textAlign:"center" }}>{sim_pct}%</div>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:12, fontWeight:700, color:"#111827" }}>{e.name}</div>
              <div style={{ fontSize:12, color:C.gray }}>{e.sector}</div>
            </div>
            <div style={{ display:"flex", gap:14, textAlign:"right" }}>
              <div>
                <div style={{ fontSize:11, color:C.gray }}>D1</div>
                <div style={{ fontSize:12, fontWeight:800, color:e.d1Return>=0?C.green:C.red }}>
                  {e.d1Return>=0?"+":""}{e.d1Return}%
                </div>
              </div>
              <div>
                <div style={{ fontSize:11, color:C.gray }}>6M</div>
                <div style={{ fontSize:12, fontWeight:800, color:e.m6Return>=0?C.green:C.red }}>
                  {e.m6Return>=0?"+":""}{e.m6Return}%
                </div>
              </div>
            </div>
          </div>
        )
      })}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// C: MULTIBAGGER ENGINE
// ─────────────────────────────────────────────────────────────────────────────
function MultibaggerEngine({ ipo }: { ipo:any }) {
  const s = ipo.score || {}
  const prob = s.multibaggerProb || 0
  const benchmarks = [
    { name:"Kaynes Technology", prob:85, d1:18, m12:145 },
    { name:"Netweb Technologies", prob:82, d1:82, m12:120 },
    { name:"DOMS Industries", prob:75, d1:68, m12:55 },
    { name:"Premier Energies", prob:78, d1:96, m12:85 },
    { name:"NSDL", prob:70, d1:10, m12:40 },
  ]

  return (
    <Card>
      <SectionTitle text="C · Multibagger Probability Engine" />
      <div style={{ display:"flex", gap:14, alignItems:"center", marginBottom:14 }}>
        {/* Probability gauge */}
        <div style={{ textAlign:"center", background:scoreBg(prob), borderRadius:14, padding:"14px 20px" }}>
          <div style={{ fontSize:38, fontWeight:900, color:scoreCol(prob), lineHeight:1 }}>{prob}%</div>
          <div style={{ fontSize:12, color:C.gray, marginTop:4 }}>MULTIBAGGER PROB</div>
        </div>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:12, fontWeight:700, color:scoreCol(prob), marginBottom:6 }}>
            {prob>=70?"Strong compounder candidate":prob>=50?"Moderate long-term potential":prob>=30?"Limited compounding case":"Low probability — listing trade only"}
          </div>
          <div style={{ fontSize:10, color:C.gray, lineHeight:1.7 }}>
            Business Quality: <strong>{s.businessScore||0}/100</strong><br/>
            Sector Momentum: <strong>{s.sectorMomentum||0}/100</strong><br/>
            Long-Term Rating: <strong>{s.businessRating||"—"}</strong>
          </div>
        </div>
      </div>
      {/* Benchmark comparisons */}
      <div style={{ fontSize:12, color:C.gray, marginBottom:6, textTransform:"uppercase", letterSpacing:"0.06em" }}>Closest compounder comparables</div>
      {benchmarks.filter(b => Math.abs(b.prob - prob) < 25).slice(0,3).map(b => (
        <div key={b.name} style={{ display:"flex", alignItems:"center", gap:8, marginBottom:5 }}>
          <div style={{ width:130, fontSize:10, fontWeight:600, color:"#374151" }}>{b.name}</div>
          <div style={{ flex:1, height:5, background:"#e5e7eb", borderRadius:3 }}>
            <div style={{ width:`${b.prob}%`, height:"100%", background:C.purple, borderRadius:3 }} />
          </div>
          <div style={{ fontSize:12, color:C.gray, width:30 }}>{b.prob}%</div>
          <div style={{ fontSize:12, color:b.m12>=50?C.green:C.amber, width:48, textAlign:"right" }}>12M +{b.m12}%</div>
        </div>
      ))}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// D: ANCHOR HEATMAP
// ─────────────────────────────────────────────────────────────────────────────
function AnchorHeatmap({ ipo }: { ipo:any }) {
  const anchors: string[] = ipo.anchors || []
  const s = ipo.score || {}
  const anchorScore = s.anchorScore || 0
  const av = s.anchorValidation || {}

  const getTier = (name: string): 1|2|3 => {
    const n = name.toLowerCase()
    const t1 = ["adia","gic","temasek","norges","cppib","sbi mf","sbi mutual","hdfc mf","hdfc mutual","icici pru","nippon","axis mf","axis mutual","kotak mf","kotak mutual","blackrock","lic","morgan stanley","goldman sachs","wellington","fidelity","sbi life","hdfc life","icici pru life"]
    const t2 = ["franklin","mirae","dsp","nomura","ubs","bnp","hsbc","bandhan","whiteoak","ashoka"]
    if (t1.some(x => n.includes(x))) return 1
    if (t2.some(x => n.includes(x))) return 2
    return 3
  }
  const getCategory = (name: string): string => {
    const n = name.toLowerCase()
    if (["adia","gic","temasek","norges","cppib"].some(x => n.includes(x))) return "Sovereign"
    if (["sbi mf","hdfc mf","icici pru mf","nippon","axis mf","kotak mf","franklin","mirae","dsp"].some(x => n.includes(x))) return "Domestic MF"
    if (["lic","sbi life","hdfc life","icici pru life","kotak life"].some(x => n.includes(x))) return "Insurance"
    if (["blackrock","goldman sachs","morgan stanley","wellington","fidelity","nomura","ubs","bnp"].some(x => n.includes(x))) return "FPI"
    return "AIF/Other"
  }

  const cats = { "Sovereign":0, "Domestic MF":0, "Insurance":0, "FPI":0, "AIF/Other":0 }
  anchors.forEach(a => { const c = getCategory(a); cats[c as keyof typeof cats]++ })

  const [avFg, avBg] = av.label?.includes("Confirmation") ? [C.green,C.greenBg]
    : av.label?.includes("Trap") ? [C.red,C.redBg] : [C.amber,C.amberBg]

  return (
    <Card>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
        <SectionTitle text="D · Anchor Heatmap" />
        <div style={{ display:"flex", gap:8, alignItems:"center" }}>
          <div style={{ textAlign:"center", background:scoreBg(anchorScore), borderRadius:9, padding:"4px 12px" }}>
            <div style={{ fontSize:18, fontWeight:900, color:scoreCol(anchorScore) }}>{anchorScore}</div>
            <div style={{ fontSize:11, color:C.gray }}>QUALITY</div>
          </div>
          {av.label && <Tag text={av.label} color={avFg} bg={avBg} />}
        </div>
      </div>

      {/* Category breakdown */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(80px,1fr))", gap:5, marginBottom:12 }}>
        {Object.entries(cats).map(([cat, count]) => (
          <div key={cat} style={{ background:C.grayBg, borderRadius:8, padding:"7px 6px", textAlign:"center" }}>
            <div style={{ fontSize:18, fontWeight:900, color:count>0?C.blue:C.gray }}>{count}</div>
            <div style={{ fontSize:11, color:C.gray, lineHeight:1.3 }}>{cat}</div>
          </div>
        ))}
      </div>

      {/* Tier breakdown */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:6, marginBottom:10 }}>
        {[
          { label:"Tier 1", color:C.green, bg:C.greenBg, desc:"Sovereign · MF · Insurance", anchors:anchors.filter(a=>getTier(a)===1) },
          { label:"Tier 2", color:C.blue,  bg:C.blueBg,  desc:"Mid-tier FPI · MF",         anchors:anchors.filter(a=>getTier(a)===2) },
          { label:"Tier 3", color:C.gray,  bg:C.grayBg,  desc:"AIF · PMS · Family",        anchors:anchors.filter(a=>getTier(a)===3) },
        ].map(t => (
          <div key={t.label} style={{ background:t.bg, borderRadius:9, padding:"8px 10px", textAlign:"center" }}>
            <div style={{ fontSize:20, fontWeight:900, color:t.color }}>{t.anchors.length}</div>
            <div style={{ fontSize:11, fontWeight:700, color:t.color }}>{t.label}</div>
            <div style={{ fontSize:11, color:C.gray }}>{t.desc}</div>
          </div>
        ))}
      </div>

      {/* Named anchors */}
      {anchors.length > 0 && (
        <div style={{ display:"flex", gap:5, flexWrap:"wrap", marginBottom:8 }}>
          {anchors.map((a:string) => {
            const t = getTier(a)
            const [c,bg] = t===1?[C.green,C.greenBg]:t===2?[C.blue,C.blueBg]:[C.gray,C.grayBg]
            return <Tag key={a} text={`${t===1?"★ ":t===2?"◆ ":" "}${a}`} color={c} bg={bg} />
          })}
        </div>
      )}
      {anchors.length === 0 && <div style={{ fontSize:11, color:C.gray }}>No anchor data yet — upload SBI Sec PDF or fetch live data</div>}
      {av.detail && <div style={{ fontSize:10, color:C.gray, lineHeight:1.5, marginTop:6 }}>{av.detail}</div>}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// E: MARKET REGIME WIDGET
// ─────────────────────────────────────────────────────────────────────────────
function RegimeWidget({ regime }: { regime:any }) {
  if (!regime) return null
  const map: Record<string,[string,string,string]> = {
    HOT:    [C.green,  C.greenBg,  "HOT 🔥"],
    NORMAL: [C.blue,   C.blueBg,   "NORMAL"],
    COLD:   [C.red,    C.redBg,    "COLD ❄"],
  }
  const [fg, bg, label] = map[regime.label] || map.NORMAL
  const recentStats: Record<string,{avg:number,pos:number,count:number}> = {
    HOT:    { avg:34, pos:89, count:27 },
    NORMAL: { avg:9,  pos:68, count:95 },
    COLD:   { avg:2,  pos:42, count:24 },
  }
  const stats = recentStats[regime.label] || recentStats.NORMAL

  return (
    <div style={{ background:bg, border:`1px solid ${fg}30`, borderRadius:12, padding:"12px 16px", marginBottom:12 }}>
      <SectionTitle text="E · Market Regime" />
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr 1fr", gap:8, alignItems:"center" }}>
        <div>
          <div style={{ fontSize:22, fontWeight:900, color:fg }}>{label}</div>
          <div style={{ fontSize:12, color:C.gray, marginTop:2 }}>Score: {regime.score}/100</div>
        </div>
        {[
          { l:"12M avg gain",    v:`+${stats.avg}%` },
          { l:"Positive rate",   v:`${stats.pos}%` },
          { l:"GMP efficiency",  v:`${Math.round((regime.gmpEfficiency||0.6)*100)}%` },
        ].map(s => (
          <div key={s.l} style={{ textAlign:"center" }}>
            <div style={{ fontSize:11, color:C.gray, textTransform:"uppercase", marginBottom:2 }}>{s.l}</div>
            <div style={{ fontSize:16, fontWeight:900, color:fg }}>{s.v}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// F: OFS vs FRESH ISSUE BANNER
// ─────────────────────────────────────────────────────────────────────────────
function IssueBanner({ ipo }: { ipo:any }) {
  const fresh = ipo.freshIssuePct ?? 0
  const ofs   = ipo.ofsPct ?? 100
  const isBad = ofs >= 70
  const isGood = fresh >= 70

  return (
    <Card>
      <SectionTitle text="F · OFS vs Fresh Issue" />
      <div style={{ height:22, borderRadius:11, overflow:"hidden", display:"flex", marginBottom:10 }}>
        {fresh > 0 && (
          <div style={{ width:`${fresh}%`, background:C.green, display:"flex", alignItems:"center", justifyContent:"center" }}>
            {fresh > 12 && <span style={{ fontSize:12, color:"#fff", fontWeight:800 }}>{fresh}% Fresh</span>}
          </div>
        )}
        <div style={{ flex:1, background:"#fca5a5", display:"flex", alignItems:"center", justifyContent:"center" }}>
          <span style={{ fontSize:12, color:"#7f1d1d", fontWeight:800 }}>{ofs}% OFS</span>
        </div>
      </div>
      {/* Warning / badge */}
      {isBad && (
        <div style={{ background:C.redBg, border:`1px solid ${C.redBd}`, borderRadius:8, padding:"8px 12px", marginBottom:8 }}>
          <div style={{ fontSize:11, fontWeight:700, color:C.red }}>
            🔴 OFS {ofs}% — {ofs>=90?"100% OFS: zero growth capital raised. Existing investors exiting.":"High OFS: majority is investor exit, not growth funding."}
          </div>
        </div>
      )}
      {isGood && (
        <div style={{ background:C.greenBg, border:`1px solid ${C.greenBd}`, borderRadius:8, padding:"8px 12px", marginBottom:8 }}>
          <div style={{ fontSize:11, fontWeight:700, color:C.green }}>✅ Fresh Issue {fresh}% — growth capital badge: company raising funds for expansion</div>
        </div>
      )}
      {!isBad && !isGood && (
        <div style={{ fontSize:11, color:C.amber }}>⚠ Mixed issue — partial growth capital, partial investor exit</div>
      )}
      {ipo.peRatio && ipo.peerPE && (
        <div style={{ marginTop:8, padding:"7px 10px", background:C.grayBg, borderRadius:8, fontSize:11, color:"#374151" }}>
          PE: <strong>{ipo.peRatio}x</strong> vs peers ({ipo.peerLabel})
          <span style={{ marginLeft:8, fontWeight:700, color:ipo.peRatio<ipo.peerPE?C.green:C.amber }}>
            {ipo.peRatio<ipo.peerPE
              ? `${Math.round((1-ipo.peRatio/ipo.peerPE)*100)}% discount ✅`
              : `${Math.round((ipo.peRatio/ipo.peerPE-1)*100)}% premium ⚠`}
          </span>
        </div>
      )}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// G: LISTING-DAY TRADING ENGINE
// ─────────────────────────────────────────────────────────────────────────────
function TradingEngine({ ipo, onGmpUpdate }: { ipo:any; onGmpUpdate:(v:number)=>void }) {
  const ip = ipo.priceBandHigh || ipo.priceBandLow || 192
  const [gmp, setGmp] = useState<number>(ipo.gmpPrice || 0)
  const lot = ipo.lotSize || 78
  const regime = ipo.score?.regime?.label || "NORMAL"
  const eff = regime==="HOT"?0.70:regime==="COLD"?0.50:0.60
  const gmpPct = ip>0 ? (gmp/ip*100) : 0
  const gmpStrength = gmpPct>=50?"Very Hot 🔥":gmpPct>=20?"Strong":gmpPct>=8?"Moderate":gmpPct>=3?"Weak":"No Signal"
  const entry = ip + gmp
  const bull  = Math.round(ip + gmp*0.90)
  const base  = Math.round(ip + gmp*eff)
  const bear  = Math.round(ip - gmp*0.20)
  const stop  = Math.round(entry*0.90)
  const exitL = Math.round(entry*1.05)
  const exitH = Math.round(entry*1.12)
  const trend = ipo.gmpTrend || []

  const [gmpInput, setGmpInput] = useState(String(ipo.gmpPrice||""))
  const [saved, setSaved] = useState(false)
  const handleSave = async () => {
    const n = parseFloat(gmpInput)
    if (!isNaN(n)) {
      setGmp(n)
      onGmpUpdate(n)
      await fetch("/api/ipo/gmp", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ name:ipo.name, gmpPrice:n }) })
      setSaved(true); setTimeout(()=>setSaved(false), 2000)
    }
  }

  return (
    <Card>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
        <SectionTitle text="G · Listing-Day Trading Engine" />
        <div style={{ display:"flex", gap:8, alignItems:"center" }}>
          {trend.length > 1 && (
            <div style={{ display:"flex", alignItems:"flex-end", gap:2, height:18 }}>
              {trend.map((v:number,i:number) => { const mx=Math.max(...trend); const h=Math.max(2,Math.round(v/mx*18)); return <div key={i} style={{ width:5,height:h,borderRadius:2,background:i===trend.length-1?C.green:"#d1d5db" }} /> })}
            </div>
          )}
          <Tag text={gmpStrength} color={gmpPct>=20?C.green:gmpPct>=8?C.amber:C.gray} bg={gmpPct>=20?C.greenBg:gmpPct>=8?C.amberBg:C.grayBg} />
        </div>
      </div>

      {/* GMP Slider */}
      <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:12 }}>
        <span style={{ fontSize:10, color:C.gray, whiteSpace:"nowrap" }}>GMP ₹</span>
        <input type="range" min={0} max={250} step={1} value={gmp} onChange={e=>setGmp(+e.target.value)}
          style={{ flex:1, accentColor:C.blue }} />
        <span style={{ fontSize:20, fontWeight:900, color:"#0f172a", minWidth:40, textAlign:"right" }}>{gmp}</span>
        <span style={{ fontSize:10, color:C.gray }}>({gmpPct.toFixed(1)}%)</span>
      </div>

      {/* Key prices */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:8, marginBottom:12 }}>
        {[
          { l:"Issue price",    v:`₹${ip}`,              c:"#374151", bg:C.grayBg },
          { l:"Current GMP",    v:`+₹${gmp}`,            c:C.green,   bg:C.greenBg },
          { l:"GMP entry price",v:`₹${Math.round(entry)}`,c:C.blue,   bg:C.blueBg },
        ].map(s => (
          <div key={s.l} style={{ background:s.bg, borderRadius:10, padding:"9px 10px", textAlign:"center" }}>
            <div style={{ fontSize:11, color:C.gray, marginBottom:3, textTransform:"uppercase" }}>{s.l}</div>
            <div style={{ fontSize:16, fontWeight:900, color:s.c }}>{s.v}</div>
          </div>
        ))}
      </div>

      {/* 3 scenarios */}
      <div style={{ display:"flex", flexDirection:"column", gap:6, marginBottom:12 }}>
        {[
          { label:`Bull listing — 90% GMP captured → sell Week 1`, price:bull, gain:entry>0?((bull-entry)/entry*100):0, good:true },
          { label:`Base listing — ${Math.round(eff*100)}% GMP (${regime} market)`, price:base, gain:entry>0?((base-entry)/entry*100):0, good:base>=entry },
          { label:"Bad day — GMP −20% at open (hard stop triggered)", price:bear, gain:entry>0?((bear-entry)/entry*100):0, good:false },
        ].map((s,i) => (
          <div key={i} style={{ background:s.good?C.greenBg:C.redBg, borderRadius:9, padding:"10px 12px", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
            <div style={{ fontSize:10, color:s.good?C.green:C.red, fontWeight:600 }}>{s.label}</div>
            <div style={{ textAlign:"right", flexShrink:0 }}>
              <div style={{ fontSize:15, fontWeight:900, color:s.good?C.green:C.red }}>₹{s.price}</div>
              <div style={{ fontSize:10, color:s.good?"#16a34a":"#dc2626" }}>{s.gain>=0?"+":""}{s.gain.toFixed(1)}%</div>
            </div>
          </div>
        ))}
      </div>

      {/* Per-lot P&L */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:6, marginBottom:12 }}>
        {[
          { l:`Max gain · ${lot} shares`,   v:`+₹${Math.abs(Math.round((bull-entry)*lot)).toLocaleString("en-IN")}`, c:C.green, bg:C.greenBg },
          { l:"Hard stop −10%",              v:`−₹${Math.abs(Math.round((stop-entry)*lot)).toLocaleString("en-IN")}`, c:C.red,   bg:C.redBg },
          { l:"D1 exit target",              v:`₹${exitL}–₹${exitH}`,  c:C.blue, bg:C.blueBg },
        ].map(s => (
          <div key={s.l} style={{ background:s.bg, borderRadius:9, padding:"8px 10px", textAlign:"center" }}>
            <div style={{ fontSize:11, color:C.gray, textTransform:"uppercase", marginBottom:3 }}>{s.l}</div>
            <div style={{ fontSize:12, fontWeight:900, color:s.c }}>{s.v}</div>
          </div>
        ))}
      </div>

      {/* Two outcomes */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:6, marginBottom:10 }}>
        <div style={{ background:C.greenBg, borderRadius:9, padding:"9px 12px" }}>
          <div style={{ fontSize:10, fontWeight:800, color:C.green, marginBottom:3 }}>↑ Positive listing</div>
          <div style={{ fontSize:10, color:"#16a34a", lineHeight:1.6 }}>
            Exit ₹{exitL}–₹{exitH} by Week 1.<br/>
            Do not hold beyond Week 1 without base.
          </div>
        </div>
        <div style={{ background:C.redBg, borderRadius:9, padding:"9px 12px" }}>
          <div style={{ fontSize:10, fontWeight:800, color:C.red, marginBottom:3 }}>↓ Negative listing</div>
          <div style={{ fontSize:10, color:"#dc2626", lineHeight:1.6 }}>
            Exit at open − 10% stop = ₹{stop}.<br/>
            No averaging. Wait for IPO base.
          </div>
        </div>
      </div>

      {/* GMP manual update */}
      <div style={{ borderTop:"1px solid #f1f5f9", paddingTop:10, display:"flex", gap:8, alignItems:"center", flexWrap:"wrap" }}>
        <span style={{ fontSize:10, color:C.gray }}>Update GMP:</span>
        <input value={gmpInput} onChange={e=>setGmpInput(e.target.value)} placeholder="₹ e.g. 70"
          style={{ width:90, border:"1px solid #e5e7eb", borderRadius:7, padding:"5px 8px", fontSize:12 }} />
        <button onClick={handleSave}
          style={{ padding:"5px 12px", background:saved?C.green:"#0f172a", border:"none", borderRadius:7, color:"#fff", fontSize:11, fontWeight:700, cursor:"pointer" }}>
          {saved?"✓ Saved":"Set GMP"}
        </button>
        <span style={{ fontSize:12, color:"#9ca3af" }}>Sources: InvestorGain · IPOWatch · 5paisa</span>
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// H: IPO DNA CLASSIFICATION
// ─────────────────────────────────────────────────────────────────────────────
function IpoDna({ ipo }: { ipo:any }) {
  const sector = ipo.sector || ""
  const examples = ipo.similar?.examples || []
  const archetypes: Record<string,{icon:string;color:string;traits:string}> = {
    "Defense":          { icon:"🛡", color:C.blue,   traits:"High-conviction institutional · Defense capex cycle · Strong OB visibility" },
    "EMS/Electronics":  { icon:"⚡", color:C.cyan,   traits:"Revenue visibility · Customer stickiness · Operating leverage play" },
    "Solar":            { icon:"☀", color:C.amber,  traits:"PLI beneficiary · Capacity expansion · Green energy tailwind" },
    "SaaS":             { icon:"💾", color:C.purple, traits:"Recurring revenue · Low capex · High margin scalability" },
    "Financial Infrastructure": { icon:"🏛", color:C.green, traits:"Regulatory moat · Network effect · High ROCE visibility" },
    "NBFC":             { icon:"💰", color:C.green,  traits:"Spread business · Asset quality watch · Growth vs NPAs" },
    "IT Infrastructure":{ icon:"🖥", color:C.blue,   traits:"Domestic enterprise spend · AI/cloud infra · High win rates" },
    "Pharma":           { icon:"💊", color:C.cyan,   traits:"USFDA pipeline · Domestic formulations · Export diversification" },
    "Manufacturing":    { icon:"🏭", color:C.gray,   traits:"China+1 play · Capacity addition · Operating leverage" },
    "Infrastructure EPC":{ icon:"🏗", color:C.amber, traits:"Order book · Execution track record · Working capital watch" },
    "PSU":              { icon:"🏢", color:C.gray,   traits:"Government dividend · Low valuation · Liquidity discount" },
    "Retail/Apparel":   { icon:"🛍", color:C.red,    traits:"Brand building · Unit economics · Store expansion" },
  }
  const match = Object.keys(archetypes).find(k => sector.toLowerCase().includes(k.split("/")[0].toLowerCase()))
  const arch = match || "Manufacturing"
  const meta = archetypes[arch]

  return (
    <Card>
      <SectionTitle text="H · IPO DNA Classification" />
      <div style={{ display:"flex", gap:12, alignItems:"flex-start", marginBottom:14 }}>
        <div style={{ fontSize:36 }}>{meta.icon}</div>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:16, fontWeight:900, color:meta.color }}>{arch}</div>
          <div style={{ fontSize:10, color:C.gray, marginBottom:6 }}>{sector}</div>
          <div style={{ fontSize:10, color:"#374151", lineHeight:1.6 }}>{meta.traits}</div>
        </div>
        <div style={{ textAlign:"center", background:scoreBg(ipo.score?.multibaggerProb||0), borderRadius:10, padding:"8px 14px" }}>
          <div style={{ fontSize:22, fontWeight:900, color:scoreCol(ipo.score?.multibaggerProb||0) }}>{ipo.score?.multibaggerProb||0}%</div>
          <div style={{ fontSize:11, color:C.gray }}>MULTIBAGGER</div>
        </div>
      </div>
      {examples.length > 0 && (
        <div>
          <div style={{ fontSize:12, color:C.gray, marginBottom:8, textTransform:"uppercase", letterSpacing:"0.06em" }}>This IPO behaves like:</div>
          {examples.map((e:any,i:number) => {
            const pcts=[65,22,13]
            return (
              <div key={i} style={{ display:"flex", alignItems:"center", gap:8, marginBottom:5 }}>
                <div style={{ fontSize:10, fontWeight:700, color:"#374151", width:140, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{e.name}</div>
                <div style={{ flex:1, height:6, background:"#e5e7eb", borderRadius:3 }}>
                  <div style={{ width:`${pcts[i]}%`, height:"100%", background:C.blue, borderRadius:3 }} />
                </div>
                <div style={{ fontSize:10, color:C.gray, width:30 }}>{pcts[i]}%</div>
                <div style={{ fontSize:10, color:e.d1Return>=0?C.green:C.red, width:48, textAlign:"right" }}>
                  D1 {e.d1Return>=0?"+":""}{e.d1Return}%
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// I: RISK FLAGS
// ─────────────────────────────────────────────────────────────────────────────
function RiskPanel({ ipo }: { ipo:any }) {
  const s = ipo.score || {}
  const flags  = s.flags  || []
  const greens = s.greens || []
  const level  = s.risk?.level || "MEDIUM"
  const [lFg,lBg] = level==="EXTREME"||level==="HIGH"?[C.red,C.redBg]:level==="MEDIUM"?[C.amber,C.amberBg]:[C.green,C.greenBg]

  return (
    <Card>
      <SectionTitle text="I · Risk Engine" />
      <div style={{ display:"flex", gap:8, alignItems:"center", marginBottom:12 }}>
        <div style={{ background:lBg, border:`1px solid ${lFg}30`, borderRadius:8, padding:"6px 14px" }}>
          <span style={{ fontSize:13, fontWeight:900, color:lFg }}>RISK: {level}</span>
        </div>
        <div style={{ fontSize:11, color:C.gray }}>Score: {s.risk?.score??0}/100</div>
        {s.riskMultiplier < 1 && <div style={{ fontSize:10, color:C.red }}>Penalty: {Number(s.riskMultiplier).toFixed(2)}x applied</div>}
      </div>
      {(flags.length > 0 || greens.length > 0) && (
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10 }}>
          {greens.length > 0 && (
            <div style={{ background:C.greenBg, border:`1px solid ${C.greenBd}`, borderRadius:11, padding:12 }}>
              <div style={{ fontSize:12, fontWeight:800, color:C.green, marginBottom:7, letterSpacing:"0.06em" }}>✅ GREEN FLAGS</div>
              {greens.map((g:string,i:number) => <div key={i} style={{ fontSize:10, color:"#374151", marginBottom:4, lineHeight:1.4 }}>{g}</div>)}
            </div>
          )}
          {flags.length > 0 && (
            <div style={{ background:C.redBg, border:`1px solid ${C.redBd}`, borderRadius:11, padding:12 }}>
              <div style={{ fontSize:12, fontWeight:800, color:C.red, marginBottom:7, letterSpacing:"0.06em" }}>⚠ RISK FLAGS</div>
              {flags.map((f:string,i:number) => <div key={i} style={{ fontSize:10, color:"#374151", marginBottom:4, lineHeight:1.4 }}>{f}</div>)}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// J: POST-LISTING ACTION PLAN
// ─────────────────────────────────────────────────────────────────────────────
function ActionPlan({ ipo }: { ipo:any }) {
  const s = ipo.score || {}
  const qualGood = (s.businessScore||0) >= 75
  const riskLow  = (s.risk?.score||50) < 40
  const listing  = (s.listingScore||0) >= 65
  const ip = ipo.priceBandHigh || ipo.priceBandLow || 0
  const gmp = ipo.gmpPrice || 0
  const exitL = Math.round((ip+gmp)*1.05)
  const exitH = Math.round((ip+gmp)*1.12)

  const steps = [
    { t:"Day 1", icon:"🔔",
      text: listing
        ? `If positive open: sell between 10AM–12PM. Target exit ₹${exitL}–₹${exitH}. Do not wait for close.`
        : "If opens negative: exit at market immediately. Apply hard stop −10%. Zero averaging." },
    { t:"Week 1", icon:"📊",
      text:"Trail stop at opening price. Book 50% if gain >15%. Watch volume — continuation only on rising volume." },
    { t:"Month 1", icon:"⏳",
      text:"Do not average down. Wait for IPO base formation (price consolidation 3–6 weeks after listing). Re-enter only on clean breakout with volume." },
    { t:"Long Term", icon: qualGood&&riskLow?"🌱":"⚠",
      text: qualGood&&riskLow
        ? `Quality ${s.businessScore}/100 + Risk ${s.risk?.score}/100 → eligible long-term hold. Review quarterly results. Exit if ROCE drops below 15%.`
        : `Quality ${s.businessScore||0}/100 — not yet a long-term hold. Exit on listing pop. Watch for 2–3 quarters before re-evaluating.` },
  ]

  return (
    <Card>
      <SectionTitle text="J · Post-Listing Action Plan" />
      {steps.map((step,i) => (
        <div key={i} style={{ display:"flex", gap:12, padding:"9px 11px", background:C.grayBg, borderRadius:9, marginBottom:6 }}>
          <div style={{ fontSize:16 }}>{step.icon}</div>
          <div>
            <div style={{ fontSize:12, fontWeight:800, color:C.gray, textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:3 }}>{step.t}</div>
            <div style={{ fontSize:11, color:"#374151", lineHeight:1.6 }}>{step.text}</div>
          </div>
        </div>
      ))}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// DUAL MODEL SCORES
// ─────────────────────────────────────────────────────────────────────────────
function DualModels({ ipo }: { ipo:any }) {
  const s = ipo.score || {}
  return (
    <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:12 }}>
      {/* Model 1 */}
      <Card style={{ marginBottom:0 }}>
        <div style={{ fontSize:12, fontWeight:800, color:"#374151", marginBottom:10, letterSpacing:"0.06em" }}>MODEL 1 · LISTING ENGINE</div>
        <div style={{ fontSize:28, fontWeight:900, color:scoreCol(s.listingScore??0), lineHeight:1 }}>{s.listingScore??0}</div>
        <div style={{ fontSize:10, fontWeight:700, color:scoreCol(s.listingScore??0), marginBottom:10 }}>{s.listingRating||"—"}</div>
        {Object.entries(s.listingComponents||{}).map(([k,v]:any) => (
          <div key={k} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:4 }}>
            <span style={{ fontSize:12, color:C.gray, textTransform:"capitalize" }}>{k.replace(/([A-Z])/g," $1")}</span>
            <div style={{ display:"flex", alignItems:"center", gap:4 }}>
              <div style={{ width:50, height:3, background:"#e5e7eb", borderRadius:2 }}>
                <div style={{ width:`${Math.round((v/25)*100)}%`, height:"100%", background:C.blue, borderRadius:2 }} />
              </div>
              <span style={{ fontSize:12, fontWeight:700, color:"#374151", minWidth:18, textAlign:"right" }}>{v}</span>
            </div>
          </div>
        ))}
      </Card>
      {/* Model 2 */}
      <Card style={{ marginBottom:0 }}>
        <div style={{ fontSize:12, fontWeight:800, color:"#374151", marginBottom:10, letterSpacing:"0.06em" }}>MODEL 2 · BUSINESS QUALITY</div>
        <div style={{ fontSize:28, fontWeight:900, color:scoreCol(s.businessScore??0), lineHeight:1 }}>{s.businessScore??0}</div>
        <div style={{ fontSize:10, fontWeight:700, color:scoreCol(s.businessScore??0), marginBottom:10 }}>{s.businessRating||"—"}</div>
        {Object.entries(s.businessComponents||{}).map(([k,v]:any) => (
          <div key={k} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:4 }}>
            <span style={{ fontSize:12, color:C.gray, textTransform:"capitalize" }}>{k.replace(/([A-Z])/g," $1")}</span>
            <div style={{ display:"flex", alignItems:"center", gap:4 }}>
              <div style={{ width:50, height:3, background:"#e5e7eb", borderRadius:2 }}>
                <div style={{ width:`${Math.round((v/20)*100)}%`, height:"100%", background:C.green, borderRadius:2 }} />
              </div>
              <span style={{ fontSize:12, fontWeight:700, color:"#374151", minWidth:18, textAlign:"right" }}>{v}</span>
            </div>
          </div>
        ))}
        {(s.multibaggerProb||0) > 0 && (
          <div style={{ marginTop:8, padding:"6px 10px", background:s.multibaggerProb>=60?C.greenBg:C.grayBg, borderRadius:8 }}>
            <div style={{ fontSize:11, color:C.gray }}>Multibagger probability</div>
            <div style={{ fontSize:14, fontWeight:900, color:s.multibaggerProb>=60?C.green:"#374151" }}>{s.multibaggerProb}%</div>
          </div>
        )}
      </Card>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MANAGEMENT QUALITY
// ─────────────────────────────────────────────────────────────────────────────
function MgmtPanel({ ipo }: { ipo:any }) {
  const s = ipo.score || {}
  const mgmt = s.managementScore ?? 0
  if (!mgmt) return null
  return (
    <Card>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:12 }}>
        <SectionTitle text="Management Quality Score" />
        <div style={{ textAlign:"center", background:scoreBg(mgmt), borderRadius:9, padding:"4px 12px" }}>
          <div style={{ fontSize:20, fontWeight:900, color:scoreCol(mgmt) }}>{mgmt}</div>
          <div style={{ fontSize:11, color:C.gray }}>/ 100</div>
        </div>
      </div>
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:4, marginBottom:10 }}>
        {Object.entries(s.managementComponents||{}).map(([k,v]:any) => (
          <div key={k} style={{ display:"flex", justifyContent:"space-between", padding:"5px 0", borderBottom:"1px solid #f3f4f6" }}>
            <span style={{ fontSize:12, color:C.gray, textTransform:"capitalize" }}>{k.replace(/([A-Z])/g," $1").trim()}</span>
            <span style={{ fontSize:12, fontWeight:700, color:v>=8?C.green:v>=5?"#374151":C.red }}>{v}</span>
          </div>
        ))}
      </div>
      {s.managementPositives?.map((p:string,i:number) => <div key={i} style={{ fontSize:10, color:C.green, marginBottom:3 }}>✅ {p}</div>)}
      {s.managementFlags?.map((f:string,i:number) => <div key={i} style={{ fontSize:10, color:C.red, marginBottom:3 }}>⚠ {f}</div>)}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PDF UPLOAD
// ─────────────────────────────────────────────────────────────────────────────
function PdfUpload({ onData }: { onData:(d:any)=>void }) {
  const ref = useRef<HTMLInputElement>(null)
  const [state, setState] = useState<"idle"|"loading"|"done"|"error">("idle")
  const [msg, setMsg] = useState("")

  const handle = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setState("loading")
    setMsg(`Reading ${file.name}…`)
    try {
      const fd = new FormData()
      fd.append("file", file)
      const res = await fetch("/api/ipo/upload", { method:"POST", body:fd })
      const d = await res.json()
      if (d.ok) {
        setState("done")
        setMsg(d.message)
        onData(d.extracted)
      } else {
        setState("error")
        setMsg(`Error: ${d.error}`)
      }
    } catch (err: any) {
      setState("error")
      setMsg(`Error: ${err.message}`)
    }
    // Reset so same file can be re-uploaded
    if (ref.current) ref.current.value = ""
  }

  return (
    <div style={{ border:"1.5px dashed #cbd5e1", borderRadius:12, padding:"12px 16px", background:"#FAFAF8", marginBottom:12 }}>
      <div style={{ display:"flex", alignItems:"center", gap:12, flexWrap:"wrap" }}>
        <button onClick={() => ref.current?.click()}
          style={{ padding:"8px 16px", background:"#0f172a", color:"#f8fafc", border:"none", borderRadius:8, fontSize:12, fontWeight:700, cursor:"pointer" }}>
          📄 Upload SBI Sec / Broker PDF
        </button>
        <div style={{ fontSize:11, color:
          state==="loading"?"#3b82f6":state==="done"?C.green:state==="error"?C.red:"#64748b" }}>
          {state==="idle"  && "Upload any broker research note — auto-fills all engine values"}
          {state==="loading" && `⏳ ${msg}`}
          {state==="done"    && `✅ ${msg}`}
          {state==="error"   && `❌ ${msg}`}
        </div>
        <input ref={ref} type="file" accept=".pdf,.txt,.PDF" onChange={handle} style={{ display:"none" }} />
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SCRAPE BUTTON
// ─────────────────────────────────────────────────────────────────────────────
function ScrapeButton({ ipoName, onData }: { ipoName:string; onData:(d:any)=>void }) {
  const [state, setState] = useState<"idle"|"loading"|"done">("idle")
  const run = async () => {
    setState("loading")
    try {
      const res = await fetch("/api/ipo/scrape", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ name:ipoName })
      })
      const d = await res.json()
      if (d.ok && d.results?.[0]) {
        onData(d.results[0])
        setState("done")
      } else setState("idle")
    } catch { setState("idle") }
    setTimeout(() => setState("idle"), 4000)
  }
  return (
    <button onClick={run} disabled={state==="loading"}
      style={{ padding:"6px 13px", background:state==="done"?C.green:C.blue, color:"#fff", border:"none", borderRadius:7, fontSize:10, fontWeight:700, cursor:"pointer", opacity:state==="loading"?0.7:1 }}>
      {state==="loading"?"⏳ Fetching…":state==="done"?"✅ Updated":"🔄 Fetch Live Data"}
    </button>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// IPO LIST CARD
// ─────────────────────────────────────────────────────────────────────────────
function IpoCard({ ipo, onClick }: { ipo:any; onClick:()=>void }) {
  const s = ipo.score || {}
  const rec = s.recommendation || "Watch — Selective Apply"
  const [recFg,,recLabel] = REC[rec] || [C.gray,C.grayBg,"WATCH"]
  const ip = ipo.priceBandHigh || ipo.priceBandLow || 0
  const gmpEntry = ipo.gmpPrice ? ip + ipo.gmpPrice : null
  const statusCol: Record<string,string> = { OPEN:C.green, UPCOMING:C.blue, LISTED:C.gray, CLOSED:C.gray }
  const sCol = statusCol[ipo.status||""] || C.gray

  return (
    <div onClick={onClick}
      style={{ background:"#fff", border:"1px solid #e5e7eb", borderRadius:14, overflow:"hidden", cursor:"pointer", transition:"box-shadow .15s,transform .15s" }}
      onMouseEnter={e=>{const d=e.currentTarget as HTMLDivElement;d.style.boxShadow="0 8px 24px rgba(0,0,0,0.10)";d.style.transform="translateY(-1px)"}}
      onMouseLeave={e=>{const d=e.currentTarget as HTMLDivElement;d.style.boxShadow="none";d.style.transform="none"}}>

      <div style={{ height:3, background:sCol }} />
      <div style={{ padding:"12px 14px 11px" }}>
        {/* Name + recommendation */}
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:9 }}>
          <div style={{ flex:1, paddingRight:8 }}>
            <div style={{ fontSize:13, fontWeight:800, color:"#0f172a", lineHeight:1.3, marginBottom:1 }}>{ipo.name}</div>
            <div style={{ fontSize:12, color:C.gray }}>{ipo.sector} · ₹{ipo.issueSize}Cr</div>
          </div>
          <div style={{ background:scoreBg(s.listingScore??0), border:`1.5px solid ${scoreCol(s.listingScore??0)}30`, borderRadius:9, padding:"5px 9px", flexShrink:0, textAlign:"center" }}>
            <div style={{ fontSize:18, fontWeight:900, color:scoreCol(s.listingScore??0), lineHeight:1 }}>{s.listingScore??0}</div>
            <div style={{ fontSize:11, fontWeight:700, color:scoreCol(s.listingScore??0), marginTop:1, letterSpacing:"0.04em" }}>LISTING</div>
          </div>
        </div>

        {/* GMP block */}
        {gmpEntry ? (
          <div style={{ background:C.greenBg, borderRadius:9, padding:"8px 11px", marginBottom:8 }}>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:4 }}>
              {[
                { l:"Issue",  v:`₹${ip}`,               c:"#374151" },
                { l:"GMP",    v:`+₹${ipo.gmpPrice}`,    c:C.green },
                { l:"Entry",  v:`₹${Math.round(gmpEntry)}`, c:C.blue },
              ].map(s => (
                <div key={s.l} style={{ textAlign:"center" }}>
                  <div style={{ fontSize:11, color:C.gray, marginBottom:1 }}>{s.l}</div>
                  <div style={{ fontSize:12, fontWeight:800, color:s.c }}>{s.v}</div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ background:C.grayBg, border:"1px dashed #e5e7eb", borderRadius:9, padding:"6px 11px", marginBottom:8, textAlign:"center" }}>
            <div style={{ fontSize:10, color:C.gray }}>No GMP · tap to add</div>
          </div>
        )}

        {/* 3 model scores */}
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:5, marginBottom:8 }}>
          {[
            { l:"Listing",  v:s.listingScore??0,   bg:C.blueBg },
            { l:"Business", v:s.businessScore??0,  bg:C.greenBg },
            { l:"Mgmt",     v:s.managementScore??0,bg:C.purpleBg },
          ].map(t => (
            <div key={t.l} style={{ background:t.bg, borderRadius:7, padding:"5px 8px", textAlign:"center" }}>
              <div style={{ fontSize:11, color:C.gray, marginBottom:1 }}>{t.l}</div>
              <div style={{ fontSize:15, fontWeight:900, color:scoreCol(t.v) }}>{t.v||"?"}</div>
            </div>
          ))}
        </div>

        {/* Tags */}
        <div style={{ display:"flex", gap:4, flexWrap:"wrap" }}>
          <Tag text={ipo.status} color={sCol} bg={sCol+"18"} />
          <Tag text={recLabel} color={recFg} bg={recFg+"15"} />
          {ipo.brokerReco && <Tag text={`SBI ${ipo.brokerReco}`} color={C.green} bg={C.greenBg} />}
          {(ipo.freshIssuePct??0)===0 && <Tag text="100% OFS" color={C.red} bg={C.redBg} />}
          {(s.multibaggerProb??0)>=65 && <Tag text="Multibagger" color={C.purple} bg={C.purpleBg} />}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// DETAIL VIEW — full command center
// ─────────────────────────────────────────────────────────────────────────────
function IpoDetail({ ipo: _ipo, onBack }: { ipo:any; onBack:()=>void }) {
  const [ipo, setIpo] = useState(_ipo)

  const merge = (d: any) => setIpo((prev: any) => ({ ...prev, ...d }))

  return (
    <div>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
        <button onClick={onBack}
          style={{ padding:"7px 14px", background:C.grayBg, border:"1px solid #e5e7eb", borderRadius:8, cursor:"pointer", fontSize:12, color:"#374151", fontWeight:600 }}>
          ← All IPOs
        </button>
        <ScrapeButton ipoName={ipo.name} onData={merge} />
      </div>

      {/* PDF Upload */}
      <HeroPanel ipo={ipo} />
      <PdfUpload onData={merge} />
      <DrhpUpload ipoName={ipo.name} />
      <ConvictionPanel ipo={ipo} />
      <RegimeWidget regime={ipo.score?.regime} />
      <SubscriptionTracker ipo={ipo} />
      <SimilarityEngine ipo={ipo} />
      <MultibaggerEngine ipo={ipo} />
      <AnchorHeatmap ipo={ipo} />
      <IssueBanner ipo={ipo} />
      <TradingEngine ipo={ipo} onGmpUpdate={(v) => setIpo((p: any) => ({ ...p, gmpPrice:v }))} />
      <IpoDna ipo={ipo} />
      <DualModels ipo={ipo} />
      <MgmtPanel ipo={ipo} />
      <RiskPanel ipo={ipo} />
      <ActionPlan ipo={ipo} />
      <IpoMemoPanel ipo={ipo} />

      {/* Live Tape Engine — Section 19 */}
      <LiveTape ipo={ipo} />

      {/* Contrarian engine */}
      {(ipo.score?.contraryScore||0) >= 50 && (
        <Card style={{ background:C.purpleBg, border:`2px solid ${C.purpleBd}` }}>
          <div style={{ fontSize:10, fontWeight:900, color:C.purple, marginBottom:8, letterSpacing:"0.06em" }}>🎯 CONTRARIAN ENGINE</div>
          <div style={{ display:"flex", gap:14, alignItems:"center" }}>
            <div style={{ textAlign:"center" }}>
              <div style={{ fontSize:30, fontWeight:900, color:C.purple }}>{ipo.score.contraryScore}</div>
              <div style={{ fontSize:11, color:C.gray }}>score</div>
            </div>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:11, color:"#374151", lineHeight:1.6, marginBottom:6 }}>
                {ipo.score.contraryScore >= 70
                  ? "Weak subscription + strong fundamentals. Post-listing base formation opportunity."
                  : "Monitor post-listing for IPO base entry."}
              </div>
              <div style={{ fontSize:12, fontWeight:800, color:C.purple }}>{ipo.score.postListingRating}</div>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────
// SPRINT 2 — DRHP RED FLAG SCANNER
// ─────────────────────────────────────────────────────────────────────────────
function DrhpUpload({ ipoName }: { ipoName: string }) {
  const dRef = useRef<HTMLInputElement>(null)
  const [state, setState] = useState<"idle"|"loading"|"done"|"error">("idle")
  const [msg, setMsg] = useState("")
  const [flags, setFlags] = useState<any>(null)

  const handle = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setState("loading")
    setMsg(`Scanning ${file.name} for red flags…`)
    try {
      const fd = new FormData()
      fd.append("file", file)
      const res = await fetch("/api/ipo/drhp", { method: "POST", body: fd })
      const d = await res.json()
      if (d.ok) {
        setState("done")
        setMsg(`Scan complete — ${d.flags.overallFlag} overall · ${d.sizeMB}MB`)
        setFlags(d.flags)
      } else if (d.tooLarge) {
        setState("error")
        setMsg(d.error)
      } else {
        setState("error")
        setMsg(d.error || "Scan failed")
      }
    } catch (err: any) {
      setState("error")
      setMsg(err.message)
    }
    if (dRef.current) dRef.current.value = ""
  }

  const fCol  = (f: string) => f === "GREEN" ? C.green  : f === "AMBER" ? C.amber  : f === "RED" ? C.red  : C.gray
  const fBg   = (f: string) => f === "GREEN" ? C.greenBg : f === "AMBER" ? C.amberBg : f === "RED" ? C.redBg : C.grayBg
  const fBd   = (f: string) => f === "GREEN" ? C.greenBd : f === "AMBER" ? C.amberBd : f === "RED" ? C.redBd : C.grayBd
  const fIcon = (f: string) => f === "GREEN" ? "✅" : f === "AMBER" ? "⚠️" : f === "RED" ? "🔴" : "—"

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ border: "1.5px dashed #c4b5fd", borderRadius: 12, padding: "10px 16px", background: "#faf5ff", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <button onClick={() => dRef.current?.click()}
          style={{ padding: "8px 16px", background: C.purple, color: "#fff", border: "none", borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
          📋 Upload DRHP / Prospectus
        </button>
        <div style={{ fontSize: 11, color: state === "loading" ? "#3b82f6" : state === "done" ? C.green : state === "error" ? C.red : "#64748b", flex: 1 }}>
          {state === "idle"    && "Red flag scan: RPT% · Pledge · Litigation · Auditor · Customer concentration · Cash flow quality"}
          {state === "loading" && `⏳ ${msg}`}
          {state === "done"   && `✅ ${msg}`}
          {state === "error"  && `❌ ${msg}`}
        </div>
        <input ref={dRef} type="file" accept=".pdf,.PDF" onChange={handle} style={{ display: "none" }} />
      </div>

      {flags && (
        <Card style={{ marginTop: 8, border: `2px solid ${fCol(flags.overallFlag)}30` }}>
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
            <div>
              <SectionTitle text="DRHP Red Flag Scanner" />
              {flags.companyName && <div style={{ fontSize: 11, color: C.gray, marginTop: -8, marginBottom: 8 }}>{flags.companyName} · ₹{flags.issueSize}</div>}
            </div>
            <div style={{ textAlign: "center", background: fBg(flags.overallFlag), borderRadius: 10, padding: "8px 18px", border: `2px solid ${fBd(flags.overallFlag)}` }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: fCol(flags.overallFlag), lineHeight: 1 }}>{flags.overallRiskScore}</div>
              <div style={{ fontSize: 7, color: C.gray, marginTop: 2 }}>RISK SCORE</div>
              <div style={{ fontSize: 11, fontWeight: 800, color: fCol(flags.overallFlag), marginTop: 2 }}>{flags.overallFlag}</div>
            </div>
          </div>

          {/* OFS / Fresh bar */}
          {(flags.freshIssuePct || flags.ofsPct) && (
            <div style={{ display: "flex", height: 18, borderRadius: 9, overflow: "hidden", marginBottom: 12 }}>
              {flags.freshIssuePct > 0 && (
                <div style={{ width: `${flags.freshIssuePct}%`, background: C.green, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  {flags.freshIssuePct > 10 && <span style={{ fontSize: 8, color: "#fff", fontWeight: 800 }}>{flags.freshIssuePct}% Fresh</span>}
                </div>
              )}
              <div style={{ flex: 1, background: "#fca5a5", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ fontSize: 8, color: "#7f1d1d", fontWeight: 800 }}>{flags.ofsPct}% OFS</span>
              </div>
            </div>
          )}

          {/* 6-category grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 12 }}>
            {[
              { label: "Related Party Txns",      f: flags.rptAnalysis?.rptFlag,          detail: flags.rptAnalysis?.totalRptPct,              note: flags.rptAnalysis?.rptNote },
              { label: "Promoter Pledge",          f: flags.promoterPledge?.pledgeFlag,     detail: flags.promoterPledge?.pledgePct,              note: flags.promoterPledge?.pledgeNote },
              { label: "Litigation Risk",          f: flags.litigationRisk?.litigationFlag, detail: flags.litigationRisk?.totalContingentLiability, note: flags.litigationRisk?.litigationNote },
              { label: "Auditor Quality",          f: flags.auditorQuality?.auditorFlag,    detail: flags.auditorQuality?.auditorName,            note: flags.auditorQuality?.auditorNote },
              { label: "Customer Concentration",   f: flags.customerConcentration?.concentrationFlag, detail: flags.customerConcentration?.top5CustomerPct, note: flags.customerConcentration?.concentrationNote },
              { label: "Cash Flow Quality",        f: flags.cashFlowQuality?.cashFlag,      detail: flags.cashFlowQuality?.cffoVsPatTrend,        note: flags.cashFlowQuality?.cashNote },
            ].map(cat => {
              const f = cat.f || "—"
              return (
                <div key={cat.label} style={{ background: fBg(f), border: `1px solid ${fBd(f)}`, borderRadius: 9, padding: "10px 11px" }}>
                  <div style={{ fontSize: 7, color: C.gray, textTransform: "uppercase" as const, letterSpacing: "0.06em", marginBottom: 4 }}>{cat.label}</div>
                  <div style={{ fontSize: 18, marginBottom: 3 }}>{fIcon(f)}</div>
                  {cat.detail && <div style={{ fontSize: 10, fontWeight: 700, color: fCol(f) }}>{cat.detail}</div>}
                  {cat.note && <div style={{ fontSize: 9, color: "#374151", lineHeight: 1.4, marginTop: 4 }}>{cat.note}</div>}
                </div>
              )
            })}
          </div>

          {/* Debt strip */}
          {flags.debtStructure && (
            <div style={{ display: "flex", gap: 12, padding: "8px 11px", background: C.grayBg, borderRadius: 8, marginBottom: 10, flexWrap: "wrap" }}>
              <div><span style={{ fontSize: 8, color: C.gray }}>Total Debt: </span><strong style={{ fontSize: 11, color: fCol(flags.debtStructure.debtFlag) }}>{flags.debtStructure.totalDebt || "N/A"}</strong></div>
              <div><span style={{ fontSize: 8, color: C.gray }}>D/E: </span><strong style={{ fontSize: 11, color: fCol(flags.debtStructure.debtFlag) }}>{flags.debtStructure.debtEquity || "N/A"}</strong></div>
              {flags.debtStructure.covenants && <div style={{ fontSize: 9, color: C.amber }}>⚠ {flags.debtStructure.covenants}</div>}
            </div>
          )}

          {/* Red flags */}
          {flags.topRedFlags?.length > 0 && (
            <div style={{ background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: 9, padding: "10px 12px", marginBottom: 8 }}>
              <div style={{ fontSize: 9, fontWeight: 800, color: C.red, marginBottom: 6, letterSpacing: "0.06em" }}>🚨 TOP RED FLAGS</div>
              {flags.topRedFlags.map((f: string, i: number) => (
                <div key={i} style={{ fontSize: 10, color: "#374151", marginBottom: 4, lineHeight: 1.4 }}>✗ {f}</div>
              ))}
            </div>
          )}

          {/* Green flags */}
          {flags.greenFlags?.length > 0 && (
            <div style={{ background: C.greenBg, border: `1px solid ${C.greenBd}`, borderRadius: 9, padding: "10px 12px", marginBottom: 8 }}>
              <div style={{ fontSize: 9, fontWeight: 800, color: C.green, marginBottom: 6, letterSpacing: "0.06em" }}>✅ GREEN FLAGS</div>
              {flags.greenFlags.map((f: string, i: number) => (
                <div key={i} style={{ fontSize: 10, color: "#374151", marginBottom: 4, lineHeight: 1.4 }}>✓ {f}</div>
              ))}
            </div>
          )}

          {flags.summary && (
            <div style={{ fontSize: 11, color: "#374151", lineHeight: 1.7, padding: "9px 11px", background: C.grayBg, borderRadius: 8 }}>
              {flags.summary}
            </div>
          )}
        </Card>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SPRINT 2 — IPO AI INVESTMENT MEMO (Section K)
// UI DECISION: Inline panel after ActionPlan — analyst reasoning: research notes
// belong in the data flow, not in a modal that blocks the anchor heatmap.
// Matches Bloomberg terminal UX: scrollable sections, not popups.
// ─────────────────────────────────────────────────────────────────────────────
function IpoMemoPanel({ ipo }: { ipo: any }) {
  const [memo, setMemo] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const generate = async () => {
    setLoading(true)
    setError("")
    try {
      const res = await fetch("/api/ipo/memo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ipo })
      })
      const d = await res.json()
      if (d.memo) setMemo(d.memo)
      else setError(d.error || "Generation failed")
    } catch (e: any) {
      setError(e.message)
    }
    setLoading(false)
  }

  const rCol = (r: string) =>
    r?.includes("AGGRESSIVELY") ? C.green : r?.includes("AVOID") ? C.red :
    r?.includes("TRADE") ? C.cyan : r?.includes("WATCH") ? C.amber : C.blue
  const rBg = (r: string) =>
    r?.includes("AGGRESSIVELY") ? C.greenBg : r?.includes("AVOID") ? C.redBg :
    r?.includes("TRADE") ? C.cyanBg : r?.includes("WATCH") ? C.amberBg : C.blueBg
  const confCol = (c: string) => c === "HIGH" ? C.green : c === "LOW" ? C.red : C.amber

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: memo ? 12 : 0 }}>
        <SectionTitle text="K · AI Investment Memo" />
        <button onClick={generate} disabled={loading}
          style={{ padding: "7px 16px", background: memo ? "transparent" : "#0f172a", border: `1px solid ${memo ? "#e5e7eb" : "#0f172a"}`, borderRadius: 8, color: memo ? C.gray : "#fff", fontSize: 11, fontWeight: 700, cursor: loading ? "default" : "pointer", opacity: loading ? 0.6 : 1 }}>
          {loading ? "⏳ Writing memo…" : memo ? "↻ Regenerate" : "⚡ Generate Memo"}
        </button>
      </div>

      {!memo && !loading && !error && (
        <div style={{ textAlign: "center", padding: "20px 0 8px", color: C.gray }}>
          <div style={{ fontSize: 28, marginBottom: 6 }}>📋</div>
          <div style={{ fontSize: 11, lineHeight: 1.7 }}>
            Executive Summary · Bull/Bear Case · Valuation Analysis<br />
            Anchor Quality · IPO DNA Match · Listing Day Strategy
          </div>
        </div>
      )}

      {loading && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "18px 0", justifyContent: "center", color: C.gray, fontSize: 11 }}>
          <div style={{ width: 14, height: 14, border: "2px solid #e5e7eb", borderTopColor: C.blue, borderRadius: "50%", animation: "spin .7s linear infinite" }} />
          Writing institutional Investment Committee memo for {ipo.name}…
        </div>
      )}

      {error && (
        <div style={{ color: C.red, fontSize: 11, padding: "8px 12px", background: C.redBg, borderRadius: 8, marginTop: 8 }}>❌ {error}</div>
      )}

      {memo && (
        <div className="fade">
          {/* Recommendation hero — dark card */}
          <div style={{ background: "#0f172a", borderRadius: 12, padding: "14px 18px", marginBottom: 12, display: "flex", gap: 14, alignItems: "flex-start", flexWrap: "wrap" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 8, color: "#475569", letterSpacing: "0.08em", textTransform: "uppercase" as const, marginBottom: 6 }}>
                INVESTMENT COMMITTEE MEMO · {ipo.name?.toUpperCase()}
              </div>
              <div style={{ fontSize: 13, color: "#cbd5e1", lineHeight: 1.75 }}>{memo.executiveSummary}</div>
              {memo.confidenceReason && (
                <div style={{ fontSize: 10, color: "#475569", marginTop: 8, fontStyle: "italic" }}>{memo.confidenceReason}</div>
              )}
            </div>
            <div style={{ background: rBg(memo.recommendation), border: `2px solid ${rCol(memo.recommendation)}`, borderRadius: 12, padding: "10px 14px", textAlign: "center", flexShrink: 0, minWidth: 130 }}>
              <div style={{ fontSize: 11, fontWeight: 900, color: rCol(memo.recommendation), letterSpacing: "0.03em", lineHeight: 1.3 }}>
                {memo.recommendation}
              </div>
              <div style={{ fontSize: 9, color: C.gray, marginTop: 5 }}>
                Confidence: <span style={{ color: confCol(memo.confidence), fontWeight: 800 }}>{memo.confidence}</span>
              </div>
            </div>
          </div>

          {/* Key metrics strip */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 12 }}>
            {[
              { l: "Listing Target", v: memo.targetListingGain,  c: C.green  },
              { l: "12M Target",     v: memo.targetT12M,         c: C.purple },
              { l: "Position Size",  v: memo.positionSizing,     c: C.blue   },
              { l: "Exit When",      v: memo.exitCondition?.slice(0, 28) + "…", c: C.gray },
            ].map(s => (
              <div key={s.l} style={{ background: C.grayBg, borderRadius: 9, padding: "8px 10px", textAlign: "center" }}>
                <div style={{ fontSize: 7, color: C.gray, textTransform: "uppercase" as const, marginBottom: 3 }}>{s.l}</div>
                <div style={{ fontSize: 11, fontWeight: 800, color: s.c, lineHeight: 1.3 }}>{s.v}</div>
              </div>
            ))}
          </div>

          {/* Bull / Bear */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
            <div style={{ background: C.greenBg, border: `1px solid ${C.greenBd}`, borderRadius: 10, padding: "11px 13px" }}>
              <div style={{ fontSize: 9, fontWeight: 800, color: C.green, marginBottom: 8, letterSpacing: "0.06em" }}>🐂 BULL CASE</div>
              {memo.bullCase?.map((b: string, i: number) => (
                <div key={i} style={{ fontSize: 10, color: "#374151", marginBottom: 5, lineHeight: 1.5, paddingLeft: 8, borderLeft: `2px solid ${C.green}` }}>✓ {b}</div>
              ))}
            </div>
            <div style={{ background: C.redBg, border: `1px solid ${C.redBd}`, borderRadius: 10, padding: "11px 13px" }}>
              <div style={{ fontSize: 9, fontWeight: 800, color: C.red, marginBottom: 8, letterSpacing: "0.06em" }}>🐻 BEAR CASE</div>
              {memo.bearCase?.map((b: string, i: number) => (
                <div key={i} style={{ fontSize: 10, color: "#374151", marginBottom: 5, lineHeight: 1.5, paddingLeft: 8, borderLeft: `2px solid ${C.red}` }}>✗ {b}</div>
              ))}
            </div>
          </div>

          {/* Analysis sections */}
          {[
            { title: "Valuation Analysis",      icon: "📊", text: memo.valuationAnalysis,   color: C.blue,   bg: C.blueBg   },
            { title: "Anchor Quality Analysis", icon: "⚓", text: memo.anchorAnalysis,      color: C.purple, bg: C.purpleBg },
            { title: "IPO DNA Match",           icon: "🧬", text: memo.dnaMatch,            color: C.cyan,   bg: C.cyanBg   },
            { title: "Listing Day Strategy",    icon: "📅", text: memo.listingDayStrategy,  color: C.amber,  bg: C.amberBg  },
          ].map(s => (
            <div key={s.title} style={{ background: s.bg, border: `1px solid ${s.color}25`, borderRadius: 9, padding: "10px 12px", marginBottom: 8 }}>
              <div style={{ fontSize: 9, fontWeight: 800, color: s.color, marginBottom: 4, letterSpacing: "0.06em" }}>{s.icon} {s.title.toUpperCase()}</div>
              <div style={{ fontSize: 11, color: "#374151", lineHeight: 1.7 }}>{s.text}</div>
            </div>
          ))}

          {/* Key risk */}
          {memo.keyRisk && (
            <div style={{ display: "flex", gap: 8, padding: "9px 12px", background: "#fff7ed", border: `1px solid ${C.amberBd}`, borderRadius: 9, marginBottom: 8, alignItems: "flex-start" }}>
              <span style={{ fontSize: 14 }}>⚡</span>
              <div>
                <div style={{ fontSize: 8, fontWeight: 800, color: C.amber, letterSpacing: "0.06em", marginBottom: 2 }}>BIGGEST RISK</div>
                <div style={{ fontSize: 11, color: "#374151" }}>{memo.keyRisk}</div>
              </div>
            </div>
          )}

          {/* Data gaps */}
          {memo.missing?.length > 0 && (
            <div style={{ background: C.grayBg, border: `1px solid ${C.grayBd}`, borderRadius: 8, padding: "8px 12px" }}>
              <div style={{ fontSize: 8, fontWeight: 800, color: C.gray, marginBottom: 5, letterSpacing: "0.06em" }}>⚠ DATA GAPS — UPLOAD DRHP OR SBI SEC REPORT TO FILL</div>
              {memo.missing.map((m: string, i: number) => (
                <div key={i} style={{ fontSize: 10, color: C.gray, marginBottom: 3 }}>→ {m}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// SPRINT 3 — SUBSCRIPTION DAY TRACKER
// Paste this entire block into AACapitalApp.tsx BEFORE the // ═══════════════════════════════════════════════════════════════════
// CAPITAL COMPOUNDING ENGINE
// Philosophy: 20 high-conviction IPOs → 30%+ returns → ₹1Cr
// Two-Mode Strategy: IPO Mode ↔ Recovery Mode (Guru stocks)
// Every decision answers: Does this help compound capital?
// MAIN PAGE
// ─────────────────────────────────────────────────────────────────────────────
function IpoPage() {
  const [ipos, setIpos]     = useState<any[]>([])
  const [dash, setDash]     = useState<any>(null)
  const [loading, setLoad]  = useState(true)
  const [sel, setSel]       = useState<any>(null)
  const [view, setView]     = useState<"list"|"detail">("list")
  const [filter, setFilter] = useState("ALL")
  const [search, setSearch] = useState("")
  const [showUpload, setShowUpload] = useState(false)

  useEffect(() => {
    // Try live BSE data first, fall back to DB data
    Promise.all([
      fetch("/api/ipo/live").then(r=>r.json()).catch(()=>null),
      fetch("/api/ipo").then(r=>r.json()).catch(()=>null),
    ]).then(([liveData, dbData]) => {
      if (liveData?.ok && liveData.ipos?.length > 0) {
        // Map live BSE data to IpoPage format
        const mapped = liveData.ipos.map((ipo:any) => ({
          name:    ipo.company,
          sector:  ipo.category || "Unknown",
          size:    ipo.issue_size_cr || 0,
          band:    ipo.price_band_high
                   ? `₹${ipo.price_band_low}–${ipo.price_band_high}`
                   : "TBA",
          listing: ipo.listing_date || ipo.close_date || "TBA",
          status:  ipo.status,
          gmp:     ipo.gmp ? `+${ipo.gmp}` : "—",
          qib:     "—", hni: "—", retail: "—",
          anchor:  [],
          drhp:    false,
          ofsP:    0,
          source:  "live",
          listingGainPct: ipo.listing_gain_pct ?? null,
        }))
        // Add any DB ipos not in live feed (historical scored ones)
        const dbIpos = (dbData?.ipos || []).filter((d:any) =>
          !mapped.find((m:any) => m.name.toLowerCase().includes(d.name?.toLowerCase()?.slice(0,8)))
        )
        setIpos([...mapped, ...dbIpos])
        setDash(dbData?.dashboard || null)
      } else {
        // Fall back to DB data
        setIpos(dbData?.ipos || DEFAULT_IPOS)
        setDash(dbData?.dashboard || null)
      }
      setLoad(false)
    }).catch(() => { setIpos(DEFAULT_IPOS); setLoad(false) })
  }, [])

  const filtered = ipos.filter(i => {
    const mf = filter==="ALL" || i.status===filter
    const ms = !search || i.name.toLowerCase().includes(search.toLowerCase()) || (i.sector||"").toLowerCase().includes(search.toLowerCase())
    return mf && ms
  })

  if (loading) return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center", height:200, gap:10, color:C.gray, fontSize:13 }}>
      <div style={{ width:16, height:16, border:"2px solid #e5e7eb", borderTopColor:C.blue, borderRadius:"50%", animation:"spin 0.8s linear infinite" }} />
      Loading IPO Intelligence Engine…
    </div>
  )

  return (
    <div style={{ fontFamily:"-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>

      {/* HEADER */}
      <div style={{ background:"#FFFFFF", padding:"14px 20px", borderBottom:"1px solid #F0EDE8" }}>
        <div style={{ maxWidth:960, margin:"0 auto" }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12, flexWrap:"wrap", gap:10 }}>
            <div>
              <div style={{ fontSize:17, fontWeight:900, color:"#111827", letterSpacing:"-0.02em" }}>IPO Intelligence</div>
              <div style={{ fontSize:12, color:"#6b7280", marginTop:1 }}>Listing · Business · Management · Two Outcomes Only</div>
            </div>
            <div style={{ display:"flex", gap:5, flexWrap:"wrap" }}>
              {(["ALL","OPEN","UPCOMING","LISTED"] as const).map(f => (
                <button key={f} onClick={()=>setFilter(f)}
                  style={{ padding:"5px 11px", borderRadius:8, border:`1px solid ${filter===f?C.blue:"#e5e7eb"}`, background:filter===f?C.blue:"transparent", color:filter===f?"#fff":"#374151", fontSize:10, fontWeight:700, cursor:"pointer" }}>
                  {f}
                </button>
              ))}
              <button onClick={()=>setShowUpload(v=>!v)}
                style={{ padding:"5px 11px", borderRadius:8, border:"1px solid #e5e7eb", background:showUpload?"#f0fdf4":"transparent", color:"#6b7280", fontSize:10, fontWeight:700, cursor:"pointer" }}>
                📄 Upload PDF
              </button>
            </div>
          </div>

          {/* Global PDF upload */}
          {showUpload && (
            <div style={{ marginBottom:12 }}>
              <PdfUpload onData={d => {
                setShowUpload(false)
                // If we can match to an existing IPO, show it
                if (d.name) {
                  const match = ipos.find(i => i.name.toLowerCase().includes((d.name||"").toLowerCase()))
                  if (match) { setSel({...match,...d}); setView("detail") }
                }
              }} />
            </div>
          )}

          {/* Dashboard stats */}
          {dash && (
            <div style={{ display:"grid", gridTemplateColumns:"repeat(6,1fr)", gap:6, background:"#f9fafb", borderRadius:10, padding:"10px 12px", marginTop:8 }}>
              {[
                { l:"Open",      v:dash.openCount,     c:"#4ade80" },
                { l:"Upcoming",  v:dash.upcomingCount, c:"#60a5fa" },
                { l:"Listed",    v:dash.listedCount,   c:"#c084fc" },
                { l:"Apply",     v:dash.hotIpos,       c:"#fbbf24" },
                { l:"Avoid",     v:dash.avoidCount,    c:"#f87171" },
                { l:"Avg Score", v:dash.avgScore,      c:"#4ade80" },
              ].map(s => (
                <div key={s.l} style={{ background:"rgba(255,255,255,0.04)", borderRadius:9, padding:"7px 0", textAlign:"center" }}>
                  <div style={{ fontSize:11, color:"#475569", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:2 }}>{s.l}</div>
                  <div style={{ fontSize:16, fontWeight:900, color:s.c }}>{s.v}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* BODY */}
      <div style={{ maxWidth:960, margin:"0 auto", padding:"16px 20px" }}>
        {view === "list" && (
          <>
            {/* Post-Listing Opportunity Monitor */}
            <PostListingMonitor />

            <input value={search} onChange={e=>setSearch(e.target.value)}
              placeholder="Search by name or sector…"
              style={{ width:"100%", boxSizing:"border-box", border:"1px solid #e5e7eb", borderRadius:10, padding:"10px 14px", fontSize:13, marginBottom:16, outline:"none", background:"#fff" }} />
            {filtered.length === 0 ? (
              <div style={{ textAlign:"center", padding:"60px 20px", color:C.gray }}>
                <div style={{ fontSize:32, marginBottom:8 }}>🔍</div>
                <div>No IPOs match</div>
              </div>
            ) : (
              <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(290px,1fr))", gap:14 }}>
                {filtered.map(ipo => (
                  <IpoCard key={ipo.name} ipo={ipo} onClick={()=>{ setSel(ipo); setView("detail") }} />
                ))}
              </div>
            )}
          </>
        )}
        {view === "detail" && sel && (
          <IpoDetail ipo={sel} onBack={()=>setView("list")} />
        )}
      </div>

      <style>{`@keyframes spin{to{transform:rotate(360deg)}}*{box-sizing:border-box}`}</style>
    </div>
  )
}

export default function App(){
  const [tab,setTab]=useState("today");
  const [workspaceSymbol,setWorkspaceSymbol]=useState<string|null>(null);
  const [discoveryView,setDiscoveryView]=useState("command_center");
  const [portfolioView,setPortfolioView]=useState("holdings");
  // V10 new state
  const [oppView,setOppView]=useState("multibagger");
  const [portView,setPortView]=useState("doctor");
  const [simpleMode,setSimpleMode]=useState(false);
  const [sym,setSym]=useState("");
  const [inp,setInp]=useState("");
  const [data,setData]=useState(null);
  const [searchErr,setSearchErr]=useState("");
  const [suggestions,setSuggestions]=useState([]);
  const [showSugg,setShowSugg]=useState(false);
  const [page,setPage]=useState("overview");
  const [loading,setLoading]=useState(false);
  const [liveP,setLiveP]=useState(null);
  const [liveLoad,setLiveLoad]=useState(false);
  const [livePErr,setLivePErr]=useState(false);
  const [memo,setMemo]=useState(null);
  const [memoLoad,setMemoLoad]=useState(false);
  // Screener
  const [activeGuru,setActiveGuru]=useState(null);
  const [activeGurus,setActiveGurus]=useState([]); // multi-select
  const [minBuyScore,setMinBuyScore]=useState(0);
  const [tierFilter,setTierFilter]=useState("ALL");
  const [screenerMode,setScreenerMode]=useState("single"); // single | multi
  const [screenerResults,setScreenerResults]=useState([]);
  const [screenerLoading,setScreenerLoading]=useState(false);
  const [screenerDone,setScreenerDone]=useState(false);
  const [showBackend,setShowBackend]=useState(false);
  const [watchlist,setWatchlist]=useState(["POLYCAB","HBLENGINE","BEL","ABCAPITAL"]);
  const [showWatchlist,setShowWatchlist]=useState(false);
  const [watchlistInput,setWatchlistInput]=useState("");
  // IPO
  const [ipos,setIpos]=useState(DEFAULT_IPOS);
  const [ipoSearch,setIpoSearch]=useState("");
  const [selIpo,setSelIpo]=useState(DEFAULT_IPOS[0]);
  const [newIpo,setNewIpo]=useState({name:"",sector:"",size:"",band:"",listing:"",gmp:"",qib:"",hni:"",retail:"",anchor:""});
  const [showAdd,setShowAdd]=useState(false);
  const [refreshTime,setRefresh]=useState("");

  // ── GURU SCREENER ────────────────────────────────────────────────
  const runScreener=useCallback((guruKey)=>{
    setActiveGuru(guruKey);
    setScreenerLoading(true);
    setScreenerDone(false);
    setScreenerResults([]);
    const guru=GURU_FILTERS[guruKey];
    setTimeout(()=>{
      const results=[];
      UNIVERSE.forEach(s=>{
        const d=makeStock(s);
        if(guru.criteria(d)) results.push({...d,guruScore:Math.round(guru.sort(d)*10)/10});
      });
      results.sort((a,b)=>b.guruScore-a.guruScore);
      const filtered=results.filter(r=>r.buyZone>=minBuyScore&&(
        tierFilter==="ALL"||(tierFilter==="1A"&&r.tier==="1A")||(tierFilter==="1"&&["1A","1"].includes(r.tier))||(tierFilter==="2"&&["1A","1","2"].includes(r.tier))
      ));
      setScreenerResults(filtered.slice(0,50));
      setScreenerLoading(false);
      setScreenerDone(true);
setScreenerDone(true);
fetch("/api/guru",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({guruKey,results:filtered.slice(0,50).map(r=>({sym:r.sym,tier:r.tier,overall:r.overall,buyZone:r.buyZone,roce:r.roce,roe:r.roe,rev3:r.rev3,pat3:r.pat3,debt:r.debt,promoter:r.promoter,pledge:r.pledge,pe:r.pe,adtv:r.adtv}))})}).catch(()=>{})
    },700);
  },[minBuyScore,tierFilter]);

  const runMultiScreener=useCallback((gurus,minBZ,tier)=>{
    setScreenerLoading(true);
    setScreenerDone(false);
    setScreenerResults([]);
    setTimeout(()=>{
      const results=[];
      UNIVERSE.forEach(s=>{
        const d=makeStock(s);
        // Must pass ALL selected guru filters
        const passGurus=gurus.length===0||gurus.every(gk=>GURU_FILTERS[gk]?.criteria(d));
        const passBZ=d.buyZone>=minBZ;
        const passTier=tier==="ALL"||(tier==="1A"&&d.tier==="1A")||(tier==="1"&&(d.tier==="1A"||d.tier==="1"))||(tier==="2"&&(d.tier==="1A"||d.tier==="1"||d.tier==="2"))||(tier==="AVOID"&&d.tier==="AVOID");
        if(passGurus&&passBZ&&passTier){
          const avgScore=gurus.length>0?gurus.reduce((a,gk)=>a+(GURU_FILTERS[gk]?.sort(d)||0),0)/gurus.length:d.overall;
          results.push({...d,guruScore:Math.round(avgScore*10)/10});
        }
      });
      results.sort((a,b)=>b.buyZone-a.buyZone);
      setScreenerResults(results.slice(0,50));
      setScreenerLoading(false);
      setScreenerDone(true);
setScreenerDone(true);
fetch("/api/guru",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({guruKey:"multi:"+gurus.join(","),results:results.slice(0,50).map(r=>({sym:r.sym,tier:r.tier,overall:r.overall,buyZone:r.buyZone,roce:r.roce,roe:r.roe,rev3:r.rev3,pat3:r.pat3,debt:r.debt,promoter:r.promoter,pledge:r.pledge,pe:r.pe,adtv:r.adtv}))})}).catch(()=>{})
    },700);
  },[]);

  // Transcript
  const [transcriptText,setTranscriptText]=useState("");
  const [transcriptFile,setTranscriptFile]=useState(null);
  const [transcriptSym,setTranscriptSym]=useState("");
  const [transcriptResult,setTranscriptResult]=useState(null);
  const [transcriptLoading,setTranscriptLoading]=useState(false);
  const [transcriptType,setTranscriptType]=useState("earnings");
  // Market pulse (PCR + VIX)
  const [marketData,setMarketData]=useState(null);
  const [marketLoading,setMarketLoading]=useState(false);
 const [marketFetched,setMarketFetched]=useState(false);
  const [marketFetchTime,setMarketFetchTime]=useState<Date|null>(null);

  const fetchLive=useCallback(async(s)=>{
    setLiveLoad(true);setLiveP(null);setLivePErr(false);
    try{
      const res=await fetch(`/api/price?sym=${s}`);
      const p=await res.json();
      if(p.price>0){setLiveP(p);setLiveLoad(false);return;}
      setLivePErr(true);
    }catch(e){setLivePErr(true);}
    setLiveLoad(false);
  },[]);

  const analyze=useCallback(async(s)=>{
    const upper=(s||"").toUpperCase().trim();
    if(!upper){setSearchErr("Please enter a stock symbol.");return;}
    // Allow any symbol — NSE + NASDAQ + NYSE
    // Just warn if not in our known list but still proceed
    if(!UNIVERSE.includes(upper)){
      // Try it anyway — could be a US stock or new addition
      console.log(upper+" not in local universe, trying API anyway");
    }
    setSearchErr("");setSuggestions([]);setShowSugg(false);
    setLoading(true);setData(null);setMemo(null);setPage("overview");setLiveP(null);setLivePErr(false);
    setTab("stocks");setSym(upper);
    const base=makeStock(upper);
    try{
      const r=await fetch("/api/stock?sym="+upper);
      if(r.ok){
        const live=await r.json();
        if(!live.error){
          // Map new API format to original field names
          const p=live.price||{};
          const f=live.fundamentals||{};
          const t=live.technicals||{};
          const merged={...base,
            cmp:p.price||base.cmp, change:p.change, changePct:p.changePct,
            dayHigh:p.dayHigh, dayLow:p.dayLow,
            week52h:p.week52h, week52l:p.week52l, mcap:f.mcap||base.mcap,
            ema20:t.ema20||base.ema20, ema50:t.ema50||base.ema50, ema200:t.ema200||base.ema200,
            rsi:t.rsi||base.rsi, macd:t.macd||base.macd, atr:t.atr,
            s1:t.support1||base.s1, s2:t.support2||base.s2,
            r1:t.resist1||base.r1, r2:t.resist2||base.r2,
            sl:t.support1?+(t.support1*0.97).toFixed(0):base.sl,
            t1:base.t1, t2:base.t2, t3:base.t3,
            buyRange:base.buyRange, trend:t.trend||base.trend,
            emaExtPct:t.ema20&&p.price?+(((p.price-t.ema20)/t.ema20)*100).toFixed(1):base.emaExtPct,
            pe:f.pe||base.pe, pb:f.pb||base.pb, peg:base.peg,
            evEb:base.evEb, roe:f.roe||base.roe,
            opMarg:f.operatingMargin||base.opMarg, debt:f.debtToEquity||base.debt,
            cT:f.targetMean||base.cT, bullT:f.targetHigh||base.bullT, bearT:f.targetLow||base.bearT,
            analystCount:f.analystCount||base.analystCount, buyPct:f.buyPct||base.buyPct,
            rev:f.quarterlyRevenue?.length?f.quarterlyRevenue:base.rev,
            pat:f.quarterlyPAT?.length?f.quarterlyPAT:base.pat,
            fcf:f.quarterlyFCF?.length?f.quarterlyFCF:base.fcf,
            qs:f.quarterlyLabels?.length?f.quarterlyLabels:base.qs,
            dataSource:live.source, dataNote:live.dataNote, liveDataLoaded:true,
            exchange:live.exchange||live.exch||"NSE",
          };
          setLiveP({price:p.price,change:p.change,changePct:p.changePct,
            high:p.dayHigh,low:p.dayLow,week52h:p.week52h,week52l:p.week52l});
          setData(merged);
          setRefresh(new Date().toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"}));
          setLoading(false);
          return;
        }
      }
    }catch(e){console.log("Live fetch failed:",e.message);}
    setData(base);
    setRefresh(new Date().toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"}));
    setLoading(false);
  },[])

  // ── MARKET PULSE: PCR + VIX ───────────────────────────────────
  const fetchMarket=useCallback(async()=>{
    setMarketLoading(true);
    try{
      const res=await fetch("/api/market");
      const j=await res.json();
      if(j.data){
        setMarketData(j.data);
        setMarketFetched(true);
      } else {
        setMarketData({
          vix:{value:14.2,change:0.8,changePct:5.9,trend:"Rising"},
          niftyPcr:{value:0.82,change:-0.06,signal:"Buy Zone",callOI:48200000,putOI:39524000},
          nifty:{value:24412,change:88,changePct:0.36},
          bankNifty:{value:52180,change:195,changePct:0.37},
          fetchTime:"Simulated",simulated:true
        });
setMarketFetched(true);
        setMarketFetchTime(new Date());
      }
    }catch(e){
      setMarketData({
        vix:{value:14.2,change:0.8,changePct:5.9,trend:"Rising"},
        niftyPcr:{value:0.82,change:-0.06,signal:"Buy Zone",callOI:48200000,putOI:39524000},
        nifty:{value:24412,change:88,changePct:0.36},
        bankNifty:{value:52180,change:195,changePct:0.37},
        fetchTime:"Simulated",simulated:true
      });
      setMarketFetched(true);
    }
    setMarketLoading(false);
  },[]);

  useEffect(()=>{
    if(tab==="market"&&!marketFetched&&!marketLoading) fetchMarket()
  },[tab])

  // ── TRANSCRIPT ANALYZER
  const analyzeTranscript=useCallback(async()=>{
    if(!transcriptText.trim()&&!transcriptSym.trim())return;
    setTranscriptLoading(true);setTranscriptResult(null);
    try{
      const res=await fetch("/api/ai/transcript",{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          symbol:transcriptSym||sym,
          text:transcriptText.trim(),
          type:transcriptType
        })
      });
      const j=await res.json();
      if(j.result){setTranscriptResult(j.result);}
    }catch(e){setTranscriptResult(null);}
    setTranscriptLoading(false);
  },[transcriptText,transcriptSym,transcriptType]);

  const genMemo=async()=>{
    if(!data)return;
    setMemoLoad(true);
    try{
      const res=await fetch("/api/ai/memo",{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({symbol:sym,data:{
          overall:data.overall,mbScore:data.mbScore,buyZone:data.buyZoneAdj,
          convictionScore:data.convictionScore,convictionLabel:data.convictionLabel,
          tierLabel:data.tierLabel,rev3:data.rev3,pat3:data.pat3,roce:data.roce,
          roe:data.roe,debt:data.debt,pe:data.pe,pb:data.pb,peg:data.peg,
          opMarg:data.opMarg,promoter:data.promoter,pledge:data.pledge,
          beneish:data.beneish,piotroski:data.piotroski,auditorResigned:data.auditorResigned,
          topTierAuditor:data.topTierAuditor,rsi:data.rsi,rsiW:data.rsiW,rsiM:data.rsiM,
          rsiAligned:data.rsiAligned,emaExtPct:data.emaExtPct,del:data.del,
          del10Avg:data.del10Avg,smartMoney:data.smartMoney,govRisk:data.govRisk,
          capCompScore:data.capCompScore,moatLabel:data.moatLabel,moatScore:data.moatScore,
          relStrLabel:data.relStrLabel,relStrength:data.relStrength,
          adtv:data.adtv,fcfPatDivergence:data.fcfPatDivergence,exchange:data.exchange||"NSE"
        }})
      });
      const j=await res.json();
      if(j.memo){setMemo(j.memo);}
    }catch(e){setMemo(null);}
    setMemoLoad(false);
  };

  const addIpo=()=>{
    if(!newIpo.name)return;
    const ipo={
      name:newIpo.name,sector:newIpo.sector||"Unknown",
      size:parseInt(newIpo.size)||0,band:newIpo.band||"TBD",
      listing:newIpo.listing||"TBD",status:"UPCOMING",
      gmp:newIpo.gmp||"N/A",qib:newIpo.qib||"0x",
      hni:newIpo.hni||"0x",retail:newIpo.retail||"0x",
      anchor:newIpo.anchor?newIpo.anchor.split(",").map(a=>a.trim()):[],
      drhp:false,ofsP:0
    };
    setIpos(prev=>[ipo,...prev]);
    setSelIpo(ipo);
    setNewIpo({name:"",sector:"",size:"",band:"",listing:"",gmp:"",qib:"",hni:"",retail:"",anchor:""});
    setShowAdd(false);
  };

  // No auto-analyze on mount — user must search

  const D=data;
  const filteredIpos=ipos.filter(i=>!ipoSearch||i.name.toLowerCase().includes(ipoSearch.toLowerCase())||i.sector.toLowerCase().includes(ipoSearch.toLowerCase()));
  const buyZoneColor=(bz)=>bz>=91?"#7c3aed":bz>=76?"#16a34a":bz>=61?"#1d4ed8":bz>=41?"#d97706":"#dc2626";
  const buyZoneLabel=(bz)=>bz>=91?"⚡ High Conviction Buy":bz>=76?"✅ Buy Zone":bz>=61?"📌 Accumulate":bz>=41?"👁 Watchlist":"❌ Avoid";

  return(
    <div style={{background:"#FAFAF8",minHeight:"100vh",fontFamily:"'DM Sans',sans-serif",color:"#111827"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&family=DM+Sans:wght@300;400;500;600&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        ::-webkit-scrollbar{width:4px;height:4px;}::-webkit-scrollbar-thumb{background:#d1d5db;border-radius:2px;}
        input,button,textarea{outline:none;font-family:inherit;}
        .hr:hover{background:#f9fafb!important;}
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes fade{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
        .fade{animation:fade .3s ease}
        @keyframes shimmer{0%,100%{opacity:.5}50%{opacity:1}}
        .shimmer{animation:shimmer 1.4s ease infinite}
      `}</style>

      {showBackend&&<BackendModal onClose={()=>setShowBackend(false)}/>}

      {/* ── NAV ── */}
      <div style={{background:"#FFFFFF",borderBottom:"1px solid #F0EDE8",padding:"0 16px",display:"flex",alignItems:"center",gap:12,height:56,position:"sticky",top:0,zIndex:300,overflow:"visible"}}>
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <div style={{width:34,height:34,borderRadius:9,background:"linear-gradient(135deg,#2563EB)",display:"flex",alignItems:"center",justifyContent:"center",fontFamily:"'Sora',sans-serif",fontWeight:800,color:"#fff",fontSize:14}}>AA</div>
          <div>
            <div style={{fontFamily:"'Sora',sans-serif",fontWeight:800,fontSize:16,color:"#111827",letterSpacing:"-0.3px"}}>AACapital</div>
            <div style={{fontFamily:"'IBM Plex Mono',monospace",fontSize:11,color:"#475569",letterSpacing:"1px"}}>Institutional Research · NSE/BSE</div>
          </div>
        </div>
        <div style={{flex:1}}/>
        {/* Global stock search */}
        <div style={{width:320,marginRight:6,position:"relative",zIndex:99999}}>
          <StockSearch onSelect={(sym)=>setWorkspaceSymbol(sym)} placeholder="Search stock..." />
        </div>
        {[
  {v:"today",         l:"Today",        icon:<Home        size={13}/>},
  {v:"opportunities", l:"Opportunities", icon:<TrendingUp   size={13}/>},
  {v:"portfolio",     l:"Portfolio",     icon:<Briefcase    size={13}/>},
  {v:"ipo",           l:"IPO",           icon:<Zap          size={13}/>},
  {v:"research",      l:"Research",      icon:<BarChart2    size={13}/>},
].map(({v,l,icon})=>(
  <button key={v} onClick={()=>setTab(v)} style={{
    display:"flex",alignItems:"center",gap:5,
    padding:"5px 11px",borderRadius:7,border:"none",
    background:tab===v?"#EFF6FF":"transparent",
    color:tab===v?"#2563EB":"#6B7280",
    fontFamily:"'IBM Plex Mono',monospace",fontSize:11,
    fontWeight:tab===v?600:400,
    cursor:"pointer",transition:"all .12s",whiteSpace:"nowrap",
  }}>
    {icon}{l}
  </button>
))}
        <button onClick={()=>setTab("calc")} style={{padding:"5px 12px",borderRadius:6,border:"1px solid #e5e7eb",background:tab==="calc"?"#fef3c7":"transparent",color:tab==="calc"?"#92400e":"#d97706",fontFamily:"'IBM Plex Mono',monospace",fontSize:10,cursor:"pointer",transition:"all .15s",whiteSpace:"nowrap",fontWeight:tab==="calc"?700:400}}>🧮</button>
        <button onClick={()=>{const n=!simpleMode;setSimpleMode(n);localStorage.setItem("aac_simple_mode",String(n));}} style={{padding:"4px 10px",borderRadius:14,border:"1px solid #E5E7EB",background:simpleMode?"#2563EB":"transparent",color:simpleMode?"#fff":"#6B7280",fontSize:10,cursor:"pointer",fontWeight:500,whiteSpace:"nowrap"}}>
          {simpleMode?"Simple":"Advanced"}
        </button>
        {refreshTime&&<div style={{fontFamily:"'IBM Plex Mono',monospace",fontSize:11,color:"#374151"}}>↻{refreshTime}</div>}
      </div>

      {/* ══ STOCK RESEARCH WORKSPACE (global overlay) ══ */}
      {workspaceSymbol&&(
        <StockResearchWorkspace
          symbol={workspaceSymbol}
          onClose={()=>setWorkspaceSymbol(null)}
        />
      )}

      {/* ══════════════════════════════════════════════════
          V10 NAVIGATION — TODAY · OPPORTUNITIES · PORTFOLIO · IPO · RESEARCH
          Each tab answers exactly one of the 7 core questions
      ══════════════════════════════════════════════════════ */}

      {/* ── Simple/Advanced toggle ── */}
      {tab==="today"&&(
        <TodayScreen
  simple={simpleMode}
  onStockSelect={(s) => setWorkspaceSymbol(s)}
/>
      )}

      {tab==="opportunities"&&(
        <div style={{background:"#FAFAF8",minHeight:"100vh"}}>
          <div style={{background:"#fff",borderBottom:"1px solid #E5E7EB",position:"sticky",top:52,zIndex:9}}>
            <div style={{padding:"12px 16px 0"}}>
              <div style={{fontSize:18,fontWeight:800,color:"#111827",marginBottom:10}}>Opportunities</div>
            </div>
            <div style={{display:"flex",borderBottom:"1px solid #E5E7EB",padding:"0 16px"}}>
              {([
                {id:"multibagger",  label:simpleMode?"Potential multibaggers":"Multibagger discovery"},
                {id:"intelligence", label:simpleMode?"Stock intelligence":"Intelligence dashboard"},
                {id:"technical",    label:simpleMode?"Technical setups":"Technical screener"},
                {id:"earnings",     label:"Earnings"},
                {id:"sector",       label:"Sector leaders"},
              ] as {id:string;label:string}[]).map(t=>(
                <button key={t.id} onClick={()=>setOppView(t.id as any)}
                  style={{padding:"10px 14px",border:"none",fontSize:12,
                    fontWeight:oppView===t.id?700:500,
                    color:oppView===t.id?"#2563EB":"#6B7280",
                    background:"transparent",cursor:"pointer",
                    borderBottom:oppView===t.id?"2px solid #2563EB":"2px solid transparent",
                    whiteSpace:"nowrap"}}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          {oppView==="multibagger"  && <MultibaggerDiscovery simple={simpleMode} onStockSelect={(s)=>setWorkspaceSymbol(s)}/>}
          {oppView==="intelligence" && <div style={{maxWidth:960,margin:"0 auto",padding:16}}><IntelligenceDashboard/></div>}
          {oppView==="technical"    && <TechnicalScreener simple={simpleMode} onStockSelect={(s)=>setWorkspaceSymbol(s)}/>}
          {oppView==="earnings"    && <EarningsScreen onStockSelect={(s)=>setWorkspaceSymbol(s)}/>}
          {oppView==="sector"       && <SectorRotationScreen/>}
        </div>
      )}

      {tab==="portfolio"&&(
        <div style={{background:"#FAFAF8",minHeight:"100vh"}}>
          <div style={{background:"#fff",borderBottom:"1px solid #E5E7EB",position:"sticky",top:52,zIndex:9}}>
            <div style={{padding:"12px 16px 0"}}>
              <div style={{fontSize:18,fontWeight:800,color:"#111827",marginBottom:10}}>Portfolio</div>
            </div>
            <div style={{display:"flex",borderBottom:"1px solid #E5E7EB",padding:"0 16px"}}>
              {([
                {id:"doctor",   label:simpleMode?"What to do":"Portfolio doctor"},
                {id:"holdings", label:"Holdings"},
                {id:"deploy",   label:"Deploy capital"},
              ] as {id:string;label:string}[]).map(t=>(
                <button key={t.id} onClick={()=>setPortView(t.id as any)}
                  style={{padding:"10px 14px",border:"none",fontSize:12,
                    fontWeight:portView===t.id?700:500,
                    color:portView===t.id?"#2563EB":"#6B7280",
                    background:"transparent",cursor:"pointer",
                    borderBottom:portView===t.id?"2px solid #2563EB":"2px solid transparent",
                    whiteSpace:"nowrap"}}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          {portView==="doctor"   && <PortfolioDoctor simple={simpleMode} onStockSelect={(s)=>setWorkspaceSymbol(s)}/>}
          {portView==="holdings" && <PortfolioTab/>}
          {portView==="deploy"   && <CapitalDeploymentOptimizer/>}
        </div>
      )}

      {tab==="ipo"&&(
        <div>
          <IpoCommandCenter simple={simpleMode}/>
          <div style={{maxWidth:720,margin:"0 auto",padding:"0 16px 16px"}}>
            <AnchorLockupTracker/>
          </div>
        </div>
      )}

      {tab==="research"&&(
        <div style={{background:"#FAFAF8",minHeight:"100vh"}}>
          <div style={{background:"#fff",borderBottom:"1px solid #E5E7EB",position:"sticky",top:52,zIndex:9}}>
            <div style={{padding:"12px 16px 0"}}>
              <div style={{fontSize:18,fontWeight:800,color:"#111827",marginBottom:2}}>Research lab</div>
              <div style={{fontSize:11,color:"#6B7280",marginBottom:10}}>Advanced tools</div>
            </div>
            <div style={{display:"flex",borderBottom:"1px solid #E5E7EB",padding:"0 16px",overflowX:"auto"}}>
              {([
                {id:"convergence", label:"⚡ Convergence"},
                {id:"dna",         label:"🧬 DNA lab"},
                {id:"journal",     label:"📓 Journal"},
                {id:"cron",        label:"⚙ System"},
                {id:"settings",    label:"🔧 Settings"},
              ] as {id:string;label:string}[]).map(t=>(
                <button key={t.id} onClick={()=>setDiscoveryView(t.id)}
                  style={{padding:"10px 14px",border:"none",fontSize:12,
                    fontWeight:discoveryView===t.id?700:500,
                    color:discoveryView===t.id?"#2563EB":"#6B7280",
                    background:"transparent",cursor:"pointer",
                    borderBottom:discoveryView===t.id?"2px solid #2563EB":"2px solid transparent",
                    whiteSpace:"nowrap"}}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          {discoveryView==="convergence" && <InvestmentCommandCenter/>}
          {discoveryView==="dna"         && <DNALabScreen/>}
          {discoveryView==="sector"      && <SectorRotationScreen/>}
          {discoveryView==="journal"     && <TradeJournalScreen/>}
          {discoveryView==="cron"        && <CronMonitor/>}
          {discoveryView==="settings"    && <SettingsTab/>}
        </div>
      )}

    </div>
  )
}

