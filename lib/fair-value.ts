// lib/fair-value.ts — THE fair-value implementation. One source.
// History: /api/ipo-command computed FV inline while /api/ipo/live-preopen
// first SELECTed a phantom column (#159 outage) then hardcoded null — the
// same screen showed ₹368 (card) and ₹419 (live anchor) on 2026-07-16.
// Both routes now import THIS. Chain per Rakesh: modeled formula → callers
// fall back to GMP-implied / issue-price floor when this returns null.
// Changing the formula = locked-number-class change: sanity-check vs known
// listings before merging.

export function fairValue(c: Record<string, unknown>) {
      const price = Number(c.issue_price) || 0;
      // Prefer post-issue EPS; fall back to deriving it from ipo_pe (eps = price / P/E)
      // so fair value lights up on the ~392 IPOs that have ipo_pe even when eps_post is null.
      let eps = Number(c.eps_post) || 0;
      let epsSource = "post-issue EPS";
      if (eps <= 0) {
        const ipoPe = Number(c.ipo_pe) || 0;
        if (ipoPe > 0 && price > 0) {
          eps = price / ipoPe;
          epsSource = "EPS derived from issue P/E";
        }
      }
      const peerPE = Number(c.peer_median_pe) || 0;
      if (eps <= 0 || peerPE <= 0 || price <= 0) {
        const missing: string[] = [];
        if (eps <= 0) missing.push("EPS (no eps_post or issue P/E)");
        if (peerPE <= 0) missing.push("peer P/E");
        if (price <= 0) missing.push("issue price");
        return { fair_value: null, fair_mos: null, fair_verdict: null, fair_note: `needs ${missing.join(" + ")}` };
      }
      // Step 1: base
      const base = eps * peerPE;
      // Step 2: quality factor ±15% (ROE, revenue CAGR, low debt)
      const roe = Number(c.roe) || 0;
      const revCagr = Number(c.revenue_cagr_3y) || 0;
      const de = Number(c.debt_equity);
      let q = 1.0;
      if (roe >= 18) q += 0.06; else if (roe > 0 && roe < 10) q -= 0.06;
      if (revCagr >= 20) q += 0.05; else if (revCagr > 0 && revCagr < 8) q -= 0.05;
      if (!isNaN(de) && de <= 0.3) q += 0.04; else if (!isNaN(de) && de > 1.5) q -= 0.04;
      q = Math.max(0.85, Math.min(1.15, q));
      // Step 3: structure factor ±10% (fresh vs OFS)
      const ofsPct = Number(c.ofs_pct);
      let sfac = 1.0;
      if (!isNaN(ofsPct)) {
        if (ofsPct < 20) sfac += 0.06;        // mostly fresh — capex/expansion, good
        else if (ofsPct > 60) sfac -= 0.08;   // OFS-heavy — backtested statistical drag (NOT a motive claim; Phase-7)
      }
      sfac = Math.max(0.90, Math.min(1.10, sfac));
      const fv = base * q * sfac;
      const mos = ((fv / price) - 1) * 100;   // margin of safety vs issue price
      // ── SANITY LEASH (2026-07-16, after LASER modeled ₹786 on a ₹214 issue) ──
      // A single-witness modeled FV beyond ±150% of issue price is almost always
      // a bad peer median or a distorted derived EPS, not a real 2.5x mispricing.
      // Refusing to quote it protects the user; callers fall to GMP/floor anchors.
      if (Math.abs(mos) > 150) {
        return { fair_value: null, fair_mos: null, fair_verdict: null,
          fair_note: `modeled FV ₹${Math.round(fv)} is ${mos > 0 ? "+" : ""}${Math.round(mos)}% vs issue — outside the ±150% sanity band (suspect peer P/E ${peerPE.toFixed(0)}${epsSource.includes("derived") ? " or derived EPS" : ""}); not quoted` };
      }
      const verdict = mos >= 10 ? "undervalued" : mos <= -10 ? "rich" : "fair";
      return {
        fair_value: Math.round(fv),
        fair_mos: Math.round(mos * 10) / 10,
        fair_verdict: verdict,
        fair_note: `EPS ₹${eps.toFixed(1)}${epsSource.includes("derived") ? "*" : ""} × peer P/E ${peerPE.toFixed(0)} × quality ${q.toFixed(2)} × structure ${sfac.toFixed(2)}${epsSource.includes("derived") ? " · *EPS est. from issue P/E" : ""}`,
      };
    }

export default fairValue;
