import { getCloudflareContext } from "@opennextjs/cloudflare";

type D1Prepared = {
  bind: (...values: unknown[]) => D1Prepared;
  first: <T = Record<string, unknown>>() => Promise<T | null>;
  all: <T = Record<string, unknown>>() => Promise<{ results?: T[] }>;
  run: () => Promise<unknown>;
};

type D1DatabaseLike = {
  prepare: (sql: string) => D1Prepared;
};

async function db(): Promise<D1DatabaseLike> {
  const { env } = await getCloudflareContext({ async: true });
  const bound = (env as unknown as { DB?: D1DatabaseLike }).DB;
  if (!bound) throw new Error("Cloudflare D1 binding DB is not configured");
  return bound;
}

export async function d1First<T = Record<string, unknown>>(sql: string, values: unknown[] = []): Promise<T | null> {
  const database = await db();
  return database.prepare(sql).bind(...values).first<T>();
}

export async function d1All<T = Record<string, unknown>>(sql: string, values: unknown[] = []): Promise<T[]> {
  const database = await db();
  const out = await database.prepare(sql).bind(...values).all<T>();
  return out.results ?? [];
}

export async function d1Run(sql: string, values: unknown[] = []): Promise<void> {
  const database = await db();
  await database.prepare(sql).bind(...values).run();
}
