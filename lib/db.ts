/**
 * Legacy tagged-template DB helper retained only for deterministic UAT fixtures.
 * Production callers must use D1/KV-specific helpers. A forgotten runtime caller
 * fails visibly instead of silently waking the retired database.
 */

type QueryValue = unknown

let _fixture: Record<string, any[]> | null | undefined
function fixtureRows(q: string): any[] | null {
  if (_fixture === undefined) {
    const path = process.env.UAT_FIXTURE_JSON
    if (!path) { _fixture = null } else {
      try {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        _fixture = JSON.parse(require("fs").readFileSync(path, "utf8"))
        console.warn(`[db] UAT FIXTURE MODE — serving queries from ${path}`)
      } catch { _fixture = null }
    }
  }
  if (!_fixture) return null
  const lower = q.toLowerCase()
  for (const k of Object.keys(_fixture)) {
    if (lower.includes(k)) return JSON.parse(JSON.stringify(_fixture[k]))
  }
  return []
}

async function runQuery(strings: TemplateStringsArray): Promise<any[]> {
  const fx = fixtureRows(strings.join(" "))
  if (fx !== null) return fx
  throw new Error("legacy lib/db runtime access is retired; use D1/KV helper")
}

export async function sql(strings: TemplateStringsArray, ..._values: QueryValue[]): Promise<any[]> {
  return runQuery(strings)
}

export async function localSql(strings: TemplateStringsArray, ..._values: QueryValue[]): Promise<any[]> {
  return runQuery(strings)
}

export function normalizeSymbol(symbol: string | null | undefined): string {
  return String(symbol || '').trim().toUpperCase().replace(/\.NS$/i, '')
}

export function ok(data: unknown, init?: ResponseInit) {
  return Response.json({ success: true, data }, init)
}

export function fail(message: string, status = 500, details?: unknown) {
  return Response.json({ success: false, error: message, details }, { status })
}

export function fixtureAwareNeon(_url?: string) {
  return (async (strings: TemplateStringsArray, ..._values: QueryValue[]) => runQuery(strings)) as any
}
