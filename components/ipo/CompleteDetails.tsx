"use client";
// components/ipo/CompleteDetails.tsx — THE full IPO record screen. KV-only
// consumer of the ipo-details-v1 snapshot. Every leaf is driven off
// DetailField.state (AVAILABLE / PENDING / MISSING / VENDOR_FALLBACK / STALE);
// real values render richly, genuine gaps show an honest reason + the producer
// that would fill them. NO JSON.stringify / [object Object] ever reaches the
// DOM — all values pass through the shared ValueNode renderer.
import { type ReactNode } from "react";
import { Badge } from "@/components/ui/primitives";
import { VARS as C, FONT, type Tone } from "@/lib/theme";
import {
  fieldDisplay, toValueNode, humanizeKey, classLabel, splitEvidence,
  deriveMarketCap, deriveLotValue, buildMissingRegister, fmtNum, fmtCr, fmtRupee,
  type ValueNode, type DetailField, type FieldState, type EvidenceItem,
} from "@/lib/ui/details-format";

type R = Record<string, any>;
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const mult = (n: number) => `${fmtNum(n)}×`;
const pct = (n: number) => `${fmtNum(n)}%`;
const miss = (reason: string, source: string): DetailField => ({ state: "MISSING", value: null, reason, source });

const STATE_TONE: Record<FieldState, Tone> = {
  AVAILABLE: "good", VENDOR_FALLBACK: "watch", STALE: "watch", PENDING: "watch", MISSING: "neutral",
};
const CLASS_TONE: Record<string, Tone> = {
  "VERIFIED FACT": "good", "DETERMINISTIC PRO-FORMA": "info", "SCENARIO / OPTIONALITY": "watch", "UNVERIFIED / UNKNOWN": "neutral",
};

// ── The single guard: render any value without stringifying it ───────────────
function Value({ node }: { node: ValueNode }) {
  if (node.kind === "empty") return <span style={{ color: C.dim }}>—</span>;
  if (node.kind === "scalar") return <span style={{ overflowWrap: "anywhere" }}>{node.text}</span>;
  if (node.kind === "list")
    return <ul style={{ margin: "2px 0", paddingLeft: 16, display: "grid", gap: 3 }}>{node.items.map((it, i) => <li key={i}><Value node={it} /></li>)}</ul>;
  return (
    <div style={{ display: "grid", gap: 3, minWidth: 0 }}>
      {node.rows.map((r, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(84px,.45fr) minmax(0,1fr)", gap: 6 }}>
          <span style={{ color: C.meta, fontSize: 11 }}>{r.label}</span>
          <div style={{ minWidth: 0 }}><Value node={r.value} /></div>
        </div>
      ))}
    </div>
  );
}

// ── A DetailField as a labeled row: value or honest missing/pending reason ───
function FieldRow({ label, f, fmt }: { label: string; f?: DetailField; fmt?: (n: number) => string }) {
  const fd = fieldDisplay(f);
  const raw = f?.value;
  const node: ValueNode = !fd.hasValue ? { kind: "empty" }
    : fmt && typeof raw === "number" ? { kind: "scalar", text: fmt(raw) }
    : toValueNode(raw);
  return (
    <div className="drow">
      <span className="dlabel">{label}</span>
      <div className="dval">
        {fd.hasValue
          ? <b><Value node={node} /></b>
          : <span style={{ color: C.dim }}>{fd.state === "PENDING" ? "pending" : "not available"}{fd.reason ? ` — ${fd.reason}` : ""}</span>}
        {fd.proxyLabel ? <> <Badge label={fd.proxyLabel} tone="watch" title="Proxy — not a disclosed or reported company ratio" /></> : null}
      </div>
      <Badge label={fd.state} tone={STATE_TONE[fd.state]} />
      {fd.hasValue && (fd.source || fd.as_of)
        ? <small className="dmeta">{fd.source ? `source: ${fd.source}` : ""}{fd.as_of ? `${fd.source ? " · " : ""}as of ${fd.as_of}` : ""}</small>
        : null}
    </div>
  );
}

// ── A computed / canonical scalar with an evidence-class badge ──────────────
function Metric({ label, text, cls, note }: { label: string; text: string; cls: string; note?: string }) {
  return (
    <div className="drow">
      <span className="dlabel">{label}</span>
      <div className="dval"><b>{text}</b></div>
      <Badge label={cls} tone={CLASS_TONE[cls] ?? "neutral"} />
      {note ? <small className="dmeta">{note}</small> : null}
    </div>
  );
}

// ── A collapsible section that still exposes a real <h2> heading ────────────
function Section({ id, title, sub, tone, open = true, children }:
  { id?: string; title: string; sub?: string; tone?: "green" | "blue" | "amber" | "plain"; open?: boolean; children: ReactNode }) {
  const bd = tone === "green" ? C.greenBd : tone === "blue" ? C.blueBd : tone === "amber" ? C.amberBd : C.border;
  const bg = tone === "green" ? C.greenBg : tone === "blue" ? C.blueBg : tone === "amber" ? C.amberBg : C.surface;
  return (
    <details open={open} className="sec" style={{ border: `1px solid ${bd}`, background: bg }}>
      <summary className="sechd">
        <span className="chev" aria-hidden>▸</span>
        <h2 id={id} style={{ margin: 0, fontSize: 14, fontFamily: FONT.display }}>{title}</h2>
        {sub ? <span className="secsub">{sub}</span> : null}
      </summary>
      <div className="secbody">{children}</div>
    </details>
  );
}

function EvidenceList({ items, empty }: { items: EvidenceItem[]; empty: string }) {
  if (!items.length) return <p style={{ color: C.sub, fontSize: 12 }}>{empty}</p>;
  return (
    <>{items.map((e, i) => (
      <article key={`${e.doc_id}-${e.page_number}-${i}`} style={{ borderTop: i ? `1px solid ${C.line}` : "none", padding: "10px 0" }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "baseline" }}>
          <strong style={{ fontSize: 12.5 }}>Verified excerpt, p.{e.page_number}</strong>
          {e.source_type ? <Badge label={String(e.source_type)} tone="info" /> : null}
          {e.direction ? <Badge label={String(e.direction)} tone={String(e.direction).toLowerCase() === "negative" ? "junk" : "neutral"} /> : null}
        </div>
        <blockquote style={{ margin: "7px 0", paddingLeft: 12, borderLeft: `3px solid ${C.green}`, overflowWrap: "anywhere" }}>{e.excerpt}</blockquote>
        <small style={{ color: C.meta, overflowWrap: "anywhere" }}>
          {[e.document?.doc_type, e.category].filter(Boolean).join(" · ")}
          {e.document?.url ? <> · <a href={String(e.document.url)} target="_blank" rel="noopener noreferrer">source document</a></> : null}
        </small>
      </article>
    ))}</>
  );
}

export default function CompleteDetails({ details: d }: { details: R }) {
  const id = d.identity || {};
  const issue = d.issue || {};
  const v = d.valuation || {};
  const o = d.listing_outcome || {};
  const dec = d.decision || {};
  const gov = d.governance_and_risk || {};
  const ai = d.ai_analysis || {};
  const p = d.intelligence_profile || null;
  const pv = p && p.valuation && p.valuation.status === "AVAILABLE" ? p.valuation : null;

  const issuePrice = fieldDisplay(issue.issue_price).hasValue ? Number(issue.issue_price.value) : null;
  const lotSize = fieldDisplay(issue.lot_size).hasValue ? Number(issue.lot_size.value) : null;
  const postShares = pv && finite(pv.post_issue_shares_cr) ? pv.post_issue_shares_cr : null;
  const marketCap = deriveMarketCap(issuePrice, postShares);
  const lotValue = deriveLotValue(lotSize, issuePrice);

  const { rhp, sbi, other } = splitEvidence(d.verified_evidence);
  const register = buildMissingRegister(d);
  const period = p?.provenance?.financial_period ? String(p.provenance.financial_period) : null;
  const basis = p?.provenance?.financial_basis ? String(p.provenance.financial_basis) : null;
  const periodNote = [period, basis].filter(Boolean).join(" · ") || undefined;

  // §3 canonical rows (only those actually present)
  const verifiedRows = pv ? [
    { label: "Reported PAT", text: fmtCr(pv.reported_pat_cr), on: finite(pv.reported_pat_cr) },
    { label: "Reported debt", text: fmtCr(pv.reported_debt_cr), on: finite(pv.reported_debt_cr) },
    { label: "Cash", text: fmtCr(pv.cash_cr), on: finite(pv.cash_cr) },
    { label: "EBITDA", text: fmtCr(p?.financials?.ebitda_cr), on: finite(p?.financials?.ebitda_cr) },
    { label: "ROCE", text: finite(pv.roce) ? pct(pv.roce) : "—", on: finite(pv.roce) },
  ].filter(m => m.on) : [];
  const proFormaRows = pv ? [
    { label: "Pro-forma PAT", text: fmtCr(pv.pro_forma_pat_cr), on: finite(pv.pro_forma_pat_cr) },
    { label: "Reported EPS", text: fmtRupee(pv.reported_eps), on: finite(pv.reported_eps) },
    { label: "Pro-forma EPS", text: fmtRupee(pv.pro_forma_eps), on: finite(pv.pro_forma_eps) },
    { label: "Reported P/E", text: finite(pv.reported_pe) ? mult(pv.reported_pe) : "—", on: finite(pv.reported_pe) },
    { label: "Pro-forma P/E", text: finite(pv.pro_forma_pe) ? mult(pv.pro_forma_pe) : "—", on: finite(pv.pro_forma_pe) },
    { label: "Net debt (post-IPO)", text: fmtCr(pv.net_debt_cr), on: finite(pv.net_debt_cr) },
    { label: "Post-IPO debt", text: fmtCr(pv.post_ipo_debt_cr), on: finite(pv.post_ipo_debt_cr) },
    { label: "EV / EBITDA", text: finite(pv.ev_ebitda) ? mult(pv.ev_ebitda) : "—", on: finite(pv.ev_ebitda) },
    { label: "ROE", text: finite(pv.roe) ? pct(pv.roe) : "—", on: finite(pv.roe) },
    { label: "Free cash flow", text: fmtCr(pv.fcf_cr), on: finite(pv.fcf_cr) },
    { label: "Post-issue shares", text: finite(pv.post_issue_shares_cr) ? `${fmtNum(pv.post_issue_shares_cr)} Cr sh` : "—", on: finite(pv.post_issue_shares_cr) },
  ].filter(m => m.on) : [];
  const canonMissing: string[] = pv && Array.isArray(pv.missing_inputs) ? pv.missing_inputs.map(String) : [];

  return (
    <main data-testid="complete-details" style={{ display: "grid", gap: 12, minWidth: 0 }}>
      {/* §1 IDENTITY & TIMELINE */}
      <Section id="identity" title="Identity & timeline">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 6 }}>
          <h1 style={{ fontFamily: FONT.display, margin: 0, fontSize: 20 }}>{id.company_name}</h1>
          {id.symbol ? <Badge label={String(id.symbol)} tone="neutral" mono /> : null}
          {id.isin ? <Badge label={String(id.isin)} tone="neutral" mono /> : null}
        </div>
        <FieldRow label="Listing date" f={id.listing_date} />
        <FieldRow label="Sector / industry" f={miss("Not carried in the details snapshot.", "NSE / RHP classification")} />
        <FieldRow label="Lifecycle status" f={miss("No NSE lifecycle status field ships in v1.", "NSE lifecycle")} />
        <FieldRow label="Open / close / allotment dates" f={miss("Only the listing date ships in v1.", "NSE / Chittorgarh timeline")} />
      </Section>

      {/* §2 ISSUE OVERVIEW */}
      <Section id="issue" title="Issue overview">
        <FieldRow label="Issue price" f={issue.issue_price} fmt={fmtRupee} />
        <FieldRow label="Band low" f={issue.band_low} fmt={fmtRupee} />
        <FieldRow label="Band high" f={issue.band_high} fmt={fmtRupee} />
        <FieldRow label="Issue size" f={issue.issue_size_cr} fmt={(n) => fmtCr(n)} />
        <FieldRow label="Fresh issue" f={issue.fresh_issue_cr} fmt={(n) => fmtCr(n)} />
        <FieldRow label="Offer for sale (OFS)" f={issue.ofs_cr} fmt={(n) => fmtCr(n)} />
        <FieldRow label="Lot size" f={issue.lot_size} fmt={(n) => `${fmtNum(n)} sh`} />
        <FieldRow label="Face value" f={issue.face_value} fmt={fmtRupee} />
        <div className="drow">
          <span className="dlabel">Market cap at issue</span>
          <div className="dval">{marketCap.available ? <b>{marketCap.text}</b> : <span style={{ color: C.dim }}>not available — {marketCap.reason}</span>}</div>
          <Badge label="DETERMINISTIC PRO-FORMA" tone="info" />
          <small className="dmeta">{marketCap.formula}</small>
        </div>
        <div className="drow">
          <span className="dlabel">Lot value</span>
          <div className="dval">{lotValue.available ? <b>{lotValue.text}</b> : <span style={{ color: C.dim }}>not available — {lotValue.reason}</span>}</div>
          <Badge label="DETERMINISTIC PRO-FORMA" tone="info" />
          <small className="dmeta">{lotValue.formula}</small>
        </div>
        <FieldRow label="Reservation split (QIB / NII / retail)" f={issue.reservation_split} />
        <FieldRow label="Subscription (× times, per category)" f={miss("Subscription figures are not shipped in this snapshot.", "NSE archive")} />
      </Section>

      {/* §3 FINANCIALS & DETERMINISTIC PRO-FORMA */}
      <Section id="financials" title="Financials & pro-forma" sub={periodNote}>
        {!pv ? (
          <p style={{ color: C.sub, fontSize: 12.5 }}>
            <Badge label="UNAVAILABLE" tone="neutral" /> Canonical financial evidence is not yet sufficient to build this profile —
            canonical financials require reported PAT, debt, post-issue shares and issue price, and not all are present.
            <br />Revenue and margins are not carried in v1 (source: RHP financial-table extraction).
          </p>
        ) : (
          <>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
              <Badge label="VERIFIED FACT" tone="good" /><Badge label="DETERMINISTIC PRO-FORMA" tone="info" />
              <Badge label="SCENARIO / OPTIONALITY" tone="watch" />
            </div>
            <Metric label="Status / evidence class" text={`${String(pv.status)} · ${classLabel(pv.classification)}`} cls={classLabel(pv.classification)} />
            {verifiedRows.map((m) => <Metric key={m.label} label={m.label} text={m.text} cls="VERIFIED FACT" note={periodNote} />)}
            {proFormaRows.map((m) => <Metric key={m.label} label={m.label} text={m.text} cls="DETERMINISTIC PRO-FORMA" note={pv?.formulas?.[proFormaFormulaKey(m.label)] as string | undefined} />)}
            {canonMissing.length ? <small style={{ color: C.meta, display: "block", marginTop: 6 }}>Missing pro-forma inputs: {canonMissing.map(humanizeKey).join(", ")}.</small> : null}
            <FieldRow label="Revenue & margins" f={miss("Revenue is not carried in financial_statements; margins cannot be derived.", "RHP financial-table extraction")} />
          </>
        )}
      </Section>

      {/* §4 VALUATION & FAIR VALUE — the decision core */}
      <Section id="valuation" title="Valuation & fair value" tone="blue">
        <FieldRow label="House score" f={v.score} />
        <div className="drow">
          <span className="dlabel">Verdict band</span>
          <div className="dval">{fieldDisplay(v.band).hasValue ? <Badge label={String(v.band.value)} /> : <span style={{ color: C.dim }}>not available{v.band?.reason ? ` — ${v.band.reason}` : ""}</span>}</div>
          <Badge label={fieldDisplay(v.band).state} tone={STATE_TONE[fieldDisplay(v.band).state]} />
          <small className="dmeta">qualitative label only — no historical-performance %</small>
        </div>
        <FieldRow label="P/E" f={v.pe} fmt={mult} />
        <FieldRow label="P/B" f={v.pb} fmt={mult} />
        <FieldRow label="P/E basis" f={v.pe_source} />
        <FieldRow label="P/B basis" f={v.pb_source} />
        <FieldRow label="Peer median P/E" f={v.peer_median_pe} fmt={mult} />
        <FieldRow label="Engine version" f={v.engine_version} />

        <div className="subhd">House fair value</div>
        <FieldRow label="Fair value low" f={v.fair_value_low} fmt={fmtRupee} />
        <FieldRow label="Fair value high" f={v.fair_value_high} fmt={fmtRupee} />
        <div className="drow">
          <span className="dlabel">Margin of safety</span>
          <div className="dval">{marginOfSafety(v.margin_of_safety)}</div>
          <Badge label={fieldDisplay(v.margin_of_safety).state} tone={STATE_TONE[fieldDisplay(v.margin_of_safety).state]} />
          <small className="dmeta">vs issue price · (fair_value − issue_price) / issue_price</small>
        </div>

        <div className="subhd">Canonical pro-forma fair value</div>
        {pv && finite(pv.fair_value) ? (
          <>
            <Metric label="Canonical fair value" text={fmtRupee(pv.fair_value)} cls="DETERMINISTIC PRO-FORMA" note="peer_pe × pro-forma EPS" />
            {finite(pv.margin_of_safety_pct) ? <Metric label="Canonical margin of safety" text={pct(pv.margin_of_safety_pct)} cls="DETERMINISTIC PRO-FORMA" note="(fair_value − issue_price) / fair_value" /> : null}
          </>
        ) : (
          <p style={{ color: C.sub, fontSize: 12 }}>Not computable — a peer multiple and a positive pro-forma EPS are required{pv ? "" : "; canonical profile unavailable"}.</p>
        )}
        <FieldRow label="Earnings basis" f={earningsBasisField(p, v)} />
        <FieldRow label="Inputs used" f={v.inputs_used} />
        <FieldRow label="Missing inputs" f={v.missing_inputs} />
      </Section>

      {/* §5 RHP EVIDENCE */}
      <Section id="rhp-evidence" title="RHP evidence" tone="green" sub={`${rhp.length} excerpt${rhp.length === 1 ? "" : "s"}`}>
        <EvidenceList items={rhp} empty="No verified RHP excerpts are currently available." />
        {other.length ? <><div className="subhd">Other structured evidence</div><EvidenceList items={other} empty="" /></> : null}
      </Section>

      {/* §6 SBI EVIDENCE */}
      <Section id="sbi-evidence" title="SBI evidence" tone="green" sub={`${sbi.length} excerpt${sbi.length === 1 ? "" : "s"}`}>
        <EvidenceList items={sbi} empty="No SBI research-note excerpts for this IPO in this snapshot." />
        <FieldRow label="SBI rating / target / peer table" f={miss("No structured SBI extraction ships; only verbatim SBI excerpts appear above (when present).", "SBI Sonnet extraction")} />
      </Section>

      {/* AI analysis (evidence-class prose, kept distinct from verified excerpts) */}
      <Section id="ai-analysis" title="AI analysis" tone="blue">
        <div style={{ fontSize: 11.5, color: C.meta, marginBottom: 6 }}>
          Model {show(ai.model)} · Prompt {show(ai.prompt_version)} · Confidence {show(ai.confidence)}{ai.analyzed_at ? ` · ${ai.analyzed_at}` : ""}
        </div>
        {ai.state === "AVAILABLE"
          ? <Value node={toValueNode(ai.findings)} />
          : <p style={{ color: C.sub }}>{ai.reason || "AI analysis has not yet run."}</p>}
      </Section>

      {/* §7 GOVERNANCE & RISK */}
      <Section id="governance" title="Governance & risk">
        {Object.entries(gov).map(([k, f]) => <FieldRow key={k} label={humanizeKey(k)} f={f as DetailField} />)}
        <FieldRow label="Red-flag count" f={{ state: ai.red_flag_count != null ? "AVAILABLE" : "PENDING", value: ai.red_flag_count ?? null, reason: ai.reason }} />
        <FieldRow label="Junk signals" f={ai.state === "AVAILABLE"
          ? { state: "AVAILABLE", value: Array.isArray(ai.junk_signals) && ai.junk_signals.length ? ai.junk_signals : ["None recorded"] }
          : { state: "PENDING", value: null, reason: ai.reason || "AI analysis has not yet run." }} />
      </Section>

      {/* §8 PERSISTED DECISION — Company Quality, kept visually separate */}
      <Section id="decision" title="Persisted decision — company quality" tone="amber">
        <div className="drow">
          <span className="dlabel">Verdict</span>
          <div className="dval">{fieldDisplay(dec.verdict).hasValue ? <Badge label={String(dec.verdict.value)} /> : <span style={{ color: C.dim }}>pending — a persisted decision is not yet available</span>}</div>
          <Badge label={fieldDisplay(dec.verdict).state} tone={STATE_TONE[fieldDisplay(dec.verdict).state]} />
          <small className="dmeta">stored verdict — displayed as persisted, not relabeled</small>
        </div>
        <FieldRow label="Reasons" f={dec.reasons} />
        <FieldRow label="Evidence" f={dec.evidence} />
        {dec.verdict?.value === "JUNK" ? <FieldRow label="Derived kill reason" f={dec.kill_reason} /> : null}
        <FieldRow label="Engine version" f={v.engine_version} />
      </Section>

      {/* §9 LISTING OUTCOME */}
      <Section id="listing" title="Listing outcome">
        <FieldRow label="Listing open" f={o.listing_open} fmt={fmtRupee} />
        <FieldRow label="Gap %" f={o.gap_pct} fmt={pct} />
        <FieldRow label="Day-1 close" f={o.d1_close} fmt={fmtRupee} />
        <FieldRow label="Best close" f={o.best_close} fmt={fmtRupee} />
        <FieldRow label="Worst close" f={o.worst_close} fmt={fmtRupee} />
        <FieldRow label="Held positive vs open" f={o.hold_positive_vs_open} />
        <FieldRow label="Winner (≥35% vs issue)" f={o.winner_35} />
        <FieldRow label="Pool" f={o.pool} />
        <FieldRow label="Ceiling indicator (non-executable)" f={o.ceiling_20} />
        <FieldRow label="Computed at" f={o.computed_at} />
        <FieldRow label="Dataset version" f={o.dataset_version} />
      </Section>

      {/* GMP — stale by design */}
      <section data-testid="gmp-stale" style={{ border: `1px solid ${C.amberBd}`, background: C.amberBg, borderRadius: "var(--radius-3)", padding: 14 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}><h2 style={{ margin: 0, fontSize: 14, fontFamily: FONT.display }}>Grey market premium</h2><Badge label="STALE" tone="watch" /></div>
        <p style={{ fontSize: 12, color: C.sub, margin: "6px 0 0" }}>Available: no · Last updated: {d.gmp?.last_updated} · {d.gmp?.reason}</p>
      </section>

      {/* §10 MISSING-DATA REGISTER — collapsed by default */}
      <Section id="missing-register" title="Missing-data register" sub={`${register.length} pending`} open={false}>
        <p style={{ fontSize: 11.5, color: C.meta, marginTop: 0 }}>Everything this IPO is missing, and the producer that would fill it. The honest inverse of the sections above.</p>
        <div className="aac-table-wrap">
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead><tr>{["Field", "Why it's missing", "Filling producer"].map(h => <th key={h} style={{ textAlign: "left", padding: "5px 8px", color: C.meta, fontSize: 9.5, textTransform: "uppercase", borderBottom: `1px solid ${C.line}` }}>{h}</th>)}</tr></thead>
            <tbody>{register.map((row, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${C.line}` }}>
                <td style={{ padding: "5px 8px", color: C.text, fontWeight: 600, overflowWrap: "anywhere" }}>{row.field}</td>
                <td style={{ padding: "5px 8px", color: C.sub, overflowWrap: "anywhere" }}>{row.reason}</td>
                <td style={{ padding: "5px 8px", color: C.meta, overflowWrap: "anywhere" }}>{row.producer}</td>
              </tr>))}</tbody>
          </table>
        </div>
      </Section>

      <style jsx>{`
        .sec { border-radius: var(--radius-3); padding: 4px 14px; }
        .sec[open] { padding-bottom: 14px; }
        .sechd { display: flex; align-items: center; gap: 8px; cursor: pointer; list-style: none; padding: 12px 0; user-select: none; }
        .sechd::-webkit-details-marker { display: none; }
        .secsub { color: ${C.meta}; font-size: 11px; font-family: ${FONT.mono}; margin-left: auto; }
        .chev { color: ${C.meta}; font-size: 11px; transition: transform .15s ease; }
        .sec[open] .chev { transform: rotate(90deg); }
        .secbody { display: grid; gap: 0; min-width: 0; }
        .subhd { font-size: 10.5px; font-weight: 800; letter-spacing: .5px; text-transform: uppercase; color: ${C.meta}; margin: 12px 0 4px; }
        .drow { display: grid; grid-template-columns: minmax(130px,.8fr) minmax(0,1.4fr) auto; gap: 8px; padding: 8px 0; border-top: 1px solid ${C.line}; align-items: start; overflow-wrap: anywhere; }
        .drow:first-child { border-top: none; }
        .dlabel { color: ${C.meta}; font-size: 12px; }
        .dval { min-width: 0; font-size: 13px; }
        .dmeta { grid-column: 2 / 4; color: ${C.meta}; font-size: 10.5px; }
        @media (max-width: 600px) {
          .drow { grid-template-columns: 1fr auto; }
          .dval, .dmeta { grid-column: 1 / 3; }
        }
      `}</style>
    </main>
  );
}

// Non-stringifying scalar for the AI meta line (numbers/strings only).
function show(v: unknown): string {
  if (v == null || v === "") return "—";
  if (typeof v === "number") return fmtNum(v);
  if (typeof v === "object") return "—"; // never [object Object]; objects render via <Value/>
  return String(v);
}

function proFormaFormulaKey(label: string): string {
  const map: Record<string, string> = {
    "Pro-forma PAT": "pro_forma_pat", "Reported EPS": "eps", "Pro-forma EPS": "eps",
    "Reported P/E": "pe", "Pro-forma P/E": "pe", "EV / EBITDA": "ev_ebitda", "Free cash flow": "fcf", "ROCE": "roce",
  };
  return map[label] ?? "";
}

function marginOfSafety(f?: DetailField) {
  const fd = fieldDisplay(f);
  if (!fd.hasValue) return <span style={{ color: C.dim }}>not available{fd.reason ? ` — ${fd.reason}` : ""}</span>;
  const val = f!.value as R;
  if (val && finite(val.mos_low_pct) && finite(val.mos_high_pct))
    return <b>{pct(val.mos_low_pct)} to {pct(val.mos_high_pct)}</b>;
  return <b><Value node={toValueNode(val)} /></b>;
}

function earningsBasisField(p: R | null, v: R): DetailField {
  const epsField = p?.provenance?.post_issue_shares_cr?.rhp_eps_field;
  const warn = p?.provenance?.post_issue_shares_cr?.alignment_warning;
  if (epsField) return { state: "AVAILABLE", value: warn ? { rhp_eps_field: String(epsField), note: String(warn) } : { rhp_eps_field: String(epsField) }, source: "valuation.inputs_used" };
  const src = fieldDisplay(v?.pe_source);
  if (src.hasValue) return { state: "AVAILABLE", value: String(v.pe_source.value), source: "valuation" };
  return miss("Earnings basis (RHP vs canonical) is not recorded in this snapshot.", "valuation");
}
