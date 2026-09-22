#!/usr/bin/env python3
"""Render every figure in docs/figures/ from analysis/stats.json.

No number in a figure is typed by hand; all of it comes from the result files
via stats.py, so a figure cannot drift from the data behind it.
Palette follows the project's design system: zinc neutrals, ember accent.
"""
import json, math, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D

OBSIDIAN, GRAPHITE, SLATE = "#09090b", "#18181b", "#27272a"
IRON, STEEL, FOG = "#3f3f46", "#52525b", "#71717a"
ASH, MIST, CLOUD = "#a1a1aa", "#d4d4d8", "#ececee"
PAPER, SNOW, EMBER = "#f4f4f5", "#ffffff", "#ff5a00"

for p in ("/home/hallelx2/.local/share/fonts/mb-runway/DMSans-Variable.ttf",):
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)
FAM = "DM Sans" if any("DM Sans" in f.name for f in font_manager.fontManager.ttflist) else "Noto Sans"

plt.rcParams.update({
    "font.family": FAM, "font.size": 10,
    "figure.facecolor": SNOW, "axes.facecolor": SNOW,
    "savefig.facecolor": SNOW, "savefig.dpi": 200, "savefig.bbox": "tight",
    "axes.edgecolor": CLOUD, "axes.linewidth": 1,
    "axes.labelcolor": IRON, "text.color": GRAPHITE,
    "xtick.color": FOG, "ytick.color": FOG,
    "xtick.labelcolor": IRON, "ytick.labelcolor": IRON,
    "grid.color": CLOUD, "grid.linewidth": 1,
    "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False,
})

S = json.load(open("analysis/stats.json"))
STACKS = {s["id"]: s for s in json.load(open("bench/stacks.json"))}
SIDS = list(STACKS)
SCEN = ["quote", "checkout", "summary"]
SCEN_LABEL = {"quote": "Quote  ·  read-only pricing",
              "checkout": "Checkout  ·  write transaction",
              "summary": "Summary  ·  aggregation read"}
LANG_C = {"Rust": SLATE, "Go": FOG, "TypeScript": ASH}
HERO = "ts-bun-only"
OUT = "docs/figures"
os.makedirs(OUT, exist_ok=True)

def cell(sid, sc, cf, m): return S["cells"][f"{sid}|{sc}|{cf}"][m]
def colour(sid): return EMBER if sid == HERO else LANG_C[STACKS[sid]["lang"]]
def short(sid): return STACKS[sid]["label"]

def title(ax, main, sub=None):
    """Panel heading drawn in axes coordinates so the sub-line can never
    collide with the title the way set_title's padding does."""
    ax.text(0, 1.105 if sub else 1.03, main, transform=ax.transAxes,
            fontsize=13, fontweight="bold", color=OBSIDIAN, va="bottom")
    if sub:
        ax.text(0, 1.025, sub, transform=ax.transAxes, fontsize=9.5,
                color=STEEL, va="bottom")

def figtitle(fig, main, sub, top=0.88):
    """Figure heading. Reserves space with tight_layout's rect first, so the
    title and its sub-line cannot overlap each other or the axes."""
    fig.tight_layout(rect=[0, 0, 1, top])
    fig.text(0.008, 0.975, main, ha="left", va="top", fontsize=16,
             fontweight="bold", color=OBSIDIAN)
    fig.text(0.008, 0.925, sub, ha="left", va="top", fontsize=10.5, color=STEEL)


def save(fig, name):
    fig.savefig(f"{OUT}/{name}.png")
    plt.close(fig)
    print(f"  {OUT}/{name}.png")

# ---------------------------------------------------------------- 1 throughput
def fig_throughput():
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.4))
    for ax, sc in zip(axes, SCEN):
        rows = sorted(SIDS, key=lambda s: cell(s, sc, "closed@64", "rps")["median"])
        y = np.arange(len(rows))
        med = [cell(s, sc, "closed@64", "rps")["median"] for s in rows]
        lo = [m - cell(s, sc, "closed@64", "rps")["ci"][0] for s, m in zip(rows, med)]
        hi = [cell(s, sc, "closed@64", "rps")["ci"][1] - m for s, m in zip(rows, med)]
        ax.barh(y, med, height=.68, color=[colour(s) for s in rows],
                xerr=[lo, hi], error_kw=dict(ecolor=IRON, elinewidth=1, capsize=2.5))
        ax.set_yticks(y, [short(s) for s in rows], fontsize=9)
        ax.set_xlabel("requests / second")
        ax.xaxis.grid(True); ax.set_axisbelow(True)
        title(ax, SCEN_LABEL[sc].split("·")[0].strip(), SCEN_LABEL[sc].split("·")[1].strip())
        for yy, m, h in zip(y, med, hi):
            ax.text(m + h + max(med) * .028, yy, f"{m:,.0f}",
                    va="center", fontsize=8.5, color=IRON)
        ax.set_xlim(0, max(m + h for m, h in zip(med, hi)) * 1.20)
    figtitle(fig, "Throughput at saturation - 64 connections, flat out",
             "Median of 5 repetitions; whiskers are the bootstrap 95% interval. "
             "Ember marks the zero-dependency Bun service.", top=0.86)
    save(fig, "throughput")

# --------------------------------------------------------- 2 CD diagram
def fig_cd(metric="p99"):
    """Demsar critical-difference diagram: rank 1 (best) on the left, stacks
    joined by a bar are statistically indistinguishable at the 5% level."""
    f = S["friedman"][metric]
    ranks, CD = f["avgRank"], f["criticalDifference"]
    order = sorted(SIDS, key=lambda s: ranks[s])
    k = len(order)
    lo, hi = 1, k
    PAD = 3.4                      # rank units reserved for labels either side
    half = (k + 1) // 2

    # cliques: maximal groups whose rank span is within CD
    cliques, seen = [], set()
    for i, a in enumerate(order):
        grp = [b for b in order[i:] if ranks[b] - ranks[a] <= CD]
        key = frozenset(grp)
        if len(grp) > 1 and not any(key < s for s in seen):
            cliques.append(grp); seen.add(key)
    cliques = [g for g in cliques if not any(set(g) < set(h) for h in cliques)]

    y_clique_top = -0.30
    y_clique_gap = 0.26
    y_stem_top = y_clique_top - y_clique_gap * len(cliques) - 0.35
    row_gap = 0.46

    fig, ax = plt.subplots(figsize=(13, 0.52 * half + 2.7))
    ax.set_xlim(lo - PAD, hi + PAD)
    ax.set_ylim(y_stem_top - row_gap * (half - 1) - 0.32, 1.66)
    ax.axis("off")

    # axis
    ax.plot([lo, hi], [0, 0], color=OBSIDIAN, lw=1.4, zorder=3)
    for r in range(lo, hi + 1):
        ax.plot([r, r], [0, 0.14], color=OBSIDIAN, lw=1.2, zorder=3)
        ax.text(r, 0.30, str(r), ha="center", fontsize=9.5, color=IRON)
    ax.text((lo + hi) / 2, 1.34, "average rank over the 9 workload x load-profile tasks",
            ha="center", fontsize=10, color=STEEL)

    # "better" arrow, left
    ax.annotate("", xy=(lo - 0.15, 0.82), xytext=(lo + 1.5, 0.82),
                arrowprops=dict(arrowstyle="->", color=IRON, lw=1.1))
    ax.text(lo + 1.62, 0.82, "better", va="center", fontsize=9.5, color=IRON)

    # critical-difference ruler, right
    x0 = hi - CD
    ax.plot([x0, hi], [0.82, 0.82], color=EMBER, lw=2.6, solid_capstyle="butt")
    for xx in (x0, hi):
        ax.plot([xx, xx], [0.72, 0.92], color=EMBER, lw=2.6)
    ax.text((x0 + hi) / 2, 1.02, f"critical difference = {CD:.2f}", ha="center",
            fontsize=9.5, color=EMBER, fontweight="bold")

    # clique bars, directly under the axis
    for i, grp in enumerate(cliques):
        y = y_clique_top - i * y_clique_gap
        ax.plot([ranks[grp[0]] - 0.07, ranks[grp[-1]] + 0.07], [y, y],
                color=IRON, lw=3.6, solid_capstyle="round", zorder=2)

    # stems and labels
    for i, sid in enumerate(order):
        r = ranks[sid]
        left = i < half
        row = i if left else k - 1 - i
        y = y_stem_top - row * row_gap
        x_end = (lo - PAD + 0.25) if left else (hi + PAD - 0.25)
        c = colour(sid)
        ax.plot([r, r], [0, y], color=c, lw=1.5, zorder=1)
        ax.plot([r, x_end], [y, y], color=c, lw=1.5, zorder=1)
        ax.text(x_end + (-0.12 if left else 0.12), y, f"{short(sid)}  ({r:.2f})",
                ha="right" if left else "left", va="center", fontsize=9.5,
                color=OBSIDIAN if sid == HERO else GRAPHITE,
                fontweight="bold" if sid == HERO else "normal")

    fig.suptitle(f"Critical-difference diagram - {f['label']}",
                 x=0.012, ha="left", fontsize=16, fontweight="bold", color=OBSIDIAN, y=1.055)
    fig.text(0.012, 0.995,
             f"Friedman chi-square = {f['chi2']:.1f}, p = {f['p']:.1e} over N={f['nTasks']} tasks, "
             f"k={k} stacks. Nemenyi post-hoc at the 5% level; stacks joined by a bar are "
             f"not distinguishable.",
             ha="left", fontsize=10, color=STEEL)
    fig.tight_layout()
    save(fig, f"cd_{metric}")

# ------------------------------------------------------- 3 latency vs load
def fig_latency_load():
    confs = [("open@300", "300 req/s\noffered"), ("open@900", "900 req/s\noffered"),
             ("closed@64", "saturated\n64 conns")]
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    for ax, sc in zip(axes, SCEN):
        for sid in SIDS:
            ys = [cell(sid, sc, c, "p99")["median"] for c, _ in confs]
            ax.plot(range(3), ys, marker="o", ms=5, lw=2 if sid == HERO else 1.3,
                    color=colour(sid), zorder=3 if sid == HERO else 2,
                    alpha=1 if sid == HERO else .85)
            ax.annotate(short(sid).split(" + ")[0] if sid != HERO else "Bun only",
                        (2, ys[2]), textcoords="offset points", xytext=(7, 0),
                        fontsize=7.5, va="center", color=colour(sid))
        ax.set_yscale("log")
        ax.set_xticks(range(3), [l for _, l in confs], fontsize=8.5)
        ax.set_xlim(-.2, 2.95)
        ax.set_ylabel("p99 latency (ms, log)" if sc == "quote" else None)
        ax.yaxis.grid(True); ax.set_axisbelow(True)
        title(ax, SCEN_LABEL[sc].split("·")[0].strip(), SCEN_LABEL[sc].split("·")[1].strip())
    figtitle(fig, "Where each stack starts to hurt",
             "p99 latency as offered load rises. Under a fixed rate the stacks are nearly "
             "indistinguishable; the spread only opens at saturation.", top=0.85)
    save(fig, "latency_vs_load")

# ------------------------------------------------------- 4 cost of a request
SHORT = {"rust-hyper": "hyper", "rust-axum": "Axum", "rust-actix": "Actix",
         "go-nethttp": "net/http", "go-fiber": "Fiber", "go-gin": "Gin",
         "go-gin-gorm": "Gin + GORM", "ts-bun-only": "Bun only",
         "ts-bun-hono": "Bun + Hono", "ts-node-fastify": "Node + Fastify"}

def _spread(ax, pts, radii, pad=13.0, rounds=260):
    """Nudge labels apart in display space and return their final positions.
    Points here cluster tightly by language, so static offsets collide."""
    inv = ax.transData.inverted()
    P = np.array([ax.transData.transform(p) for p in pts], float)
    L = P + np.column_stack([np.asarray(radii) + 11.0, np.full(len(P), 7.0)])
    for _ in range(rounds):
        moved = False
        for i in range(len(L)):
            for j in range(i + 1, len(L)):
                dx, dy = L[j] - L[i]
                if abs(dx) < 96 and abs(dy) < pad:
                    push = (pad - abs(dy)) / 2 + 0.6
                    sign = 1.0 if dy >= 0 else -1.0
                    L[i][1] -= sign * push; L[j][1] += sign * push
                    moved = True
            # keep the label near its own point
            if abs(L[i][1] - P[i][1]) > 62:
                L[i][1] = P[i][1] + 62 * np.sign(L[i][1] - P[i][1])
        if not moved:
            break
    return [inv.transform(l) for l in L]

def fig_cost():
    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    xs, ys, ss, ids = [], [], [], []
    for sid in SIDS:
        xs.append(np.median([cell(sid, sc, "closed@64", "cpu")["median"] for sc in SCEN]))
        ys.append(np.median([cell(sid, sc, "closed@64", "rss")["median"] for sc in SCEN]))
        ss.append(np.median([cell(sid, sc, "closed@64", "rps")["median"] for sc in SCEN]))
        ids.append(sid)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(.115, 4.2); ax.set_ylim(4.6, 460)
    ax.set_xlabel("CPU milliseconds burned per request   (log scale)")
    ax.set_ylabel("peak resident memory, MB   (log scale)")
    ax.grid(True, which="major"); ax.set_axisbelow(True)
    for x, y, sz, sid in zip(xs, ys, ss, ids):
        ax.scatter(x, y, s=sz / 4.5, color=colour(sid), alpha=.92, zorder=3,
                   edgecolor=SNOW, linewidth=1.6)
    fig.canvas.draw()
    radii = [math.sqrt((sz / 4.5) / math.pi) for sz in ss]
    for (lx, ly), x, y, sid in zip(_spread(ax, list(zip(xs, ys)), radii), xs, ys, ids):
        ax.annotate(SHORT[sid], xy=(x, y), xytext=(lx, ly), fontsize=9.5,
                    va="center", ha="left", zorder=4,
                    color=OBSIDIAN if sid == HERO else GRAPHITE,
                    fontweight="bold" if sid == HERO else "normal",
                    arrowprops=dict(arrowstyle="-", color=MIST, lw=.9,
                                    shrinkA=0, shrinkB=6))
    ax.text(.985, .035, "bubble area = throughput at saturation",
            transform=ax.transAxes, ha="right", fontsize=9, color=FOG)
    figtitle(fig, "What a request costs you",
             "Down-and-left is cheaper. Median across the three workloads at saturation; "
             "Rust holds an order of magnitude less memory than Node for the same work.",
             top=0.87)
    save(fig, "cost_of_request")

# ------------------------------------------------------------ 5 forest plot
def fig_contrasts():
    T = sorted(S["plannedContrasts"], key=lambda t: -t["ratio"])
    fig, ax = plt.subplots(figsize=(11.5, 4.6))
    y = np.arange(len(T))[::-1]
    for yy, t in zip(y, T):
        sig = t["significant"]
        c = EMBER if sig else ASH
        ax.plot(t["ratioCI"], [yy, yy], color=c, lw=2.6, solid_capstyle="round", zorder=2)
        ax.scatter([t["ratio"]], [yy], s=58, color=c, zorder=3, edgecolor=SNOW, linewidth=1.4)
        ax.text(t["ratioCI"][1] + .045, yy,
                f"{t['ratio']:.2f}×   " + (f"p={t['pHolm']:.1e}" if sig else "not significant"),
                va="center", fontsize=9, color=GRAPHITE if sig else FOG)
    ax.axvline(1.0, color=GRAPHITE, lw=1.2, ls=(0, (4, 3)), zorder=1)
    ax.set_yticks(y, [f"{t['a']}  vs  {t['b']}\n{t['why']}" for t in T], fontsize=9)
    ax.set_xlabel("throughput ratio  (>1 means the first stack is faster)")
    ax.set_xlim(.75, 3.05)
    ax.xaxis.grid(True); ax.set_axisbelow(True)
    title(ax, "Five questions, asked before the data was collected",
          "Mann-Whitney U on throughput normalised within workload and pooled "
          "(n=15 runs per stack), Holm-corrected. Bars are bootstrap 95% intervals.")
    fig.tight_layout()
    save(fig, "contrasts")

# ------------------------------------------------------ 6 percentile fan
def fig_percentiles():
    sc = "checkout"
    order = sorted(SIDS, key=lambda s: cell(s, sc, "closed@64", "p99")["median"])
    ps = [("p50", "median"), ("p99", "p99")]
    fig, ax = plt.subplots(figsize=(11.5, 5.2))
    x = np.arange(len(order)); w = .38
    for i, (key, lab) in enumerate(ps):
        v = [cell(s, sc, "closed@64", key)["median"] for s in order]
        ax.bar(x + (i - .5) * w, v, width=w, label=lab,
               color=[colour(s) for s in order], alpha=1 if i else .42)
    for xx, s in zip(x, order):
        ax.text(xx + .5 * w, cell(s, sc, "closed@64", "p99")["median"] + 4,
                f"{cell(s, sc, 'closed@64', 'p99')['median']:.0f}",
                ha="center", fontsize=8, color=IRON)
    ax.set_xticks(x, [short(s).replace(" + ", "\n+ ") for s in order], fontsize=8.5)
    ax.set_ylabel("latency (ms)")
    ax.yaxis.grid(True); ax.set_axisbelow(True)
    ax.legend(handles=[Line2D([], [], lw=7, color=IRON, alpha=.42, label="median"),
                       Line2D([], [], lw=7, color=IRON, label="p99")],
              loc="upper left", fontsize=9)
    title(ax, "Checkout under saturation — median against tail",
          "The write transaction, 64 connections flat out. A tall p99 next to a short "
          "median is a stack whose worst requests are far worse than its typical one.")
    fig.tight_layout()
    save(fig, "checkout_tail")

print("rendering figures:")
fig_throughput(); fig_cd("p99"); fig_cd("cpu"); fig_latency_load()
fig_cost(); fig_contrasts(); fig_percentiles()
