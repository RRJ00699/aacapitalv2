// app/api/cron/premarket-brief/route.ts
// Runs at 6:00 AM IST (00:30 UTC) every weekday
// Sends pre-market intelligence brief to Telegram
// Also fires convergence score alerts when 6-sigma setups found
// vercel.json schedule: "30 0 * * 1-5"

import { NextRequest, NextResponse } from "next/server"
import { neon } from "@neondatabase/serverless"

function db() { return neon(process.env.DATABASE_URL!) }

const TELEGRAM_API = "https://api.telegram.org"

async function sendTelegram(message: string, chatId?: string): Promise<boolean> {
  const token  = process.env.TELEGRAM_BOT_TOKEN
  const target = chatId ?? process.env.TELEGRAM_CHAT_ID
  if (!token || !target) return false

  try {
    const res = await fetch(`${TELEGRAM_API}/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: target,
        text: message,
        parse_mode: "HTML",
        disable_web_page_preview: true,
      }),
    })
    return res.ok
  } catch {
    return false
  }
}

// ── Format currency ───────────────────────────────────────────────────────────
function inr(n: number) {
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(1)}Cr`
  if (n >= 100000)   return `₹${(n / 100000).toFixed(1)}L`
  return `₹${n.toLocaleString("en-IN")}`
}

export async function GET(req: NextRequest) {
  // Auth
  const authHeader = req.headers.get("authorization")
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const sql = db()
  const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "https://aacapital.vercel.app"
  const results: Record<string, unknown> = {}

  try {
    // 1. Get market snapshot
    const snapshotRows = await sql`
      SELECT regime, nifty_close, banknifty_close, pcr, fii_net, dii_net, created_at
      FROM market_snapshot ORDER BY created_at DESC LIMIT 1
    `.catch(() => [])
    const snapshot = (snapshotRows[0] ?? {}) as Record<string, unknown>

    // 2. Get open IPOs
    const ipos = await sql`
      SELECT name, conviction_score, listing_score, ev_score, close_date
      FROM ipo_master
      WHERE status = 'open'
      ORDER BY conviction_score DESC NULLS LAST
      LIMIT 3
    `.catch(() => [])

    // 3. Get top DNA candidates (convergence score)
    const discovery = await fetch(`${appUrl}/api/multibagger-discovery?limit=5&min_score=60`)
      .then(r => r.json()).catch(() => ({ ok: false, data: [] }))

    // 4. Get convergence scan results
    const convergence = await fetch(`${appUrl}/api/convergence-score`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ top_n: 10 }),
    }).then(r => r.json()).catch(() => ({ ok: false, six_sigma_alerts: [] }))

    results.snapshot   = snapshot
    results.ipos       = ipos
    results.discovery  = discovery.data?.slice(0, 5) ?? []
    results.sixSigma   = convergence.six_sigma_alerts ?? []

    // 5. Build pre-market brief message
    const regime    = (snapshot.regime ?? "UNKNOWN") as string
    const regimeEmoji: Record<string, string> = {
      HOT: "🔥", NORMAL: "📈", CAUTION: "⚠️", COLD: "❄️", FROZEN: "🧊"
    }
    const emoji = regimeEmoji[regime] ?? "📊"

    const now = new Date().toLocaleDateString("en-IN", {
      weekday: "long", day: "numeric", month: "short",
      timeZone: "Asia/Kolkata"
    })

    let msg = `<b>🌅 AACapital Pre-Market Brief</b>
${now} · 6:30 AM IST

<b>${emoji} Market Regime: ${regime}</b>
Nifty: ${snapshot.nifty_close ?? "—"} | BankNifty: ${snapshot.banknifty_close ?? "—"}
PCR: ${snapshot.pcr ?? "—"} | FII: ${snapshot.fii_net ? inr(snapshot.fii_net as number) : "—"} | DII: ${snapshot.dii_net ? inr(snapshot.dii_net as number) : "—"}

`

    // IPOs
    if (ipos.length) {
      msg += `<b>📋 Open IPOs:</b>\n`
      for (const ipo of ipos) {
        const conv = ipo.conviction_score ?? "—"
        const cls  = typeof conv === "number" && conv >= 80 ? "🟢" :
                     typeof conv === "number" && conv >= 65 ? "🟡" : "🔴"
        msg += `${cls} <b>${ipo.name}</b> — Conviction ${conv} | Listing ${ipo.listing_score ?? "—"}\n`
      }
      msg += "\n"
    }

    // DNA candidates
    if (discovery.data?.length) {
      msg += `<b>🧬 Top DNA Candidates Today:</b>\n`
      for (const c of discovery.data.slice(0, 3)) {
        msg += `• <b>${c.tradingsymbol}</b> DNA:${c.dna_score} | ${c.predicted_tier.replace("_candidate","").toUpperCase()} setup\n`
      }
      msg += "\n"
    }

    // 6-sigma alerts (most important)
    if (results.sixSigma && (results.sixSigma as unknown[]).length > 0) {
      msg += `<b>🚨 6-SIGMA CONVERGENCE ALERTS:</b>\n`
      for (const alert of results.sixSigma as Record<string, unknown>[]) {
        msg += `🔴 <b>${alert.tradingsymbol}</b> — Score ${alert.convergence_score}/100 | ${alert.engines_triggered}/6 engines | ${alert.alert_tier}\n`
        if ((alert.signals as string[])?.length) {
          msg += `   ${(alert.signals as string[]).slice(0, 3).join(" · ")}\n`
        }
      }
      msg += "\n"
    }

    msg += `<a href="${appUrl}">→ Open AACapital</a>`

    // 6. Send pre-market brief
    const sent = await sendTelegram(msg)
    results.telegram_sent = sent

    // 7. Send separate 6-sigma alert if found
    if (results.sixSigma && (results.sixSigma as unknown[]).length > 0) {
      const alerts = results.sixSigma as Record<string, unknown>[]
      const alertMsg = `🚨 <b>CONVERGENCE ALERT — ${alerts.length} 6-Sigma Setup${alerts.length > 1 ? "s" : ""} Found!</b>

${alerts.map((a: Record<string, unknown>) =>
  `<b>${a.tradingsymbol}</b>
Score: ${a.convergence_score}/100 | Engines: ${a.engines_triggered}/6
${(a.signals as string[])?.slice(0, 3).join(" · ") ?? ""}
`).join("\n")}
This is a rare multi-engine convergence setup.
<a href="${appUrl}">→ Analyse in AACapital</a>`

      await sendTelegram(alertMsg)
      results.convergence_alert_sent = true
    }

    // 8. Log
    await sql`
      INSERT INTO audit_log (action, resource, details, created_at)
      VALUES ('premarket_brief', 'cron', ${JSON.stringify({
        regime: snapshot.regime,
        ipos: ipos.length,
        candidates: discovery.data?.length ?? 0,
        six_sigma: (results.sixSigma as unknown[])?.length ?? 0,
        telegram_sent: results.telegram_sent,
      })}, NOW())
    `.catch(() => {})

    return NextResponse.json({ ok: true, ...results })

  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Unknown error"
    return NextResponse.json({ ok: false, error: msg }, { status: 500 })
  }
}
