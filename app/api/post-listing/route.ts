// Post-Listing Dashboard API — 4 live microstructure signals + discipline verdict.
// Forward-looking (not backtested): computes from price_candles for a listed IPO.
//   GET /api/post-listing?symbol=CLEANMAX
import { NextRequest, NextResponse } from "next/server";
import { neon } from "@neondatabase/serverless";

export const dynamic = "force-dynamic";
const sql = neon(process.env.DATABASE_URL || process.env.NEON_DATABASE_URL!);

type Candle = { date: string; open: number; high: number; low: number; close: number; volume: number };

function vwap(cs: Candle[]) {
  // typical-price VWAP over the given candles
  let pv = 0, vol = 0;
  for (const c of cs) {
    const tp = (c.high + c.low + c.close) / 3;
    pv += tp * c.volume; vol += c.volume;
  }
  return vol > 0 ? pv / vol : null;
}

// ── distribution detectors — the "when to sell" signals ──
function volumeFade(cs: Candle[]) {
  // On up-days, is volume drying up? Fading up-day volume = buyers exhausting.
  const ups = cs.filter((c) => c.close > c.open);
  if (ups.length < 4) return { fading: false, recentAvg: null as number | null, earlyAvg: null as number | null };
  const half = Math.floor(ups.length / 2);
  const early = ups.slice(0, half), recent = ups.slice(half);
  const avg = (a: Candle[]) => a.reduce((x, c) => x + Number(c.volume), 0) / a.length;
  const earlyAvg = avg(early), recentAvg = avg(recent);
  return { fading: recentAvg < earlyAvg * 0.7, recentAvg, earlyAvg };
}
function peakDrawdown(cs: Candle[]) {
  // How far off the post-listing peak are we, and is it rolling over (lower highs)?
  if (!cs.length) return { peak: null as number | null, offPeakPct: null as number | null, lowerHighs: false };
  const peak = Math.max(...cs.map((c) => c.high));
  const price = cs[cs.length - 1].close;
  const offPeakPct = peak ? ((price / peak - 1) * 100) : null;
  // lower highs over the last 5 sessions = rolling over
  const tail = cs.slice(-5).map((c) => c.high);
  let lowerHighs = tail.length >= 3;
  for (let i = 1; i < tail.length; i++) if (tail[i] > tail[i - 1]) lowerHighs = false;
  return { peak, offPeakPct, lowerHighs };
}

function volumeProfile(cs: Candle[], bins = 12) {
  // volume-at-price histogram: where did shares actually change hands?
  if (!cs.length) return { nodes: [], poc: null as number | null, lo: 0, hi: 0 };
  const lo = Math.min(...cs.map(c => c.low));
  const hi = Math.max(...cs.map(c => c.high));
  const span = hi - lo || 1;
  const buckets = Array.from({ length: bins }, (_, i) => ({
    price: lo + (span * (i + 0.5)) / bins, vol: 0,
  }));
  for (const c of cs) {
    const tp = (c.high + c.low + c.close) / 3;
    let idx = Math.floor(((tp - lo) / span) * bins);
    if (idx < 0) idx = 0; if (idx >= bins) idx = bins - 1;
    buckets[idx].vol += c.volume;
  }
  const maxVol = Math.max(...buckets.map(b => b.vol), 1);
  const poc = buckets.reduce((a, b) => (b.vol > a.vol ? b : a), buckets[0]); // point of control
  return {
    nodes: buckets.map(b => ({ price: b.price, vol: b.vol, pct: b.vol / maxVol })),
    poc: poc.price, lo, hi,
  };
}

export async function GET(req: NextRequest) {
  const symbol = (req.nextUrl.searchParams.get("symbol") || "").toUpperCase().trim();
  if (!symbol) return NextResponse.json({ ok: false, error: "symbol required" }, { status: 400 });

  try {
    // candles since listing (most recent 60 trading days is plenty for post-listing view)
    const rows = (await sql`
      SELECT date, open, high, low, close, volume
      FROM price_candles WHERE UPPER(symbol) = ${symbol}
      ORDER BY date ASC`) as Candle[];

    if (!rows.length) {
      return NextResponse.json({ ok: true, symbol, hasData: false,
        note: "No candles yet — signals appear once trading data lands." });
    }

    const last = rows[rows.length - 1];
    const first = rows[0];
    const window = rows.slice(-20);               // last 20 sessions for profile
    const dailyVwap = vwap(rows.slice(-1));       // today's VWAP proxy (single candle typical price)
    const runVwap = vwap(rows);                   // since-listing VWAP (institutions' avg cost proxy)
    const price = last.close;

    // ── signal 1: VWAP ──
    const aboveVwap = runVwap != null && price >= runVwap;
    const vwapGapPct = runVwap ? ((price / runVwap - 1) * 100) : null;

    // ── signal 2: volume profile (20d) ──
    const vp = volumeProfile(window);
    // distribution signals (the "when to sell" tells)
    const vFade = volumeFade(rows);
    const pDraw = peakDrawdown(rows);
    const abovePOC = vp.poc != null && price >= vp.poc;  // trading above the heaviest node = support below

    // ── signal 3: free-float absorption ──
    // cumulative volume since listing vs an estimate of free float.
    const meta = (await sql`
      SELECT issue_size_cr, issue_price, anchor_lock30_date, anchor_lock90_date, listing_date, company_name
      FROM ipo_consolidated
      WHERE UPPER(COALESCE(symbol_final, nse_symbol, symbol, '')) = ${symbol}
      LIMIT 1`) as Record<string, unknown>[];
    const m = meta[0] || {};
    const cumVol = rows.reduce((a, c) => a + Number(c.volume), 0);
    const issueCr = Number(m.issue_size_cr) || null;
    const issuePrice = Number(m.issue_price) || null;
    // shares issued ≈ issue_size (₹cr → ₹) / issue_price. Float turnover = cumVol / sharesIssued.
    const sharesIssued = issueCr && issuePrice ? (issueCr * 1e7) / issuePrice : null;
    const floatTurnover = sharesIssued ? cumVol / sharesIssued : null; // >1 = whole issue traded ≥once

    // ── signal 4: anchor lock-in countdown ──
    const today = new Date();
    const daysTo = (d: unknown) => {
      if (!d) return null;
      const t = new Date(String(d)); if (isNaN(t.getTime())) return null;
      return Math.round((t.getTime() - today.getTime()) / 86400000);
    };
    const lock30 = daysTo(m.anchor_lock30_date);
    const lock90 = daysTo(m.anchor_lock90_date);
    // nearest upcoming unlock
    const upcoming = [lock30, lock90].filter((x): x is number => x != null && x >= 0).sort((a, b) => a - b)[0] ?? null;

    // ── VERDICT ENGINE — wired to the sell-early / hold-loser bias ──
    // 🟢 Accumulation: above VWAP AND above POC AND (no unlock <14d)
    // 🔴 Distribution: below VWAP AND (below POC OR unlock <7d)
    // 🟡 Base: everything else
    let verdict: "accumulation" | "base" | "distribution";
    const unlockSoon = upcoming != null && upcoming < 14;
    const unlockImminent = upcoming != null && upcoming < 7;
    // distribution tells: rolling over off the peak with fading up-day volume
    const rollingOver = pDraw.lowerHighs && (pDraw.offPeakPct != null && pDraw.offPeakPct < -8);
    const buyersExhausting = vFade.fading;
    if (aboveVwap && abovePOC && !unlockSoon && !rollingOver) verdict = "accumulation";
    else if ((!aboveVwap && (!abovePOC || unlockImminent)) || (rollingOver && buyersExhausting)) verdict = "distribution";
    else verdict = "base";

    // behavioral instruction — names the user's known bias and says do the opposite
    const instruction = {
      accumulation: "HOLD. Institutions are defending their cost and volume is holding above the heavy zone. Your urge to sell now is the mistake — let it run. Exit only on a close below VWAP.",
      base: "WAIT. No edge either way — price is churning around institutional cost. Don't force a trade or add on hope. Let the next VWAP break decide.",
      distribution: "EXIT. Price is below institutional cost and the heavy-volume floor is broken. This is the ego-trade trap — do not wait for it to 'come back.' Cut it.",
    }[verdict];

    return NextResponse.json({
      ok: true, symbol, hasData: true,
      company: m.company_name ?? symbol,
      price, listingDate: m.listing_date ?? first.date, lastDate: last.date, sessions: rows.length,
      verdict, instruction,
      signals: {
        vwap: { value: runVwap, daily: dailyVwap, price, above: aboveVwap, gapPct: vwapGapPct },
        volumeProfile: { ...vp, abovePOC },
        floatAbsorption: { cumVol, sharesIssued, turnover: floatTurnover },
        volumeFade: { fading: vFade.fading, recentUpVol: vFade.recentAvg, earlyUpVol: vFade.earlyAvg },
        peakDrawdown: { peak: pDraw.peak, offPeakPct: pDraw.offPeakPct, lowerHighs: pDraw.lowerHighs },
        anchorLockin: { lock30, lock90, nextUnlockDays: upcoming },
        // forward slots — light up when data feeds run
        delivery: { available: false, note: "Run the NSE bhavcopy feed to enable (daily, going forward)." },
        relativeStrength: { available: false, note: "Uses the live Nifty index value (added going forward)." },
      },
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "error";
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
