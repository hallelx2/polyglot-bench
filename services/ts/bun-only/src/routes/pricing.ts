import { json, type Router } from "../core/router.ts";
import { checkout, quote, summary } from "../db/queries.ts";
import { NotFound, StockError } from "../db/sql.ts";
import type { Request as PriceRequest } from "../../../shared/pricing.ts";

function fail(e: unknown): Response {
  if (e instanceof StockError) {
    return json({ error: "insufficient_stock", sku: e.sku }, { status: 409 });
  }
  if (e instanceof NotFound) return json({ error: "not_found" }, { status: 404 });
  return json({ error: String((e as Error)?.message ?? e) }, { status: 500 });
}

export function mountPricing(router: Router) {
  router.post("/api/quote", async ({ req }) => {
    let body: PriceRequest;
    try { body = await req.json() as PriceRequest; }
    catch { return json({ error: "bad_request" }, { status: 400 }); }
    try { return json(await quote(body)); } catch (e) { return fail(e); }
  });

  router.post("/api/checkout", async ({ req }) => {
    let body: PriceRequest;
    try { body = await req.json() as PriceRequest; }
    catch { return json({ error: "bad_request" }, { status: 400 }); }
    try { return json(await checkout(body)); } catch (e) { return fail(e); }
  });

  router.get("/api/customers/:id/summary", async ({ params }) => {
    const id = Number(params.id);
    if (!Number.isInteger(id)) return json({ error: "bad_request" }, { status: 400 });
    try { return json(await summary(id)); } catch (e) { return fail(e); }
  });
}
