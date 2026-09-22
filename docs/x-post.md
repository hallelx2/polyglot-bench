# Long post — X

> Attach `video/polyglot-bench-run.mp4` (48s, 1920×1080). Link:
> github.com/hallelx2/polyglot-bench

---

"Python is slow." "Rewrite it in Rust and it'll be fast."

Both true. Neither tells you whether it matters on a Tuesday, on the service you actually maintain.

So I stopped arguing and measured it.

The benchmarks everyone quotes load-test one endpoint that returns a fixed string, scaled across a cluster until the req/s number looks impressive. Almost no production code looks like that. What the rest of us ship opens a transaction, reads six tables, applies pricing rules that grew out of three years of edge cases, writes to five more, and commits.

So I built that instead: order pricing and checkout for an ecommerce API. Six reads, a discount engine with stacking rules and coupons, an eleven-statement write transaction that locks stock and books the order.

Then I wrote it ten times — TypeScript, Go, Rust — and proved all ten return byte-identical output before timing a single request. 450 runs. 6 million API calls. 44.8 million SQL statements. Zero errors.

Four things came out of it.

**1. At realistic load, the language is not the variable.**
At a fixed 300 req/s — 26 million calls a day, more than most businesses ever serve — all ten stacks land within 0.96 ms of each other on p99. Go's net/http is fastest at 2.64 ms. A zero-dependency Bun service is second at 2.66. Node + Fastify, the slowest, is 3.58. At that load your query plans decide your latency, not your runtime.

**2. Rust and Go are statistically indistinguishable here.**
Best Rust vs best Go: 1.00× (95% CI 0.86–1.07, p = 0.71). Not close to significant. On a workload dominated by database round trips, the gap people argue about does not appear. The Friedman test rejects the null hard across the board (p = 5.8e-09), so the test has power — it just doesn't separate those two.

**3. What the compiled stacks actually buy is headroom and memory.**
Flat out, Rust serves 1.45× more than the best TypeScript stack. And memory never converges: Rust holds 7.7 MB where Node holds 242.9 MB for the same work. 31×. That's your server bill, not your latency.

**4. The ORM cost more than the language.**
Same Gin router, same Go, only the data layer changed: hand-written SQL → GORM. Throughput fell 1.84×. CPU per request went 0.83 ms → 2.87 ms. p99 on checkout went 62 ms → 389 ms.

And it quietly issued a query I never asked for. Conformance proved all ten returned the same bytes; counting statements at the server caught GORM's `Preload` fetching the customer tier with a second SELECT instead of the join the spec prescribed. Seven statements where every other implementation sent six.

That's the habit worth taking from this. Not "avoid ORMs", not "use Rust". Know what your code actually sends to the database. Turn on `log_statement`, count the queries per endpoint, check the number against what you'd have written by hand.

Everything's public — the ten implementations, all 450 raw run files, the statistics, the figures, and a paper. Re-run it and argue with the numbers:

github.com/hallelx2/polyglot-bench

---

## Thread version (if you'd rather post it as one)

1/ "Python is slow." "Rewrite it in Rust." Both true. Neither tells you if it matters on the service you actually maintain. So I measured it properly. 10 implementations of one real checkout API, proved byte-identical, 450 runs, 6M calls. 🧵

2/ The benchmarks people quote load-test an endpoint returning a fixed string. Production code opens a transaction, reads six tables, applies pricing rules, writes to five more, commits. I benchmarked *that*.

3/ At 300 req/s — 26M calls a day — all ten stacks are within 0.96 ms of each other on p99. Go net/http 2.64 ms. A zero-dep Bun service 2.66 ms. Node+Fastify 3.58 ms. At that load your query plans decide your latency, not your runtime.

4/ Best Rust vs best Go: 1.00× (CI 0.86–1.07, p=0.71). Statistically indistinguishable. The omnibus test rejects the null at p=5.8e-09, so it has power — it just doesn't separate those two.

5/ What compiled languages actually buy: headroom and memory. 1.45× more throughput flat out, and Rust holds 7.7 MB where Node holds 242.9 MB for identical work. 31×. That's the server bill.

6/ The expensive decision wasn't the language. Same Gin router, same Go, swap hand-written SQL for GORM: 1.84× less throughput, 3.5× the CPU per request, p99 on checkout 62 ms → 389 ms.

7/ GORM also issued a query I never asked for. Output was byte-identical; counting statements caught `Preload` doing a second SELECT instead of a join. 7 statements where the other nine sent 6.

8/ The lesson isn't "avoid ORMs" or "use Rust". It's: know what your code sends to the database. `log_statement`, count queries per endpoint, compare against what you'd write by hand.

9/ All public — implementations, 450 raw run files, statistics, figures, paper. github.com/hallelx2/polyglot-bench
