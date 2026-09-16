"""Surface-form ablation: which output syntax can a small model actually produce?

    python3 surface/run.py --models Qwen/Qwen3-4B-Instruct-2507 --surfaces A_jquery --limit 4
    python3 surface/run.py --models Qwen/Qwen3-4B-Instruct-2507,Qwen/Qwen3-8B
    python3 surface/run.py --models Qwen/Qwen3-8B --condition few

A mutation is selector + operation + arguments. Every arm asks for the SAME 20 mutations over
the SAME fixture with the SAME selector vocabulary; only the wrapper syntax differs. So a gap
between arms is the surface's doing, not the vocabulary's.

Two conditions, holding vocabulary and the operation table constant in both:
  card -- header + vocabulary + ops + this surface's syntax block (one line, two examples)
  few  -- header + vocabulary + ops + THE SAME TWO EXAMPLES delivered as chat turns, no
          syntax line. Stages 8 and 9 both found examples beat a card on device models, so a
          card-only study could rank surfaces wrongly.

Three result buckets, because "it didn't parse" hides the failure that matters: `malformed`
means the syntax is hard, `wrong_surface` means the card lost and the model wrote a DIFFERENT
surface (JSON is the likely attractor). Different problems, different fixes.

Scores are reported per part (selector / op / args). The argument is partly transcription --
nothing but the request can say what to rename a thing TO -- so a single combined number would
be inflated relative to the selector tiers. The arity-0 subset (T01-T06) is the only one that
earns no transcription credit at all and is the cleanest signal here.

Runs on the NPU; stage 10 has the GPU. Surfaces iterate INSIDE a model because a model swap
costs minutes and a surface costs nothing.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "surface"))

import qualify as Q          # noqa: E402  device orchestration, reused wholesale
import surfaces as S         # noqa: E402

TASKS = os.path.join(HERE, "surface", "tasks.json")
CARD_V1C = os.path.join(HERE, "card_v1c.md")
OUTDIR = os.path.join(HERE, "workspace", "surface")

#: Few-shot examples: deliberately THE SAME TWO the card block shows, so the card/few
#: comparison isolates delivery (prose syntax line vs. worked turns) and not content.
FEWSHOT = [
    ("rename the helper function to run", ".fn#helper", "rename", ["run"]),
    ("in save, add x = 1 before the return", ".fn#save", "insertBefore", [".jump", "x = 1"]),
]


def log_to(path):
    fh = open(path, "a", buffering=1)

    def log(msg):
        line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        fh.write(line + "\n")
    return log


def build_messages(surface, card_body, condition, request):
    """card: one system message. few: system without the syntax block, then example turns."""
    if condition == "card":
        return None, S.build_card(card_body, surface)
    system = S.SHARED_HEADER + card_body + S.SHARED_OPS
    turns = []
    for req, sel, op, args in FEWSHOT:
        turns.append({"role": "user", "content": req})
        turns.append({"role": "assistant", "content": S.render(surface, sel, op, args)})
    return turns, system


def done_keys(path):
    """Resume: (model, surface, condition, task) already recorded."""
    seen = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            seen.add((r["model"], r["surface"], r["condition"], r["task"]))
    return seen


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, help="comma-separated device model ids")
    ap.add_argument("--surfaces", default=",".join(sorted(S.BLOCKS)))
    ap.add_argument("--condition", default="card", choices=("card", "few"))
    ap.add_argument("--limit", type=int, default=0, help="first N tasks only (smoke runs)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    spec = json.load(open(TASKS))
    tasks = spec["tasks"][:args.limit] if args.limit else spec["tasks"]
    surfaces = [s.strip() for s in args.surfaces.split(",") if s.strip()]
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    for s in surfaces:
        if s not in S.BLOCKS:
            sys.exit("unknown surface %r (have: %s)" % (s, ", ".join(sorted(S.BLOCKS))))

    card_body = S.strip_selector_instruction(open(CARD_V1C).read())
    os.makedirs(OUTDIR, exist_ok=True)
    stamp = args.out or time.strftime("%Y%m%d-%H%M%S")
    rows_path = os.path.join(OUTDIR, "rows-%s.jsonl" % stamp)
    log = log_to(os.path.join(OUTDIR, "run-%s.log" % stamp))
    seen = done_keys(rows_path)

    key = Q.auth_key()
    cat, types = Q.catalog(key), Q.model_types(key)
    unknown = [m for m in models if m not in cat]
    if unknown:
        sys.exit("not downloaded chat models on the device: %s" % unknown)

    log("surface study: %d model(s) x %d surface(s) x %d task(s), condition=%s"
        % (len(models), len(surfaces), len(tasks), args.condition))
    fh = open(rows_path, "a", buffering=1)
    for model in models:
        log("loading %s" % model)
        waited = Q.ensure_loaded(key, model, log, types)
        log("  resident after %.0fs" % waited)
        thinking = cat.get(model) or {}
        for surface in surfaces:                       # surfaces inside the model: swaps are costly
            todo = [t for t in tasks
                    if (model, surface, args.condition, t["id"]) not in seen]
            if not todo:
                log("  %s: already complete" % surface)
                continue
            turns, system = build_messages(surface, card_body, args.condition, None)
            tally = {"ok": 0, "wrong_surface": 0, "malformed": 0, "error": 0, "all": 0}
            for t in todo:
                body, mode = Q.request_body(model, thinking, system, t["request"])
                if turns:                              # few-shot: examples before the request
                    body["messages"] = ([{"role": "system", "content": system}] + turns
                                        + [{"role": "user", "content": t["request"]}])
                row = {"model": model, "surface": surface, "condition": args.condition,
                       "task": t["id"], "tier": t["tier"], "arity": t["arity"],
                       "request": t["request"], "thinking_mode": mode}
                try:
                    got = Q.chat(key, body)
                    text = got["content"]
                    status, parsed = S.judge(surface, text)
                    sc = S.score(t, parsed)
                    row.update(raw=text, status=status, parsed=parsed, score=sc,
                               latency_s=got.get("latency_s"))
                    tally[status] += 1
                    tally["all"] += 1 if sc["all"] else 0
                except Exception as e:                 # empty response, timeout, transport
                    row.update(status="error", error="%s: %s" % (type(e).__name__, str(e)[:300]))
                    tally["error"] += 1
                fh.write(json.dumps(row) + "\n")
            n = len(todo)
            log("  %-12s ok %2d/%d  wrong_surface %d  malformed %d  error %d  |  fully correct %d"
                % (surface, tally["ok"], n, tally["wrong_surface"], tally["malformed"],
                   tally["error"], tally["all"]))
    fh.close()
    log("rows -> %s" % rows_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
