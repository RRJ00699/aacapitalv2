import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // GUARDRAIL B (build stamp): a bugfix is only "done" when this hash on the
  // live footer >= the fix commit. Set at build time by CI/Workers Builds.
  env: {
    NEXT_PUBLIC_BUILD_ID: process.env.CF_PAGES_COMMIT_SHA
      || process.env.GITHUB_SHA || process.env.WORKERS_CI_COMMIT_SHA || "dev",
    NEXT_PUBLIC_BUILD_TIME: new Date().toISOString(),
  },
};

export default nextConfig;

// OpenNext Cloudflare: enables `next dev` to use CF bindings locally.
// Safe on Vercel too — this block only runs in local dev.
import { initOpenNextCloudflareForDev } from "@opennextjs/cloudflare";
initOpenNextCloudflareForDev();
