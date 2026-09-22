#!/usr/bin/env python3
"""Render every figure as a designed page: HTML and CSS for layout and
typography, inline SVG for the data marks, headless Chromium for the raster.

Matplotlib gives you correct axes and fights you on composition. Since these
figures are read as slides — a heading, a claim, one chart, a source line —
the layout work is the larger half, so it is done in CSS on the same tokens as
the dashboard. Coordinates for the marks are computed here from stats.json, so
no number is drawn by hand.
"""
import json, math, os, shutil, subprocess, tempfile

S = json.load(open("analysis/stats.json"))
STACKS = {s["id"]: s for s in json.load(open("bench/stacks.json"))}
SIDS = list(STACKS)
SCEN = ["quote", "checkout", "summary"]
SCEN_HEAD = {"quote": ("Quote", "read-only pricing"),
             "checkout": ("Checkout", "write transaction"),
             "summary": ("Summary", "aggregation read")}
HERO = "ts-bun-only"
OUT, HTML = "docs/figures", "docs/figures/_html"
os.makedirs(HTML, exist_ok=True)

C = lambda sid, sc, cf, m: S["cells"][f"{sid}|{sc}|{cf}"][m]
lab = lambda sid: STACKS[sid]["label"]
SHORT = {"rust-hyper": "hyper", "rust-axum": "Axum", "rust-actix": "Actix",
         "go-nethttp": "net/http", "go-fiber": "Fiber", "go-gin": "Gin",
         "go-gin-gorm": "Gin + GORM", "ts-bun-only": "Bun only",
         "ts-bun-hono": "Bun + Hono", "ts-node-fastify": "Node + Fastify"}
LANG = {"Rust": "var(--slate)", "Go": "var(--fog)", "TypeScript": "var(--ash)"}
col = lambda sid: "var(--ember)" if sid == HERO else LANG[STACKS[sid]["lang"]]
fmt = lambda v, d=0: f"{v:,.{d}f}"

CSS = """
:root{
  --obsidian:#09090b; --graphite:#18181b; --slate:#27272a; --iron:#3f3f46;
  --steel:#52525b; --fog:#71717a; --ash:#a1a1aa; --mist:#d4d4d8;
  --cloud:#ececee; --paper:#f4f4f5; --snow:#ffffff; --ember:#ff5a00;
}
*{box-sizing:border-box;margin:0;padding:0}
body{width:1280px;height:720px;background:var(--paper);
  font-family:"DM Sans",system-ui,sans-serif;color:var(--graphite);
  -webkit-font-smoothing:antialiased;display:flex;flex-direction:column;
  padding:44px 48px 34px}
.head h1{font-size:34px;font-weight:600;letter-spacing:-.02em;color:var(--obsidian);
  line-height:1.15}
.head p{font-size:15px;color:var(--steel);margin-top:10px;max-width:96ch;line-height:1.5}
.rule{width:56px;height:4px;background:var(--ember);border-radius:99px;margin:20px 0 26px}
.body{flex:1;display:flex;gap:20px;min-height:0}
.card{background:var(--snow);border:1px solid var(--cloud);border-radius:28px;
  padding:26px 28px 22px;flex:1;display:flex;flex-direction:column;min-width:0}
.card h2{font-size:19px;font-weight:600;color:var(--obsidian);letter-spacing:-.01em}
.card h2 em{font-style:normal;font-size:13px;font-weight:400;color:var(--fog);
  margin-left:10px}
.card .plot{flex:1;margin-top:18px;min-height:0;display:flex;flex-direction:column;
  justify-content:center}
.foot{font-size:12px;color:var(--fog);margin-top:22px;line-height:1.5}
.foot b{color:var(--steel);font-weight:500}
/* horizontal bar rows */
.rows{display:flex;flex-direction:column;gap:13px}
.row{display:grid;grid-template-columns:124px 1fr 66px;align-items:center;gap:18px}
.row .nm{font-size:12.5px;color:var(--iron);text-align:right;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.row.hero .nm{color:var(--obsidian);font-weight:600}
.track{height:23px;background:var(--paper);border-radius:7px;position:relative}
.track i{position:absolute;left:0;top:0;bottom:0;border-radius:6px}
.track u{position:absolute;top:4px;bottom:4px;width:1.5px;background:var(--iron);
  opacity:.5}
.row .vl{font-size:13px;font-variant-numeric:tabular-nums;color:var(--iron);
  text-align:right}
.row.hero .vl{color:var(--obsidian);font-weight:600}
.legend{display:flex;gap:20px;flex-wrap:wrap;margin-top:18px}
.legend span{font-size:12px;color:var(--steel);display:flex;align-items:center;gap:7px}
.legend i{width:11px;height:11px;border-radius:3px;display:block}
text{font-family:"DM Sans",sans-serif}
.tall .rows{gap:19px}
.tall .track{height:30px;border-radius:9px}
.over{position:absolute;right:9px;top:50%;transform:translateY(-50%);
  font-size:12px;color:var(--steel);font-weight:600}
"""

def page(title, sub, body, foot):
    return (f"<meta charset='utf-8'><style>{CSS}</style>"
            f"<div class='head'><h1>{title}</h1><p>{sub}</p></div>"
            f"<div class='rule'></div><div class='body'>{body}</div>"
            f"<div class='foot'>{foot}</div>")

def render(name, html):
    path = os.path.join(HTML, name + ".html")
    open(path, "w").write(html)
    png = os.path.join(OUT, name + ".png")
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run(["chromium", "--headless", "--disable-gpu", "--no-sandbox",
                        "--hide-scrollbars", "--force-device-scale-factor=2",
                        f"--user-data-dir={prof}", "--window-size=1280,720",
                        f"--screenshot={png}", os.path.abspath(path)],
                       check=True, capture_output=True, timeout=180)
    print(f"  {png}")

# ---------------------------------------------------------------- helpers
def bar_rows(rows, value, dec=0, whisk=None, maxv=None):
    # scale to the widest upper interval so no whisker lands on the value column
    mx = maxv or max((whisk(r)[1] if whisk else value(r)) for r in rows)
    out = []
    for sid in rows:
        v = value(sid)
        w = max(1.2, v / mx * 100)
        marks = ""
        if whisk:
            a, b = whisk(sid)
            marks = f"<u style='left:{a/mx*100:.2f}%'></u><u style='left:{b/mx*100:.2f}%'></u>"
        hero = " hero" if sid == HERO else ""
        out.append(
            f"<div class='row{hero}'><span class='nm'>{SHORT[sid]}</span>"
            f"<span class='track'><i style='width:{w:.2f}%;background:{col(sid)}'></i>{marks}</span>"
            f"<span class='vl'>{fmt(v, dec)}</span></div>")
    return "<div class='rows'>" + "".join(out) + "</div>"

def svg_open(w, h):
    return [f"<svg viewBox='0 0 {w} {h}' width='100%' height='100%' "
            f"preserveAspectRatio='xMidYMid meet'>"]

def logmap(v, lo, hi, a, b):
    return a + (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * (b - a)

# ------------------------------------------------------------- 1 throughput
def f_throughput():
    cards = []
    for sc in SCEN:
        rows = sorted(SIDS, key=lambda s: -C(s, sc, "closed@64", "rps")["median"])
        h, sub = SCEN_HEAD[sc]
        cards.append(
            f"<div class='card'><h2>{h}<em>{sub}</em></h2><div class='plot'>"
            + bar_rows(rows, lambda s: C(s, sc, "closed@64", "rps")["median"],
                       whisk=lambda s: tuple(C(s, sc, "closed@64", "rps")["ci"]))
            + "</div></div>")
    render("throughput", page(
        "Throughput at saturation",
        "64 connections, sending as fast as each service answers. Requests per second, "
        "median of five repetitions; the ticks on each bar are the bootstrap 95% interval.",
        "".join(cards),
        "<b>Ember</b> marks the zero-dependency Bun service. "
        "Rust in dark, Go in mid grey, TypeScript in light grey."))

# ----------------------------------------------------------- 2 CD diagram
def f_cd(metric, title, sub):
    """Demsar critical-difference diagram. Height is derived from the content
    so no row can be clipped, and each label is anchored away from the plot so
    it cannot run off the canvas."""
    f = S["friedman"][metric]
    ranks, CD = f["avgRank"], f["criticalDifference"]
    order = sorted(SIDS, key=lambda s: ranks[s])
    k = len(order)

    LBL, W, AX_Y = 292, 1368, 96
    ax0, ax1 = LBL + 34, W - LBL - 34
    x = lambda r: ax0 + (r - 1) / (k - 1) * (ax1 - ax0)

    cliques, seen = [], set()
    for i, a_ in enumerate(order):
        g = [b_ for b_ in order[i:] if ranks[b_] - ranks[a_] <= CD]
        if len(g) > 1 and not any(frozenset(g) < st for st in seen):
            cliques.append(g); seen.add(frozenset(g))
    cliques = [g for g in cliques if not any(set(g) < set(h) for h in cliques)]

    stem_top = AX_Y + 26 + len(cliques) * 15
    half = (k + 1) // 2
    RGAP = 48
    H = stem_top + 26 + (half - 1) * RGAP + 34

    s = svg_open(W, H)
    s.append(f"<line x1='{ax0}' y1='{AX_Y}' x2='{ax1}' y2='{AX_Y}' "
             f"stroke='#09090b' stroke-width='1.6'/>")
    for r in range(1, k + 1):
        s.append(f"<line x1='{x(r):.1f}' y1='{AX_Y}' x2='{x(r):.1f}' y2='{AX_Y-9}' "
                 f"stroke='#09090b' stroke-width='1.4'/>"
                 f"<text x='{x(r):.1f}' y='{AX_Y-19}' text-anchor='middle' font-size='14.5' "
                 f"fill='#3f3f46'>{r}</text>")
    cx0, cx1 = x(k - CD), x(k)
    s.append(f"<line x1='{cx0:.1f}' y1='{AX_Y-52}' x2='{cx1:.1f}' y2='{AX_Y-52}' "
             f"stroke='#ff5a00' stroke-width='3'/>"
             f"<line x1='{cx0:.1f}' y1='{AX_Y-59}' x2='{cx0:.1f}' y2='{AX_Y-45}' stroke='#ff5a00' stroke-width='3'/>"
             f"<line x1='{cx1:.1f}' y1='{AX_Y-59}' x2='{cx1:.1f}' y2='{AX_Y-45}' stroke='#ff5a00' stroke-width='3'/>"
             f"<text x='{(cx0+cx1)/2:.1f}' y='{AX_Y-68}' text-anchor='middle' font-size='14' "
             f"font-weight='600' fill='#ff5a00'>critical difference {CD:.2f}</text>")
    s.append(f"<text x='{ax0}' y='{AX_Y-68}' font-size='13.5' fill='#71717a'>"
             f"rank 1 = best</text>")

    for i, g in enumerate(cliques):
        y = AX_Y + 17 + i * 15
        s.append(f"<line x1='{x(ranks[g[0]])-4:.1f}' y1='{y}' x2='{x(ranks[g[-1]])+4:.1f}' "
                 f"y2='{y}' stroke='#3f3f46' stroke-width='5.5' stroke-linecap='round'/>")

    for i, sid in enumerate(order):
        left = i < half
        row = i if left else k - 1 - i
        y = stem_top + 26 + row * RGAP
        elbow = LBL if left else W - LBL
        tx = LBL - 16 if left else W - LBL + 16
        c = ("#ff5a00" if sid == HERO else
             "#27272a" if STACKS[sid]["lang"] == "Rust" else
             "#71717a" if STACKS[sid]["lang"] == "Go" else "#b4b4bb")
        s.append(f"<path d='M{x(ranks[sid]):.1f},{AX_Y} V{y} H{elbow}' fill='none' "
                 f"stroke='{c}' stroke-width='1.8'/>")
        s.append(f"<text x='{tx}' y='{y+5}' font-size='15' "
                 f"text-anchor='{'end' if left else 'start'}' "
                 f"fill='{'#09090b' if sid == HERO else '#18181b'}' "
                 f"font-weight='{600 if sid == HERO else 400}'>{lab(sid)}"
                 f"<tspan fill='#71717a' font-weight='400'>  {ranks[sid]:.2f}</tspan></text>")
    s.append("</svg>")
    render(f"cd_{metric}", page(
        title, sub,
        f"<div class='card'><div class='plot'>{''.join(s)}</div></div>",
        f"Friedman chi-square <b>{f['chi2']:.1f}</b>, p <b>{f['p']:.1e}</b> over "
        f"N={f['nTasks']} tasks and k={k} stacks. Nemenyi post-hoc at the 5% level: "
        f"stacks joined by a grey bar are <b>not distinguishable</b>."))

# ------------------------------------------------------ 3 latency vs load
def spread_labels(items, top, bottom, gap=16):
    """items: list of (y, payload). Returns the same list with y nudged so no
    two labels sit closer than `gap`, kept inside [top, bottom]."""
    items = sorted(items, key=lambda t: t[0])
    ys = [y for y, _ in items]
    for i in range(1, len(ys)):
        if ys[i] - ys[i - 1] < gap:
            ys[i] = ys[i - 1] + gap
    overflow = ys[-1] - bottom
    if overflow > 0:
        ys = [y - overflow for y in ys]
        for i in range(len(ys) - 2, -1, -1):
            if ys[i + 1] - ys[i] < gap:
                ys[i] = ys[i + 1] - gap
        ys = [max(top, y) for y in ys]
    return [(y, p) for y, (_, p) in zip(ys, items)]


def f_latency_load():
    confs = [("open@300", "300/s"), ("open@900", "900/s"), ("closed@64", "saturated")]
    cards = []
    for sc in SCEN:
        vals = [[C(s, sc, c, "p99")["median"] for c, _ in confs] for s in SIDS]
        lo = max(0.4, min(min(v) for v in vals) * 0.8)
        hi = max(max(v) for v in vals) * 1.25
        W, H, L, R, T, B = 470, 520, 56, 112, 24, 46
        lgh = math.log10(hi) - math.log10(lo)
        py = lambda v: H - B - (math.log10(v) - math.log10(lo)) / lgh * (H - B - T)
        px = lambda i: L + i * (W - R - L) / 2
        s = svg_open(W, H)
        for d in range(int(math.floor(math.log10(lo))), int(math.ceil(math.log10(hi))) + 1):
            for m in (1, 2, 5):
                v = m * 10 ** d
                if not lo <= v <= hi:
                    continue
                s.append(f"<line x1='{L}' y1='{py(v):.1f}' x2='{W-R}' y2='{py(v):.1f}' "
                         f"stroke='#ececee' stroke-width='1'/>"
                         f"<text x='{L-9}' y='{py(v)+4:.1f}' text-anchor='end' "
                         f"font-size='12' fill='#71717a'>{v:g}</text>")
        for i, (_, t) in enumerate(confs):
            s.append(f"<text x='{px(i):.1f}' y='{H-B+24}' text-anchor='middle' "
                     f"font-size='12.5' fill='#3f3f46'>{t}</text>")
        labels = []
        for sid, vv in zip(SIDS, vals):
            c = ("#ff5a00" if sid == HERO else
                 "#27272a" if STACKS[sid]["lang"] == "Rust" else
                 "#71717a" if STACKS[sid]["lang"] == "Go" else "#c0c0c6")
            d = " ".join(f"{'M' if i==0 else 'L'}{px(i):.1f},{py(v):.1f}"
                         for i, v in enumerate(vv))
            s.append(f"<path d='{d}' fill='none' stroke='{c}' "
                     f"stroke-width='{3 if sid == HERO else 1.7}' stroke-linejoin='round'/>")
            for i, v in enumerate(vv):
                s.append(f"<circle cx='{px(i):.1f}' cy='{py(v):.1f}' "
                         f"r='{4 if sid == HERO else 2.8}' fill='{c}'/>")
            labels.append((py(vv[2]), (sid, c, py(vv[2]))))
        for y, (sid, c, y0) in spread_labels(labels, T + 6, H - B - 6):
            s.append(f"<line x1='{px(2)+6:.1f}' y1='{y0:.1f}' x2='{px(2)+16:.1f}' "
                     f"y2='{y:.1f}' stroke='#e2e2e5' stroke-width='1'/>"
                     f"<text x='{px(2)+20:.1f}' y='{y+4:.1f}' font-size='12' fill='{c}' "
                     f"font-weight='{600 if sid == HERO else 400}'>{SHORT[sid]}</text>")
        s.append("</svg>")
        h, sub = SCEN_HEAD[sc]
        cards.append(f"<div class='card'><h2>{h}<em>{sub}</em></h2>"
                     f"<div class='plot'>{''.join(s)}</div></div>")
    render("latency_vs_load", page(
        "Where each stack starts to hurt",
        "p99 latency, milliseconds on a log scale, as offered load rises from a fixed "
        "300 requests per second to as fast as the service will go.",
        "".join(cards),
        "Under a fixed rate the ten stacks sit within a millisecond of one another. The "
        "spread only opens once a stack is pushed past what it can serve \u2014 on checkout, "
        "900 requests a second is already past that line for most of them."))

# ----------------------------------------------------------- 4 cost panels
def f_cost():
    """Two sorted panels rather than a scatter. The Rust points sit almost on
    top of one another in CPU-memory space, so any labelled scatter of them
    collides; sorted bars say the same thing and stay legible."""
    med = lambda sid, m: sorted(C(sid, sc, "closed@64", m)["median"] for sc in SCEN)[1]
    cpu_order = sorted(SIDS, key=lambda s: med(s, "cpu"))
    rss_order = sorted(SIDS, key=lambda s: med(s, "rss"))
    cards = (
        "<div class='card'><h2>CPU per request<em>milliseconds burned</em></h2>"
        f"<div class='plot'>{bar_rows(cpu_order, lambda s: med(s,'cpu'), dec=3)}</div></div>"
        "<div class='card'><h2>Memory held<em>peak resident, MB</em></h2>"
        f"<div class='plot'>{bar_rows(rss_order, lambda s: med(s,'rss'), dec=0)}</div></div>")
    ratio = med("ts-node-fastify", "rss") / med("rust-hyper", "rss")
    render("cost_of_request", page(
        "What a request costs you",
        "Two different bills for the same work, at saturation. Shorter is cheaper; "
        "median across the three workloads.",
        cards,
        f"The two orderings are not the same. Node holds <b>{ratio:.0f}x</b> the memory "
        f"of Rust, and the ORM costs more CPU per request than any runtime choice on "
        f"the board."))

# --------------------------------------------------------- 5 forest plot
def f_contrasts():
    T = sorted(S["plannedContrasts"], key=lambda t: -t["ratio"])
    W, H, L, R, T_, B = 1120, 360, 340, 210, 24, 46
    xlo, xhi = .8, 2.75
    X = lambda v: L + (v - xlo) / (xhi - xlo) * (W - R - L)
    s = svg_open(W, H)
    for v in (1.0, 1.5, 2.0, 2.5):
        dash = " stroke-dasharray='5 4'" if v == 1 else ""
        stroke = "#18181b" if v == 1 else "#ececee"
        sw = 1.6 if v == 1 else 1
        s.append(f"<line x1='{X(v):.1f}' y1='{T_}' x2='{X(v):.1f}' y2='{H-B}' "
                 f"stroke='{stroke}' stroke-width='{sw}'{dash}/>"
                 f"<text x='{X(v):.1f}' y='{H-B+22}' text-anchor='middle' font-size='12' "
                 f"fill='#71717a'>{v:g}x</text>")
    gap = (H - B - T_ - 30) / (len(T) - 1)
    for i, t in enumerate(T):
        y = T_ + 22 + i * gap
        sig = t["significant"]
        c = "#ff5a00" if sig else "#a1a1aa"
        s.append(f"<line x1='{X(t['ratioCI'][0]):.1f}' y1='{y:.1f}' "
                 f"x2='{X(t['ratioCI'][1]):.1f}' y2='{y:.1f}' stroke='{c}' "
                 f"stroke-width='4' stroke-linecap='round'/>"
                 f"<circle cx='{X(t['ratio']):.1f}' cy='{y:.1f}' r='7' fill='{c}' "
                 f"stroke='#ffffff' stroke-width='2'/>")
        s.append(f"<text x='{L-22}' y='{y-1:.1f}' text-anchor='end' font-size='14.5' "
                 f"fill='#09090b' font-weight='500'>{t['a']} vs {t['b']}</text>"
                 f"<text x='{L-22}' y='{y+16:.1f}' text-anchor='end' font-size='12' "
                 f"fill='#71717a'>{t['why']}</text>")
        note = f"p = {t['pHolm']:.0e}" if sig else "not significant"
        s.append(f"<text x='{W-R+18}' y='{y-1:.1f}' font-size='15' fill='#09090b' "
                 f"font-weight='600'>{t['ratio']:.2f}x</text>"
                 f"<text x='{W-R+18}' y='{y+16:.1f}' font-size='12' "
                 f"fill='{'#3f3f46' if sig else '#a1a1aa'}'>{note}</text>")
    s.append("</svg>")
    render("contrasts", page(
        "Five questions, asked before the data was collected",
        "Throughput ratio at saturation. A bar clear of the dashed line is a difference "
        "the data supports; a bar crossing it is not.",
        f"<div class='card'><div class='plot'>{''.join(s)}</div></div>",
        "Mann-Whitney U on throughput normalised within workload and pooled "
        "(<b>n = 15 runs per stack</b>), Holm-corrected across the five. "
        "Bars are bootstrap 95% intervals."))

# ------------------------------------------------------ 6 checkout tail
def f_tail():
    """GORM's p99 is seven times the next worst, so scaling to it would flatten
    the other nine. Bars scale to the second-longest tail and anything past it
    is clamped and marked, which keeps both comparisons readable."""
    sc = "checkout"
    order = sorted(SIDS, key=lambda s: C(s, sc, "closed@64", "p99")["median"])
    p99s = sorted((C(s, sc, "closed@64", "p99")["median"] for s in SIDS), reverse=True)
    mx = p99s[1] * 1.06
    rows = []
    for sid in order:
        p50 = C(sid, sc, "closed@64", "p50")["median"]
        p99 = C(sid, sc, "closed@64", "p99")["median"]
        clipped = p99 > mx
        w99 = min(100.0, p99 / mx * 100)
        hero = " hero" if sid == HERO else ""
        over = "<span class='over'>off the scale &#9654;</span>" if clipped else ""
        rows.append(
            f"<div class='row{hero}'><span class='nm'>{SHORT[sid]}</span>"
            f"<span class='track'>"
            f"<i style='width:{w99:.1f}%;background:{col(sid)};opacity:.3'></i>"
            f"<i style='width:{p50/mx*100:.1f}%;background:{col(sid)}'></i>{over}</span>"
            f"<span class='vl'>{fmt(p99,0)}</span></div>")
    legend = ("<div class='legend'>"
              "<span><i style='background:var(--iron)'></i>median request</span>"
              "<span><i style='background:var(--iron);opacity:.3'></i>99th percentile</span>"
              "</div>")
    gorm99 = C("go-gin-gorm", sc, "closed@64", "p99")["median"]
    gorm50 = C("go-gin-gorm", sc, "closed@64", "p50")["median"]
    render("checkout_tail", page(
        "Checkout under saturation: median against tail",
        "The write transaction with 64 connections flat out. The solid bar is the median "
        "request, the pale bar behind it the 99th percentile. Milliseconds.",
        f"<div class='card tall'><div class='plot'>{''.join(rows)}{legend}</div></div>",
        f"A long pale bar behind a short solid one is a stack whose worst requests are far "
        f"worse than its typical one. Bars are scaled to the second-longest tail: GORM runs "
        f"to <b>{gorm99:.0f} ms</b> at p99 against a <b>{gorm50:.0f} ms</b> median, which "
        f"would flatten every other bar on the slide."))

if not shutil.which("chromium"):
    raise SystemExit("chromium is required to render the figures")
print("rendering figures:")
f_throughput()
f_cd("p99", "Which differences in tail latency are real",
     "Average rank across the nine workload and load-profile tasks, one line per stack. "
     "Rank 1 is the lowest p99.")
f_cd("cpu", "Which differences in CPU cost are real",
     "Average rank across the nine tasks by CPU milliseconds consumed per request. "
     "Rank 1 is the cheapest.")
f_latency_load(); f_cost(); f_contrasts(); f_tail()
