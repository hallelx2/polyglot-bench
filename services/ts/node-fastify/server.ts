// Node.js + Fastify + node-postgres: the reference "boring Node" stack.
import Fastify from "fastify";
import { checkout, NotFound, quote, StockError, summary } from "../shared/pgdb.ts";
import type { Request as PriceRequest } from "../shared/pricing.ts";

const app = Fastify({ logger: false, disableRequestLogging: true });

function fail(reply: any, e: unknown) {
  if (e instanceof StockError) return reply.code(409).send({ error: "insufficient_stock", sku: e.sku });
  if (e instanceof NotFound) return reply.code(404).send({ error: "not_found" });
  return reply.code(500).send({ error: String((e as Error)?.message ?? e) });
}

app.get("/health", async () => ({ ok: true }));

app.post("/api/quote", async (req, reply) => {
  try { return await quote(req.body as PriceRequest); }
  catch (e) { return fail(reply, e); }
});
app.post("/api/checkout", async (req, reply) => {
  try { return await checkout(req.body as PriceRequest); }
  catch (e) { return fail(reply, e); }
});
app.get<{ Params: { id: string } }>("/api/customers/:id/summary", async (req, reply) => {
  try { return await summary(Number(req.params.id)); }
  catch (e) { return fail(reply, e); }
});

await app.listen({ port: Number(process.env.PORT ?? 8080), host: "0.0.0.0" });
