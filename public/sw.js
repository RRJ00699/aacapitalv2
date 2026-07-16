// AACapital PWA service worker — network-first for freshness, cache fallback offline.
const CACHE = "aac-v2"; // bump on shell-affecting deploys — v1 pinned users to a stale app (2026-07-16)
const SHELL = ["/dashboard/ipo2", "/manifest.json", "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  // Never cache API calls — IPO data must be live.
  if (req.url.includes("/api/")) return;
  // Network-first: try fresh, fall back to cache if offline.
  // Documents/navigations: NEVER runtime-cached — a cached shell references
  // old hashed chunks and pins users to a stale deploy. Offline fallback uses
  // only the install-time shell.
  if (req.mode === "navigate" || req.destination === "document") {
    e.respondWith(fetch(req).catch(() => caches.match("/dashboard/ipo2")));
    return;
  }
  e.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(req))
  );
});
