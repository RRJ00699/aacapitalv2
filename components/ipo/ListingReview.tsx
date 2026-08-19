"use client";
// components/ipo/ListingReview.tsx — the Listing Review / journey screen: what
// actually happened on listing day and across the first five sessions.
//
// KV-only consumer. It reads two existing KV-backed routes and nothing else:
//   /api/ipo/journey?sym=|isin=   -> journey:isin:<ISIN>:v1  (candles + level obs)
//   /api/ipo/details/<ISIN>       -> ipo-details:isin:<ISIN>:v1 (listing_outcome)
// No new API route, no SQL, no pipeline/lib-v2 dependency. The journey route
// also resolves sym -> ISIN, which is how a command-snapshot row without an
// ISIN still reaches its details record.
//
// Every listing-outcome leaf is rendered through `fieldDisplay` from
// lib/ui/details-format.ts — the SAME state renderer Complete Details uses, not
// a copy of it: AVAILABLE shows the value, PENDING/MISSING shows its reason.
// Values reach the DOM only via ValueNode, so no JSON.stringify and no
// [object Object] can leak. The one thing local to this file is the tiny JSX
// walker for a ValueNode; the state/serialisation logic is all imported.
import { useEffect, useState, type ReactNode } from "react";
import { Badge, Card, SectionHeader, EmptyState, ErrorState, Skeleton } from "@/components/ui/primitives";
import { VARS as C, FONT, type Tone } from "@/lib/theme";
import {
  fieldDisplay, toValueNode, absenceCopy, lifecycleFacts, LIFECYCLE_UNKNOWN,
  type DetailField, type FieldState, type ValueNode, type LifecycleFacts,
} from "@/lib/ui/details-format";
import {
  tapeView, outcomeRows, deriveGap, hasShippedGap, discoveryView, listingDayFacts, toNumber,
  type JourneyResponse, type DiscoveryRow, type Trend,
  DISCOVERY_CAVEAT, DISCOVERY_SCOPE_NOTE, DISCOVERY_LABEL_FALLBACK, FIRST_SESSIONS, NON_ASSERTING_STATES,
} from "@/lib/ui/listing-review-format";
import { reviewState, observations, type Facts } from "@/lib/listing-review";

type R = Record<string, unknown>;
const ISIN_RE = /^[A-Z0-9]{12}$/;
/** Narrow an unknown branch of a snapshot to a record, without casting to any. */
const obj = (v: unknown): R | null => (typeof v === "object" && v !== null && !Array.isArray(v) ? (v as R) : null);
const str = (v: unknown): string => (typeof v === "string" ? v : v == null ? "" : String(v));

const STATE_TONE: Record<FieldState, Tone> = {
  AVAILABLE: "good", VENDOR_FALLBACK: "watch", STALE: "watch", PENDING: "watch", MISSING: "neutral",
};
const TREND_COLOR: Record<Trend, string> = { up: C.green, down: C.red, flat: C.sub, none: C.dim };

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

/**
 * A row driven by DetailField.state: value when there is one, reason when not.
 * The absent branch prints `lead` + the sentence `absenceCopy` chose — the
 * producer's own reason wherever it wrote one, a lifecycle-specific sentence
 * where it only left its generic default. The badge keeps the payload's state.
 */
function StateRow({ label, state, hasValue, node, lead, reason, source, asOf, caption, producer }: {
  label: string; state: FieldState; hasValue: boolean; node: ValueNode; lead?: string;
  reason?: string | null; source?: string | null; asOf?: string | null; caption?: string | null;
  producer?: string | null;
}) {
  const meta = caption || (hasValue && (source || asOf)) || (!hasValue && producer);
  return (
    <div className="lrow">
      <span className="llabel">{label}</span>
      <div className="lval">
        {hasValue
          ? <b><Value node={node} /></b>
          : <span style={{ color: C.dim }}>{lead ?? (state === "PENDING" ? "pending" : "not available")}{reason ? ` — ${reason}` : ""}</span>}
      </div>
      <Badge label={state} tone={STATE_TONE[state]} />
      {meta
        ? <small className="lmeta">
            {caption ?? ""}
            {caption && hasValue && (source || asOf) ? " · " : ""}
            {hasValue && source ? `source: ${source}` : ""}
            {hasValue && asOf ? `${source ? " · " : ""}as of ${asOf}` : ""}
            {!hasValue && producer ? `${caption ? " · " : ""}producer: ${producer}` : ""}
          </small>
        : null}
    </div>
  );
}

function FieldRow({ label, field, format, caption, k, lc = LIFECYCLE_UNKNOWN }: {
  label: string; field?: unknown; format?: (n: number) => string; caption?: string | null;
  k?: string; lc?: LifecycleFacts;
}) {
  const f = (field && typeof field === "object" ? field : undefined) as DetailField | undefined;
  const fd = fieldDisplay(f);
  const node: ValueNode = !fd.hasValue ? { kind: "empty" }
    : format && typeof f?.value === "number" ? { kind: "scalar", text: format(f.value as number) }
    : toValueNode(f?.value);
  const gap = fd.hasValue ? null : absenceCopy(k, f, lc);
  return <StateRow label={label} state={fd.state} hasValue={fd.hasValue} node={node}
    lead={gap?.lead} reason={gap ? gap.reason : fd.reason} source={fd.source} asOf={fd.as_of}
    caption={caption ?? null} producer={gap?.producer ?? null} />;
}

function Note({ children }: { children: ReactNode }) {
  return <p style={{ fontSize: 11.5, color: C.meta, margin: "8px 0 0", overflowWrap: "anywhere" }}>{children}</p>;
}

function ObservationRows({ rows }: { rows: DiscoveryRow[] }) {
  return (
    <div style={{ display: "grid", gap: 4, marginTop: 6 }}>
      {rows.map((row, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(110px,.5fr) minmax(0,1fr)", gap: 8, fontSize: 12 }}>
          <span style={{ color: C.meta }}>{row.label}</span>
          <div style={{ minWidth: 0, color: C.text, fontFamily: FONT.mono }}><Value node={row.value} /></div>
        </div>
      ))}
    </div>
  );
}

type Load =
  | { kind: "ready"; journey: JourneyResponse & R; details: R | null; detailsNote: string | null; atMs: number }
  | { kind: "error"; title: string; detail: string };

export default function ListingReview({ c }: { c: R }) {
  const sym = str(c?.sym).toUpperCase();
  const isinProp = str(c?.isin).toUpperCase();
  // One identity key for the fetch: while the answer on hand is for a different
  // IPO (or none yet), the screen is loading. Keeping it in state avoids a
  // synchronous setState inside the effect.
  const identity = ISIN_RE.test(isinProp) ? `isin:${isinProp}` : `sym:${sym}`;
  const [result, setResult] = useState<{ identity: string; load: Load } | null>(null);

  useEffect(() => {
    if (!sym && !ISIN_RE.test(isinProp)) return;
    const ac = new AbortController();
    (async () => {
      const query = ISIN_RE.test(isinProp) ? `isin=${encodeURIComponent(isinProp)}` : `sym=${encodeURIComponent(sym)}`;
      const jr = await fetch(`/api/ipo/journey?${query}`, { signal: ac.signal });
      if (!jr.ok) throw new Error(`Journey snapshot request failed (${jr.status}).`);
      const journey = await jr.json() as JourneyResponse & R;
      const isin = str(journey?.isin ?? isinProp).toUpperCase();
      let details: R | null = null;
      let detailsNote: string | null = null;
      if (ISIN_RE.test(isin)) {
        const dr = await fetch(`/api/ipo/details/${encodeURIComponent(isin)}`, { signal: ac.signal });
        if (dr.ok) {
          const body = obj(await dr.json());
          if (body?.schema_version === "ipo-details-v1") details = body;
          else detailsNote = "The details snapshot for this ISIN does not carry the ipo-details-v1 contract, so no listing outcome is shown.";
        } else if (dr.status === 404) {
          detailsNote = `No ipo-details-v1 snapshot is published for ${isin} — the listing-outcome record is built only for the pipeline's bounded universe.`;
        } else {
          detailsNote = `Listing-outcome record unavailable (${dr.status}).`;
        }
      } else {
        detailsNote = "No ISIN resolved for this selection, and the listing-outcome record is keyed by ISIN.";
      }
      setResult({ identity, load: { kind: "ready", journey, details, detailsNote, atMs: Date.now() } });
    })().catch((e: unknown) => {
      const err = e as { name?: string; message?: string };
      if (err?.name === "AbortError") return;
      setResult({ identity, load: { kind: "error", title: "Listing review unavailable", detail: String(err?.message ?? e) } });
    });
    return () => ac.abort();
  }, [sym, isinProp, identity]);

  const load: Load | null = result && result.identity === identity ? result.load : null;

  if (!c) return <EmptyState title="Pick an IPO to review its listing." hint="The review runs from listing day through the first five sessions." />;
  if (!sym && !ISIN_RE.test(isinProp))
    return <EmptyState title="This selection carries no symbol or ISIN."
      hint="The journey and listing-outcome snapshots are keyed by ISIN (resolved from the symbol), so neither can be read for it." />;
  if (!load) return <div aria-label="Loading listing review"><Skeleton h={110} n={4} /></div>;
  if (load.kind === "error") return <ErrorState title={load.title} detail={load.detail} />;

  const { journey, details, detailsNote, atMs } = load;
  const outcome = obj(details?.listing_outcome);
  const issueField = obj(details?.issue)?.issue_price;
  const issueDisplay = fieldDisplay(obj(issueField) as DetailField | undefined);
  const issuePrice = issueDisplay.hasValue ? toNumber(obj(issueField)?.value) : toNumber(c.issue_price);
  const listingDateField = obj(details?.identity)?.listing_date;
  const listingDateDisplay = fieldDisplay(obj(listingDateField) as DetailField | undefined);
  const listingDate = listingDateDisplay.hasValue ? str(obj(listingDateField)?.value)
    : (c.listing_date ? str(c.listing_date) : null);

  // The same payload-derived lifecycle read Complete Details uses, so both
  // screens call the same absence the same thing.
  const lc = lifecycleFacts(details ?? undefined);

  const tape = tapeView(journey, issuePrice);
  const sessionsCaptured = tape.kind === "rows" ? tape.sessionsCaptured : 0;
  // `atMs` is the moment the snapshots were read — a value, not a render-time clock.
  const stage = reviewState(listingDate, atMs + 5.5 * 3600_000, false, sessionsCaptured);
  const rows = outcomeRows(outcome);
  const listingOpenDisplay = fieldDisplay(obj(outcome?.listing_open) as DetailField | undefined);
  const gap = deriveGap(listingOpenDisplay.hasValue ? obj(outcome?.listing_open)?.value : null, issuePrice);
  const showDerivedGap = !hasShippedGap(outcome);
  const discovery = discoveryView(journey?.level_observation);
  const day0 = listingDayFacts(journey, issuePrice);
  const facts: Facts = { ...day0, gmpImplied: null, fairValue: null, deliveryPct: null, volume: null, offeredShares: null };
  const reads = day0.issue != null && day0.open != null ? observations(facts) : [];
  const company = str(obj(details?.identity)?.company_name || c.company_name || journey?.sym || sym);
  const resolvedIsin = str(journey?.isin ?? isinProp).toUpperCase();

  return (
    <div data-testid="listing-review" style={{ display: "grid", gap: 12, minWidth: 0 }}>
      <Card>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <h2 style={{ margin: 0, fontFamily: FONT.display, fontWeight: 800, fontSize: 17, color: C.text, overflowWrap: "anywhere" }}>{company}</h2>
          <Badge label={stage} tone={stage === "LISTING WEEK COMPLETE" ? "neutral" : "info"} />
        </div>
        <div style={{ fontSize: 11, color: C.meta, fontFamily: FONT.mono, marginTop: 4, overflowWrap: "anywhere" }}>
          {[journey?.sym || sym, ISIN_RE.test(resolvedIsin) ? resolvedIsin : null, listingDate ? `listed ${listingDate}` : null]
            .filter(Boolean).join(" · ")}
        </div>
        <Note>Read from the published KV snapshots only — the journey candles and the ipo-details listing-outcome record. Nothing here is computed live.</Note>
      </Card>

      {/* 1 — LISTING-DAY OUTCOME (ipo-details-v1 .listing_outcome, state-driven) */}
      <Card>
        <SectionHeader>Listing-day outcome</SectionHeader>
        {details ? (
          <>
            <FieldRow label="Issue price" k="issue.issue_price" lc={lc} field={issueField} format={(n) => `₹${n}`} />
            {rows.map((row) => (
              <StateRow key={row.key} label={row.label} state={row.display.state} hasValue={row.display.hasValue}
                node={row.node} reason={row.display.reason} source={row.display.source} asOf={row.display.as_of}
                caption={row.caption} producer={row.display.hasValue ? null : row.display.source} />
            ))}
            {showDerivedGap ? (
              <div className="lrow">
                <span className="llabel">Gap (derived)</span>
                <div className="lval">{gap.available ? <b>{gap.text}</b> : <span style={{ color: C.dim }}>not available — {gap.reason}</span>}</div>
                <Badge label={gap.available ? "DERIVED" : "MISSING"} tone={gap.available ? "info" : "neutral"} />
                <small className="lmeta">{gap.formula} — computed here only because the producer&apos;s own gap_pct is not available</small>
              </div>
            ) : null}
            <FieldRow label="Outcome computed at" field={outcome?.computed_at} />
          </>
        ) : (
          <div style={{ fontSize: 12, color: C.dim }}>{detailsNote ?? "Listing-outcome record unavailable."}</div>
        )}
      </Card>

      {/* 2 — FIRST-FIVE-SESSION TAPE (daily bars; honest about what KV carries) */}
      {/* minWidth:0 — a grid item defaults to min-content width, which would let
          the 640px-min table widen the page instead of scrolling inside its wrap. */}
      <Card style={{ minWidth: 0 }}>
        <SectionHeader>First {FIRST_SESSIONS} sessions</SectionHeader>
        {tape.kind === "rows" ? (
          <>
            <div className="aac-table-wrap">
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, fontFamily: FONT.mono }}>
                <caption style={{ captionSide: "top", textAlign: "left", fontSize: 10.5, color: C.meta, padding: "0 0 6px" }}>
                  Daily price tape, sessions D0–D{tape.rows.length - 1}
                </caption>
                <thead>
                  <tr>{["Session", "Date", "High", "Low", "Close", "vs issue", "vs prev close"].map((h) => (
                    <th key={h} scope="col" style={{ textAlign: "right", padding: "4px 8px", color: C.meta, fontSize: 9.5, textTransform: "uppercase", borderBottom: `1px solid ${C.line}` }}>{h}</th>
                  ))}</tr>
                </thead>
                <tbody>
                  {tape.rows.map((row) => (
                    <tr key={row.session} style={{ borderTop: `1px solid ${C.line}` }}>
                      <th scope="row" style={{ textAlign: "right", padding: "4px 8px", color: C.meta, fontWeight: 600 }}>{row.session}</th>
                      <td style={{ textAlign: "right", padding: "4px 8px", color: C.sub }}>{row.date}</td>
                      <td style={{ textAlign: "right", padding: "4px 8px", color: C.text }}>{row.high}</td>
                      <td style={{ textAlign: "right", padding: "4px 8px", color: C.text }}>{row.low}</td>
                      <td style={{ textAlign: "right", padding: "4px 8px", color: C.text }}>{row.close}</td>
                      <td style={{ textAlign: "right", padding: "4px 8px", color: TREND_COLOR[row.vsIssueTrend] }}>{row.vsIssue}</td>
                      <td style={{ textAlign: "right", padding: "4px 8px", color: TREND_COLOR[row.vsPrevTrend] }}>{row.vsPrev}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Note>{tape.note}</Note>
            {issuePrice == null ? <Note>No issue price is available for this IPO, so the vs-issue column stays blank rather than assuming one.</Note> : null}
            {tape.sessionsCaptured > tape.rows.length
              ? <Note>{tape.sessionsCaptured} sessions are captured in the snapshot; this review shows the first {tape.rows.length}.</Note>
              : null}
          </>
        ) : (
          <>
            <div style={{ fontSize: 12, color: C.dim }}>{tape.message}</div>
            {tape.detail ? <Note>{tape.detail}</Note> : null}
          </>
        )}
      </Card>

      {/* 3 — TOP-STRUCTURE OBSERVATIONS, labeled exactly as the detector labels them */}
      <Card>
        <SectionHeader>Top observations</SectionHeader>
        {discovery.kind === "present" ? (
          <>
            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              {discovery.producerLabel ? <Badge label={discovery.producerLabel} tone="info" /> : null}
              <Badge label={discovery.state} tone={discovery.alert ? "watch" : "neutral"} />
              {NON_ASSERTING_STATES.includes(discovery.state)
                ? <Badge label="NOT EVALUATED" tone="neutral" /> : null}
              <span style={{ fontSize: 12.5, fontWeight: 700, color: C.text, overflowWrap: "anywhere" }}>{discovery.headline}</span>
            </div>
            {discovery.producerLabel ? null : <Note>{DISCOVERY_LABEL_FALLBACK}</Note>}
            <ObservationRows rows={discovery.rows} />
            {discovery.triggerRows.length ? (
              <>
                <div style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: ".5px", textTransform: "uppercase", color: C.meta, margin: "10px 0 2px" }}>Trigger detail</div>
                <ObservationRows rows={discovery.triggerRows} />
              </>
            ) : null}
            <Note>{DISCOVERY_CAVEAT}</Note>
            <Note>{DISCOVERY_SCOPE_NOTE}</Note>
            {discovery.detectorVersion || discovery.evaluatedThrough ? (
              <Note>
                {discovery.detectorVersion ? `detector ${discovery.detectorVersion}` : ""}
                {discovery.detectorVersion && discovery.evaluatedThrough ? " · " : ""}
                {discovery.evaluatedThrough ? `evaluated through ${discovery.evaluatedThrough}` : ""}
              </Note>
            ) : null}
          </>
        ) : (
          <>
            <div style={{ fontSize: 12, color: C.dim }}>{discovery.message}</div>
            <Note>{DISCOVERY_SCOPE_NOTE}</Note>
          </>
        )}
      </Card>

      {/* 4 — Deterministic listing-day read, from the day-0 facts that KV carries */}
      {reads.length ? (
        <Card>
          <SectionHeader>Listing-day read</SectionHeader>
          {reads.map((o, i) => (
            <div key={i} style={{ padding: "8px 0", borderTop: i ? `1px solid ${C.line}` : undefined }}>
              <div style={{ display: "flex", gap: 6, alignItems: "baseline", flexWrap: "wrap" }}>
                <Badge label={o.certainty} tone={o.certainty === "Confirmed" ? "good" : "watch"} />
                <span style={{ fontSize: 12.5, fontWeight: 700, color: C.text, overflowWrap: "anywhere" }}>{o.observation}</span>
              </div>
              <div style={{ fontSize: 11, color: C.sub, fontFamily: FONT.mono, marginTop: 3, overflowWrap: "anywhere" }}>{o.facts.join(" · ")}</div>
              {o.counter.length ? <div style={{ fontSize: 11, color: C.dim, marginTop: 2 }}>Counter-evidence: {o.counter.join(" ")}</div> : null}
            </div>
          ))}
          <Note>Derived from the listing-day open, high, low and close only. No delivery, grey-market or fair-value input is carried by these snapshots.</Note>
        </Card>
      ) : null}

      <style jsx>{`
        .lrow { display: grid; grid-template-columns: minmax(130px,.8fr) minmax(0,1.4fr) auto; gap: 8px; padding: 8px 0; border-top: 1px solid ${C.line}; align-items: start; overflow-wrap: anywhere; }
        .lrow:first-child { border-top: none; }
        .llabel { color: ${C.meta}; font-size: 12px; }
        .lval { min-width: 0; font-size: 13px; color: ${C.text}; }
        .lmeta { grid-column: 2 / 4; color: ${C.meta}; font-size: 10.5px; }
        @media (max-width: 600px) {
          .lrow { grid-template-columns: 1fr auto; }
          .lval, .lmeta { grid-column: 1 / 3; }
        }
      `}</style>
    </div>
  );
}
