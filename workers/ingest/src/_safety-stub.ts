// workers/ingest/src/_safety-stub.ts
//
// Intentionally-unusable top-level entrypoint. `wrangler deploy` with no
// `--env staging` compiles/loads this file. It has NO bindings and NO
// routes at the top level of `wrangler.jsonc`, and returns 410 on every
// request. If it is somehow deployed, it cannot serve production traffic
// or write to any resource.
//
// The real ingest handler lives in `src/index.ts` and is only wired under
// `env.staging`.
export default {
  async fetch(): Promise<Response> {
    return new Response(
      "AACapital Stage-A safety stub. This top-level Worker is intentionally " +
        "non-functional. Deploy with `--env staging` to run the real ingest Worker.",
      { status: 410, headers: { "content-type": "text/plain" } }
    );
  },
};
