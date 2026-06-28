import React from "react"
import { Twitter, Instagram, Facebook } from "lucide-react"

const C = {
  bg: "#FAFAF8",
  border: "#ECE8E1",
  ink: "#0F1B2D",
  sub: "#475569",
  meta: "#94a3b8",
  gold: "#B8860B",
  blue: "#2563EB",
}

const link: React.CSSProperties = {
  display: "block", color: C.sub, textDecoration: "none",
  fontSize: 14, marginBottom: 9, cursor: "pointer",
}
const head: React.CSSProperties = {
  fontSize: 12, letterSpacing: 1, color: C.ink, margin: "0 0 12px",
  textTransform: "uppercase", fontWeight: 800,
}
const mono = "'IBM Plex Mono', monospace"

function Social({ href, label, children }: { href: string; label: string; children: React.ReactNode }) {
  return (
    <a href={href} title={label} aria-label={label} target="_blank" rel="noreferrer"
      style={{ width: 38, height: 38, border: `1px solid #e6e3de`, borderRadius: 10,
        display: "flex", alignItems: "center", justifyContent: "center", color: C.ink }}>
      {children}
    </a>
  )
}

export default function Footer({
  logoSrc = "/aa-logo-full.png",
  twitter = "#",
  instagram = "#",
  facebook = "#",
}: {
  logoSrc?: string
  twitter?: string
  instagram?: string
  facebook?: string
}) {
  return (
    <footer style={{ background: C.bg, borderTop: `1px solid ${C.border}`, padding: "32px 24px 18px" }}>
      <div style={{ maxWidth: 920, margin: "0 auto", display: "flex", flexWrap: "wrap",
        gap: 28, justifyContent: "space-between", alignItems: "flex-start" }}>

        {/* brand + address */}
        <div>
          <img src={logoSrc} alt="AA Capital — Where Markets Make Sense"
            style={{ height: 132, width: "auto", objectFit: "contain", display: "block" }} />
          <div style={{ fontFamily: mono, fontSize: 12, color: C.sub, lineHeight: 1.7, marginTop: 6 }}>
            <span style={{ color: C.gold, letterSpacing: 1, fontSize: 10, display: "block", marginBottom: 3 }}>OFFICE</span>
            2761 Ironwood Drive<br />Sun Prairie, WI 53590
          </div>
        </div>

        {/* company links */}
        <div>
          <h4 style={head}>Company</h4>
          <a style={link} href="#">About</a>
          <a style={link} href="#">Contact</a>
          <a style={link} href="#">Disclosures</a>
        </div>

        {/* social */}
        <div>
          <h4 style={head}>Follow us</h4>
          <div style={{ display: "flex", gap: 12 }}>
            <Social href={twitter} label="Twitter / X"><Twitter size={16} /></Social>
            <Social href={instagram} label="Instagram"><Instagram size={16} /></Social>
            <Social href={facebook} label="Facebook"><Facebook size={16} /></Social>
          </div>
        </div>
      </div>

      {/* bottom bar */}
      <div style={{ maxWidth: 920, margin: "22px auto 0", paddingTop: 16,
        borderTop: `1px solid ${C.border}`, display: "flex", flexWrap: "wrap", gap: 8,
        justifyContent: "space-between", fontFamily: mono, fontSize: 11, color: C.meta }}>
        <div>© {new Date().getFullYear()} AA Capital. All rights reserved.</div>
        <div>Research signal, not a buy call.</div>
      </div>
    </footer>
  )
}
