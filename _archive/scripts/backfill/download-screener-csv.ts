/**
 * _scripts/backfill/download-screener-csv.ts
 * ─────────────────────────────────────────────────────────────────────────────
 * Downloads historical quarterly financials from Screener.in for all stocks
 * in company_master. Saves as SYMBOL.xlsx to _scripts/backfill/data/
 *
 * Usage:
 *   npx tsx _scripts/backfill/download-screener-csv.ts
 *   npx tsx _scripts/backfill/download-screener-csv.ts --symbol=WABAG
 *   npx tsx _scripts/backfill/download-screener-csv.ts --limit=50
 *
 * Env vars needed in .env.local:
 *   SCREENER_USERNAME=your@email.com
 *   SCREENER_PASSWORD=yourpassword
 *   DATABASE_URL=postgresql://...
 */

import fs   from 'fs'
import path from 'path'
import axios, { AxiosInstance } from 'axios'
import { Pool } from 'pg'
import { config } from 'dotenv'
import { existsSync } from 'fs'

// ─── Load env ────────────────────────────────────────────────────────────────
const envPath = path.resolve(process.cwd(), '.env.local')
if (existsSync(envPath)) config({ path: envPath })
else config()

// ─── Config ───────────────────────────────────────────────────────────────────
const USERNAME  = process.env.SCREENER_USERNAME || ''
const PASSWORD  = process.env.SCREENER_PASSWORD || ''
const EXPORT_DIR = path.join(process.cwd(), '_scripts', 'backfill', 'data')
const DELAY_MS  = 2200   // 2.2s between requests — safe for Screener rate limits
const BASE_URL  = 'https://www.screener.in'

// ─── CLI args ─────────────────────────────────────────────────────────────────
const args     = process.argv.slice(2)
const onlySym  = args.find(a => a.startsWith('--symbol='))?.split('=')[1]?.toUpperCase()
const limitArg = parseInt(args.find(a => a.startsWith('--limit='))?.split('=')[1] || '0')

// ─── Axios client with Chrome-like headers ────────────────────────────────────
const client: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 20000,
  headers: {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
  },
  maxRedirects: 5,
  validateStatus: (s) => s < 400,
  withCredentials: true,
})

// ─── Cookie jar (simple) ──────────────────────────────────────────────────────
let cookieJar: string[] = []

function mergeCookies(setCookieHeader: string[] | undefined) {
  if (!setCookieHeader) return
  for (const raw of setCookieHeader) {
    const name = raw.split('=')[0].trim()
    cookieJar = cookieJar.filter(c => !c.startsWith(name + '='))
    cookieJar.push(raw.split(';')[0].trim())
  }
}

function getCookieHeader() {
  return cookieJar.join('; ')
}

// ─── Step 1: Authenticate ─────────────────────────────────────────────────────
async function authenticate(): Promise<void> {
  if (!USERNAME || !PASSWORD) {
    throw new Error('SCREENER_USERNAME and SCREENER_PASSWORD must be set in .env.local')
  }

  console.log('🔑 Authenticating with Screener.in...')

  // Hit login page to get initial CSRF token
  const loginPage = await client.get('/login/')
  mergeCookies(loginPage.headers['set-cookie'] as string[])

  // Extract csrfmiddlewaretoken from the HTML form
  const csrfMatch = loginPage.data?.match(/csrfmiddlewaretoken.*?value="([^"]+)"/)
  const csrfToken = csrfMatch?.[1] || ''

  if (!csrfToken) {
    throw new Error('Could not extract CSRF token from Screener login page')
  }

  // Submit login form
  const params = new URLSearchParams()
  params.append('csrfmiddlewaretoken', csrfToken)
  params.append('username', USERNAME)
  params.append('password', PASSWORD)
  params.append('next', '/')

  const loginRes = await client.post('/login/', params.toString(), {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'Cookie': getCookieHeader(),
      'Referer': `${BASE_URL}/login/`,
      'Origin': BASE_URL,
    },
    maxRedirects: 0,
    validateStatus: (s) => s < 400,
  })

  mergeCookies(loginRes.headers['set-cookie'] as string[])

  const sessionId = cookieJar.find(c => c.startsWith('sessionid='))
  if (!sessionId) {
    throw new Error('Authentication failed — sessionid cookie not found. Check credentials.')
  }

  console.log('✅ Authenticated. Session established.')
}

// ─── Step 2: Download one stock ───────────────────────────────────────────────
async function downloadStock(symbol: string): Promise<'ok' | 'skip' | 'fail'> {
  const outPath = path.join(EXPORT_DIR, `${symbol}.xlsx`)

  // Skip if already downloaded
  if (existsSync(outPath)) {
    const stat = fs.statSync(outPath)
    if (stat.size > 1000) {
      console.log(`  ⏭  ${symbol} — already downloaded (${(stat.size/1024).toFixed(0)}KB), skipping`)
      return 'skip'
    }
  }

  try {
    // Screener export endpoint for consolidated financials
    const url = `/company/${symbol}/export/`

    const res = await client.get(url, {
      headers: {
        'Cookie': getCookieHeader(),
        'Referer': `${BASE_URL}/company/${symbol}/consolidated/`,
        'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*',
      },
      responseType: 'arraybuffer',
    })

    // Validate we got actual Excel data (not a redirect to login)
    const contentType = res.headers['content-type'] || ''
    if (!contentType.includes('spreadsheet') && !contentType.includes('octet-stream')) {
      // May have been redirected to login — re-authenticate
      console.warn(`  ⚠️  ${symbol} — unexpected content-type: ${contentType}`)
      return 'fail'
    }

    if (!existsSync(EXPORT_DIR)) fs.mkdirSync(EXPORT_DIR, { recursive: true })
    fs.writeFileSync(outPath, res.data)

    const kb = (Buffer.from(res.data).length / 1024).toFixed(0)
    console.log(`  ✅ ${symbol} — saved (${kb}KB)`)
    return 'ok'

  } catch (err: any) {
    console.error(`  ❌ ${symbol} — ${err.message}`)
    return 'fail'
  }
}

// ─── Step 3: Load symbol universe from DB ────────────────────────────────────
async function getSymbols(): Promise<string[]> {
  if (onlySym) return [onlySym]

  const connStr = process.env.DATABASE_URL || process.env.NEON_DATABASE_URL || ''
  if (!connStr) {
    // Fallback: read from CSV if no DB
    const csvPath = path.join(process.cwd(), 'data', 'watchlist_symbols.csv')
    if (existsSync(csvPath)) {
      const lines = fs.readFileSync(csvPath, 'utf8').split('\n').filter(Boolean)
      return lines.map(l => l.split(',')[0].trim().toUpperCase()).filter(Boolean).slice(1) // skip header
    }
    throw new Error('No DATABASE_URL and no data/watchlist_symbols.csv found')
  }

  const pool = new Pool({ connectionString: connStr, ssl: { rejectUnauthorized: false } })
  try {
    const res = await pool.query('SELECT symbol FROM company_master ORDER BY symbol')
    return res.rows.map((r: any) => r.symbol as string)
  } finally {
    await pool.end()
  }
}

// ─── Sleep helper ─────────────────────────────────────────────────────────────
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

// ─── Main ─────────────────────────────────────────────────────────────────────
async function run() {
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
  console.log(' AACapital — Screener.in Historical Data Downloader')
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')

  await authenticate()

  let symbols = await getSymbols()
  if (limitArg > 0) symbols = symbols.slice(0, limitArg)

  console.log(`\n📋 ${symbols.length} symbols to process\n`)

  const results = { ok: 0, skip: 0, fail: 0, failedSyms: [] as string[] }

  for (let i = 0; i < symbols.length; i++) {
    const sym = symbols[i]
    process.stdout.write(`[${String(i+1).padStart(3)}/${symbols.length}] ${sym.padEnd(16)}`)

    const result = await downloadStock(sym)
    results[result]++
    if (result === 'fail') results.failedSyms.push(sym)

    if (result !== 'skip') await sleep(DELAY_MS)
  }

  console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
  console.log(`✅ Downloaded: ${results.ok}`)
  console.log(`⏭  Skipped:   ${results.skip}`)
  console.log(`❌ Failed:     ${results.fail}`)
  if (results.failedSyms.length > 0) {
    console.log(`   Failed:    ${results.failedSyms.join(', ')}`)
  }
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
  console.log('\nNext step: npx tsx _scripts/backfill/backfill-earnings.ts --source=xlsx')
}

run().catch(e => { console.error(e.message); process.exit(1) })
