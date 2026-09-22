/**
 * Bench API — Bun only. Zero npm dependencies.
 *
 *   HTTP + routing   Bun.serve + a ~60-line router
 *   database         Bun.sql (Postgres wire protocol, built in)
 *
 * `bun run src/server.ts` is the whole thing. `bun build --compile` turns it
 * into one executable.
 */
import { json, Router } from "./core/router.ts";
import { mountPricing } from "./routes/pricing.ts";
import { sql } from "./db/sql.ts";

const PORT = Number(Bun.env.PORT ?? 8080);

const router = new Router();
router.get("/health", () => json({ ok: true }));

/** Event-loop lag: the one number that tells you a handler blocked everyone. */
let maxLagMs = 0;
let last = Bun.nanoseconds();
setInterval(() => {
  const now = Bun.nanoseconds();
  maxLagMs = Math.max(maxLagMs, (now - last) / 1e6 - 500);
  last = now;
}, 500).unref?.();
router.get("/metrics", () => json({
  maxEventLoopLagMs: +maxLagMs.toFixed(2),
  rss: process.memoryUsage().rss,
}));

mountPricing(router);

// Open the pool before the first request so warmup measures the server, not
// nine connection handshakes.
await sql`SELECT 1`;

const server = Bun.serve({
  port: PORT,
  hostname: "0.0.0.0",
  reusePort: true,
  development: false,
  fetch: (req) => router.handle(req),
  error(e) {
    return json({ error: String((e as Error)?.message ?? e) }, { status: 500 });
  },
});

console.log(`bench api on http://localhost:${server.port}`);
