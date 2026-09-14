"""Qualify the Tiiny's text models on the astcss pilot set: NL -> selector, scored by execution.

usage:
  qualify.py oracle [--per-tier N] [--seed S]
      scorer sanity check, no device: every sampled pair's reference selector
      is scored as if a model had produced it, and must score 100%.
  qualify.py run [--models ID,ID] [--per-tier N] [--seed S] [--out DIR]
      for each model in turn: load it on the device, ask for a selector for each
      sampled pair's NL, append every response to DIR/responses.jsonl, then score.
      Re-running with the same DIR resumes: answered (model, pair) rows are skipped.
  qualify.py score --out DIR
      re-score DIR/responses.jsonl.

This is SPEC.md §4 arm A only (astcss, free decoding, vocabulary card in the
system prompt). Scoring follows §4.2 in order of authority: executes (a stand-in
for parse-valid -- ast_select rejects what it cannot parse), execution-match
against the frozen reference, exact string. Pending pairs are never scored.

One model runs at a time: concurrent NPU load has hard-reset this device, so
there is no parallelism here by design. A model is never evicted while the
device reports in-flight requests on it, and whatever was loaded before the run
is loaded again after it.
"""
import argparse
import glob
import hashlib
import json
import os
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

import verify as V

HERE = os.path.dirname(os.path.abspath(__file__))
MGMT = os.environ.get("TIINY_MGMT", "http://p8800.api.tiiny/api/v1")
OAI = os.environ.get("TIINY_OAI", "http://api.tiiny/v1")
CARD = os.path.join(HERE, "card.md")
CHAT_TYPES = ("Text Generation", "Image-Text-to-Text")


# ---------------------------------------------------------------------------
# Pairs
# ---------------------------------------------------------------------------

def load_pairs():
    pairs = []
    for path in sorted(glob.glob(os.path.join(HERE, "pairs", "accepted-*.jsonl"))):
        pairs.extend(json.loads(line) for line in open(path) if line.strip())
    return pairs


def sample(pairs, per_tier, seed):
    """Deterministic stratified sample: the same (per_tier, seed) always picks the same ids."""
    out = []
    for tier in sorted({p["tier"] for p in pairs}):
        tier_pairs = sorted((p for p in pairs if p["tier"] == tier), key=lambda p: p["id"])
        if per_tier and per_tier < len(tier_pairs):
            tier_pairs = random.Random("%s-%s" % (seed, tier)).sample(tier_pairs, per_tier)
        out.extend(sorted(tier_pairs, key=lambda p: p["id"]))
    return out


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------

def auth_key():
    if os.environ.get("TIINY_AUTH_KEY"):
        return os.environ["TIINY_AUTH_KEY"]
    path = glob.glob(os.path.expanduser("~/.local/share/tiiny-pcsvr/auth_data/*.json"))[0]
    return json.load(open(path))["auth_key"]


def http(url, key, body=None, method="GET", timeout=60):
    req = urllib.request.Request(url, method=method, headers={"Authorization": "Bearer " + key})
    if body is not None or method == "POST":
        req.data = json.dumps(body if body is not None else {}).encode()
        req.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(req, timeout=timeout)


def mgmt(path, key, method="GET", timeout=60):
    with http("%s/%s" % (MGMT, path), key, method=method, timeout=timeout) as resp:
        return json.load(resp)


def catalog(key):
    """Downloaded chat-capable models -> their `thinking` capability object."""
    data = mgmt("models", key)["data"]
    return {m["model_id"]: m.get("thinking") or {} for m in data
            if m.get("type") in CHAT_TYPES and m.get("status") in ("downloaded", "running")}


def running(key):
    d = mgmt("models/running", key)
    active = {m.get("model_id"): (m.get("active_request_count") or 0)
              for m in d.get("instances", {}).get("running", [])}
    return list(d.get("running", [])), active


def npu_tasked(key):
    """Models the NPU itself reports active tasks for, or None if it can't be asked."""
    url = os.environ.get("TIINY_NPU", "http://192.168.4.144:8800/api/v1/npu/status")
    try:
        with http(url, key, timeout=30) as resp:
            n = json.load(resp)
    except Exception:
        return None
    return {m.get("model_name") for o in (n.get("occupants") or [])
            for m in (o.get("activate_model") or []) if m.get("active_tasks")}


def ensure_loaded(key, want, log):
    """Leave exactly `want` resident; refuse to evict anything with in-flight requests.

    `active_request_count` alone lies: in stage 1 it read 3 on an idle
    Qwen3-30B-A3B-Instruct for minutes after the last response while the NPU
    listed no occupants (the stale-count behaviour in swap-queue-trial.py).
    Busy therefore means the counter AND the NPU task list agree; if the NPU
    can't be asked, the counter is trusted, which errs toward not evicting."""
    deadline = time.time() + 300
    while True:
        now, active = running(key)
        if now == [want]:
            return 0.0
        counted = {m for m in now if m != want and active.get(m)}
        tasked = npu_tasked(key) if counted else set()
        busy = sorted(counted if tasked is None else counted & tasked)
        if not busy:
            break
        if time.time() > deadline:
            raise RuntimeError("models still report in-flight requests after 5 min: %s" % busy)
        log("  waiting: %s report in-flight requests" % busy)
        time.sleep(10)
    t0 = time.time()
    for m in now:
        if m != want:
            mgmt("models/%s/stop" % m, key, "POST")
    for _ in range(40):
        if not [m for m in running(key)[0] if m != want]:
            break
        time.sleep(3)
    if want not in running(key)[0]:
        mgmt("models/%s/start" % want, key, "POST", timeout=180)
    while time.time() - t0 < 900:
        if want in running(key)[0]:
            return time.time() - t0
        time.sleep(6)
    raise RuntimeError("%s did not come up within 15 min" % want)


def request_body(model, thinking, card, nl):
    body = {"model": model, "stream": True, "temperature": 0,
            "messages": [{"role": "system", "content": card}, {"role": "user", "content": nl}]}
    mode = "none"
    if thinking.get("supported") and thinking.get("toggleable"):
        body["chat_template_kwargs"] = {"enable_thinking": False}
        body["max_tokens"], mode = 200, "off"
    elif thinking.get("supported") and thinking.get("levels"):
        body["reasoning_effort"] = "low"
        body["max_tokens"], mode = 4000, "low"
    elif thinking.get("supported"):
        body["max_tokens"], mode = 8000, "on"
    else:
        body["max_tokens"] = 200
    return body, mode


def chat(key, body, timeout=900):
    """Streamed completion (keeps the device's idle timeout from firing on long thinking)."""
    content, reasoning, usage, finish = [], [], {}, None
    t0 = time.time()
    first = None
    with http(OAI + "/chat/completions", key, body, "POST", timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    first = first or time.time()
                    content.append(delta["content"])
                if delta.get("reasoning_content") or delta.get("reasoning"):
                    first = first or time.time()
                    reasoning.append(delta.get("reasoning_content") or delta.get("reasoning"))
                finish = choice.get("finish_reason") or finish
    return {"content": "".join(content), "reasoning_chars": len("".join(reasoning)),
            "latency_s": round(time.time() - t0, 2),
            "first_token_s": round(first - t0, 2) if first else None,
            "completion_tokens": usage.get("completion_tokens"), "finish_reason": finish}


# ---------------------------------------------------------------------------
# Extraction and scoring
# ---------------------------------------------------------------------------

def extract(text):
    """The selector a model meant: first non-empty line outside think blocks and fences."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"^.*</think>", "", text, flags=re.S)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        line = re.sub(r"^(selector|answer)\s*:\s*", "", line, flags=re.I)
        return line.strip("`'\" ").strip()
    return ""


def score(rows, pairs_by_id):
    """rows: [{"model", "id", "prediction", ...}] -> rows with executes / exec_match / exact added."""
    uniq = {}
    for r in rows:
        if r.get("prediction"):
            uniq.setdefault((pairs_by_id[r["id"]]["fixture"], r["prediction"]), "q%d" % len(uniq))
    got = V.execute([(qid, fx, sel) for (fx, sel), qid in uniq.items()]) if uniq else {}
    out = []
    for r in rows:
        p = pairs_by_id[r["id"]]
        r = dict(r, tier=p["tier"], reference=p["css"])
        res = got.get(uniq.get((p["fixture"], r.get("prediction"))), {"error": "empty prediction"})
        r["executes"] = "error" not in res
        r["exec_error"] = res.get("error")
        r["exec_match"] = r["executes"] and V._digest(res["nodes"]) == p["reference"]["sha256"]
        r["exact"] = r.get("prediction") == p["css"]
        out.append(r)
    return out


def summarize(scored):
    by_model = {}
    for r in scored:
        by_model.setdefault(r["model"], []).append(r)
    summary = []
    for model, rs in by_model.items():
        answered = [r for r in rs if not r.get("error")]
        row = {"model": model, "n": len(rs), "request_errors": len(rs) - len(answered),
               "executes": sum(r["executes"] for r in rs), "exec_match": sum(r["exec_match"] for r in rs),
               "exact": sum(r["exact"] for r in rs),
               "by_tier": {t: [sum(r["exec_match"] for r in rs if r["tier"] == t), sum(1 for r in rs if r["tier"] == t)]
                           for t in sorted({r["tier"] for r in rs})},
               "median_latency_s": statistics.median([r["latency_s"] for r in answered]) if answered else None,
               "mean_completion_tokens": (statistics.mean([r["completion_tokens"] for r in answered if r.get("completion_tokens")])
                                          if any(r.get("completion_tokens") for r in answered) else None),
               "thinking": rs[0].get("thinking")}
        summary.append(row)
    summary.sort(key=lambda s: (-s["exec_match"], s["median_latency_s"] or 1e9))
    return summary


def print_summary(summary):
    tiers = sorted({t for s in summary for t in s["by_tier"]})
    print("\n%-42s %4s %6s %6s %6s  %s  %8s %6s %s" % ("model", "n", "exec", "match", "exact",
          " ".join("T%-5s" % t for t in tiers), "med s", "tok", "think"))
    for s in summary:
        pct = lambda a: "%5.1f%%" % (100.0 * a / s["n"]) if s["n"] else "   -  "
        tier_cells = " ".join("%-6s" % ("%d/%d" % tuple(s["by_tier"].get(t, [0, 0]))) for t in tiers)
        print("%-42s %4d %6s %6s %6s  %s  %8s %6s %s" % (
            s["model"][:42], s["n"], pct(s["executes"]), pct(s["exec_match"]), pct(s["exact"]), tier_cells,
            s["median_latency_s"], "%.0f" % s["mean_completion_tokens"] if s["mean_completion_tokens"] else "-",
            s["thinking"]))


def rescore(out_dir, pairs_by_id):
    rows = [json.loads(line) for line in open(os.path.join(out_dir, "responses.jsonl")) if line.strip()]
    scored = score(rows, pairs_by_id)
    with open(os.path.join(out_dir, "scores.jsonl"), "w") as fh:
        for r in scored:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = summarize(scored)
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    print_summary(summary)
    return summary


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_oracle(args):
    pairs = sample(load_pairs(), args.per_tier, args.seed)
    by_id = {p["id"]: p for p in pairs}
    rows = [{"model": "oracle:reference", "id": p["id"], "prediction": extract(p["css"]),
             "latency_s": 0, "thinking": "-"} for p in pairs]
    # A wrong answer must also score as wrong, or 100% above proves nothing.
    rows += [{"model": "oracle:first-distractor", "id": p["id"], "prediction": p["distractors"][0],
              "latency_s": 0, "thinking": "-"} for p in pairs]
    print_summary(summarize(score(rows, by_id)))


def cmd_run(args):
    key = auth_key()
    card = open(CARD).read()
    pairs = sample(load_pairs(), args.per_tier, args.seed)
    by_id = {p["id"]: p for p in pairs}
    cat = catalog(key)
    models = args.models.split(",") if args.models else sorted(cat)
    unknown = [m for m in models if m not in cat]
    if unknown:
        sys.exit("not downloaded chat models on the device: %s" % unknown)

    out_dir = args.out or os.path.join(HERE, "runs", "qualify-" + time.strftime("%Y%m%d-%H%M"))
    os.makedirs(out_dir, exist_ok=True)
    resp_path = os.path.join(out_dir, "responses.jsonl")
    done = set()
    if os.path.exists(resp_path):
        done = {(r["model"], r["id"]) for r in map(json.loads, open(resp_path)) if not r.get("error")}
    logfile = open(os.path.join(out_dir, "run.log"), "a")

    def log(msg):
        line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        logfile.write(line + "\n")
        logfile.flush()

    meta_path = os.path.join(out_dir, "meta.json")
    if not os.path.exists(meta_path):
        json.dump({"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "models": models,
                   "per_tier": args.per_tier, "seed": args.seed, "pair_ids": [p["id"] for p in pairs],
                   "card_sha256": hashlib.sha256(card.encode()).hexdigest(),
                   "catalog_thinking": {m: cat[m] for m in models}, "engine": V.engine_identity()},
                  open(meta_path, "w"), indent=2)

    original = running(key)[0]
    log("run: %d models x %d pairs -> %s (device had %s)" % (len(models), len(pairs), out_dir, original))
    try:
        with open(resp_path, "a") as fh:
            for model in models:
                todo = [p for p in pairs if (model, p["id"]) not in done]
                if not todo:
                    log("%s: already complete" % model)
                    continue
                try:
                    load_s = ensure_loaded(key, model, log)
                    log("%s: loaded in %.0fs, %d pairs to ask" % (model, load_s, len(todo)))
                except Exception as e:
                    log("%s: LOAD FAILED %s: %s" % (model, type(e).__name__, e))
                    continue
                strikes = 0
                for p in todo:
                    body, mode = request_body(model, cat[model], card, p["nl"])
                    row = {"model": model, "id": p["id"], "thinking": mode, "nl": p["nl"]}
                    try:
                        row.update(chat(key, body))
                        row["prediction"] = extract(row["content"])
                        strikes = 0
                    except Exception as e:
                        detail = e.read().decode("utf-8", "replace")[:300] if isinstance(e, urllib.error.HTTPError) else ""
                        row["error"] = "%s: %s %s" % (type(e).__name__, e, detail)
                        strikes += 1
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    fh.flush()
                    log("%s %-7s %6ss %-40s %s" % (model.split("/")[-1][:24], p["id"], row.get("latency_s", "-"),
                                                   (row.get("prediction") or "")[:40], row.get("error", "")[:80]))
                    if strikes >= 3:
                        log("%s: 3 consecutive request errors, skipping the rest" % model)
                        break
    finally:
        if original:
            try:
                log("restoring %s" % original[0])
                ensure_loaded(key, original[0], log)
            except Exception as e:
                log("RESTORE FAILED %s: %s" % (type(e).__name__, e))
    rescore(out_dir, {p["id"]: p for p in load_pairs()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("oracle", "run", "score"))
    ap.add_argument("--models")
    ap.add_argument("--per-tier", type=int, default=10)
    ap.add_argument("--seed", default="qualify-v1")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.command == "oracle":
        cmd_oracle(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        rescore(args.out, {p["id"]: p for p in load_pairs()})


if __name__ == "__main__":
    main()
