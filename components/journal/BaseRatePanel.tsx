"use client";
// components/journal/BaseRatePanel.tsx
// Self-contained "you vs base rate" strip for the trade journal. Fetches its own
// data from /api/journal/base-rate. Drop <BaseRatePanel /> anywhere in JournalClient.
// Descriptive only — shows whether your realized IPO results beat the validated
// base rate per gap bucket. Not a buy call.

import { useEffect, useState } from "react";

const C = {
  surface: "#FFFFFF", border: "#E5E7EB", text: "#111827", meta: "#6B7280", dim: "#9CA3AF",
  green: "#16A34A", greenBg: "#F0FDF4", red: "#DC2626", redBg: "#FEF2F2",
  blue: "#2563EB", blueBg: "#EFF6FF", grayBg: "#F3F4F6",
};

type Bucket = { bucket: string; n: number; your_win: number; base_win: number | null; avg_edge: number | null };

export default function BaseRatePanel() {
  const [buckets, setBuckets] = useState<Bucket[]>([]);
  const [linked, setLinked] = useState(0);
  const [total, setTotal] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/journal/base-rate", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => {
        if (!alive) return;
        if (!j.ok) { setErr(j.error ?? "failed"); return; }
        setBuckets(j.buckets ?? []);
        setLinked(j.linked ?? 0);
        setTotal(j.total ?? 0);
      })
      .catch((e) => alive && setErr(String(e)))
      .finally(() => alive && setLoaded(true));
    return () => { alive = false; };
  }, []);

  if (!loaded) return null;
  if (err) return null; // stay quiet on the journal page if the join isn't available yet

  const order = ["LOW", "MID", "HIGH"];
  const sorted = [...buckets].sort((a, b) => order.indexOf(a.bucket) - order.indexOf(b.bucket));

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: 16, marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>You vs the base rate</div>
        <div style={{ fontSize: 11, color: C.dim }}>{linked} of {total} trades linked to an IPO gap bucket</div>
      </div>
      <div style={{ fontSize: 12, color: C.meta, marginBottom: 12 }}>
        Your realized IPO results by listing-gap bucket, against the validated backtest base rate (buy open → best close ≤10d). Descriptive, not a signal.
      </div>

      {sorted.length === 0 ? (
        <div style={{ fontSize: 12, color: C.meta }}>
          No journaled trades link to an IPO in <code>ipo_consolidated</code> yet — log a trade whose symbol matches a listed IPO and its bucket + base rate appear here.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
          {sorted.map((b) => {
            const beat = b.avg_edge != null && b.avg_edge >= 0;
            const edgeColor = b.avg_edge == null ? C.dim : beat ? C.green : C.red;
            const edgeBg = b.avg_edge == null ? C.grayBg : beat ? C.greenBg : C.redBg;
            return (
              <div key={b.bucket} style={{ border: `1px solid ${C.border}`, borderRadius: 10, padding: "12px 14px" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: C.text, letterSpacing: 0.4 }}>{b.bucket}-GAP</span>
                  <span style={{ fontSize: 11, color: C.meta, background: C.grayBg, borderRadius: 6, padding: "1px 7px" }}>N={b.n}</span>
                </div>
                <div style={{ display: "flex", gap: 14, marginBottom: 8 }}>
                  <div>
                    <div style={{ fontSize: 10, color: C.dim }}>YOUR WIN</div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: C.text }}>{b.your_win}%</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: C.dim }}>BASE WIN</div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: C.blue }}>{b.base_win ?? "—"}%</div>
                  </div>
                </div>
                <div style={{ fontSize: 12, fontWeight: 600, color: edgeColor, background: edgeBg, borderRadius: 6, padding: "3px 8px", display: "inline-block" }}>
                  {b.avg_edge == null ? "edge n/a" : `${b.avg_edge >= 0 ? "+" : ""}${b.avg_edge}% avg edge vs base`}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
