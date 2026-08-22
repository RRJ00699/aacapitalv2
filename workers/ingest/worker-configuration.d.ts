// workers/ingest/worker-configuration.d.ts
//
// Ambient Cloudflare types used by the ingest Worker. Mirrors the pattern of
// workers/kite-broker-proxy/ (which generates its own worker-configuration.d.ts
// via `wrangler types`). We hand-declare here to keep the Worker self-
// contained: types resolve at repo-wide `tsc --noEmit` without adding a new
// dependency or requiring `wrangler types --config workers/ingest/...` to
// have been run first.
//
// The declarations below are a strict SUBSET of
// @cloudflare/workers-types/D1Database, sufficient for our ingest Worker.

export {};

declare global {
  interface D1Result<T = unknown> {
    results?: T[];
    success: boolean;
    meta: {
      last_row_id?: number;
      changes?: number;
      duration?: number;
      served_by?: string;
      [k: string]: unknown;
    };
    error?: string;
  }

  interface D1PreparedStatement {
    bind(...values: unknown[]): D1PreparedStatement;
    first<T = unknown>(colName?: string): Promise<T | null>;
    run<T = unknown>(): Promise<D1Result<T>>;
    all<T = unknown>(): Promise<D1Result<T>>;
    raw<T = unknown>(): Promise<T[]>;
  }

  interface D1Database {
    prepare(sql: string): D1PreparedStatement;
    batch<T = unknown>(statements: D1PreparedStatement[]): Promise<D1Result<T>[]>;
    exec(sql: string): Promise<D1Result>;
    dump(): Promise<ArrayBuffer>;
  }

  interface ExecutionContext {
    waitUntil(promise: Promise<unknown>): void;
    passThroughOnException(): void;
  }

  interface ExportedHandler<Env = unknown> {
    fetch?(request: Request, env: Env, ctx: ExecutionContext): Response | Promise<Response>;
    scheduled?(event: ScheduledEvent, env: Env, ctx: ExecutionContext): void | Promise<void>;
  }

  interface ScheduledEvent {
    scheduledTime: number;
    cron: string;
    type: "scheduled";
  }
}
