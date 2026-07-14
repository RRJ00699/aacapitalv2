import { defineCloudflareConfig } from "@opennextjs/cloudflare";

// Minimal config to start. Caching/R2 can be added later once the base
// deploy is proven. For now, default in-memory cache is fine for a 1-user app.
export default defineCloudflareConfig({});
