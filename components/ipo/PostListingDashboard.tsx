"use client";
import { useEffect, useState } from "react";

// ── Discipline Dashboard ──────────────────────────────────────────────
// One listed IPO. One job: hold-or-exit, and stop the sell-early / hold-loser bias.
// The verdict is the hero; the 4 signals are its evidence.

type Sig = {
  vwap: { value: number | null; daily: number | null; price: number; above: boolean; gapPct: number | null };
  volumeProfile: { nodes: { price: number; vol: number; pct: number }[]; poc: number | null; lo: number; hi: number; abovePOC: boolean };
  floatAbsorption: { cumVol: number; sharesIssued: number | null; turnover: number | null };
  anchorLockin: { lock30: number | null; lock90: number | null; nextUnlockDays: number | null };
  volumeFade: { fading: boolean; recentUpVol: number | null; earlyUpVol: number | null };
  peakDrawdown: { peak: number | null; offPeakPct: number | null; lowerHighs: boolean };
  delivery: { available: boolean; note: string };
  relativeStrength: { available: boolean; note: string };
};
type Data = {
  ok: boolean; symbol: string; hasData: boolean; note?: string;
  company?: string; price?: number; sessions?: number; lastDate?: string;
  verdict?: "accumulation" | "base" | "distribution"; instruction?: string;
  signals?: Sig;
};

const V = {
  accumulation: { label: "ACCUMULATION", dot: "🟢", ink: "#0F6E56", bg: "#EAF6F1", bd: "#BCE3D5", tag: "HOLD" },
  base:         { label: "BASE BUILDING", dot: "🟡", ink: "#8A6410", bg: "#FBF4E4", bd: "#EBD9A8", tag: "WAIT" },
  distribution: { label: "DISTRIBUTION",  dot: "🔴", ink: "#B23A2E", bg: "#FBECEA", bd: "#E8C6C0", tag: "EXIT" },
} as const;

const fmt = (n: number | null | undefined, d = 1) =>
  n == null || isNaN(n) ? "—" : n.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtInt = (n: number | null | undefined) =>
  n == null || isNaN(n) ? "—" : Math.round(n).toLocaleString("en-IN");

function Card({ title, hint, children, tone }: { title: string; hint?: string; children: React.ReactNode; tone?: "good" | "bad" | "warn" | null }) {
  const edge = tone === "good" ? "#BCE3D5" : tone === "bad" ? "#E8C6C0" : tone === "warn" ? "#EBD9A8" : "#E6E9EE";
  return (
    <div style={{ background: "#fff", border: `1px solid ${edge}`, borderRadius: 14, padding: "14px 16px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.4, textTransform: "uppercase", color: "#5B6472" }}>{title}</span>
        {hint && <span style={{ fontSize: 10, color: "#98A1AE" }}>{hint}</span>}
      </div>
      <div style={{ marginTop: 8 }}>{children}</div>
    </div>
  );
}

export default function PostListingDashboard({ symbol }: { symbol: string }) {
  const [data, setData] = useState<Data | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let live = true;
    setLoading(true);
    fetch(`/api/post-listing?symbol=${encodeURIComponent(symbol)}`)
      .then(r => r.json()).then(d => { if (live) { setData(d); setLoading(false); } })
      .catch(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [symbol]);

  if (loading) return <div style={{ padding: 24, textAlign: "center", color: "#98A1AE", fontSize: 13 }}>Reading the tape…</div>;
  if (!data?.ok) return <div style={{ padding: 24, textAlign: "center", color: "#B23A2E", fontSize: 13 }}>Couldn’t load post-listing signals.</div>;
  if (!data.hasData) return (
    <div style={{ padding: 24, textAlign: "center", color: "#5B6472", fontSize: 13 }}>
      {data.note || "No trading data yet — signals appear once it lists and trades."}
    </div>
  );

  const s = data.signals!;
  const v = V[data.verdict || "base"];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, fontFamily: "'Inter',system-ui,sans-serif" }}>
      {/* ── VERDICT HERO — the signature ── */}
      <div style={{ background: v.bg, border: `1.5px solid ${v.bd}`, borderRadius: 18, padding: "18px 20px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 22 }}>{v.dot}</span>
          <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: 1, color: v.ink }}>{v.label}</span>
          <span style={{ marginLeft: "auto", fontSize: 12, fontWeight: 900, letterSpacing: 1.5, padding: "3px 12px",
            borderRadius: 999, background: v.ink, color: "#fff" }}>{v.tag}</span>
        </div>
        <p style={{ margin: "12px 0 0", fontSize: 15, lineHeight: 1.5, fontWeight: 600, color: "#20262F" }}>
          {data.instruction}
        </p>
        <div style={{ marginTop: 12, display: "flex", gap: 16, flexWrap: "wrap", fontSize: 12, color: "#5B6472" }}>
          <span><b style={{ color: "#20262F" }}>₹{fmt(data.price, 1)}</b> last</span>
          <span>{data.sessions} sessions</span>
          <span>as of {String(data.lastDate).slice(0, 10)}</span>
        </div>
      </div>

      {/* ── EVIDENCE GRID — 2-col desktop, 1-col mobile ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12 }}>
        {/* VWAP */}
        <Card title="VWAP — institutional cost" hint="since listing" tone={s.vwap.above ? "good" : "bad"}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span style={{ fontSize: 22, fontWeight: 800, color: s.vwap.above ? "#0F6E56" : "#B23A2E", fontVariantNumeric: "tabular-nums" }}>
              {s.vwap.above ? "ABOVE" : "BELOW"}
            </span>
            <span style={{ fontSize: 13, color: "#5B6472", fontVariantNumeric: "tabular-nums" }}>
              {s.vwap.gapPct != null ? `${s.vwap.gapPct > 0 ? "+" : ""}${fmt(s.vwap.gapPct, 1)}%` : ""}
            </span>
          </div>
          <p style={{ margin: "6px 0 0", fontSize: 12, color: "#5B6472" }}>
            VWAP ₹{fmt(s.vwap.value, 1)} · price ₹{fmt(s.vwap.price, 1)}. {s.vwap.above ? "Buyers in control." : "Sellers in control."}
          </p>
        </Card>

        {/* Volume Profile */}
        <Card title="Volume profile — where it traded" hint="20 sessions" tone={s.volumeProfile.abovePOC ? "good" : "warn"}>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {s.volumeProfile.nodes.slice().reverse().map((n, i) => {
              const isPoc = s.volumeProfile.poc != null && Math.abs(n.price - s.volumeProfile.poc) < 1e-6;
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 9, color: "#98A1AE", width: 46, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>₹{fmtInt(n.price)}</span>
                  <div style={{ flex: 1, height: 8, background: "#F0F2F5", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ width: `${Math.max(3, n.pct * 100)}%`, height: "100%",
                      background: isPoc ? "#0F6E56" : "#B9C2CE", borderRadius: 3 }} />
                  </div>
                </div>
              );
            })}
          </div>
          <p style={{ margin: "8px 0 0", fontSize: 12, color: "#5B6472" }}>
            Heaviest at ₹{fmtInt(s.volumeProfile.poc)}. Price {s.volumeProfile.abovePOC ? "above the wall — support below." : "below the wall — resistance above."}
          </p>
        </Card>

        {/* Float Absorption */}
        <Card title="Free-float absorption" hint="cumulative">
          <div style={{ fontSize: 22, fontWeight: 800, color: "#20262F", fontVariantNumeric: "tabular-nums" }}>
            {s.floatAbsorption.turnover != null ? `${fmt(s.floatAbsorption.turnover, 1)}×` : "—"}
          </div>
          <p style={{ margin: "6px 0 0", fontSize: 12, color: "#5B6472" }}>
            {s.floatAbsorption.turnover != null
              ? `The whole issue has changed hands ~${fmt(s.floatAbsorption.turnover, 1)}× since listing. ${s.floatAbsorption.turnover >= 1 ? "Weak hands have likely rotated out." : "Still churning — early holders haven’t fully exited."}`
              : "Need issue size + price to estimate."}
          </p>
        </Card>

        {/* Anchor Lock-in */}
        <Card title="Anchor lock-in" hint="supply events"
          tone={s.anchorLockin.nextUnlockDays != null && s.anchorLockin.nextUnlockDays < 14 ? "bad" : null}>
          {s.anchorLockin.nextUnlockDays != null ? (
            <>
              <div style={{ fontSize: 22, fontWeight: 800, color: s.anchorLockin.nextUnlockDays < 14 ? "#B23A2E" : "#20262F", fontVariantNumeric: "tabular-nums" }}>
                {s.anchorLockin.nextUnlockDays}d
              </div>
              <p style={{ margin: "6px 0 0", fontSize: 12, color: "#5B6472" }}>
                to next anchor unlock. {s.anchorLockin.nextUnlockDays < 14 ? "Fresh supply incoming — expect pressure." : "No imminent supply shock."}
              </p>
            </>
          ) : (
            <p style={{ margin: 0, fontSize: 12, color: "#5B6472" }}>Lock-in dates passed or not set.</p>
          )}
          <div style={{ marginTop: 6, fontSize: 11, color: "#98A1AE" }}>
            30d: {s.anchorLockin.lock30 != null ? `${s.anchorLockin.lock30}d` : "—"} · 90d: {s.anchorLockin.lock90 != null ? `${s.anchorLockin.lock90}d` : "—"}
          </div>
        </Card>

        {/* Volume fade — buyers exhausting */}
        <Card title="Volume fade — up-day demand" hint="distribution tell"
          tone={s.volumeFade.fading ? "bad" : "good"}>
          <div style={{ fontSize: 22, fontWeight: 800, color: s.volumeFade.fading ? "#B23A2E" : "#0F6E56" }}>
            {s.volumeFade.fading ? "FADING" : "HOLDING"}
          </div>
          <div style={{ marginTop: 8, fontSize: 12.5, color: "#5A6472", lineHeight: 1.5 }}>
            {s.volumeFade.fading
              ? "Up-day volume is drying up — buyers are exhausting. Rallies on lighter volume don't hold. A sell tell."
              : "Up-day volume is holding — real buying still supports the moves."}
          </div>
        </Card>

        {/* Peak drawdown — rolling over */}
        <Card title="Off the peak" hint="rolling over?"
          tone={s.peakDrawdown.lowerHighs && (s.peakDrawdown.offPeakPct ?? 0) < -8 ? "bad" : null}>
          <div style={{ fontSize: 22, fontWeight: 800, color: (s.peakDrawdown.offPeakPct ?? 0) < -8 ? "#B23A2E" : "#1A2438" }}>
            {s.peakDrawdown.offPeakPct != null ? `${s.peakDrawdown.offPeakPct > 0 ? "+" : ""}${fmt(s.peakDrawdown.offPeakPct, 1)}%` : "—"}
          </div>
          <div style={{ marginTop: 8, fontSize: 12.5, color: "#5A6472", lineHeight: 1.5 }}>
            {s.peakDrawdown.lowerHighs
              ? `Off the ₹${fmtInt(s.peakDrawdown.peak)} peak, making lower highs — rolling over. When this pairs with fading volume, it's distributing.`
              : `Off the ₹${fmtInt(s.peakDrawdown.peak)} peak. Not yet making lower highs.`}
          </div>
        </Card>
      </div>

      {/* ── FORWARD SLOTS — light up when feeds run ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12 }}>
        {[["Delivery %", s.delivery.note], ["Relative strength vs Nifty", s.relativeStrength.note]].map(([t, note]) => (
          <div key={t} style={{ background: "#F7F8FA", border: "1px dashed #D5DAE1", borderRadius: 14, padding: "14px 16px" }}>
            <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.4, textTransform: "uppercase", color: "#98A1AE" }}>{t}</span>
            <p style={{ margin: "6px 0 0", fontSize: 12, color: "#98A1AE" }}>{note}</p>
          </div>
        ))}
      </div>

      <p style={{ fontSize: 11, color: "#98A1AE", textAlign: "center", margin: "2px 0 0" }}>
        Research signal, not a buy call. Microstructure reads the tape — it doesn’t predict news.
      </p>
    </div>
  );
}
