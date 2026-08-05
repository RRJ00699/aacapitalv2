import test from "node:test"
import assert from "node:assert/strict"
import { approvedSymbolsFromSnapshot, inIpoDecisionWindow, fetchBrokerQuotes, overlaySnapshot } from "./broker-proxy"
import { handleBrokerRequest, type BrokerEnv } from "../../workers/kite-broker-proxy/src/index"

const env: BrokerEnv = { KITE_API_KEY: "api_key", KITE_ACCESS_TOKEN: "secret-token-never-leak", BROKER_PROXY_AUTH_SECRET: "broker-secret", KITE_BASE_URL: "https://kite.test" }
const kiteBody = { status: "success", data: { "NSE:TEST": { last_price: 123, ohlc: { open: 100, high: 130, low: 99, close: 101 }, volume: 1000, total_buy_quantity: 700, total_sell_quantity: 300, depth: { buy: [{ price: 122, quantity: 10, orders: 1 }], sell: [{ price: 124, quantity: 20, orders: 2 }] } } } }

function req(path: string, init: RequestInit = {}) { return new Request(`https://broker.test${path}`, init) }

async function withFetch<T>(impl: typeof fetch, fn: () => Promise<T>): Promise<T> {
  const old = globalThis.fetch
  globalThis.fetch = impl
  try { return await fn() } finally { globalThis.fetch = old }
}

test("public allow-list is derived from server snapshot, not browser input", () => {
  assert.deepEqual(approvedSymbolsFromSnapshot({ listings: [{ sym: "test" }, { nse_symbol: "NEXT" }, { sym: "bad symbol" }] }), ["TEST", "NEXT"])
})

test("IST decision window is bounded", () => {
  assert.equal(inIpoDecisionWindow(new Date("2026-08-05T03:24:00Z")), false) // 08:54 IST
  assert.equal(inIpoDecisionWindow(new Date("2026-08-05T03:25:00Z")), true)  // 08:55 IST
  assert.equal(inIpoDecisionWindow(new Date("2026-08-05T04:10:00Z")), true)  // 09:40 IST critical decision window
  assert.equal(inIpoDecisionWindow(new Date("2026-08-05T04:35:00Z")), true)  // 10:05 IST
  assert.equal(inIpoDecisionWindow(new Date("2026-08-05T04:36:00Z")), false) // 10:06 IST
})

test("broker authentication required", async () => {
  const res = await handleBrokerRequest(req("/quotes", { method: "POST", body: JSON.stringify({ symbols: ["TEST"], allowed_symbols: ["TEST"] }) }), env)
  assert.equal(res.status, 401)
})

test("unsupported endpoints rejected", async () => {
  const res = await handleBrokerRequest(req("/orders", { headers: { authorization: "Bearer broker-secret" } }), env)
  assert.equal(res.status, 404)
  assert.match(await res.text(), /unsupported_endpoint/)
})

test("arbitrary symbols rejected when absent from request allow-list", async () => {
  const res = await handleBrokerRequest(req("/quotes", { method: "POST", headers: { authorization: "Bearer broker-secret" }, body: JSON.stringify({ symbols: ["EVIL"], allowed_symbols: ["TEST"] }) }), env)
  assert.equal(res.status, 403)
})

test("more than 15 symbols rejected", async () => {
  const symbols = Array.from({ length: 16 }, (_, i) => `T${i}`)
  const res = await handleBrokerRequest(req("/quotes", { method: "POST", headers: { authorization: "Bearer broker-secret" }, body: JSON.stringify({ symbols, allowed_symbols: symbols }) }), env)
  assert.equal(res.status, 413)
})

test("successful live overlay returns sanitized quote/depth only", async () => {
  await withFetch(async () => new Response(JSON.stringify(kiteBody), { status: 200, headers: { "content-type": "application/json" } }), async () => {
    const res = await handleBrokerRequest(req("/quotes", { method: "POST", headers: { authorization: "Bearer broker-secret" }, body: JSON.stringify({ symbols: ["TEST"], allowed_symbols: ["TEST"] }) }), env)
    assert.equal(res.status, 200)
    const text = await res.text()
    assert.equal(text.includes(env.KITE_ACCESS_TOKEN), false)
    const body = JSON.parse(text)
    assert.equal(body.quotes.TEST.last_price, 123)
    assert.deepEqual(Object.keys(body.quotes.TEST).sort(), ["as_of", "close", "depth", "high", "instrument", "last_price", "low", "open", "symbol", "total_buy_quantity", "total_sell_quantity", "volume"].sort())
    const overlaid = overlaySnapshot({ listings: [{ sym: "TEST" }] }, body.quotes, body.as_of)
    assert.equal(overlaid.live_overlay, "AVAILABLE")
    assert.equal(overlaid.book_live, true)
  })
})

test("token never appears in broker error responses", async () => {
  await withFetch(async () => new Response(`upstream says ${env.KITE_ACCESS_TOKEN}`, { status: 500 }), async () => {
    const res = await handleBrokerRequest(req("/quotes", { method: "POST", headers: { authorization: "Bearer broker-secret" }, body: JSON.stringify({ symbols: ["FAILX"], allowed_symbols: ["FAILX"] }) }), env)
    assert.equal(res.status, 502)
    assert.equal((await res.text()).includes(env.KITE_ACCESS_TOKEN), false)
  })
})

test("public broker client sends only symbols and allow-list, not Kite token", async () => {
  let outbound = ""
  await fetchBrokerQuotes({ brokerUrl: "https://broker.test", brokerSecret: "broker-secret", symbols: ["TEST"], fetchImpl: (async (_url, init) => { outbound = String(init?.body ?? ""); return new Response(JSON.stringify({ ok: true, quotes: {}, as_of: "now" }), { status: 200 }) }) as typeof fetch })
  assert.equal(outbound.includes("KITE_ACCESS_TOKEN"), false)
  assert.equal(outbound.includes("secret-token"), false)
  assert.match(outbound, /allowed_symbols/)
})
