import React from "react"

const C = {
  bg: "#FAFAF8",
  border: "#ECE8E1",
  ink: "#0F1B2D",
  sub: "#475569",
  meta: "#94a3b8",
  gold: "#B8860B",
}

const mono = "'IBM Plex Mono', monospace"
const link: React.CSSProperties = { display: "block", color: C.sub, textDecoration: "none", fontSize: 14, marginBottom: 9, cursor: "pointer" }
const head: React.CSSProperties = { fontSize: 12, letterSpacing: 1, color: C.ink, margin: "0 0 12px", textTransform: "uppercase", fontWeight: 800 }

/* inline SVG social glyphs — no icon-library dependency (lucide dropped brand icons) */
const XIcon = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
  </svg>
)
const IgIcon = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
    <rect x="2" y="2" width="20" height="20" rx="5" />
    <circle cx="12" cy="12" r="4" />
    <circle cx="17.5" cy="6.5" r="1.3" fill="currentColor" stroke="none" />
  </svg>
)
const FbIcon = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
    <path d="M22 12a10 10 0 1 0-11.563 9.875v-6.987H7.898V12h2.539V9.797c0-2.506 1.492-3.89 3.777-3.89 1.094 0 2.238.195 2.238.195v2.46h-1.26c-1.243 0-1.63.771-1.63 1.562V12h2.773l-.443 2.888h-2.33v6.987A10.002 10.002 0 0 0 22 12z" />
  </svg>
)

function Social({ href, label, children }: { href: string; label: string; children: React.ReactNode }) {
  return (
    <a href={href} title={label} aria-label={label} target="_blank" rel="noreferrer"
      style={{ width: 38, height: 38, border: "1px solid #e6e3de", borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", color: C.ink }}>
      {children}
    </a>
  )
}

export default function Footer({
  logoSrc = "/aa-logo-full.png",
  twitter = "#",
  instagram = "#",
  facebook = "#",
}: { logoSrc?: string; twitter?: string; instagram?: string; facebook?: string }) {
  return (
    <footer style={{ background: C.bg, borderTop: `1px solid ${C.border}`, padding: "32px 24px 18px" }}>
      <div style={{ maxWidth: 920, margin: "0 auto", display: "flex", flexWrap: "wrap", gap: 28, justifyContent: "space-between", alignItems: "flex-start" }}>

        <div>
          <img src={logoSrc} alt="AA Capital — Where Markets Make Sense" style={{ height: 132, width: "auto", objectFit: "contain", display: "block" }} />
          <div style={{ fontFamily: mono, fontSize: 12, color: C.sub, lineHeight: 1.7, marginTop: 6 }}>
            <span style={{ color: C.gold, letterSpacing: 1, fontSize: 10, display: "block", marginBottom: 3 }}>OFFICE</span>
            2761 Ironwood Drive<br />Sun Prairie, WI 53590
          </div>
        </div>

        <div>
          <h4 style={head}>Company</h4>
          <a style={link} href="#">About</a>
          <a style={link} href="#">Contact</a>
          <a style={link} href="#">Disclosures</a>
        </div>

        <div>
          <h4 style={head}>Follow us</h4>
          <div style={{ display: "flex", gap: 12 }}>
            <Social href={twitter} label="Twitter / X"><XIcon /></Social>
            <Social href={instagram} label="Instagram"><IgIcon /></Social>
            <Social href={facebook} label="Facebook"><FbIcon /></Social>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 920, margin: "22px auto 0", paddingTop: 16, borderTop: `1px solid ${C.border}`, display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "space-between", fontFamily: mono, fontSize: 11, color: C.meta }}>
        <div>© {new Date().getFullYear()} AA Capital. All rights reserved.</div>
        <div>Research signal, not a buy call.</div>
      </div>
    </footer>
  )
}
