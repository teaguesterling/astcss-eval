"""Spot-test the mutator grammar on device models. No GPU: stage 11 owns the card."""
import json, os, sys, time
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "mutator"))
import qualify as Q
import judge as J
from card import build as build_card

models = (sys.argv[1] if len(sys.argv) > 1 else "Qwen/Qwen3.5-9B").split(",")
spec = json.load(open(os.path.join(HERE, "mutator/tasks.json")))
tasks = spec["tasks"]
card = build_card()
key = Q.auth_key(); cat = Q.catalog(key); types = Q.model_types(key)
out = os.path.join(HERE, "workspace/mutator-spot.jsonl")
os.makedirs(os.path.dirname(out), exist_ok=True)
fh = open(out, "a", buffering=1)

for model in models:
    Q.ensure_loaded(key, model, lambda m: print("  " + m), types)
    tally = {"ok": 0, "wrong_surface": 0, "malformed": 0, "error": 0,
             "sel": 0, "op": 0, "args": 0, "all": 0}
    print("\n=== %s ===" % model.split("/")[-1])
    for t in tasks:
        body, _ = Q.request_body(model, cat.get(model) or {}, card, t["request"])
        row = {"model": model, "task": t["id"], "op": t["op"], "request": t["request"]}
        try:
            raw = Q.chat(key, body)["content"]
            st, got = J.judge(raw)
            sc = J.score(t, got)
            tally[st] += 1
            for k in ("selector", "op", "args", "all"):
                tally[{"selector": "sel"}.get(k, k)] += 1 if sc[k] else 0
            row.update(raw=raw, status=st, score=sc)
            mark = "".join(c if sc[k] else "-" for c, k in
                           zip("SOA", ("selector", "op", "args")))
            print("  %-4s %-14s [%-13s] %s  %s" % (t["id"], t["op"], st, mark,
                                                   " ".join(raw.split())[:74]))
        except Exception as e:
            tally["error"] += 1
            row.update(status="error", error="%s: %s" % (type(e).__name__, str(e)[:200]))
            print("  %-4s %-14s [error] %s" % (t["id"], t["op"], str(e)[:60]))
        fh.write(json.dumps(row) + "\n")
    n = len(tasks)
    print("  -> parse ok %d/%d | wrong_surface %d | malformed %d | error %d"
          % (tally["ok"], n, tally["wrong_surface"], tally["malformed"], tally["error"]))
    print("  -> selector %d  op %d  args %d  ALL %d /%d"
          % (tally["sel"], tally["op"], tally["args"], tally["all"], n))
