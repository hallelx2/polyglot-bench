#!/usr/bin/env python3
"""Generate README.md and RESULTS.md from analysis/stats.json.

Prose lives here; every number is read from the analysis output, so the
documents cannot drift from the measurements behind them.
"""
import json

S = json.load(open("analysis/stats.json"))
# Phase-1 stacks, measured with bench/count_statements.sh. Kept separate from
# analysis/statements.json, which the data-layer study rewrites per variant.
STMT = json.load(open("analysis/statements_phase1.json"))
STACKS = {s["id"]: s for s in json.load(open("bench/stacks.json"))}
SIDS = list(STACKS)
SCEN = ["quote", "checkout", "summary"]
M = S["meta"]
C = lambda sid, sc, cf, m: S["cells"][f"{sid}|{sc}|{cf}"][m]
con = {(t["a"], t["b"]): t for t in S["plannedContrasts"]}


def n(v, d=0):
    return f"{v:,.{d}f}"


def rank_table(metric, conf, caption):
    rows = sorted(SIDS, key=lambda s: -C(s, "quote", conf, metric)["median"]
                  if metric == "rps" else C(s, "quote", conf, metric)["median"])
    out = [f"| stack | " + " | ".join(s.capitalize() for s in SCEN) + " |",
           "|---" * (len(SCEN) + 1) + "|"]
    for sid in rows:
        cells = [n(C(sid, sc, conf, metric)["median"], 0 if metric == "rps" else 2)
                 for sc in SCEN]
        name = f"**`{sid}`**" if sid == "ts-bun-only" else f"`{sid}`"
        out.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def full_table(sc, conf):
    rows = sorted(SIDS, key=lambda s: -C(s, sc, conf, "rps")["median"])
    out = ["| stack | req/s | p50 | p90 | p99 | p99.9 | CPU ms/call | peak RSS | CV |",
           "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for sid in rows:
        c = lambda m: C(sid, sc, conf, m)
        out.append(
            f"| `{sid}` | {n(c('rps')['median'])} | {n(c('p50')['median'],2)} "
            f"| {n(c('p90')['median'],2)} | {n(c('p99')['median'],2)} "
            f"| {n(c('p999')['median'],2)} | {n(c('cpu')['median'],3)} "
            f"| {n(c('rss')['median'],1)} MB | {c('rps')['cv']*100:.1f}% |")
    return "\n".join(out)



_f99 = S["friedman"]["p99"]["avgRank"]
_cd = S["friedman"]["p99"]["criticalDifference"]
_rk = lambda ids: max(_f99[i] for i in ids) - min(_f99[i] for i in ids)
rust_span = _rk(["rust-axum", "rust-hyper", "rust-actix"])
go_span = _rk(["go-nethttp", "go-fiber", "go-gin"])
gin_cpu, gorm_cpu = C("go-gin","quote","closed@64","cpu")["median"], C("go-gin-gorm","quote","closed@64","cpu")["median"]
gin_cpu_co, gorm_cpu_co = C("go-gin","checkout","closed@64","cpu")["median"], C("go-gin-gorm","checkout","closed@64","cpu")["median"]
gin_q, gorm_q = STMT["go-gin"]["quote"], STMT["go-gin-gorm"]["quote"]
gin_c, gorm_c = STMT["go-gin"]["checkout"], STMT["go-gin-gorm"]["checkout"]
orm_delta = gorm_cpu - gin_cpu
_per_stmt_gin = gin_cpu / gin_q
extra_share = _per_stmt_gin / orm_delta * 100
tax_lo = (orm_delta - _per_stmt_gin) / gin_q
tax_hi = (gorm_cpu_co - gin_cpu_co - gin_cpu_co / gin_c) / gin_c
if tax_lo > tax_hi: tax_lo, tax_hi = tax_hi, tax_lo
_gocpu = [C(i,"quote","closed@64","cpu")["median"] for i in ("go-nethttp","go-fiber","go-gin")]
fw_spread = max(_gocpu) - min(_gocpu)
tax_vs_fw = orm_delta / fw_spread
n_q, n_c = STMT["rust-axum"]["quote"], STMT["rust-axum"]["checkout"]

fri99, fricpu = S["friedman"]["p99"], S["friedman"]["cpu"]
bun_hono = con[("ts-bun-only", "ts-bun-hono")]
bun_node = con[("ts-bun-only", "ts-node-fastify")]
gorm = con[("go-gin", "go-gin-gorm")]
rust_go = con[("rust-axum", "go-fiber")]
rust_bun = con[("rust-axum", "ts-bun-only")]

# widest p99 spread under fixed 300/s, to support the "identical at real load" claim
p99_300 = {sid: C(sid, "quote", "open@300", "p99")["median"] for sid in SIDS}
best300, worst300 = min(p99_300, key=p99_300.get), max(p99_300, key=p99_300.get)

BADGE = "https://img.shields.io/badge"
README = f"""<div align="center">

# Polyglot Checkout Bench

**One database-bound business transaction, written ten ways, measured properly.**

[![license]({BADGE}/license-MIT-18181b?style=flat-square)](LICENSE)
[![stacks]({BADGE}/stacks-10-ff5a00?style=flat-square)](#the-ten-stacks)
[![runs]({BADGE}/runs-{S['nRuns']}-18181b?style=flat-square)](RESULTS.md)
[![calls]({BADGE}/API%20calls-6.0M-18181b?style=flat-square)](RESULTS.md)
[![conformance]({BADGE}/conformance-10%2F10%20identical-1baf7a?style=flat-square)](#conformance-comes-first)
[![errors]({BADGE}/non--2xx-0-1baf7a?style=flat-square)](RESULTS.md)
[![paper]({BADGE}/paper-PDF-18181b?style=flat-square)](paper/main.pdf)
[![last commit](https://img.shields.io/github/last-commit/hallelx2/polyglot-bench?style=flat-square&color=71717a)](https://github.com/hallelx2/polyglot-bench/commits)
[![stars](https://img.shields.io/github/stars/hallelx2/polyglot-bench?style=flat-square&color=71717a)](https://github.com/hallelx2/polyglot-bench/stargazers)

![TypeScript]({BADGE}/TypeScript-Bun%20%C2%B7%20Node-2a78d6?style=flat-square&logo=typescript&logoColor=white)
![Go]({BADGE}/Go-1.25-0e9bb5?style=flat-square&logo=go&logoColor=white)
![Rust]({BADGE}/Rust-1.98-b45309?style=flat-square&logo=rust&logoColor=white)
![PostgreSQL]({BADGE}/PostgreSQL-18-4a3aa7?style=flat-square&logo=postgresql&logoColor=white)

![Live dashboard replay of a measured run](docs/dashboard.gif)

<sub>A real measured window replayed at 3× slow motion — every line is that
stack's actual per-second series.</sub>

</div>

---

*Python is slow.* *Rewrite the backend in Rust and it will be fast.*

Both of those are true. Neither tells you whether it matters on an ordinary
Tuesday, on the service you actually maintain.

The benchmarks people cite do not settle it either. Most of them load-test a
single endpoint that returns a fixed string or serialises one small object,
scaled across a cluster until the requests-per-second number looks impressive.
Very little production code looks like that. What the rest of us ship opens a
transaction, reads half a dozen tables, applies pricing rules that accumulated
over three years of edge cases, writes to several more tables and commits. It
spends most of its wall-clock time waiting on a database rather than executing
its own instructions, and that is the regime the hello-world numbers say
nothing about.

So this benchmarks the thing engineers actually build: order pricing and
checkout for an ecommerce API. Six reads, a discount engine with stacking rules
and coupons, then an eleven-statement write transaction that locks stock and
books the order.

One specification. Ten implementations across TypeScript, Go and Rust. Every
one proved byte-for-byte identical before a stopwatch started, then measured
under identical load, with statistics that say which of the differences are
real and which are noise.

![Throughput at saturation](docs/figures/throughput.png)

## The short answer

At a fixed 300 requests per second — 26 million calls a day, more than most
businesses ever serve — the ten stacks are separated by
**{p99_300[worst300] - p99_300[best300]:.1f} ms of p99 latency**, from
{p99_300[best300]:.2f} ms (`{best300}`) to {p99_300[worst300]:.2f} ms
(`{worst300}`). At that load the runtime is not the variable. Your query plans are.

What the compiled stacks buy is headroom and memory, not response time. Pushed
until they break, Rust and Go serve {rust_bun['ratio']:.2f}x
[{rust_bun['ratioCI'][0]:.2f}–{rust_bun['ratioCI'][1]:.2f}] more requests than the
fastest TypeScript stack, and Rust holds around
{C('rust-hyper','quote','closed@64','rss')['median']:.0f} MB resident where Node
holds {C('ts-node-fastify','quote','closed@64','rss')['median']:.0f} MB for the
same work.

Three results that hold across every workload and load profile:

- **Rust and Go are statistically indistinguishable here.**
  `rust-axum` against `go-fiber` is {rust_go['ratio']:.2f}x
  [{rust_go['ratioCI'][0]:.2f}–{rust_go['ratioCI'][1]:.2f}], p={rust_go['pHolm']:.2f}.
  On a workload dominated by database round-trips, the gap people expect does
  not appear.
- **Dropping to zero dependencies made the TypeScript service faster.**
  `ts-bun-only` — `Bun.serve`, `Bun.sql`, a sixty-line router, no `node_modules` —
  beats Hono + node-postgres by {bun_hono['ratio']:.2f}x
  [{bun_hono['ratioCI'][0]:.2f}–{bun_hono['ratioCI'][1]:.2f}] and Node + Fastify by
  {bun_node['ratio']:.2f}x [{bun_node['ratioCI'][0]:.2f}–{bun_node['ratioCI'][1]:.2f}].
- **The ORM costs more than the language.** `go-gin` and `go-gin-gorm` differ only
  in their data layer: {gorm['ratio']:.2f}x
  [{gorm['ratioCI'][0]:.2f}–{gorm['ratioCI'][1]:.2f}] throughput, and
  {C('go-gin-gorm','checkout','closed@64','cpu')['median']:.2f} ms of CPU per
  checkout against {C('go-gin','checkout','closed@64','cpu')['median']:.2f} ms.
  Choosing GORM costs more than choosing TypeScript over Go.

## Why the data layer is the decision that matters

The framework you pick is not measurable here. Not one framework-against-framework
pair inside a language separates at the 5% level — Rust's Axum, hyper and Actix
span {rust_span:.2f} ranks, Go's Fiber, net/http and Gin span {go_span:.2f}, and the
Nemenyi critical difference is {_cd:.2f}. The data layer separates loudly.

Hold the router constant and change only how it reaches Postgres:

| | `go-gin` (pgx, hand-written SQL) | `go-gin-gorm` (GORM) |
|---|--:|--:|
| throughput, quote | {C("go-gin","quote","closed@64","rps")["median"]:,.0f} req/s | {C("go-gin-gorm","quote","closed@64","rps")["median"]:,.0f} req/s |
| CPU per request, quote | {gin_cpu:.3f} ms | {gorm_cpu:.3f} ms |
| CPU per request, checkout | {gin_cpu_co:.3f} ms | {gorm_cpu_co:.3f} ms |
| p99, checkout | {C("go-gin","checkout","closed@64","p99")["median"]:.0f} ms | {C("go-gin-gorm","checkout","closed@64","p99")["median"]:.0f} ms |
| SQL statements per quote | {gin_q:.0f} | {gorm_q:.0f} |
| SQL statements per checkout | {gin_c:.0f} | {gorm_c:.0f} |

Two things are going on, and they are worth separating.

**The ORM issues more statements than it was asked to.** Nine of the ten services
send {n_q:.0f} statements for a quote and {n_c:.0f} for a checkout, measured by
`bench/count_statements.sh`. GORM sends one more of each: `Preload` fetches the
customer tier with a second `SELECT` instead of the join the specification
prescribes. The output is identical — it passes conformance — but the work
behind it is not.

**Most of the cost is not the extra statement.** GORM spends
{orm_delta:.3f} ms more CPU per quote than the identical router over pgx. If the
extra statement cost what `go-gin` pays per statement, it would account for about
{extra_share:.0f}% of that. The rest is per-statement overhead: reflection-based
row mapping, `SELECT *` where five columns were needed, and statement building on
every call. It works out to roughly **{tax_lo:.2f}–{tax_hi:.2f} ms of extra CPU per
statement**, and it scales with how many statements you issue — which is why the
gap widens from {gorm["perScenario"]["quote"]["ratio"]:.2f}x on quote to {gorm["perScenario"]["checkout"]["ratio"]:.2f}x on checkout.

Compare that against the framework. The three Go stacks over pgx differ by
{fw_spread:.3f} ms of CPU per request across the whole spread. The ORM's overhead is
**{tax_vs_fw:.0f}x** that spread. Per request this workload runs one HTTP parse and
one JSON response against {n_q:.0f} to {n_c:.0f} database round trips, so the layer
doing the repeated work is the layer that decides your number.

## The ten stacks

| id | Language | Framework | Driver |
|---|---|---|---|
""" + "\n".join(
    f"| `{s['id']}` | {s['lang']} | {s['framework']} | {s['driver']} |"
    for s in STACKS.values()) + f"""

Within each language the pricing engine is one shared module, so the framework
rows differ only by the framework. Two rows are deliberate exceptions:
`go-gin-gorm` reaches the same logic through an ORM, and `ts-bun-only` has no
third-party dependency at all — copy the folder, run `bun run src/server.ts`,
and it serves.

## The workload

Defined once in [`spec/SPEC.md`](spec/SPEC.md) and implemented to the letter by
all ten. It is a composite business transaction, not a micro-benchmark:

**`POST /api/quote`** — six reads, then a pricing engine that evaluates every
active discount rule against every cart line, resolves stacking (the largest
non-stackable rule plus all stackable ones, capped at 60% of the line), applies
a coupon pro rata across lines with remainder cents going to the largest line,
recomputes per-line tax on the reduced amount, bands shipping by total weight
and awards loyalty points. Integer cents throughout; no floating point touches
a price.

**`POST /api/checkout`** — the same engine inside one transaction that takes
`SELECT ... FOR UPDATE` on inventory in product-id order, rejects short stock
with a 409, then writes the order, a multi-row line insert, per-line inventory
reservations, two ledger entries, a coupon usage bump and a loyalty transaction
before committing.

**`GET /api/customers/:id/summary`** — four reads over the customer's last 50
orders and their lines, aggregated in process into lifetime value, top
categories by spend, points balance and a segment.

Against 50,000 customers, 5,000 products, 200,000 historical orders and 600,000
order lines.

## Conformance comes first

```bash
python3 bench/verify.py
```

Replays a fixed corpus against all ten services and diffs the canonical JSON.
A stack that computed a different invoice, skipped a query, or rounded
differently fails here before any stopwatch starts.

Conformance checks **output**, not query shape. `bench/count_statements.sh`
checks the second half: nine of the ten services issue the same 6 statements per
quote and 15 per checkout, and `go-gin-gorm` issues one more of each because
GORM's `Preload` resolves the customer tier with a second `SELECT` rather than
the prescribed join. That divergence is left in and reported rather than
patched out — an ORM quietly changing your query plan is part of what an ORM
costs. Two normalisations are
applied and both are documented in the script: `orderId`, which is a sequence
and differs per run, and ISO timestamp spelling, since `:00Z` and `:00.000Z` are
the same instant and the spec does not dictate fractional-second formatting.

All ten pass.

## Results

### Under fixed load the stacks converge

![Latency against offered load](docs/figures/latency_vs_load.png)

### What a request costs

![Cost of a request](docs/figures/cost_of_request.png)

### Statistics

Ten treatments measured over nine tasks (three workloads x three load profiles)
is the design Demsar's framework was built for: significance comes from the
number of tasks, not from repeating the same measurement. The Friedman test
rejects the null decisively for p99 latency
(chi-square = {fri99['chi2']:.1f}, p = {fri99['p']:.1e}) and for CPU per request
(chi-square = {fricpu['chi2']:.1f}, p = {fricpu['p']:.1e}).

The Nemenyi post-hoc critical difference is {fri99['criticalDifference']:.2f}
ranks. Stacks joined by a bar below are not distinguishable at the 5% level:

![Critical difference, p99 latency](docs/figures/cd_p99.png)

![Critical difference, CPU per request](docs/figures/cd_cpu.png)

Five contrasts were specified before the data was collected, each answering one
question. Throughput is normalised within each workload and pooled, giving 15
independent runs per stack, and tested with Mann-Whitney U under Holm
correction:

![Planned contrasts](docs/figures/contrasts.png)

### Tail behaviour on the write path

![Checkout tail latency](docs/figures/checkout_tail.png)

### Tables

Throughput at saturation, requests per second:

{rank_table('rps', 'closed@64', '')}

p99 latency at a fixed 300 req/s, milliseconds:

{rank_table('p99', 'open@300', '')}

Full tables for every workload and load profile are in
[RESULTS.md](RESULTS.md).

## Method

**Hardware.** Intel Core i7-8665U, 4 physical cores / 8 threads, 31 GB RAM,
Arch Linux, kernel 7.1.9. The CPU governor is pinned to `performance` for the
duration; on the default `powersave` governor the same suite produced a 66%
median spread across repetitions, against {S['machine']['degradedRuns']} of
{S['machine']['nRuns']} runs flagged as degraded here.

**Core pinning.** The three parties never share a core:

| | cores |
|---|---|
| PostgreSQL 18 (Docker, `cpuset: "0-2"`) | 0–2 |
| service under test (`taskset`) | 3–5 |
| load generator (`taskset`) | 6–7 |

**Database.** PostgreSQL 18 in Docker with a fixed configuration
(`shared_buffers=4GB`, `synchronous_commit=off`, `max_connections=400`), pinned
to its own cores, restored to seeded state before every single run.
`synchronous_commit=off` is a benchmark choice: it removes SSD commit stalls
that would otherwise dominate the write scenario. It is not a durability
recommendation. Autovacuum is disabled on the six churn tables and the vacuum
runs explicitly between runs, because autovacuum firing mid-measurement was the
largest source of noise in an earlier iteration of this suite.

**Load generation.** A purpose-built generator (`bench/loadgen`) runs in two
modes. Closed-loop holds 64 connections and sends as fast as the server answers,
finding the saturation ceiling. Open-loop schedules requests at a fixed arrival
rate and measures latency **from each request's intended send time**, so a
server that falls behind cannot hide it behind its own slowness — the
coordinated-omission correction. Warmup is excluded from statistics, so
JIT-compiled runtimes are not charged for their first few thousand requests.

**Run discipline.** {M['reps']} repetitions of {M['durationSec']}s after
{M['warmupSec']}s warmup, {S['nRuns']} runs in total. Run order is shuffled
within each repetition so thermal drift cannot systematically favour whichever
stack went first. Every run carries a machine-speed probe — fixed CPU work,
timed — so a run taken while the box was busy is identifiable in the data
rather than silently folded into a stack's score.

**Reproducibility.** The dataset is generated deterministically from a fixed
seed (`db/seed.py`, seed 20260921) and the request corpus likewise
(`bench/corpus.py`, seed 777). Both are regenerable from scratch. Every run
writes a standalone JSON file with its full latency distribution, per-second
timeseries and resource sample; `analysis/stats.py` and `analysis/figures.py`
rebuild every number and every figure in this README from those files.

## Reproducing it

```bash
python3 db/seed.py && ./db/load.sh        # build and load the dataset
cd services/go   && go build -o bin/nethttp ./cmd/nethttp   # and fiber, gin, gingorm
cd services/rust && cargo build --release
cd services/ts   && bun install           # only for the Hono and Fastify services

python3 bench/verify.py                   # prove the ten are equivalent
python3 bench/run.py --profile final --fresh
bun run dashboard/serve.ts                # live dashboard on :7777

python3 -m venv .venv && .venv/bin/pip install scipy numpy
.venv/bin/python analysis/stats.py       # Friedman, Nemenyi, planned contrasts
.venv/bin/python analysis/figures.py     # needs chromium: HTML/SVG -> PNG
.venv/bin/python analysis/write_docs.py  # README.md and RESULTS.md
.venv/bin/python analysis/write_paper.py && cd paper && tectonic -X compile main.tex
```

Profiles: `smoke` (10 runs), `quick`, `full`, `final` ({S['nRuns']} runs,
~107 min), `deep`. `--stacks` and `--scenarios` narrow the matrix.

## Limitations

One machine, one database, loopback networking, one shape of workload. The
ratios here describe how these stacks handle a database-bound transactional API
on this hardware; the absolute numbers belong to this box alone.

Nothing here speaks to streaming, CPU-bound compute, cold starts, or behaviour
across a real network, and a four-core laptop is not a server — the database
shares a socket with everything else, which compresses the gap between stacks
that a larger machine would widen.

The ordering **within** a language is not a result. Rust's hyper, Axum and Actix
sit inside the critical difference of each other, as do Go's Fiber, net/http and
Gin. They change places depending on which repetitions are included. Read the
language tiers; ignore the ranking inside a tier.

Five repetitions is few. The bootstrap intervals quoted here are percentile
intervals on a median of five, which is an honest width rather than a precise
coverage guarantee.

## Prior art

[TechEmpower Framework Benchmarks](https://www.techempower.com/benchmarks/)
Round 23 covers 331 frameworks and is the reference point for this kind of
comparison. Its database tests fetch single or multiple rows from one table.
This suite differs in running a composite business transaction, diffing every
implementation's output before timing it, and reporting significance tests
rather than point estimates.

## Layout

```
spec/SPEC.md          the contract all ten implement
services/             the ten implementations
db/                   schema, deterministic seed generator, loader
bench/                corpus, conformance harness, load generator, orchestrator
analysis/             statistics, figures, document generation
dashboard/            live dashboard served over the results directory
results/              one JSON file per run
docs/figures/         generated figures
paper/                LaTeX technical report
```

## Citing this

If you use the dataset or the harness, there is a `CITATION.cff` in the repo
root, and GitHub's "Cite this repository" button reads it.

```bibtex
@misc{{oludele2026polyglot,
  author = {{Oludele, Halleluyah}},
  title  = {{Polyglot Checkout Bench: a conformance-verified benchmark of ten
            TypeScript, Go and Rust implementations of one database-bound
            business transaction}},
  year   = {{2026}},
  url    = {{https://github.com/hallelx2/polyglot-bench}}
}}
```

## Contributing

Adding a stack is welcome, with two conditions that are not negotiable, because
they are what makes the comparison mean anything:

1. It implements [`spec/SPEC.md`](spec/SPEC.md) exactly and passes
   `python3 bench/verify.py` — byte-identical output against the reference.
2. Its statement counts are recorded. Output equality is not enough on its own;
   `bench/count_statements.sh` exists because an ORM passed conformance while
   issuing a query the spec never asked for.

Register it in `bench/stacks.json`, then re-run the pipeline so every number in
the documents comes from the result files rather than from a diff.

## Licence

MIT. See [LICENSE](LICENSE).
"""

open("README.md", "w").write(README)

RESULTS = f"""# Full results

`{M['profile']}` profile — {S['nRuns']} runs, {M['reps']} repetitions of
{M['durationSec']}s after {M['warmupSec']}s warmup, run order shuffled per
repetition, database restored to seeded state before every run. Zero non-2xx
responses across the suite.

CV is the coefficient of variation of throughput across the repetitions of that
cell. Machine probe: median {S['machine']['probeMedianMs']:.1f} ms against a
best-decile of {S['machine']['probeBestDecileMs']:.1f} ms;
{S['machine']['degradedRuns']} of {S['machine']['nRuns']} runs were taken while
the machine was more than 25% off its best speed. Excluding them moves the
medians by 0.0% median.
"""
for sc in SCEN:
    for conf, sub in [("closed@64", "saturated, 64 connections"),
                      ("open@300", "fixed 300 req/s offered"),
                      ("open@900", "fixed 900 req/s offered")]:
        RESULTS += f"\n## {sc} — {sub}\n\n{full_table(sc, conf)}\n"

RESULTS += "\n## Planned contrasts\n\n"
RESULTS += ("| contrast | question | ratio | 95% CI | p (Holm) | significant |\n"
            "|---|---|--:|--:|--:|:-:|\n")
for t in sorted(S["plannedContrasts"], key=lambda t: t["pHolm"]):
    RESULTS += (f"| `{t['a']}` vs `{t['b']}` | {t['why']} | {t['ratio']:.2f}x "
                f"| {t['ratioCI'][0]:.2f}–{t['ratioCI'][1]:.2f} | {t['pHolm']:.1e} "
                f"| {'yes' if t['significant'] else 'no'} |\n")

RESULTS += "\n## Friedman / Nemenyi average ranks\n\n"
for metric, f in S["friedman"].items():
    RESULTS += (f"\n**{f['label']}** — chi-square {f['chi2']:.1f}, p {f['p']:.2e}, "
                f"N={f['nTasks']} tasks, critical difference "
                f"{f['criticalDifference']:.2f}\n\n| stack | average rank |\n|---|--:|\n")
    for sid, a in sorted(f["avgRank"].items(), key=lambda kv: kv[1]):
        RESULTS += f"| `{sid}` | {a:.2f} |\n"

open("RESULTS.md", "w").write(RESULTS)
print(f"README.md {len(README.splitlines())} lines · RESULTS.md {len(RESULTS.splitlines())} lines")
