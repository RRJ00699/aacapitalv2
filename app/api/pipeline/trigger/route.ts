// app/api/pipeline/trigger/route.ts
// Triggers GitHub Actions daily pipeline via workflow_dispatch
// Called by Settings → Data Pipeline buttons

import { NextRequest, NextResponse } from "next/server"

export const dynamic = "force-dynamic"

const GITHUB_TOKEN = process.env.GITHUB_TOKEN
const GITHUB_REPO  = process.env.GITHUB_REPO || "RRJ00699/aacapitalv2"

export async function POST(req: NextRequest) {
  try {
    const { mode = "full" } = await req.json()

    if (!GITHUB_TOKEN) {
      return NextResponse.json({
        ok: false,
        error: "GITHUB_TOKEN not set in Vercel env vars. Add it in Vercel → Settings → Environment Variables.",
      }, { status: 500 })
    }

    const validModes = ["full", "signals_only", "purge_only"]
    if (!validModes.includes(mode)) {
      return NextResponse.json({ ok: false, error: `Invalid mode: ${mode}` }, { status: 400 })
    }

    const res = await fetch(
      `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/daily-pipeline.yml/dispatches`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${GITHUB_TOKEN}`,
          "Accept":        "application/vnd.github+json",
          "Content-Type":  "application/json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({
          ref:    "main",
          inputs: { mode },
        }),
      }
    )

    if (res.ok || res.status === 204) {
      const modeLabels: Record<string, string> = {
        full:         "Full pipeline triggered — candles + signals + commentary. Takes ~5 min.",
        signals_only: "Signal regeneration triggered — NR7/EMA200/momentum. Takes ~2 min.",
        purge_only:   "Purge triggered — cleaning stale data per retention policy.",
      }
      return NextResponse.json({
        ok:      true,
        message: modeLabels[mode] ?? "Pipeline triggered. Check GitHub Actions for progress.",
        github_url: `https://github.com/${GITHUB_REPO}/actions`,
      })
    }

    const body = await res.text().catch(() => "")
    return NextResponse.json({
      ok:    false,
      error: `GitHub API returned ${res.status}: ${body}`,
    }, { status: 500 })

  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err.message }, { status: 500 })
  }
}
