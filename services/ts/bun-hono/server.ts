// Bun runtime + Hono + node-postgres: the ordinary npm stack, run on Bun.
import { Hono } from "hono";
import { checkout, NotFound, quote, StockError, summary } from "../shared/pgdb.ts";
import type { Request as PriceRequest } from "../shared/pricing.ts";

const app = new Hono();

function fail(c: any, e: unknown) {
  if (e instanceof StockError) return c.json({ error: "insufficient_stock", sku: e.sku }, 409);
  if (e instanceof NotFound) return c.json({ error: "not_found" }, 404);
  return c.json({ error: String((e as Error)?.message ?? e) }, 500);
}

app.get("/health", (c) => c.json({ ok: true }));

app.post("/api/quote", async (c) => {
  try { return c.json(await quote(await c.req.json() as PriceRequest)); }
  catch (e) { return fail(c, e); }
});
app.post("/api/checkout", async (c) => {
  try { return c.json(await checkout(await c.req.json() as PriceRequest)); }
  catch (e) { return fail(c, e); }
});
app.get("/api/customers/:id/summary", async (c) => {
  try { return c.json(await summary(Number(c.req.param("id")))); }
  catch (e) { return fail(c, e); }
});

export default {
  port: Number(process.env.PORT ?? 8080),
  reusePort: true,
  fetch: app.fetch,
};
