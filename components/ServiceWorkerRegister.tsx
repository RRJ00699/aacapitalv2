"use client";
import { useEffect } from "react";

// Registers the PWA service worker once, client-side. Silent — no UI.
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;
    const reg = () => navigator.serviceWorker.register("/sw.js").catch(() => {});
    if (document.readyState === "complete") reg();
    else window.addEventListener("load", reg);
    return () => window.removeEventListener("load", reg);
  }, []);
  return null;
}
