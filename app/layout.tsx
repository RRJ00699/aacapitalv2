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

// Pre-paint theme boot — runs before React hydrates so the correct palette is
// on <html> from the first frame. Prevents the light→dark (or dark→light) flash
// a useEffect-only theme would cause. Kept in sync with lib/theme.ts (mode
// values, storage key, and the LIGHT/DARK background hexes).
const THEME_BOOT = `(function(){try{var k='aac-theme',m=localStorage.getItem(k);if(m==='auto'){m='system';try{localStorage.setItem(k,m)}catch(e){}}var r=document.documentElement;if(m==='light'){r.setAttribute('data-theme','light')}else if(m==='dark'){r.setAttribute('data-theme','dark')}else{r.removeAttribute('data-theme')}var dark=m==='dark'||((m==='system'||!m)&&window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches);r.style.background=dark?'#12202B':'#EDF1F6';r.style.colorScheme=dark?'dark':'light';}catch(e){}})();`

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body style={{ margin: 0, padding: 0 }}>
        <ServiceWorkerRegister />
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  )
}
