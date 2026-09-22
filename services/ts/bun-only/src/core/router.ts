/**
 * A tiny router over Bun.serve. No dependencies — Bun already parses the URL,
 * the body and the headers; all that is missing is an opinion.
 */
export type Ctx = {
  req: Request;
  url: URL;
  params: Record<string, string>;
};
export type Handler = (ctx: Ctx) => Response | Promise<Response>;
type Route = { method: string; parts: string[]; handler: Handler };

export function json(data: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(data), {
    ...init,
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
  });
}

export class Router {
  #routes: Route[] = [];

  add(method: string, pattern: string, handler: Handler) {
    this.#routes.push({ method, parts: pattern.split("/").filter(Boolean), handler });
    return this;
  }
  get(p: string, h: Handler) { return this.add("GET", p, h); }
  post(p: string, h: Handler) { return this.add("POST", p, h); }

  #match(method: string, path: string) {
    const segs = path.split("/").filter(Boolean);
    for (const r of this.#routes) {
      if (r.method !== method || r.parts.length !== segs.length) continue;
      const params: Record<string, string> = {};
      let ok = true;
      for (let i = 0; i < segs.length; i++) {
        const p = r.parts[i];
        if (p.charCodeAt(0) === 58 /* : */) params[p.slice(1)] = segs[i];
        else if (p !== segs[i]) { ok = false; break; }
      }
      if (ok) return { route: r, params };
    }
    return null;
  }

  async handle(req: Request): Promise<Response> {
    const url = new URL(req.url);
    const m = this.#match(req.method, url.pathname);
    if (!m) return json({ error: "not_found" }, { status: 404 });
    return await m.route.handler({ req, url, params: m.params });
  }
}
