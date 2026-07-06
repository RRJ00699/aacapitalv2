// app/login/page.tsx
"use client";
import { signIn } from "next-auth/react";
import { useState } from "react";

const C = { bg:"#FAFAF8", surface:"#FFFFFF", border:"#E5E7EB", text:"#111827",
  meta:"#6B7280", dim:"#9CA3AF", gold:"#B8860B", green:"#16A34A" };

export default function Login() {
  const [busy, setBusy] = useState(false);
  const requested = typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).has("requested");
  return (
    <main style={{ minHeight:"100dvh", display:"grid", placeItems:"center",
      background:`radial-gradient(1100px 600px at 50% -10%, #FFF7E6 0%, ${C.bg} 55%)`,
      fontFamily:'-apple-system,"Segoe UI",Inter,Roboto,sans-serif', padding:20 }}>
      <div style={{ width:"100%", maxWidth:400, textAlign:"center" }}>

        {/* brand */}
        <img src="/icon.png" alt="AACapital" width={72} height={72}
          style={{ borderRadius:18, boxShadow:"0 8px 28px rgba(184,134,11,.22)", marginBottom:18 }}/>
        <h1 style={{ margin:0, fontSize:28, fontWeight:800, letterSpacing:-0.5, color:C.text }}>
          AACapital
        </h1>
        <div style={{ marginTop:6, fontSize:11.5, fontWeight:700, letterSpacing:3,
          color:C.gold, textTransform:"uppercase",
          fontFamily:"ui-monospace,SFMono-Regular,Menlo,monospace" }}>
          Where markets make sense
        </div>

        {/* card */}
        <div style={{ marginTop:28, background:C.surface, border:`1px solid ${C.border}`,
          borderRadius:16, padding:"26px 24px", boxShadow:"0 10px 34px rgba(17,24,39,.06)" }}>
          {requested && (
            <div style={{ background:"#F0FDF4", border:"1px solid #BBF7D0", color:C.green,
              borderRadius:10, padding:"10px 12px", fontSize:13, fontWeight:600, marginBottom:16 }}>
              ✓ Access request sent — the owner has been notified. Once approved, just sign in again.
            </div>
          )}
          <div style={{ fontSize:14.5, fontWeight:700, color:C.text }}>Private research platform</div>
          <div style={{ fontSize:12.5, color:C.meta, marginTop:4, marginBottom:20 }}>
            Access is limited to invited accounts.
          </div>

          <button
            onClick={() => { setBusy(true); signIn("google", { callbackUrl: "/" }); }}
            disabled={busy}
            style={{ width:"100%", display:"flex", alignItems:"center", justifyContent:"center",
              gap:10, padding:"12px 16px", borderRadius:10, cursor: busy ? "wait" : "pointer",
              background:C.surface, border:`1px solid ${C.border}`, fontSize:14.5, fontWeight:600,
              color:C.text, boxShadow:"0 1px 2px rgba(17,24,39,.05)", opacity: busy ? .7 : 1 }}>
            <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
              <path fill="#EA4335" d="M24 9.5c3.54 0 6.7 1.22 9.2 3.6l6.85-6.85C35.9 2.4 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.2C12.43 13.72 17.74 9.5 24 9.5z"/>
              <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
              <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.2C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
              <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
            </svg>
            {busy ? "Redirecting to Google…" : "Continue with Google"}
          </button>

          <div style={{ display:"flex", alignItems:"center", gap:8, marginTop:18,
            justifyContent:"center", fontSize:11.5, color:C.dim }}>
            <span style={{ width:6, height:6, borderRadius:"50%", background:C.green,
              display:"inline-block" }}/>
            Research signal, not a buy call
          </div>
        </div>

        <div style={{ marginTop:18, fontSize:11.5, color:C.dim }}>
          © {new Date().getFullYear()} AACapital · Family &amp; invited users only
        </div>
      </div>
    </main>
  );
}
