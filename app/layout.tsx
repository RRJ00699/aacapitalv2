import type { Metadata } from "next"
import "./globals.css"

export const metadata: Metadata = {
  title: "AACapital — Institutional Research Platform",
  description: "NSE/BSE/NASDAQ/NYSE — Tier 1A Research, Screener, IPO Analysis",
  viewport: "width=device-width, initial-scale=1, maximum-scale=1",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, padding: 0 }}>
        {children}
      </body>
    </html>
  )
}
