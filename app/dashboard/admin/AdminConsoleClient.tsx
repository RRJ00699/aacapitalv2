"use client";
// app/dashboard/admin/AdminConsoleClient.tsx
// One-click job runner. Polls /api/admin/jobs; enqueues a job_runs row on Run.
// The VM's job_runner.py (cron, every minute) claims it, runs the whitelisted
// script, and writes back status + exit code + last 60 log lines. UI just polls.

import { useCallback, useEffect, useMemo, useState } from "react";

const C = {
  bg: "var(--t-bg)", surface: "var(--t-surface)", border: "var(--t-border)", hover: "var(--t-surface2)",
  text: "var(--t-text)", textSub: "var(--t-sub)", meta: "var(--t-meta)", dim: "var(--t-dim)",
  green: "var(--t-green)", greenBg: "var(--t-greenBg)", greenBd: "var(--t-greenBd)",
  blue: "var(--t-blue)", blueBg: "var(--t-blueBg)", blueBd: "var(--t-blueBd)",
  amber: "var(--t-amber)", amberBg: "var(--t-amberBg)", amberBd: "var(--t-amberBd)",
  red: "var(--t-red)", redBg: "var(--t-redBg)", redBd: "var(--t-redBd)",
  grayBg: "var(--t-grayBg)",
};

// Mirrors the whitelist in _scripts/job_runner.py, with human labels.
// IPO Power House — IPO-only job catalog. Mirrors the IPO-only whitelist in
// _scripts/job_runner.py. Non-IPO jobs (theses, exit/base backtests, coverage,
// universe backfill, screener, convergence) removed.
const JOB_CATALOG: { key: string; label: string; desc: string; heavy?: boolean }[] = [
  { key: "pipeline",        label: "Run full pipeline (lean)", desc: "The production 08:30/17:00 flow: discovery → enrich → peer PE → GMP → candles → SBI → Haiku/Sonnet → score → verdicts → consolidated → gates", heavy: true },
  { key: "pipeline_weekly", label: "Pipeline + weekly purge", desc: "Lean pipeline plus the post-lock candle purge", heavy: true },
  { key: "ipo_lifecycle",   label: "Run IPO lifecycle", desc: "Per-IPO NSE issue, forward subscription, anchor allocation and listing-day pre-open actions" },
  { key: "consolidate",     label: "Golden table consolidation", desc: "Fill-empty into ipo_consolidated: intelligence scalars, RHP Sonnet + SBI Haiku JSON, street article, candles_json (listing→lock-in)" },
  { key: "news",            label: "Street news discovery", desc: "Whitelisted RSS (Reuters preferred, ET/MC/BS/Mint fallback) → one article per IPO; manual override wins" },
  { key: "peer_pe_notes",   label: "Peer P/E from SBI notes", desc: "Median of the Haiku-extracted peer table → peer_median_pe (fill-empty; runs before Screener)" },
  { key: "peer_pe",         label: "Fetch peer P/E (Screener)", desc: "Screener peer multiples → peer_median_pe — fills whatever the SBI notes left NULL" },
  { key: "vm_verify",       label: "VM verify (report)",    desc: "One-command reality check — stages, cron, files, per-IPO matrices. Read-only; output lands in the job log" },
  { key: "gmp",             label: "Refresh GMP",           desc: "Scrape InvestorGain grey-market premium → ipo_gmp" },
  { key: "breadth",         label: "Market breadth",        desc: "NIFTY advances/declines from NSE → Domestic panel (U16)" },
  { key: "token",           label: "Refresh Kite token",    desc: "TOTP re-auth → platform_config" },
  { key: "sbi_download",    label: "Download SBI notes",    desc: "Pull the latest SBI research PDFs", heavy: true },
  { key: "sbi_parse",       label: "Parse SBI notes",       desc: "Parse downloaded PDFs → ipo_research_notes" },
  { key: "rhp_auto",        label: "RHP auto (new IPOs)",   desc: "SEBI download → Sonnet extract (mainboard, $1 cap) → ipo_rhp_intel → purge PDF after anchor lock-in", heavy: true },
    { key: "ipomatrix",       label: "IPOMatrix enrich",     desc: "Fill anchors/structure for new IPOs from IPOMatrix JSON (needs fresh cookie)", heavy: false },
  { key: "sync",            label: "Sync code from GitHub", desc: "git reset to origin/main — pulls merged PRs onto the VM instantly" },
  // Added 2026-07-18: these were in job_runner's whitelist but had NO button, so
  // they were invisible from the phone. Run `schema` FIRST after any merge that
  // touches the DDL — it repairs missing tables/columns before anything reads them.
  { key: "schema",          label: "Schema sync (run first)", desc: "Apply all DDL — creates/repairs missing tables & columns. Run this before any other job after a code merge." },
  { key: "verdicts",        label: "Recompute verdicts",   desc: "compute_verdicts --apply → TRADE / WATCH / CAUTION / AVOID on every IPO" },
  { key: "score",           label: "Recompute ipo_score",  desc: "ipo_score --apply → tally, band and backtested win-rate" },
  { key: "quality",         label: "Recompute quality",    desc: "compute_quality_score --apply → the 0-100 junk filter behind the dial" },
  { key: "sbi_haiku",       label: "SBI Haiku extract",    desc: "Read unextracted SBI notes with Haiku ($0.50/day cap, new IPOs only)", heavy: true },
  { key: "smoke",           label: "Smoke probe",          desc: "Verify the DB contract + worker chain — run after schema to confirm everything is wired" },
];

type Run = {
  id: number; job: string; status: string; requested_by: string | null;
  requested_at: string | null; started_at: string | null; finished_at: string | null;
  exit_code: number | null; error: string | null; log_tail: string | null;
};

const STATUS_STYLE: Record<string, { bg: string; bd: string; fg: string; icon: string; label: string }> = {
  queued:  { bg: C.amberBg, bd: C.amberBd, fg: C.amber, icon: "⏳", label: "Queued" },
  running: { bg: C.blueBg,  bd: C.blueBd,  fg: C.blue,  icon: "🔄", label: "Running" },
  done:    { bg: C.greenBg, bd: C.greenBd, fg: C.green, icon: "✓", label: "Done" },
  failed:  { bg: C.redBg,   bd: C.redBd,   fg: C.red,   icon: "✕", label: "Failed" },
};

function ago(iso: string | null): string {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function StatusPill({ status }: { status: string }) {
  const s = STATUS_STYLE[status] ?? { bg: C.grayBg, bd: C.border, fg: C.meta, icon: "•", label: status };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 600,
      color: s.fg, background: s.bg, border: `1px solid ${s.bd}`, borderRadius: 20, padding: "2px 10px",
    }}>
      <span>{s.icon}</span>{s.label}
    </span>
  );
}


export default function AdminConsoleClient({ adminEmail }: { adminEmail: string }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [warning, setWarning] = useState<string | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);   // job key being enqueued
  const [toast, setToast] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/admin/jobs", { cache: "no-store" });
      const j = await r.json();
      if (!j.ok) { setLoadErr(j.error ?? "load failed"); return; }
      setRuns(j.runs ?? []);
      setWarning(j.warning ?? null);
      setLoadErr(null);
    } catch (e) {
      setLoadErr(e instanceof Error ? e.message : "network error");
    } finally {
      setLoaded(true);
    }
  }, []);

  // latest run per job (for card status + disabling the Run button)
  const latestByJob = useMemo(() => {
    const m: Record<string, Run> = {};
    for (const run of runs) if (!m[run.job]) m[run.job] = run; // runs already DESC
    return m;
  }, [runs]);

  const anyActive = useMemo(
    () => runs.some((r) => r.status === "queued" || r.status === "running"),
    [runs],
  );

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const ms = anyActive ? 2000 : 5000;   // poll faster while something is in flight
    const id = setInterval(load, ms);
    return () => clearInterval(id);
  }, [load, anyActive]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(id);
  }, [toast]);

  async function run(job: string) {
    setBusy(job);
    try {
      const r = await fetch("/api/admin/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job }),
      });
      const j = await r.json();
      if (!j.ok) setToast(j.error ?? "failed to queue");
      else setToast(`Queued ${job} (#${j.id})`);
      await load();
    } catch (e) {
      setToast(e instanceof Error ? e.message : "network error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div style={{ padding: "20px 24px", background: C.bg, minHeight: "100vh" }}>
      {/* header */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
          <a href="/ipo" style={{
            fontSize: 13, fontWeight: 600, color: C.blue, textDecoration: "none",
            background: C.blueBg, border: `1px solid ${C.blueBd}`, borderRadius: 8, padding: "5px 10px",
          }}>← IPO Command Center</a>
          <a href="/dashboard/settings" style={{ fontSize: 13, fontWeight: 600, color: C.blue, textDecoration: "none",
            background: C.blueBg, border: `1px solid ${C.blueBd}`, borderRadius: 8, padding: "5px 10px", marginLeft: 8 }}>⚙️ Settings</a>
          <a href="/dashboard/access" style={{ fontSize: 13, fontWeight: 600, color: C.blue, textDecoration: "none",
            background: C.blueBg, border: `1px solid ${C.blueBd}`, borderRadius: 8, padding: "5px 10px", marginLeft: 8 }}>🔑 Access</a>
          <h1 style={{fontFamily:"var(--f-display)",letterSpacing:-0.3, fontSize: 20, fontWeight: 800, color: C.text, margin: 0 }}>⚙️ Admin · Job Console</h1>
        </div>
        {/* Refresh removed (Rakesh 2026-07-17): gave no feedback and the list
            auto-loads on mount + after each job. Pull-to-refresh covers manual. */}
      </div>
      <p style={{ fontSize: 13, color: C.meta, marginTop: 0, marginBottom: 18 }}>
        Run any pipeline job with one click. web → Neon only; the VM polls and runs it. Signed in as {adminEmail}.
      </p>

      {warning && (
        <div style={{
          background: C.amberBg, border: `1px solid ${C.amberBd}`, color: C.amber,
          borderRadius: 10, padding: "10px 14px", fontSize: 13, marginBottom: 16,
        }}>
          job_runs table is unavailable — provision it with explicit migration tooling; nothing runs until{" "}
          <code>job_runner.py</code> is scheduled on the VM (cron, every minute).
        </div>
      )}
      {loadErr && (
        <div style={{
          background: C.redBg, border: `1px solid ${C.redBd}`, color: C.red,
          borderRadius: 10, padding: "10px 14px", fontSize: 13, marginBottom: 16,
        }}>
          {loadErr}
        </div>
      )}

      {/* job cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12, marginBottom: 28 }}>
        {JOB_CATALOG.map((jc) => {
          const last = latestByJob[jc.key];
          const active = last && (last.status === "queued" || last.status === "running");
          const disabled = busy === jc.key || !!active;
          return (
            <div key={jc.key} style={{
              background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12,
              padding: 16, display: "flex", flexDirection: "column", gap: 10,
            }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>
                  {jc.label}
                  {jc.heavy && (
                    <span style={{ marginLeft: 6, fontSize: 10, fontWeight: 700, color: C.meta,
                      background: C.grayBg, border: `1px solid ${C.border}`, borderRadius: 6, padding: "1px 6px" }}>
                      HEAVY
                    </span>
                  )}
                </div>
                {last && <StatusPill status={last.status} />}
              </div>
              <div style={{ fontSize: 12, color: C.meta, lineHeight: 1.4, minHeight: 34 }}>{jc.desc}</div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <span style={{ fontSize: 11, color: C.dim }}>
                  {last ? `last ${last.status} · ${ago(last.finished_at ?? last.started_at ?? last.requested_at)}` : "never run"}
                </span>
                <button onClick={() => run(jc.key)} disabled={disabled} style={{
                  fontSize: 13, fontWeight: 600, padding: "7px 16px", borderRadius: 8, cursor: disabled ? "default" : "pointer",
                  color: disabled ? C.dim : "#fff", background: disabled ? C.grayBg : C.text,
                  border: `1px solid ${disabled ? C.border : C.text}`,
                }}>
                  {busy === jc.key ? "Queuing…" : active ? "Running…" : "Run"}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* recent runs */}
      <h2 style={{ fontSize: 15, fontWeight: 700, color: C.text, margin: "0 0 10px" }}>Recent runs</h2>
      {loaded && runs.length === 0 && (
        <div style={{ fontSize: 13, color: C.meta, padding: "16px 0" }}>No runs yet.</div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {runs.map((r) => {
          const isOpen = expanded === r.id;
          const label = JOB_CATALOG.find((j) => j.key === r.job)?.label ?? r.job;
          return (
            <div key={r.id} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10 }}>
              <div
                onClick={() => setExpanded(isOpen ? null : r.id)}
                style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", cursor: "pointer" }}
              >
                <StatusPill status={r.status} />
                <span style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{label}</span>
                <span style={{ fontSize: 12, color: C.dim, fontFamily: "monospace" }}>{r.job}</span>
                {r.exit_code !== null && r.status === "failed" && (
                  <span style={{ fontSize: 12, color: C.red }}>exit {r.exit_code}</span>
                )}
                <span style={{ marginLeft: "auto", fontSize: 12, color: C.meta }}>
                  {r.requested_by ? `${r.requested_by} · ` : ""}{ago(r.requested_at)}
                </span>
                <span style={{ fontSize: 12, color: C.dim }}>{isOpen ? "▲" : "▼"}</span>
              </div>
              {isOpen && (
                <div style={{ borderTop: `1px solid ${C.border}`, padding: "12px 14px" }}>
                  {r.error && (
                    <div style={{
                      fontSize: 12, color: C.red, background: C.redBg, border: `1px solid ${C.redBd}`,
                      borderRadius: 8, padding: "8px 10px", marginBottom: 10, whiteSpace: "pre-wrap",
                    }}>
                      {r.error}
                    </div>
                  )}
                  <pre style={{
                    margin: 0, fontSize: 11.5, lineHeight: 1.5, fontFamily: "var(--f-mono)", color: "#94A3B8", background: "#0B1020",
                    borderRadius: 8, padding: "10px 12px", overflowX: "auto", maxHeight: 320,
                  }}>
                    <code style={{ color: "#C7D2FE" }}>{r.log_tail || "(no output captured)"}</code>
                  </pre>
                  <div style={{ fontSize: 11, color: C.dim, marginTop: 8 }}>
                    queued {ago(r.requested_at)}
                    {r.started_at ? ` · started ${ago(r.started_at)}` : ""}
                    {r.finished_at ? ` · finished ${ago(r.finished_at)}` : ""}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {toast && (
        <div style={{
          position: "fixed", bottom: 20, left: "50%", transform: "translateX(-50%)",
          background: C.text, color: "#fff", fontSize: 13, padding: "10px 18px",
          borderRadius: 10, boxShadow: "0 4px 16px rgba(0,0,0,0.2)", zIndex: 50,
        }}>
          {toast}
        </div>
      )}
    </div>
  );
}
