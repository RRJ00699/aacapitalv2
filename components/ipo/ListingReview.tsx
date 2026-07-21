"use client";
// components/ipo/ListingReview.tsx — the after-listing screen (D2, 2026-07-22).
// First 5 trading sessions tracked from the golden object's candles_json;
// evidence-backed observations from lib/listing-review (deterministic,
// attribution-safe — PROHIBITED regexes test-pinned). No new joins: one card.
import { Badge, Card, SectionHeader, Stat, EmptyState } from "@/components/ui/primitives";
import { VARS as C, FONT } from "@/lib/theme";
import { reviewState, observations, type Facts } from "@/lib/listing-review";

type R = Record<string, unknown>;
type Candle = { d: string; o: number; h: number; l: number; c: number; v: number };
const N = (v: unknown) => (v == null || v === "" || isNaN(Number(v)) ? null : Number(v));
const pct = (a: number, b: number) => ((a - b) / b) * 100;
const f1 = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;

export default function ListingReview({ c }: { c: R }) {
  if (!c) return <EmptyState title="Pick an IPO to review its listing." hint="The review runs from listing day through the first five sessions." />;
  const candles: Candle[] = Array.isArray(c.candles_json) ? (c.candles_json as Candle[]).slice(0, 5) : [];
  const issue = N(c.issue_price);
  const d0 = candles[0];
  const last = candles[candles.length - 1];
  const state = reviewState(c.listing_date ? String(c.listing_date) : null, Date.now() + 5.5 * 3600_000, false, candles.length);
  const gmp = N(c.gmp_day_before_pct);
  const facts: Facts = {
    issue, open: d0 ? d0.o : null, high: d0 ? d0.h : null, low: d0 ? d0.l : null,
    close: d0 ? d0.c : null, gmpImplied: issue != null && gmp != null ? issue * (1 + gmp / 100) : null,
    fairValue: null, deliveryPct: null, volume: d0 ? d0.v : null, offeredShares: null,
  };
  const obs = d0 && issue ? observations(facts) : [];
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <Card>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontFamily: FONT.display, fontWeight: 800, fontSize: 17, color: C.text }}>{String(c.company_name ?? "")}</span>
          <Badge label={state} tone={state === "LISTING WEEK COMPLETE" ? "neutral" : "info"} />
        </div>
        <div className="aac-cols-4" style={{ marginTop: 10 }}>
          <Stat label="Issue price" value={issue != null ? `₹${issue}` : "—"} />
          <Stat label="Listing open" value={d0 ? `₹${d0.o}` : "—"} sub={d0 && issue ? `${f1(pct(d0.o, issue))} vs issue` : undefined} />
          <Stat label="D0 close" value={d0 ? `₹${d0.c}` : "—"} sub={d0 && issue ? `${f1(pct(d0.c, issue))} vs issue` : undefined} />
          <Stat label="Latest close" value={last ? `₹${last.c}` : "—"} sub={last && issue ? `${f1(pct(last.c, issue))} vs issue · session ${candles.length}` : undefined} />
        </div>
      </Card>

      <Card><SectionHeader>First five sessions</SectionHeader>
        {candles.length ? (
          <div className="aac-table-wrap"><table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, fontFamily: FONT.mono }}>
            <thead><tr>{["Session", "Date", "Open", "High", "Low", "Close", "vs issue", "Day"].map(h =>
              <th key={h} style={{ textAlign: "right", padding: "4px 8px", color: C.meta, fontSize: 9.5, textTransform: "uppercase" }}>{h}</th>)}</tr></thead>
            <tbody>{candles.map((k, i) => (
              <tr key={k.d} style={{ borderTop: `1px solid ${C.line}` }}>
                <td style={{ textAlign: "right", padding: "4px 8px", color: C.meta }}>D{i}</td>
                <td style={{ textAlign: "right", padding: "4px 8px", color: C.sub }}>{k.d.slice(0, 10)}</td>
                {[k.o, k.h, k.l, k.c].map((v, j) => <td key={j} style={{ textAlign: "right", padding: "4px 8px", color: C.text }}>₹{v}</td>)}
                <td style={{ textAlign: "right", padding: "4px 8px", color: issue != null && k.c >= issue ? C.green : C.red }}>{issue != null ? f1(pct(k.c, issue)) : "—"}</td>
                <td style={{ textAlign: "right", padding: "4px 8px", color: i > 0 ? (k.c >= candles[i - 1].c ? C.green : C.red) : C.dim }}>{i > 0 ? f1(pct(k.c, candles[i - 1].c)) : "—"}</td>
              </tr>))}</tbody>
          </table></div>
        ) : <div style={{ fontSize: 12, color: C.dim }}>No sessions captured yet — candles land with each pipeline run once trading begins.</div>}
      </Card>

      <Card><SectionHeader>What happened — evidence-backed</SectionHeader>
        {obs.length ? obs.map((o, i) => (
          <div key={i} style={{ padding: "8px 0", borderTop: i ? `1px solid ${C.line}` : undefined }}>
            <div style={{ display: "flex", gap: 6, alignItems: "baseline", flexWrap: "wrap" }}>
              <Badge label={o.certainty} tone={o.certainty === "Confirmed" ? "good" : "watch"} />
              <span style={{ fontSize: 12.5, fontWeight: 700, color: C.text }}>{o.observation}</span>
            </div>
            <div style={{ fontSize: 11, color: C.sub, fontFamily: FONT.mono, marginTop: 3 }}>{o.facts.join(" · ")}</div>
            {o.counter.length ? <div style={{ fontSize: 11, color: C.dim, marginTop: 2 }}>Counter-evidence: {o.counter.join(" ")}</div> : null}
          </div>
        )) : <div style={{ fontSize: 12, color: C.dim }}>Observations appear once the listing-day candle is captured.</div>}
      </Card>
    </div>
  );
}
