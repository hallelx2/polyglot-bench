// Local dashboard server: static page + live results directory.
const ROOT = new URL("..", import.meta.url).pathname;
const port = Number(process.env.DASH_PORT ?? 7777);

Bun.serve({
  port,
  async fetch(req) {
    const p = new URL(req.url).pathname;
    const file = p === "/" ? "dashboard/index.html"
      : p.startsWith("/results/") ? p.slice(1)
      : "dashboard" + p;
    const f = Bun.file(ROOT + file);
    if (!(await f.exists())) return new Response("not found", { status: 404 });
    return new Response(f, { headers: { "cache-control": "no-store" } });
  },
});
console.log(`dashboard on http://localhost:${port}`);
