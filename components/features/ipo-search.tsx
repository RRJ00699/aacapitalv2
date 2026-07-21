// components/features/ipo-search.tsx
// Phase 9 — Search as the product's entry hub: Search → Understand → Navigate
// → Decide. Consumes the KV-served /api/ipo-command payload only (zero-idle:
// no new endpoints, no Neon on keystroke). All research statuses come from
// the API's structured `research` block — the UI formats, never infers.
"use client";
import { useState, useEffect, useRef, useMemo } from "react";
import { FILTER_CHIPS, type Chip, type Row, runSearch, stageOf, primaryAction } from "@/lib/search-intent";

import { VARS, TONE, toneFor } from "@/lib/theme";
// Token-converged (feat/ux-premium): same keys, CSS-var values — dark mode
// and palette changes now propagate here automatically.
const C = { surface: VARS.surface, border: VARS.border, text: VARS.text, sub: VARS.sub,
  bg: VARS.surface2, dim: VARS.dim, green: VARS.green, greenBg: VARS.greenBg, red: VARS.red,
  redBg: VARS.redBg, amber: VARS.amber, amberBg: VARS.amberBg, blue: VARS.blue, blueBg: VARS.blueBg };

interface Props { onSelect: (company: string, target?: string) => void; placeholder?: string }

// Stage colors ride the ONE tone system (LISTING = urgent-red is a deliberate
// exception for the decision window; the rest map through toneFor).
const STAGE_STYLE: Record<string, [string, string]> = {
  LISTING: [C.red, C.redBg],
  OPEN: [TONE[toneFor("OPEN")].fg, TONE[toneFor("OPEN")].bg],
  UPCOMING: [TONE[toneFor("UPCOMING")].fg, TONE[toneFor("UPCOMING")].bg],
  LISTED: [TONE.neutral.fg, TONE.neutral.bg], CLOSED: [TONE.watch.fg, TONE.watch.bg] };
const D = (v: unknown) => (v ? String(v).slice(5, 10) : "—");

function Badge({ t, fg, bg }: { t: string; fg: string; bg: string }) {
  return <span style={{ fontSize: 9, fontWeight: 800, letterSpacing: .3, color: fg, background: bg,
    borderRadius: 999, padding: "2px 7px", whiteSpace: "nowrap" }}>{t}</span>;
}

function Skeleton() {
  return <div aria-hidden style={{ padding: "10px 12px", display: "grid", gap: 8 }}>
    {[0, 1, 2].map((i) => <div key={i} className="aac-skeleton" style={{ height: 44 }} />)}
  </div>;
}

export function IpoSearch({ onSelect, placeholder = "Search IPO, symbol, or try: good · listing today · rhp pending" }: Props) {
  const [query, setQuery] = useState("");
  const [deb, setDeb] = useState("");
  const [cards, setCards] = useState<Row[] | null>(null);   // null = loading
  const [post, setPost] = useState<Row[]>([]);
  const [chips, setChips] = useState<Chip[]>([]);
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState(0);
  const [preview, setPreview] = useState<Row | null>(null);
  const [recent, setRecent] = useState<string[]>([]);
  const ref = useRef<HTMLDivElement>(null);
  const fetched = useRef(false);

  // ONE payload fetch, once (duplicate-call guard) — same KV body the page uses.
  useEffect(() => {
    if (fetched.current) return; fetched.current = true;
    let live = true;
    fetch("/api/ipo-command").then((r) => r.json()).then((d) => {
      if (!live) return;
      setCards((d?.cards ?? []) as Row[]);
      setPost((d?.post ?? []) as Row[]);
    }).catch(() => setCards([]));
    return () => { live = false; };
  }, []);

  useEffect(() => { const t = setTimeout(() => setDeb(query), 200); return () => clearTimeout(t); }, [query]);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) { setOpen(false); setPreview(null); } };
    document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h);
  }, []);

  const results = useMemo(
    () => (cards ? runSearch(cards, post, deb, chips) : []),
    [cards, post, deb, chips]);
  // reset selection when the query/filters change — derived during render
  // (not in an effect) so keyboard state can't lag a frame behind results.
  const selKey = `${deb}|${chips.join(",")}`;
  const lastKey = useRef(selKey);
  if (lastKey.current !== selKey) { lastKey.current = selKey; if (sel !== 0) setSel(0); }

  function pick(c: Row) {
    const name = String(c.company_name ?? "");
    setRecent((r) => [name, ...r.filter((x) => x !== name)].slice(0, 5));
    setQuery(""); setOpen(false); setPreview(null);
    onSelect(name, primaryAction(c).target);
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Escape") { setOpen(false); setPreview(null); return; }
    if (!results.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, results.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    if (e.key === "Enter") { e.preventDefault(); pick(results[sel]); }
  }

  const rsh = (c: Row) => (c.research ?? {}) as Record<string, Record<string, unknown> & string | undefined> & Record<string, unknown>;

  return (
    <div ref={ref} style={{ position: "relative", width: "100%", maxWidth: 460 }}>
      <input role="combobox" aria-expanded={open} aria-controls="aac-search-listbox" aria-label="Search IPOs by name, symbol or status"
        value={query} placeholder={placeholder}
        onFocus={() => setOpen(true)} onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onKeyDown={onKey}
        style={{ width: "100%", padding: "9px 13px", borderRadius: 10, border: `1.5px solid ${C.border}`,
          fontSize: 13, color: C.text, background: C.surface }} />
      {open && (
        <div id="aac-search-listbox" role="listbox" aria-label="IPO search results"
          style={{ position: "absolute", top: "110%", left: 0, right: 0, zIndex: 60, background: C.surface,
            border: `1px solid ${C.border}`, borderRadius: 12, boxShadow: "0 12px 34px rgba(20,30,60,.14)",
            maxHeight: 480, overflowY: "auto" }}>
          {/* filter chips — combine with text */}
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap", padding: "9px 10px 4px" }}>
            {FILTER_CHIPS.map((ch) => {
              const on = chips.includes(ch);
              return <button key={ch} onClick={() => setChips((cs) => on ? cs.filter((x) => x !== ch) : [...cs, ch])}
                aria-pressed={on}
                style={{ fontSize: 9.5, fontWeight: 700, padding: "3px 8px", borderRadius: 999, cursor: "pointer",
                  border: `1px solid ${on ? C.blue : C.border}`, color: on ? "#fff" : C.sub,
                  background: on ? C.blue : C.surface }}>{ch}</button>;
            })}
          </div>
          {cards === null && <Skeleton />}
          {cards !== null && !deb && !chips.length && (
            <div style={{ padding: "8px 12px", fontSize: 11, color: C.dim }}>
              {recent.length ? <>Recent: {recent.map((r, i) =>
                <button key={i} onClick={() => setQuery(r)} style={{ margin: "0 5px 0 0", fontSize: 11, color: C.blue,
                  background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>{r}</button>)}</>
                : "Type a name/symbol, or a status: good · junk · listing today · rhp pending · high qib"}
            </div>
          )}
          {cards !== null && (deb || chips.length > 0) && results.length === 0 && (
            <div style={{ padding: "14px 14px 16px", fontSize: 12, color: C.sub }}>
              No IPO matched your search.
              <div style={{ marginTop: 7, display: "flex", gap: 6, flexWrap: "wrap" }}>
                {(["Upcoming", "Listing Today", "Recently Listed", "GOOD"] as Chip[]).map((ch) =>
                  <button key={ch} onClick={() => { setQuery(""); setChips([ch]); }}
                    style={{ fontSize: 10, fontWeight: 700, padding: "3px 9px", borderRadius: 999,
                      border: `1px solid ${C.border}`, background: C.bg, color: C.sub, cursor: "pointer" }}>{ch}</button>)}
              </div>
            </div>
          )}
          {results.map((c, i) => {
            const stage = stageOf(c); const [fg, bg] = STAGE_STYLE[stage] ?? [C.sub, C.bg];
            const r = rsh(c);
            const cq = (r.company_quality ?? {}) as { status?: string; verdict?: string };
            const comp = (r.research_completeness ?? {}) as { label?: string };
            const ps = (r.prelisting_score ?? {}) as { score?: number | null; band?: string | null };
            const act = primaryAction(c);
            const active = i === sel;
            return (
              <div key={i} role="option" aria-selected={active}
                onMouseEnter={() => setSel(i)}
                onClick={() => pick(c)}
                style={{ padding: "9px 12px", borderTop: `1px solid ${C.border}`, cursor: "pointer",
                  background: active ? C.bg : C.surface }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 12.5, fontWeight: 700, color: C.text }}>{String(c.company_name ?? "")}</span>
                  {c.sym ? <span style={{ fontSize: 10, color: C.dim, fontFamily: "monospace" }}>{String(c.sym)}</span> : null}
                  <Badge t={stage === "LISTING" ? "LISTING TODAY" : stage} fg={fg} bg={bg} />
                  <span style={{ marginLeft: "auto" }} />
                  <button onClick={(e) => { e.stopPropagation(); window.location.href = `/dashboard/ipo2?view=details&ipo=${encodeURIComponent(String(c.sym ?? ""))}`; }}
                    style={{ fontSize: 11, color: C.text, background: C.surface, border: `1px solid ${C.border}`,
                      borderRadius: 8, padding: "4px 9px", cursor: "pointer" }}>Complete Details</button>
                  <button onClick={(e) => { e.stopPropagation(); setPreview(preview === c ? null : c); }}
                    aria-expanded={preview === c} aria-label="Toggle quick preview"
                    style={{ fontSize: 10, fontWeight: 800, color: C.sub, background: C.bg,
                      border: `1px solid ${C.border}`, borderRadius: 8, padding: "4px 8px", cursor: "pointer" }}>
                    {preview === c ? "hide" : "info"}</button>
                  <button onClick={(e) => { e.stopPropagation(); pick(c); }}
                    aria-label={`${act.label} for ${String(c.company_name ?? "")}`}
                    style={{ fontSize: 10, fontWeight: 800, color: "#fff", background: C.blue, border: "none",
                      borderRadius: 8, padding: "4px 9px", cursor: "pointer" }}>{act.label}</button>
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 5, alignItems: "center" }}>
                  <span style={{ fontSize: 9.5, color: C.dim }}>open {D(c.open_date)} · close {D(c.close_date)} · list {D(c.listing_date)}</span>
                  {comp.label ? <Badge t={String(comp.label)} fg={comp.label === "Research Complete" ? C.green : C.amber}
                    bg={comp.label === "Research Complete" ? C.greenBg : C.amberBg} /> : null}
                  {cq.status === "CONFIRMED" && cq.verdict
                    ? <Badge t={String(cq.verdict)} fg={cq.verdict === "GOOD" ? C.green : cq.verdict === "JUNK" ? C.red : C.amber}
                        bg={cq.verdict === "GOOD" ? C.greenBg : cq.verdict === "JUNK" ? C.redBg : C.amberBg} />
                    : <Badge t="QUALITY: INCOMPLETE" fg={C.sub} bg={C.bg} />}
                  {r.rhp_status ? <Badge t={`RHP ${String(r.rhp_status)}`} fg={r.rhp_status === "CONFIRMED" ? C.green : C.sub} bg={C.bg} /> : null}
                  {r.sbi_status ? <Badge t={`SBI ${String(r.sbi_status)}`} fg={r.sbi_status === "CONFIRMED" ? C.green : C.sub} bg={C.bg} /> : null}
                  {ps.band ? <Badge t={`${ps.score ?? "—"} · ${String(ps.band)}`} fg={C.blue} bg={C.blueBg} /> : null}
                  {r.fair_value_status === "UNAVAILABLE" ? <Badge t="FV UNAVAILABLE" fg={C.amber} bg={C.amberBg} /> : null}
                </div>
                {preview === c && (
                  <div aria-label="IPO quick preview" style={{ marginTop: 8, padding: "9px 11px", background: C.bg,
                    borderRadius: 9, fontSize: 11, color: C.sub, lineHeight: 1.6 }}>
                    <div><b>Pipeline:</b> {String(r.pipeline_status ?? "—")} · <b>Research:</b> {String(comp.label ?? "—")}</div>
                    <div><b>Fair value:</b> {String(r.fair_value_status ?? "—")} · <b>MoS:</b> {String(r.margin_of_safety_status ?? "—")}
                      {r.fair_value_note ? ` — ${String(r.fair_value_note)}` : ""}</div>
                    {Array.isArray(r.evidence) && (r.evidence as Array<Record<string, unknown>>).length ? <div style={{ marginTop: 3 }}>
                      {(r.evidence as Array<Record<string, unknown>>).slice(0, 3).map((ev, j) =>
                        <div key={j}><span style={{ color: ev.direction === "negative" ? C.red : ev.direction === "positive" ? C.green : C.dim, fontWeight: 800 }}>
                          {ev.direction === "negative" ? "−" : ev.direction === "positive" ? "+" : "·"}</span> {String(ev.statement ?? "")}</div>)}
                    </div> : <div style={{ color: C.dim }}>No evidence rows yet — reasons appear once RHP analysis lands.</div>}
                    <button onClick={(e) => { e.stopPropagation(); pick(c); }}
                      style={{ marginTop: 6, fontSize: 10.5, fontWeight: 800, color: "#fff", background: C.blue,
                        border: "none", borderRadius: 8, padding: "5px 11px", cursor: "pointer" }}>{act.label} →</button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
