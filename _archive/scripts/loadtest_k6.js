// k6 load script — RUN FROM YOUR PC ONLY, AND ONLY IF YOU ACCEPT THE COST:
// every VU request counts against the Cloudflare free tier (100k req/day) and
// a cache MISS wakes Neon. The zero-idle design means warm-path p95 should be
// KV-served (~<100ms edge); this script verifies that WITHOUT touching Neon:
// it hits only GET endpoints that are KV-cached and asserts x-cache != MISS.
//   k6 run -e BASE=https://aacapitalprivatelimited.com _scripts/loadtest_k6.js
import http from "k6/http";
import { check } from "k6";
export const options = {
  scenarios: { steady: { executor: "constant-vus", vus: 20, duration: "60s" } },
  thresholds: {
    http_req_duration: ["p(95)<200"],   // owner target
    http_req_failed: ["rate<0.001"],    // <0.1% errors
  },
};
export default function () {
  const r = http.get(`${__ENV.BASE}/api/ipo-command`);
  check(r, {
    "status 200/401": (x) => x.status === 200 || x.status === 401, // 401 = auth gate, still edge-served
    "served from KV, Neon asleep": (x) => x.status !== 200 || (x.headers["X-Cache"] ?? "") !== "MISS",
  });
}
