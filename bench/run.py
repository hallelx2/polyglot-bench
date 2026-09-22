#!/usr/bin/env python3
"""Benchmark orchestrator.

Runs (stack x scenario x load-config x repetition), one service at a time,
each pinned to its own cpuset, with the database reset to seeded state after
every write run. Run order is shuffled within each repetition so thermal drift
and background noise cannot favour whichever stack happens to go first.

Results are written one JSON file per run plus an index the dashboard polls.
"""
import argparse, json, os, random, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
RUNDIR = os.path.join(ROOT, ".run")
STACKS = json.load(open(f"{ROOT}/bench/stacks.json"))

PROFILES = {
    # name: (reps, measured seconds, warmup seconds, load configs)
    "smoke": (1, 5, 2, [("closed", 32, 0)]),
    "quick": (1, 10, 4, [("closed", 64, 0), ("open", 64, 400)]),
    "full":  (3, 15, 5, [("closed", 64, 0), ("open", 64, 300), ("open", 128, 900)]),
    # 5 reps: enough that a single degraded repetition cannot move the median.
    "final": (5, 10, 3, [("closed", 64, 0), ("open", 64, 300), ("open", 128, 900)]),
    "deep":  (5, 20, 6, [("closed", 32, 0), ("closed", 64, 0), ("closed", 128, 0),
                         ("open", 64, 200), ("open", 64, 500),
                         ("open", 128, 1000), ("open", 128, 1600)]),
}
SCENARIOS = ["quote", "checkout", "summary"]


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def start(stack_id):
    sh([f"{ROOT}/bench/svc.sh", "start", stack_id], stdout=subprocess.DEVNULL)
    return int(open(f"{RUNDIR}/{stack_id}.pid").read().strip())


def stop(stack_id):
    subprocess.run([f"{ROOT}/bench/svc.sh", "stop", stack_id],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def reset_db():
    subprocess.run([f"{ROOT}/bench/reset.sh"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write_index(meta, done, total, started):
    runs = []
    for fn in sorted(os.listdir(RESULTS)):
        if fn.endswith(".json") and fn != "index.json":
            try:
                runs.append(json.load(open(os.path.join(RESULTS, fn))))
            except Exception:
                pass
    idx = {
        "meta": meta,
        "progress": {"done": done, "total": total,
                     "elapsedSec": round(time.time() - started, 1),
                     "running": done < total},
        "stacks": STACKS,
        "runs": runs,
    }
    tmp = os.path.join(RESULTS, ".index.tmp")
    with open(tmp, "w") as f:
        json.dump(idx, f)
    os.replace(tmp, os.path.join(RESULTS, "index.json"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="quick", choices=list(PROFILES))
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--stacks", default="")
    ap.add_argument("--fresh", action="store_true", help="clear previous results")
    ap.add_argument("--svc-cpus", default="3-5")
    ap.add_argument("--gen-cpus", default="6,7")
    args = ap.parse_args()

    reps, dur, warm, configs = PROFILES[args.profile]
    scenarios = args.scenarios.split(",")
    stacks = [s for s in STACKS
              if not args.stacks or s["id"] in args.stacks.split(",")]

    os.makedirs(RESULTS, exist_ok=True)
    if args.fresh:
        for fn in os.listdir(RESULTS):
            os.remove(os.path.join(RESULTS, fn))

    plan = []
    for rep in range(reps):
        block = [(s, sc, mode, conns, rate)
                 for s in stacks for sc in scenarios
                 for (mode, conns, rate) in configs]
        random.Random(1000 + rep).shuffle(block)
        plan += [(rep, *b) for b in block]

    meta = {
        "profile": args.profile, "reps": reps, "durationSec": dur,
        "warmupSec": warm, "configs": [{"mode": m, "conns": c, "rate": r}
                                       for (m, c, r) in configs],
        "scenarios": scenarios, "svcCpus": args.svc_cpus,
        "genCpus": args.gen_cpus,
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": {"cores": os.cpu_count()},
    }
    started = time.time()
    total = len(plan)
    print(f"profile={args.profile}  {total} runs  "
          f"~{total * (dur + warm + 4) / 60:.0f} min estimated\n", flush=True)
    write_index(meta, 0, total, started)

    env = dict(os.environ, SVC_CPUS=args.svc_cpus)

    for i, (rep, stack, scenario, mode, conns, rate) in enumerate(plan, 1):
        sid = stack["id"]
        tag = f"{sid}__{scenario}__{mode}{rate or conns}__rep{rep}"
        out = os.path.join(RESULTS, tag + ".json")
        print(f"[{i}/{total}] {tag}", flush=True)
        reset_db()
        try:
            subprocess.run([f"{ROOT}/bench/svc.sh", "start", sid],
                           check=True, env=env, stdout=subprocess.DEVNULL)
            pid = int(open(f"{RUNDIR}/{sid}.pid").read().strip())
            cmd = ["taskset", "-c", args.gen_cpus, f"{RUNDIR}/loadgen",
                   "-base", f"http://127.0.0.1:{stack['port']}",
                   "-stack", sid, "-scenario", scenario, "-mode", mode,
                   "-conns", str(conns), "-duration", f"{dur}s",
                   "-warmup", f"{warm}s", "-corpus", f"{ROOT}/bench/corpus.json",
                   "-rep", str(rep), "-pid", str(pid), "-out", out]
            if mode == "open":
                cmd += ["-rate", str(rate)]
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"    run failed: {e}", file=sys.stderr)
            log = f"{RUNDIR}/{sid}.log"
            if os.path.exists(log):
                print("    " + "\n    ".join(open(log).read().splitlines()[-8:]),
                      file=sys.stderr)
        finally:
            stop(sid)
        write_index(meta, i, total, started)

    reset_db()
    write_index(meta, total, total, started)
    print(f"\ndone in {(time.time() - started) / 60:.1f} min -> {RESULTS}/index.json")


if __name__ == "__main__":
    main()
