"use client";
import { useEffect, useState, useCallback } from "react";

type Entry = { id: number; who: string; severity: string; what: string; created_at: string };

const C = {
  surface: "#FBFCFD", surface2: "#F4F6FA", border: "#DAE0E8", line: "#E7EBF1",
  text: "#1A2438", sub: "#3A4560", meta: "#68738C", dim: "#98A2B6",
  accent: "#1B7A6A", red: "#C43D2F", redBg: "#FBEEEC", redBd: "#EEC9C3",
  amber: "#9A6A12", amberBg: "#FAF2E2", amberBd: "#E8D3A0",
};
const W: Record<string, number> = { low: 1, mid: 2, high: 3 };

export default function TrackerClient() {
  const [rows, setRows] = useState<Entry[]>([]);
  const [who, setWho] = useState("");
  const [sev, setSev] = useState("mid");
  const [what, setWhat] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/tracker");
      const d = await r.json();
      setRows(d.rows || []);
    } catch { /* keep */ }
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  async function add() {
    if (!who.trim() || !what.trim() || saving) return;
    setSaving(true);
    try {
      const r = await fetch("/api/tracker", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ who: who.trim(), severity: sev, what: what.trim() }),
      });
      const d = await r.json();
      if (d.ok && d.entry) { setRows([d.entry, ...rows]); setWho(""); setWhat(""); setSev("mid"); }
    } catch { /* keep */ }
    setSaving(false);
  }

  async function del(id: number) {
    setRows(rows.filter((x) => x.id !== id));
    try { await fetch(`/api/tracker?id=${id}`, { method: "DELETE" }); } catch { /* keep */ }
  }

  const fmt = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })
      + " · " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  };

  // scoreboard
  const tally: Record<string, number> = {};
  rows.forEach((e) => { tally[e.who] = (tally[e.who] || 0) + (W[e.severity] || 1); });
  const board = Object.entries(tally).sort((a, b) => b[1] - a[1]);
  const maxScore = board[0]?.[1] || 1;

  const sevColor = (s: string) => s === "high" ? C.red : s === "low" ? C.accent : C.amber;
  const sevBg = (s: string) => s === "high" ? C.redBg : s === "low" ? "#E8F4F1" : C.amberBg;
  const sevBd = (s: string) => s === "high" ? C.redBd : s === "low" ? "#BEE0D8" : C.amberBd;

  const card: React.CSSProperties = {
    background: `linear-gradient(180deg,${C.surface},${C.surface2})`, border: `1px solid ${C.border}`,
    borderRadius: 16, padding: 16, marginBottom: 16,
    boxShadow: "0 1px 0 rgba(255,255,255,.8) inset, 0 8px 24px -12px rgba(28,36,58,.22)",
  };
  const inp: React.CSSProperties = {
    width: "100%", border: `1px solid ${C.border}`, borderRadius: 9, background: C.surface2,
    fontSize: 14, color: C.text, padding: "9px 11px", outline: "none", fontFamily: "inherit",
  };

  return (
    <div style={{ maxWidth: 680, margin: "auto", padding: "16px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
        <span style={{ fontSize: 22 }}>🦁</span>
        <span style={{ fontSize: 19, fontWeight: 800, letterSpacing: "-.01em", color: C.text }}>Frustration Tracker</span>
        <span style={{ fontSize: 12, color: C.meta, marginLeft: "auto" }}>private · only you</span>
      </div>
      <div style={{ fontSize: 12, color: C.meta, marginBottom: 16, lineHeight: 1.5 }}>
        Who / what pulled me off the goal — saved to the DB with date &amp; time. Keep the score.
      </div>

      {/* composer */}
      <div style={card}>
        <div style={{ display: "flex", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
          <div style={{ flex: "0 0 42%", minWidth: 130, display: "flex", flexDirection: "column", gap: 4 }}>
            <label style={{ fontSize: 10, fontWeight: 800, letterSpacing: ".05em", textTransform: "uppercase", color: C.dim }}>Who / what</label>
            <input style={inp} value={who} onChange={(e) => setWho(e.target.value)} placeholder="Claude, a call, myself…" />
          </div>
          <div style={{ flex: "0 0 30%", minWidth: 110, display: "flex", flexDirection: "column", gap: 4 }}>
            <label style={{ fontSize: 10, fontWeight: 800, letterSpacing: ".05em", textTransform: "uppercase", color: C.dim }}>Severity</label>
            <select style={inp} value={sev} onChange={(e) => setSev(e.target.value)}>
              <option value="low">Low — minor</option>
              <option value="mid">Mid — annoying</option>
              <option value="high">High — cost me time</option>
            </select>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
          <label style={{ fontSize: 10, fontWeight: 800, letterSpacing: ".05em", textTransform: "uppercase", color: C.dim }}>What happened</label>
          <textarea style={{ ...inp, resize: "none", minHeight: 52, lineHeight: 1.45 }} value={what}
            onChange={(e) => setWhat(e.target.value)} placeholder="What pulled you off track…" />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 11, color: C.dim }}>Saves with date &amp; time</span>
          <button onClick={add} disabled={!who.trim() || !what.trim() || saving}
            style={{
              marginLeft: "auto", background: C.red, color: "#fff", border: "none", fontFamily: "inherit",
              fontSize: 13, fontWeight: 700, padding: "9px 20px", borderRadius: 9,
              cursor: (!who.trim() || !what.trim() || saving) ? "default" : "pointer",
              opacity: (!who.trim() || !what.trim() || saving) ? 0.4 : 1,
            }}>{saving ? "Saving…" : "Log it"}</button>
        </div>
      </div>

      {/* scoreboard */}
      {board.length > 0 && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: "12px 14px", marginBottom: 18, boxShadow: "0 4px 16px -10px rgba(28,36,58,.18)" }}>
          <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: ".06em", textTransform: "uppercase", color: C.meta, marginBottom: 9 }}>🏆 Frustration scoreboard</div>
          {board.map(([name, score]) => (
            <div key={name} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0" }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: C.text, minWidth: 90 }}>{name}</span>
              <span style={{ flex: 1, height: 6, background: C.line, borderRadius: 4, overflow: "hidden", margin: "0 4px" }}>
                <span style={{ display: "block", height: "100%", width: `${Math.round(score / maxScore * 100)}%`, background: C.red, borderRadius: 4 }} />
              </span>
              <span style={{ fontSize: 12, fontWeight: 800, color: C.red, minWidth: 22, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{score}</span>
            </div>
          ))}
        </div>
      )}

      {/* log */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "0 2px 10px" }}>
        <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: ".06em", textTransform: "uppercase", color: C.meta }}>Log</span>
        <span style={{ fontSize: 11, color: C.dim, marginLeft: "auto" }}>{rows.length ? `${rows.length} ${rows.length === 1 ? "entry" : "entries"}` : ""}</span>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", color: C.meta, fontSize: 13, padding: 20 }}>Loading…</div>
      ) : rows.length === 0 ? (
        <div style={{ textAlign: "center", color: C.dim, fontSize: 13, padding: "30px 10px", lineHeight: 1.6 }}>No distractions logged.<br />Stay on the goal. 🦁</div>
      ) : (
        rows.map((e) => (
          <div key={e.id} style={{ background: C.surface, border: `1px solid ${C.border}`, borderLeft: `3px solid ${sevColor(e.severity)}`, borderRadius: 14, padding: "12px 15px", marginBottom: 11, boxShadow: "0 4px 16px -10px rgba(28,36,58,.18)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 14, fontWeight: 800, color: C.text }}>{e.who}</span>
              <span style={{ fontSize: 10, fontWeight: 800, textTransform: "uppercase", letterSpacing: ".04em", padding: "2px 8px", borderRadius: 6, background: sevBg(e.severity), color: sevColor(e.severity), border: `1px solid ${sevBd(e.severity)}` }}>{e.severity}</span>
            </div>
            <div style={{ fontSize: 14, lineHeight: 1.5, color: C.sub, whiteSpace: "pre-wrap", wordWrap: "break-word" }}>{e.what}</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 9, paddingTop: 9, borderTop: `1px solid ${C.line}` }}>
              <span style={{ fontSize: 11, color: C.meta, fontVariantNumeric: "tabular-nums" }}>{fmt(e.created_at)}</span>
              <button onClick={() => del(e.id)} style={{ marginLeft: "auto", fontSize: 11, color: C.dim, cursor: "pointer", background: "none", border: "none", fontFamily: "inherit", padding: "2px 6px", borderRadius: 6 }}>delete</button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
