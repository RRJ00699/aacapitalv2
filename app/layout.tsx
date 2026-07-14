import type { Metadata, Viewport } from "next"
import "./globals.css"
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister"
import { ThemeProvider } from "@/lib/theme"

export const metadata: Metadata = {
  title: "AACapital — IPO Power House",
  description: "Indian IPO post-listing research — where markets make sense. Research signal, not a buy call.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    title: "AACapital",
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: [
      { url: "/icons/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [
      { url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" },
    ],
  },
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
  themeColor: "#0B1628",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, padding: 0 }}>
        <ServiceWorkerRegister />
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  )
}
