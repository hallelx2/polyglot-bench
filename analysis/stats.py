#!/usr/bin/env python3
"""
Statistical analysis of the polyglot benchmark.

Design follows Demsar (2006): with many treatments measured over several
tasks, significance comes from the number of TASKS, not the number of
repetitions. We therefore run the Friedman test over the 9 (workload x load
profile) tasks with Nemenyi post-hoc, and keep repetitions for uncertainty
intervals rather than for manufacturing power.

Throughput is reported for the saturated profile only, with bootstrap
intervals and no omnibus test: 3 tasks is too few for Friedman and saying so
is better than pretending otherwise.

Writes analysis/stats.json; prints a human summary.
"""
import json, glob, itertools, math
from collections import defaultdict

import numpy as np
from scipy.stats import friedmanchisquare, mannwhitneyu, rankdata

RNG = np.random.default_rng(20260922)
B = 20000  # bootstrap resamples

runs = [json.load(open(f)) for f in glob.glob('results/*.json') if 'index' not in f]
stacks = {s['id']: s for s in json.load(open('bench/stacks.json'))}
SIDS = list(stacks)
meta = json.load(open('results/index.json'))['meta']

def cfg(r):  return f"open@{r['targetRate']}" if r['mode'] == 'open' else f"closed@{r['conns']}"
def cpu(r):
    x = r['resource']
    return (x['cpuSecondsUser'] + x['cpuSecondsSys']) * 1000 / r['requests']

cell = defaultdict(list)
for r in runs:
    cell[(r['stack'], r['scenario'], cfg(r))].append(r)

SCEN = ['quote', 'checkout', 'summary']
CONF = sorted({cfg(r) for r in runs}, key=lambda c: (c.split('@')[0], int(c.split('@')[1])))
TASKS = [(sc, cf) for sc in SCEN for cf in CONF]

METRICS = {
    'p99':  (lambda r: r['latency']['p99Ms'], 'lower', 'p99 latency (ms)'),
    'p50':  (lambda r: r['latency']['p50Ms'], 'lower', 'median latency (ms)'),
    'p90':  (lambda r: r['latency']['p90Ms'], 'lower', 'p90 latency (ms)'),
    'p999': (lambda r: r['latency']['p999Ms'], 'lower', 'p99.9 latency (ms)'),
    'cpu':  (cpu,                             'lower', 'CPU ms per request'),
    'rss':  (lambda r: r['resource']['peakRssMb'], 'lower', 'peak RSS (MB)'),
    'rps':  (lambda r: r['rps'],              'higher', 'throughput (req/s)'),
}

def vals(sid, sc, cf, metric):
    return np.array([METRICS[metric][0](r) for r in cell[(sid, sc, cf)]], float)

def boot_ci(x, stat=np.median, alpha=0.05):
    """Percentile bootstrap. With n=5 this is a coarse interval; it is reported
    as an honest width, not as a precise coverage guarantee."""
    if len(x) == 0: return (math.nan, math.nan)
    idx = RNG.integers(0, len(x), size=(B, len(x)))
    d = stat(x[idx], axis=1)
    return tuple(np.percentile(d, [100*alpha/2, 100*(1-alpha/2)]))

def ratio_ci(a, b, alpha=0.05):
    """Bootstrap CI for median(a)/median(b)."""
    ia = RNG.integers(0, len(a), size=(B, len(a)))
    ib = RNG.integers(0, len(b), size=(B, len(b)))
    d = np.median(a[ia], axis=1) / np.median(b[ib], axis=1)
    return float(np.median(a)/np.median(b)), tuple(np.percentile(d, [100*alpha/2, 100*(1-alpha/2)]))

out = {'meta': meta, 'nRuns': len(runs), 'tasks': [f"{s}/{c}" for s, c in TASKS]}

# ---------------------------------------------------------------- Friedman
out['friedman'] = {}
for metric in ('p99', 'cpu', 'rss'):
    direction = METRICS[metric][1]
    M = np.array([[np.median(vals(sid, sc, cf, metric)) for sid in SIDS]
                  for sc, cf in TASKS])                      # tasks x stacks
    stat, p = friedmanchisquare(*M.T)
    # per-task ranks, 1 = best
    R = np.array([rankdata(row if direction == 'lower' else -row) for row in M])
    avg = R.mean(axis=0)
    k, N = len(SIDS), len(TASKS)
    q05 = {2:1.960,3:2.343,4:2.569,5:2.728,6:2.850,7:2.949,8:3.031,9:3.102,10:3.164}[k]
    CD = q05 * math.sqrt(k*(k+1)/(6*N))
    out['friedman'][metric] = {
        'label': METRICS[metric][2], 'chi2': float(stat), 'p': float(p),
        'nTasks': N, 'nStacks': k, 'criticalDifference': CD,
        'avgRank': {sid: float(a) for sid, a in zip(SIDS, avg)},
        'significantPairs': [[a, b] for a, b in itertools.combinations(SIDS, 2)
                             if abs(avg[SIDS.index(a)] - avg[SIDS.index(b)]) > CD],
    }

# ------------------------------------------------- planned pairwise contrasts
# Pre-specified, each answering one question. Holm-corrected within the family.
CONTRASTS = [
    ('ts-bun-only', 'ts-bun-hono',   'Zero-dependency Bun vs Hono + node-postgres'),
    ('ts-bun-only', 'ts-node-fastify','Bun vs Node, both TypeScript'),
    ('go-gin',      'go-gin-gorm',    'Cost of the ORM, router held constant'),
    ('rust-axum',   'go-fiber',       'Best Rust vs best Go'),
    ('rust-axum',   'ts-bun-only',    'Best Rust vs best TypeScript'),
]
# Throughput is normalised within each workload (divided by that workload's
# grand median over all stacks) so the three workloads' different absolute
# scales do not dominate, then pooled. Each stack contributes 5 reps x 3
# workloads = 15 independent runs — separate process starts, shuffled order,
# database reset between each. This is a blocked design: it buys power from
# the blocking, not from re-using observations.
grand = {sc: np.median(np.concatenate([vals(s2, sc, 'closed@64', 'rps') for s2 in SIDS]))
         for sc in SCEN}
def pooled(sid):
    return np.concatenate([vals(sid, sc, 'closed@64', 'rps') / grand[sc] for sc in SCEN])

tests = []
for a, b, why in CONTRASTS:
    xa, xb = pooled(a), pooled(b)
    u, p = mannwhitneyu(xa, xb, alternative='two-sided')
    ratio, ci = ratio_ci(xa, xb)
    per_scen = {}
    for sc in SCEN:
        ya, yb = vals(a, sc, 'closed@64', 'rps'), vals(b, sc, 'closed@64', 'rps')
        r, c = ratio_ci(ya, yb)
        per_scen[sc] = {'ratio': r, 'ci': list(c),
                        'medianA': float(np.median(ya)), 'medianB': float(np.median(yb))}
    tests.append({'a': a, 'b': b, 'why': why, 'metric': 'rps (normalised, pooled)',
                  'n': int(len(xa)), 'ratio': ratio, 'ratioCI': list(ci),
                  'U': float(u), 'p': float(p), 'perScenario': per_scen})

# Holm-Bonferroni
order = np.argsort([t['p'] for t in tests])
m = len(tests)
prev = 0.0
for rank, i in enumerate(order):
    adj = min(1.0, (m - rank) * tests[i]['p'])
    adj = max(adj, prev); prev = adj
    tests[i]['pHolm'] = float(adj)
    tests[i]['significant'] = bool(adj < 0.05)
out['plannedContrasts'] = tests

# ------------------------------------------------------------- cell summary
out['cells'] = {}
for sid in SIDS:
    for sc, cf in TASKS:
        rec = {}
        for metric in METRICS:
            x = vals(sid, sc, cf, metric)
            lo, hi = boot_ci(x)
            rec[metric] = {'median': float(np.median(x)), 'ci': [float(lo), float(hi)],
                           'cv': float(np.std(x)/np.mean(x)) if np.mean(x) else 0.0,
                           'n': int(len(x))}
        out['cells'][f"{sid}|{sc}|{cf}"] = rec

# ------------------------------------------------------------ machine health
probe = np.array([r['machineProbeMs'] for r in runs])
base = float(np.percentile(probe, 10))
out['machine'] = {'probeMedianMs': float(np.median(probe)), 'probeBestDecileMs': base,
                  'probeWorstMs': float(probe.max()),
                  'degradedRuns': int((probe > base*1.25).sum()), 'nRuns': len(probe)}

json.dump(out, open('analysis/stats.json', 'w'), indent=1)

# ------------------------------------------------------------------ summary
print(f"{len(runs)} runs · {len(TASKS)} tasks · {len(SIDS)} stacks\n")
for metric, f in out['friedman'].items():
    print(f"Friedman on {f['label']}: chi2={f['chi2']:.1f}, p={f['p']:.2e} "
          f"(N={f['nTasks']} tasks, k={f['nStacks']}), Nemenyi CD={f['criticalDifference']:.2f} ranks")
    for sid, a in sorted(f['avgRank'].items(), key=lambda kv: kv[1]):
        print(f"    {a:5.2f}  {sid}")
    print()
print("Planned contrasts — saturated throughput, normalised within workload and")
print("pooled (n=15 runs per stack), Mann-Whitney U, Holm-corrected over 5 tests:\n")
for t in sorted(out['plannedContrasts'], key=lambda t: t['pHolm']):
    star = "*" if t['significant'] else " "
    print(f" {star} {t['a']:15s} vs {t['b']:15s} "
          f"{t['ratio']:5.2f}x [{t['ratioCI'][0]:.2f},{t['ratioCI'][1]:.2f}]  "
          f"p={t['p']:.2e}  holm={t['pHolm']:.2e}   {t['why']}")
    for sc, d in t['perScenario'].items():
        print(f"        {sc:9s} {d['medianA']:7.0f} vs {d['medianB']:7.0f} rps  "
              f"= {d['ratio']:.2f}x [{d['ci'][0]:.2f},{d['ci'][1]:.2f}]")
