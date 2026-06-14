/**
 * _scripts/backfill/screener-pipeline.ts
 * Parses Screener Premium 10-year Excel exports into Neon DB.
 *
 * Usage:
 *   npx tsx _scripts/backfill/screener-pipeline.ts --parse-only
 *   npx tsx _scripts/backfill/screener-pipeline.ts --symbol=WABAG --parse-only
 *   npx tsx _scripts/backfill/screener-pipeline.ts --resume
 */

import fs from "fs";
import path from "path";
import axios from "axios";
import * as XLSX from "xlsx";
import { Pool } from "pg";
import * as dotenv from "dotenv";

dotenv.config({ path: ".env.local" });
dotenv.config({ path: ".env" });

const COOKIE     = process.env.SCREENER_COOKIE ?? "";
const BASE_URL   = "https://www.screener.in";
const DELAY_MS   = 2500;
const OUTPUT_DIR = path.join(process.cwd(), "data", "fundamental_raw");
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const args       = process.argv.slice(2);
const SYMBOL_ARG = args.find(a => a.startsWith("--symbol="))?.split("=")[1];
const PARSE_ONLY = args.includes("--parse-only");
const RESUME     = args.includes("--resume");
const LIMIT      = parseInt(args.find(a => a.startsWith("--limit="))?.split("=")[1] ?? "0");

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || process.env.NEON_DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

async function getSymbols(): Promise<string[]> {
  if (SYMBOL_ARG) return [SYMBOL_ARG.toUpperCase()];
  const client = await pool.connect();
  try {
    const { rows } = await client.query(
      "SELECT symbol FROM company_master WHERE symbol IS NOT NULL ORDER BY symbol"
    );
    return rows.map(r => r.symbol as string);
  } finally { client.release(); }
}

async function downloadXlsx(symbol: string): Promise<string | null> {
  const outFile = path.join(OUTPUT_DIR, `${symbol}_10yr.xlsx`);
  if (RESUME && fs.existsSync(outFile) && fs.statSync(outFile).size > 5000) {
    console.log(`  ○ ${symbol} — skipped (exists)`);
    return outFile;
  }
  if (!COOKIE || COOKIE.includes("YOUR_SESSION")) {
    return fs.existsSync(outFile) ? outFile : null;
  }
  for (const url of [
    `${BASE_URL}/company/${symbol}/consolidated/export/`,
    `${BASE_URL}/company/${symbol}/export/`,
  ]) {
    try {
      const r = await axios.get(url, {
        responseType: "arraybuffer", timeout: 30000,
        headers: {
          Cookie: COOKIE,
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
          Referer: `${BASE_URL}/company/${symbol}/consolidated/`,
        },
      });
      const magic = Buffer.from(r.data as ArrayBuffer).slice(0, 4).toString("hex");
      if (magic === "504b0304") {
        fs.writeFileSync(outFile, Buffer.from(r.data as ArrayBuffer));
        console.log(`  ✓ ${symbol} — downloaded`);
        return outFile;
      }
    } catch { continue; }
  }
  console.log(`  ✗ ${symbol} — download failed`);
  return fs.existsSync(outFile) ? outFile : null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function n(val: any): number | null {
  if (val === null || val === undefined || val === "") return null;
  const v = parseFloat(String(val).replace(/,/g, "").trim());
  return isNaN(v) ? null : v;
}

// Normalise col-0 label: trim spaces, lowercase for matching
function label(val: any): string {
  return String(val ?? "").trim().toLowerCase();
}

/**
 * Convert Screener date formats to YYYY-MM-DD:
 *   "Mar-17"  → "2017-03-31"
 *   "Mar-24"  → "2024-03-31"   (2-digit year: <50 = 2000s, >=50 = 1900s)
 *   "Dec-23"  → "2023-12-31"
 *   "2024-03-31" → "2024-03-31"
 *   44927 (Excel serial) → converted via XLSX
 */
const MON: Record<string, string> = {
  jan:"01",feb:"02",mar:"03",apr:"04",may:"05",jun:"06",
  jul:"07",aug:"08",sep:"09",oct:"10",nov:"11",dec:"12",
};

function toIsoDate(val: any): string | null {
  if (!val) return null;
  const s = String(val).trim();

  // Already ISO
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.substring(0, 10);

  // "Mar-17" or "Mar-2017"
  const m = s.match(/^([A-Za-z]{3})-(\d{2,4})$/);
  if (m) {
    const mon = MON[m[1].toLowerCase()];
    if (!mon) return null;
    let year = parseInt(m[2]);
    if (year < 100) year += year < 50 ? 2000 : 1900;
    // Last day of that month
    const lastDay = new Date(year, parseInt(mon), 0).getDate();
    return `${year}-${mon}-${String(lastDay).padStart(2, "0")}`;
  }

  // Excel serial number
  if (/^\d{5}$/.test(s)) {
    const d = XLSX.SSF.parse_date_code(parseInt(s));
    if (d) {
      const mm = String(d.m).padStart(2, "0");
      const dd = String(d.d).padStart(2, "0");
      return `${d.y}-${mm}-${dd}`;
    }
  }

  return null;
}

// ── Parse Data Sheet ──────────────────────────────────────────────────────────

function parseDataSheet(wb: XLSX.WorkBook, symbol: string) {
  const ws = wb.Sheets["Data Sheet"] ?? wb.Sheets[wb.SheetNames[0]];
  if (!ws) throw new Error(`No usable sheet found. Sheets: ${wb.SheetNames.join(", ")}`);

  // Read raw — keeps numbers as numbers, strings as strings
  const data: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1, defval: null, raw: true });

  // Find section start row index by col-0 label
  const secIdx = (keyword: string, from = 0): number =>
    data.findIndex((r, i) => i >= from && label(r[0]).includes(keyword));

  // Find first row after `from` whose col-0 label matches keyword
  const rowAfter = (keyword: string, from: number): any[] | null => {
    const idx = secIdx(keyword, from);
    return idx >= 0 ? data[idx] : null;
  };

  // ── Annual P&L ──
  const plIdx = secIdx("profit & loss");
  const annual: any[] = [];

  if (plIdx >= 0) {
    // dates row is immediately after section header
    const dateRow = data[plIdx + 1] ?? [];
    const dates   = dateRow.slice(1).map(toIsoDate).filter(Boolean) as string[];

    const salesRow = rowAfter("sales",            plIdx + 2);
    const opRow    = rowAfter("operating profit", plIdx + 2);
    const expRow   = rowAfter("expenses",         plIdx + 2); // fallback for OP calc
    const netRow   = rowAfter("net profit",       plIdx + 2);
    const intRow   = rowAfter("interest",         plIdx + 2);
    const depRow   = rowAfter("depreciation",     plIdx + 2);

    dates.forEach((dt, i) => {
      const col = i + 1;
      const rev = n(salesRow?.[col]);
      let   opr = n(opRow?.[col]);
      if (opr === null && rev !== null) {
        const exp = n(expRow?.[col]);
        if (exp !== null) opr = Math.round((rev - exp) * 100) / 100;
      }
      annual.push({
        symbol, year_end: dt,
        revenue_cr: rev,
        operating_profit_cr: opr,
        opm_pct: (opr != null && rev && rev > 0) ? Math.round(opr/rev*10000)/100 : null,
        net_profit_cr: n(netRow?.[col]),
        interest_cr: n(intRow?.[col]),
        depreciation_cr: n(depRow?.[col]),
      });
    });
  }

  // ── Quarterly ──
  const qIdx = secIdx("quarters");
  const quarterly: any[] = [];

  if (qIdx >= 0) {
    const dateRow = data[qIdx + 1] ?? [];
    const dates   = dateRow.slice(1).map(toIsoDate).filter(Boolean) as string[];

    const salesRow = rowAfter("sales",            qIdx + 2);
    const expRow   = rowAfter("expenses",         qIdx + 2);
    const opRow    = rowAfter("operating profit", qIdx + 2);
    const netRow   = rowAfter("net profit",       qIdx + 2);
    const intRow   = rowAfter("interest",         qIdx + 2);

    dates.forEach((dt, i) => {
      const col = i + 1;
      const rev = n(salesRow?.[col]);
      let   opr = n(opRow?.[col]);
      if (opr === null && rev !== null) {
        const exp = n(expRow?.[col]);
        if (exp !== null) opr = Math.round((rev - exp) * 100) / 100;
      }
      quarterly.push({
        symbol,
        quarter_end: dt,
        quarter_label: dt.substring(0, 7),
        revenue_cr: rev,
        operating_profit_cr: opr,
        opm_pct: (opr != null && rev && rev > 0) ? Math.round(opr/rev*10000)/100 : null,
        net_profit_cr: n(netRow?.[col]),
        interest_cr: n(intRow?.[col]),
      });
    });
  }

  // ── Balance Sheet ──
  const bsIdx = secIdx("balance sheet");
  const bsRows: any[] = [];

  if (bsIdx >= 0) {
    const dateRow = data[bsIdx + 1] ?? [];
    const dates   = dateRow.slice(1).map(toIsoDate).filter(Boolean) as string[];

    const eqRow   = rowAfter("equity share capital", bsIdx + 2);
    const resRow  = rowAfter("reserves",             bsIdx + 2);
    const borRow  = rowAfter("borrowings",           bsIdx + 2);
    const cashRow = rowAfter("cash",                 bsIdx + 2);
    const recvRow = rowAfter("receivable",           bsIdx + 2);

    dates.forEach((dt, i) => {
      const col = i + 1;
      bsRows.push({
        symbol, year_end: dt,
        equity_cr: n(eqRow?.[col]), reserves_cr: n(resRow?.[col]),
        borrowings_cr: n(borRow?.[col]), cash_cr: n(cashRow?.[col]),
        receivables_cr: n(recvRow?.[col]),
      });
    });
  }

  // ── Cash Flow ──
  const cfIdx = secIdx("cash flow");
  const cfRows: any[] = [];

  if (cfIdx >= 0) {
    const dateRow = data[cfIdx + 1] ?? [];
    const dates   = dateRow.slice(1).map(toIsoDate).filter(Boolean) as string[];

    const cfoRow = rowAfter("operating", cfIdx + 2);
    const cfiRow = rowAfter("investing", cfIdx + 2);
    const cffRow = rowAfter("financing", cfIdx + 2);

    dates.forEach((dt, i) => {
      const col = i + 1;
      cfRows.push({
        symbol, year_end: dt,
        cfo_cr: n(cfoRow?.[col]),
        cfi_cr: n(cfiRow?.[col]),
        cff_cr: n(cffRow?.[col]),
      });
    });
  }

  if (annual.length === 0 && quarterly.length === 0) {
    // Diagnostic: show what dates looked like
    const plDateRow = data[plIdx + 1] ?? [];
    console.log(`  ⚠ Debug: plIdx=${plIdx} qIdx=${qIdx}`);
    console.log(`  ⚠ Date row sample: ${JSON.stringify(plDateRow.slice(0,5))}`);
  }

  return { annual, quarterly, balanceSheet: bsRows, cashFlow: cfRows };
}

// ── DB Upsert ─────────────────────────────────────────────────────────────────

async function upsertToDb(data: ReturnType<typeof parseDataSheet>) {
  const client = await pool.connect();
  try {
    // Annual rows — fiscal_quarter = "FY" to distinguish from quarterly
    for (const r of data.annual) {
      try {
        await client.query(`
          INSERT INTO quarterly_results
            (symbol, fiscal_year, fiscal_quarter, result_date,
             revenue, operating_profit, ebitda, pat, ebitda_margin, pat_margin)
          VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
          ON CONFLICT (symbol, fiscal_year, fiscal_quarter) DO UPDATE SET
            revenue=EXCLUDED.revenue,
            operating_profit=EXCLUDED.operating_profit,
            ebitda=EXCLUDED.ebitda,
            pat=EXCLUDED.pat,
            ebitda_margin=EXCLUDED.ebitda_margin,
            pat_margin=EXCLUDED.pat_margin, result_date=EXCLUDED.result_date,
            updated_at=NOW()
        `, [
          r.symbol,
          parseInt(r.year_end.substring(0, 4)),
          "FY",
          r.year_end,
          r.revenue_cr,
          r.operating_profit_cr,
          r.operating_profit_cr,
          r.net_profit_cr,
          r.opm_pct,
          (r.net_profit_cr != null && r.revenue_cr && r.revenue_cr > 0)
            ? Math.round(r.net_profit_cr / r.revenue_cr * 10000) / 100
            : null,
        ]);
      } catch (rowErr: any) {
        console.log(`    ✗ annual row failed: symbol=${r.symbol} year=${r.year_end} — ${rowErr.message}`);
        await client.query('ROLLBACK').catch(() => {});
        await client.query('BEGIN').catch(() => {});
      }
    }

    // Quarterly rows
    for (const r of data.quarterly) {
      const qLabel = r.quarter_end.substring(0, 7);
      try {
        await client.query(`
          INSERT INTO quarterly_results
            (symbol, fiscal_year, fiscal_quarter, result_date,
             revenue, operating_profit, ebitda, pat, ebitda_margin, pat_margin)
          VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
          ON CONFLICT (symbol, fiscal_year, fiscal_quarter) DO UPDATE SET
            revenue=EXCLUDED.revenue,
            operating_profit=EXCLUDED.operating_profit,
            ebitda=EXCLUDED.ebitda,
            pat=EXCLUDED.pat,
            ebitda_margin=EXCLUDED.ebitda_margin,
            pat_margin=EXCLUDED.pat_margin, result_date=EXCLUDED.result_date,
            updated_at=NOW()
        `, [
          r.symbol,
          parseInt(r.quarter_end.substring(0, 4)),
          qLabel,
          r.quarter_end,
          r.revenue_cr,
          r.operating_profit_cr,
          r.operating_profit_cr,
          r.net_profit_cr,
          r.opm_pct,
          (r.net_profit_cr != null && r.revenue_cr && r.revenue_cr > 0)
            ? Math.round(r.net_profit_cr / r.revenue_cr * 10000) / 100
            : null,
        ]);
      } catch (rowErr: any) {
        console.log(`    ✗ quarterly row failed: symbol=${r.symbol} qtr=${r.quarter_end} — ${rowErr.message}`);
        await client.query('ROLLBACK').catch(() => {});
        await client.query('BEGIN').catch(() => {});
      }
    }

    console.log(`  ✓ DB: ${data.annual.length} annual + ${data.quarterly.length} quarterly inserted`);
  } catch (e: any) {
    const sample = data.annual[0] || data.quarterly[0];
    if (sample) {
      const s = sample as any;
      console.log(`  ✗ DB: ${e.message}`);
      console.log(`    First row: symbol=[${s.symbol}] date=[${s.year_end || s.quarter_end}] rev=[${s.revenue_cr}]`);
    } else {
      console.log(`  ✗ DB: ${e.message} (no data rows)`);
    }
  } finally { client.release(); }
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  console.log("═══════════════════════════════════════════");
  console.log("  AACapital — Screener Fundamentals Pipeline");
  console.log("═══════════════════════════════════════════");
  console.log(`  Mode       : ${PARSE_ONLY ? "parse-only" : "download + parse"}`);
  console.log(`  Cookie set : ${!!COOKIE && !COOKIE.includes("YOUR")}`);
  console.log();

  const symbols   = await getSymbols();
  const toProcess = LIMIT ? symbols.slice(0, LIMIT) : symbols;
  console.log(`Stocks: ${toProcess.length}\n`);

  let okDl = 0, failDl = 0, okParse = 0, failParse = 0;

  for (const [i, symbol] of toProcess.entries()) {
    console.log(`[${String(i+1).padStart(3)}/${toProcess.length}] ${symbol}`);

    let xlsxFile: string | null = null;

    if (!PARSE_ONLY) {
      xlsxFile = await downloadXlsx(symbol);
      if (xlsxFile) okDl++; else { failDl++; continue; }
      await new Promise(r => setTimeout(r, DELAY_MS));
    } else {
      const f = path.join(OUTPUT_DIR, `${symbol}_10yr.xlsx`);
      if (!fs.existsSync(f)) { console.log(`  ○ no xlsx`); continue; }
      xlsxFile = f;
    }

    try {
      const wb   = XLSX.readFile(xlsxFile, { raw: true });
      const data = parseDataSheet(wb, symbol);
      await upsertToDb(data);
      okParse++;
    } catch (e: any) {
      console.log(`  ✗ parse: ${e.message}`);
      failParse++;
    }
  }

  await pool.end();
  console.log("\n═══════════════════════════════════════════");
  if (!PARSE_ONLY) console.log(`  Downloads : ${okDl} ok, ${failDl} failed`);
  console.log(`  Parsed    : ${okParse} ok, ${failParse} failed`);
  console.log("✅ Done");
}

main().catch(err => { console.error(err); process.exit(1); });
// DEBUG PATCH - this should not be in the file
