// components/features/cron-monitor.tsx
// Batch/Cron Job Monitor — shows status of all automated jobs
// Add to Settings tab or as a new "System" tab

"use client"
import { useState, useEffect } from "react"

const C = {
  surface: "#FFFFFF", border: "#E5E7EB", text: "#111827",
  green: "#16A34A", red: "#DC2626", blue: "#2563EB",
  amber: "#D97706", gray: "#6b7280", bg: "#F9FAFB",
  greenBg: "#F0FDF4", redBg: "#FEF2F2", amberBg: "#FFFBEB",
}

interface Job {
  id: string
  name: string
  description: string
  schedule: string
  last_run: string | null
  next_run: string | null
  status: "SUCCESS" | "FAILED" | "RUNNING" | "PENDING" | "NEVER_RUN"
  last_duration_ms: number | null
  records_processed: number | null
  error_message: string | null
  category: string
}

const JOBS: Job[] = [
  // Automated cron jobs (Vercel)
  {
    id: "premarket-brief",
    name: "Pre-market Telegram Brief",
    description: "Sends daily market summary + top opportunities to Telegram at 6:30 AM IST",
    schedule: "Mon–Fri 6:30 AM IST",
    category: "Automated",
    last_run: null, next_run: null, status: "PENDING",
    last_duration_ms: null, records_processed: null, error_message: null,
  },
  {
    id: "dna-refresh",
    name: "Weekly DNA Scan",
    description: "Scans 1,942 stocks for NR7, Stage, RS signals from Yahoo Finance",
    schedule: "Saturday 1:00 AM IST",
    category: "Automated",
    last_run: null, next_run: null, status: "PENDING",
    last_duration_ms: null, records_processed: null, error_message: null,
  },
  // Manual scripts
  {
    id: "earnings-seed",
    name: "Earnings Seed",
    description: "Extracts EPS, revenue, surprise, guidance for 30 capital stocks via Claude",
    schedule: "Quarterly (manual)",
    category: "Manual",
    last_run: null, next_run: null, status: "NEVER_RUN",
    last_duration_ms: null, records_processed: null, error_message: null,
  },
  {
    id: "orderbook-seed",
    name: "Order Book Seed",
    description: "Extracts order book history for 40 capital-intensive stocks via Claude",
    schedule: "Quarterly (manual)",
    category: "Manual",
    last_run: null, next_run: null, status: "NEVER_RUN",
    last_duration_ms: null, records_processed: null, error_message: null,
  },
  {
    id: "mgmt-commentary",
    name: "Management Commentary Seed",
    description: "Extracts management tone, guidance, key drivers via Claude web search",
    schedule: "Quarterly (manual)",
    category: "Manual",
    last_run: null, next_run: null, status: "NEVER_RUN",
    last_duration_ms: null, records_processed: null, error_message: null,
  },
  {
    id: "fundamentals-import",
    name: "Fundamentals Import",
    description: "Imports Screener.in CSV — ROCE, EPS, D/E for 1,779 stocks",
    schedule: "Monthly (manual)",
    category: "Manual",
    last_run: null, next_run: null, status: "NEVER_RUN",
    last_duration_ms: null, records_processed: null, error_message: null,
  },
  {
    id: "smart-money-import",
    name: "Smart Money Import",
    description: "Imports NSE bulk/block deals CSV — institutional flows",
    schedule: "Monthly (manual)",
    category: "Manual",
    last_run: null, next_run: null, status: "NEVER_RUN",
    last_duration_ms: null, records_processed: null, error_message: null,
  },
  {
    id: "local-db-backup",
    name: "Local DB Backup",
    description: "pg_dump from Neon to local PostgreSQL — full 152MB backup",
    schedule: "Monthly (manual)",
    category: "Manual",
    last_run: null, next_run: null, status: "NEVER_RUN",
    last_duration_ms: null, records_processed: null, error_message: null,
  },
]

// Database stats
interface DBStats {
  table: string
  rows: number
  size: string
}

const COMMANDS: Record<string, string> = {
  "earnings-seed":       "node scripts/earnings-seed.mjs --resume",
  "orderbook-seed":      "node scripts/orderbook-seed.mjs --resume",
  "mgmt-commentary":     "node scripts/management-commentary-seed-v2.mjs --resume",
  "fundamentals-import": "node scripts/fundamentals-import.mjs",
  "smart-money-import":  "node scripts/smart-money-import.mjs",
  "local-db-backup":     'pg_dump $NEON_URL --no-owner -f "C:\\AACapital\\backup\\aacapital-dump.sql"',
}

function StatusBadge({ status }: { status: Job["status"] }) {
  const config = {
    SUCCESS:   { color: C.green,  bg: C.greenBg, label: "✓ Success" },
    FAILED:    { color: C.red,    bg: C.redBg,   label: "✗ Failed" },
    RUNNING:   { color: C.blue,   bg: "#EFF6FF",  label: "⟳ Running" },
    PENDING:   { color: C.amber,  bg: C.amberBg, label: "⏰ Scheduled" },
    NEVER_RUN: { color: C.gray,   bg: C.bg,      label: "— Never run" },
  }[status]
  return (
    <span style={{ fontSize: 10, fontWeight: 600, padding: "2px 8px",
      borderRadius: 4, background: config.bg, color: config.color }}>
      {config.label}
    </span>
  )
}

export function CronMonitor() {
  const [dbStats, setDbStats] = useState<DBStats[]>([])
  const [copied, setCopied]   = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<Record<string, Job["status"]>>({})

  useEffect(() => {
    // Fetch DB stats
    fetch("/api/system/db-stats")
      .then(r => r.json())
      .then(d => setDbStats(d.tables ?? []))
      .catch(() => {})

    // Fetch cron status from audit log
    fetch("/api/system/cron-status")
      .then(r => r.json())
      .then(d => setJobStatus(d.statuses ?? {}))
      .catch(() => {})
  }, [])

  function copyCommand(jobId: string) {
    const cmd = COMMANDS[jobId]
    if (!cmd) return
    navigator.clipboard.writeText(cmd).then(() => {
      setCopied(jobId)
      setTimeout(() => setCopied(null), 2000)
    })
  }

  const automated = JOBS.filter(j => j.category === "Automated")
  const manual    = JOBS.filter(j => j.category === "Manual")

  return (
    <div style={{ padding: 16, maxWidth: 900, margin: "0 auto" }}>
      <div style={{ fontWeight: 800, fontSize: 20, color: C.text, marginBottom: 4 }}>
        🔧 System Monitor
      </div>
      <div style={{ fontSize: 12, color: C.gray, marginBottom: 20 }}>
        All automated cron jobs and manual data refresh scripts
      </div>

      {/* DB Stats */}
      {dbStats.length > 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`,
          borderRadius: 12, padding: 16, marginBottom: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: C.gray,
            textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 12 }}>
            Database Tables
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
            {dbStats.slice(0, 9).map(t => (
              <div key={t.table} style={{ background: C.bg, borderRadius: 8, padding: "8px 10px" }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: C.text }}>{t.table}</div>
                <div style={{ fontSize: 10, color: C.gray, marginTop: 2 }}>
                  {Number(t.rows).toLocaleString()} rows · {t.size}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Automated jobs */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: C.gray,
          textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 10 }}>
          Automated (Vercel Cron)
        </div>
        {automated.map(job => (
          <div key={job.id} style={{ background: C.surface, border: `1px solid ${C.border}`,
            borderRadius: 10, padding: "12px 14px", marginBottom: 8 }}>
            <div style={{ display: "flex", alignItems: "center",
              justifyContent: "space-between", marginBottom: 4 }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: C.text }}>{job.name}</div>
              <StatusBadge status={jobStatus[job.id] ?? job.status} />
            </div>
            <div style={{ fontSize: 11, color: C.gray, marginBottom: 4 }}>{job.description}</div>
            <div style={{ fontSize: 10, color: "#9CA3AF" }}>Schedule: {job.schedule}</div>
          </div>
        ))}
      </div>

      {/* Manual scripts */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 700, color: C.gray,
          textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 10 }}>
          Manual Scripts (Run in PowerShell)
        </div>
        {manual.map(job => (
          <div key={job.id} style={{ background: C.surface, border: `1px solid ${C.border}`,
            borderRadius: 10, padding: "12px 14px", marginBottom: 8 }}>
            <div style={{ display: "flex", alignItems: "center",
              justifyContent: "space-between", marginBottom: 4 }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: C.text }}>{job.name}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StatusBadge status={jobStatus[job.id] ?? job.status} />
                {COMMANDS[job.id] && (
                  <button
                    onClick={() => copyCommand(job.id)}
                    style={{ fontSize: 10, padding: "3px 10px", borderRadius: 5,
                      border: `1px solid ${C.border}`, background: copied === job.id ? C.greenBg : C.bg,
                      color: copied === job.id ? C.green : C.gray, cursor: "pointer", fontWeight: 600 }}>
                    {copied === job.id ? "✓ Copied!" : "Copy command"}
                  </button>
                )}
              </div>
            </div>
            <div style={{ fontSize: 11, color: C.gray, marginBottom: 4 }}>{job.description}</div>
            <div style={{ fontSize: 10, color: "#9CA3AF", marginBottom: COMMANDS[job.id] ? 6 : 0 }}>
              Schedule: {job.schedule}
            </div>
            {COMMANDS[job.id] && (
              <div style={{ background: "#1E293B", borderRadius: 6,
                padding: "6px 10px", fontSize: 10, color: "#94A3B8",
                fontFamily: "monospace", wordBreak: "break-all" }}>
                {COMMANDS[job.id]}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Quick reference */}
      <div style={{ background: "#F5F3FF", border: "1px solid #DDD6FE",
        borderRadius: 10, padding: 14, marginTop: 20 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#7C3AED", marginBottom: 8 }}>
          Quarterly Maintenance Checklist
        </div>
        {[
          "Run earnings-seed.mjs --resume",
          "Run management-commentary-seed-v2.mjs --resume",
          "Run orderbook-seed.mjs --resume",
          "Export Screener.in CSV → run fundamentals-import.mjs",
          "Download NSE bulk/block deals → run smart-money-import.mjs",
          "Run local DB backup (pg_dump)",
          "Check Kite API key expiry (renew at developers.kite.trade)",
        ].map((item, i) => (
          <div key={i} style={{ display: "flex", gap: 8, marginBottom: 4,
            fontSize: 11, color: "#374151" }}>
            <span style={{ color: "#7C3AED", fontWeight: 700 }}>{i + 1}.</span>
            {item}
          </div>
        ))}
      </div>
    </div>
  )
}
