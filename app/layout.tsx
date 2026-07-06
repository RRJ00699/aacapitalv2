import type { Metadata, Viewport } from "next"
import "./globals.css"

export const metadata: Metadata = {
  title: "AACapital — Institutional Research Platform",
  description: "NSE/BSE/NASDAQ/NYSE — Tier 1A Research, Screener, IPO Analysis",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    title: "AACapital",
    statusBarStyle: "default",
  },
  icons: {
    icon: "/icon.png",
    apple: "/icon.png",
  },
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#FAFAF8",
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
