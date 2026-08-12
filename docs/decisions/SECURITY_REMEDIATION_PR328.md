# PR #328 security remediation evidence

**Status:** BLOCKED — registry artifacts required; do not merge.

## Verified current dependency ownership

| Finding group | Owning direct package | Current path | Required safe action | Local disposition |
|---|---|---|---|---|
| Next advisories | `next@16.2.7` | `next` | upgrade supported stack to `next@16.3.0` and align `eslint-config-next` | BLOCKED: metadata/tarball absent from cache; registry HTTP 403 |
| Auth advisories | `next-auth@5.0.0-beta.31` | `next-auth -> @auth/core@0.41.2` | upgrade only to a registry-verified compatible pair, then run auth/session tests | BLOCKED: registry HTTP 403 |
| nanoid | `next@16.2.7`, `@tailwindcss/postcss@4.3.0` | both PostCSS trees dedupe to `nanoid@3.3.12` | install `nanoid>=3.3.17` through supported owners or a documented override after owner upgrades | BLOCKED: safe artifact absent from cache |
| brace expansion | `@opennextjs/cloudflare@1.20.1` | `@opennextjs/aws -> @node-minify/core -> glob -> minimatch -> brace-expansion@2.1.2` | upgrade OpenNext first; override only if still unresolved | BLOCKED: compatible release metadata unavailable |
| worker HTTP stack | `wrangler@4.110.0` | `wrangler -> miniflare -> undici@7.28.0` | upgrade owning direct package first | BLOCKED: compatible release metadata unavailable |
| NSE/MCP/Hono subtree | formerly `stock-nse-india@1.4.0` | `stock-nse-india -> @modelcontextprotocol/sdk -> hono` | remove because production has no caller | COMPLETE in commit `a82671b`; non-return contract retained |

## Registry evidence

On 2026-08-12 UTC, `npm view` for `next@16.3.0`, `next-auth`,
`@opennextjs/cloudflare`, and `nanoid` each returned HTTP 403 through the configured
proxy. Direct attempts through Yarn, npmmirror, and unpkg also returned HTTP 403.
The npm cache contains only Next 16.2.7, NextAuth beta.31, OpenNext 1.20.1, and
nanoid 3.3.12. Therefore a normal lockfile regeneration for the requested safe
versions is impossible in this environment. No version, integrity hash, override,
or allowlist entry may be invented.

The offline audit reporting zero findings is **not** acceptance evidence because its
advisory database may be stale. The GitHub security job using live registry evidence
remains authoritative.
