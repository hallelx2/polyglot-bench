#!/usr/bin/env python3
"""Conformance: every stack must return byte-identical canonical JSON for the
same inputs. A stack that skips work fails here before it can win a benchmark."""
import datetime as dt, json, os, re, subprocess, sys, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STACKS = json.load(open(f"{ROOT}/bench/stacks.json"))
CORPUS = json.load(open(f"{ROOT}/bench/corpus.json"))
N = int(os.environ.get("VERIFY_N", "150"))

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})$")

def canon(obj):
    """Drop orderId (a sequence, different per run) and normalise timestamp
    spelling — `...:00Z` and `...:00.000Z` are the same instant, and the spec
    does not dictate fractional-second formatting."""
    if isinstance(obj, dict):
        return {k: canon(v) for k, v in sorted(obj.items()) if k != "orderId"}
    if isinstance(obj, list):
        return [canon(v) for v in obj]
    if isinstance(obj, str) and ISO.match(obj):
        return dt.datetime.fromisoformat(obj.replace("Z", "+00:00")).timestamp()
    return obj

def call(port, method, path, body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def svc(action, sid):
    subprocess.run([f"{ROOT}/bench/svc.sh", action, sid], check=(action == "start"),
                   stdout=subprocess.DEVNULL)

def collect(phase):
    """Run one phase against every stack, one stack at a time."""
    results = {}
    for s in STACKS:
        svc("start", s["id"])
        try:
            out = []
            if phase == "summary":
                for cid in CORPUS["summary"][:N]:
                    out.append(call(s["port"], "GET", f"/api/customers/{cid}/summary"))
            else:
                path = "/api/quote" if phase == "quote" else "/api/checkout"
                for body in CORPUS["price"][:N]:
                    out.append(call(s["port"], "POST", path, body))
            results[s["id"]] = out
        finally:
            svc("stop", s["id"])
        print(f"  {phase:9s} {s['id']:16s} {len(results[s['id']])} responses", flush=True)
    return results

def compare(phase, results):
    base_id = STACKS[0]["id"]
    base = results[base_id]
    failures = []
    for s in STACKS[1:]:
        got = results[s["id"]]
        for i, (b, g) in enumerate(zip(base, got)):
            if b[0] != g[0] or canon(b[1]) != canon(g[1]):
                failures.append((s["id"], i, b, g))
                if len(failures) >= 5:
                    break
        if len(failures) >= 5:
            break
    return failures

def main():
    print(f"conformance: {len(STACKS)} stacks x {N} requests x 3 endpoints")
    print(f"reference stack: {STACKS[0]['id']}\n")
    ok = True
    for phase in ("summary", "quote", "checkout"):
        results = collect(phase)
        fails = compare(phase, results)
        if fails:
            ok = False
            print(f"\n  FAIL {phase}: {len(fails)} divergence(s)")
            for sid, i, b, g in fails[:3]:
                print(f"    request #{i} — {STACKS[0]['id']} vs {sid}")
                print(f"      expected {b[0]} {json.dumps(canon(b[1]))[:400]}")
                print(f"      got      {g[0]} {json.dumps(canon(g[1]))[:400]}")
        else:
            print(f"  PASS {phase}: all {len(STACKS)} stacks identical\n")
    print("CONFORMANCE PASS" if ok else "CONFORMANCE FAIL")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
