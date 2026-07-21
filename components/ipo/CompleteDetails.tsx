"use client";
// components/ipo/CompleteDetails.tsx — the "IPO 360" page (2026-07-22 v1).
// Renders EVERY field the production payload already carries, in the A–O
// skeleton. Missing data renders "—" with the responsible source — never
// invented, never hidden. Field-by-source matrix: docs/DETAILS_AND_REVIEW.md.
import { Card, Stat, SectionHeader, Badge, EmptyState } from "@/components/ui/primitives";
import { VARS as C, FONT } from "@/lib/theme";

type R = Record<string, unknown>;
const S = (v: unknown) => (v == null || v === "" ? null : String(v));
const N = (v: unknown) => (v == null || v === "" || isNaN(Number(v)) ? null : Number(v));
const D = (v: unknown) => (S(v) ? String(v).slice(0, 10) : null);
const Rs = (v: unknown) => (N(v) != null ? `₹${N(v)}` : null);
const Cr = (v: unknown) => (N(v) != null ? `₹${Number(N(v)).toLocaleString("en-IN")}cr` : null);
const P = (v: unknown) => (N(v) != null ? `${N(v)}%` : null);

function Row({ k, v, src }: { k: string; v: string | null; src?: string }) {
  return (
    <div style={{ display: "flex", gap: 10, padding: "5px 0", borderBottom: `1px solid ${C.line}`, fontSize: 12 }}>
      <span style={{ color: C.meta, flex: "0 0 46%" }}>{k}</span>
      <span style={{ color: v ? C.text : C.dim, fontFamily: FONT.mono, flex: 1 }}>
        {v ?? "—"}{!v && src ? <span style={{ fontSize: 9.5, color: C.dim }}>  · pending ({src})</span> : null}
      </span>
    </div>
  );
}

export default function CompleteDetails({ c }: { c: R }) {
  if (!c) return <EmptyState title="Pick an IPO to open its complete details." hint="Search or tap any card, then Complete Details." />;
  const r = (c.research ?? {}) as R;
  const cq = (r.company_quality ?? {}) as R;
  const news = c.news as R | null;
  const insights = Array.isArray(c.insights) ? (c.insights as R[]) : [];
  const sbi = ((): R => { try { return typeof c.sbi_full === "string" ? JSON.parse(String(c.sbi_full)) : (c.sbi_full as R) ?? {}; } catch { return {}; } })();
  return (
    <div style={{ display: "grid", gap: 12 }}>
      {/* A · Identity + decision summary first (5-second rule) */}
      <Card>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontFamily: FONT.display, fontWeight: 800, fontSize: 17, color: C.text }}>{S(c.company_name)}</span>
          {S(c.sym) ? <span style={{ fontFamily: FONT.mono, fontSize: 11, color: C.dim }}>{S(c.sym)}</span> : null}
          {S(c.state) ? <Badge label={String(c.state)} /> : null}
          {cq.status === "CONFIRMED" && cq.verdict ? <Badge label={String(cq.verdict)} /> : <Badge label="QUALITY: INCOMPLETE" tone="neutral" />}
          {S(c.verdict) ? <Badge label={`AAC · ${c.verdict}`} /> : null}
        </div>
        <div className="aac-cols-4" style={{ marginTop: 10 }}>
          <Stat label="Issue price" value={Rs(c.issue_price) ?? "—"} />
          <Stat label="Size" value={Cr(c.issue_size_cr) ?? "—"} />
          <Stat label="Score" value={`${N(c.ipo_score) ?? "—"} · ${S(c.score_band) ?? "—"}`} />
          <Stat label="Fair value" value={S((r as R).fair_value_status) === "READY" ? "computed" : "unavailable"}
            sub={S((r as R).fair_value_status) === "READY" ? undefined : "needs EPS + peer P/E"} />
        </div>
      </Card>

      {/* B · Timeline */}
      <Card><SectionHeader>Timeline</SectionHeader>
        <Row k="Subscription opens" v={D(c.open_date)} src="Chittorgarh" />
        <Row k="Subscription closes" v={D(c.close_date)} src="Chittorgarh" />
        <Row k="Basis of allotment" v={null} src="NSE — not yet captured" />
        <Row k="Listing date" v={D(c.listing_date)} src="NSE" />
      </Card>

      {/* C · Issue structure */}
      <Card><SectionHeader>Issue structure</SectionHeader>
        <Row k="Price band" v={N(c.band_low) != null ? `₹${N(c.band_low)}–₹${N(c.band_high)}` : null} src="Chittorgarh" />
        <Row k="Fresh issue" v={Cr(c.fresh_issue_cr)} src="RHP" />
        <Row k="Offer for sale" v={Cr(c.ofs_cr)} src="RHP" />
        <Row k="OFS share" v={P(c.ofs_pct)} src="RHP" />
        <Row k="Lot size" v={null} src="Chittorgarh — not yet captured" />
        <Row k="BRLMs" v={S(c.brlm_names)} src="Chittorgarh" />
      </Card>

      {/* D · Demand */}
      <Card><SectionHeader>Demand & anchors</SectionHeader>
        <Row k="Anchor investors" v={N(c.anchor_count) != null ? `${c.anchor_count} anchors` : null} src="NSE anchor report" />
        <Row k="QIB (final)" v={N(c.final_qib) != null ? `${c.final_qib}×` : null} src="NSE" />
        <Row k="NII (final)" v={N(c.final_nii) != null ? `${c.final_nii}×` : null} src="NSE" />
        <Row k="Retail (final)" v={N(c.final_retail) != null ? `${c.final_retail}×` : null} src="NSE" />
        <Row k="Total (final)" v={N(c.final_total) != null ? `${c.final_total}×` : null} src="NSE" />
        <Row k="Day-wise subscription" v={null} src="NSE — not yet captured" />
      </Card>

      {/* E · Financ何 + valuation */}
      <Card><SectionHeader>Financials & valuation</SectionHeader>
        <Row k="EPS (post-issue)" v={S(c.eps_post)} src="RHP" />
        <Row k="P/E at issue" v={S(c.ipo_pe)} src="IPOMatrix" />
        <Row k="Peer median P/E" v={S(c.peer_median_pe)} src="SBI note / Screener" />
        <Row k="ROE" v={P(c.roe)} src="IPOMatrix" />
        <Row k="Debt / equity" v={S(c.debt_equity)} src="IPOMatrix" />
        <Row k="Revenue CAGR (3y)" v={P(c.revenue_cagr_3y)} src="RHP" />
        <Row k="3-line financial table" v={null} src="RHP tables — extraction not yet wired" />
      </Card>

      {/* F · Research & evidence */}
      <Card><SectionHeader>Research & evidence</SectionHeader>
        <Row k="RHP status" v={S((r as R).rhp_status)} />
        <Row k="SBI status" v={S((r as R).sbi_status)} />
        {S(sbi.one_line) ? <Row k="SBI one-line" v={S(sbi.one_line)} /> : <Row k="SBI one-line" v={null} src="SBI note" />}
        {insights.length ? insights.slice(0, 6).map((ev, i) => (
          <div key={i} style={{ padding: "6px 0", borderBottom: `1px solid ${C.line}`, fontSize: 12 }}>
            <span style={{ fontWeight: 800, color: ev.direction === "negative" ? C.red : ev.direction === "positive" ? C.green : C.sub }}>
              {ev.direction === "negative" ? "−" : ev.direction === "positive" ? "+" : "·"} </span>
            <span style={{ color: C.text }}>{String(ev.statement ?? "")}</span>
            {S(ev.excerpt) ? <div style={{ color: C.dim, fontSize: 11, fontStyle: "italic" }}>&ldquo;{String(ev.excerpt)}&rdquo; <span style={{ fontStyle: "normal" }}>· {String(ev.source ?? "RHP")} {String(ev.locator ?? "")}</span></div> : null}
          </div>
        )) : <Row k="RHP evidence rows" v={null} src="Sonnet fan-out — pending analysis" />}
      </Card>

      {/* G · Street report */}
      <Card><SectionHeader>Street report</SectionHeader>
        {news && S(news.headline) ? (
          <div style={{ fontSize: 12.5 }}>
            <a href={String(news.url)} target="_blank" rel="noopener noreferrer" style={{ color: C.blue, fontWeight: 700 }}>
              {String(news.headline)}</a>
            <div style={{ color: C.dim, fontSize: 11, marginTop: 2 }}>{String(news.publisher)}{S(news.published_at) ? ` · ${D(news.published_at)}` : ""} · linked & summarized, never scraped</div>
            {S(news.snippet) ? <div style={{ color: C.sub, fontSize: 11.5, marginTop: 4 }}>{String(news.snippet)}</div> : null}
          </div>
        ) : <div style={{ fontSize: 12, color: C.dim }}>No street report available yet — discovery runs with the pipeline (Reuters preferred; ET/MC fallback); a manual override always wins.</div>}
      </Card>
    </div>
  );
}
