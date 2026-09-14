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
import concurrent.futures
import glob
import hashlib
import json
import os
import random
import re
import signal
import statistics
import subprocess
import sys
import tempfile
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


def leaked_ids(card, pairs):
    """Pairs whose exact selector appears in the card as a whole token -- the prompt
    hands the model that answer. Bare classes and node types are the vocabulary the
    card exists to list, so they don't count."""
    out = []
    for p in pairs:
        if re.fullmatch(r"\.?[A-Za-z_]+", p["css"]):
            continue
        if re.search(r"(?:^|(?<=\s))" + re.escape(p["css"]) + r"(?=\s|$)", card, flags=re.M):
            out.append(p["id"])
    return sorted(out)


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


def model_types(key):
    return {m["model_id"]: m.get("type") for m in mgmt("models", key)["data"]}


def yield_npu(key, model, log, max_wait=1800):
    """Wait until no other model has NPU tasks, so our requests never overlap another
    client's work (concurrent NPU load is what hard-resets this device). A batch that
    starts during one of our ~1 s requests can still overlap; this narrows the window,
    it does not close it. An unreadable NPU status counts as busy."""
    t0, said = time.time(), False
    while True:
        tasked = npu_tasked(key)
        others = None if tasked is None else sorted(m for m in tasked if m != model)
        if others == []:
            if said:
                log("  npu free after %.0fs" % (time.time() - t0))
            return
        if time.time() - t0 > max_wait:
            raise RuntimeError("NPU still busy (%s) after %ds" % (others, max_wait))
        if not said:
            log("  yielding: NPU tasks on %s" % (others if others is not None else "unknown -- status unreadable"))
            said = True
        time.sleep(3)


def ensure_loaded(key, want, log, types):
    """Make `want` resident, stopping only other chat models; refuse to evict anything
    with in-flight requests. Non-chat models (the embedder another client uses) stay.

    `active_request_count` alone lies: in stage 1 it read 3 on an idle
    Qwen3-30B-A3B-Instruct for minutes after the last response while the NPU
    listed no occupants (the stale-count behaviour in swap-queue-trial.py).
    Busy therefore means the counter AND the NPU task list agree; if the NPU
    can't be asked, the counter is trusted, which errs toward not evicting."""
    deadline = time.time() + 300
    while True:
        now, active = running(key)
        evict = [m for m in now if m != want and types.get(m) in CHAT_TYPES]
        if want in now and not evict:
            return 0.0
        counted = {m for m in evict if active.get(m)}
        tasked = npu_tasked(key) if counted else set()
        busy = sorted(counted if tasked is None else counted & tasked)
        if not busy:
            break
        if time.time() > deadline:
            raise RuntimeError("models still report in-flight requests after 5 min: %s" % busy)
        log("  waiting: %s report in-flight requests" % busy)
        time.sleep(10)
    t0 = time.time()
    for m in evict:
        mgmt("models/%s/stop" % m, key, "POST")
    for _ in range(40):
        if not set(evict) & set(running(key)[0]):
            break
        time.sleep(3)
    if want not in running(key)[0]:
        mgmt("models/%s/start" % want, key, "POST", timeout=180)
    while time.time() - t0 < 900:
        if want in running(key)[0]:
            return time.time() - t0
        time.sleep(6)
    raise RuntimeError("%s did not come up within 15 min" % want)


EMBED_HOST = os.environ.get("QUALIFY_EMBED_HOST", "longbottom")
# The leading [e] keeps the pattern from matching the remote shell running pgrep.
EMBED_MATCH = os.environ.get("QUALIFY_EMBED_MATCH", "[e]mbed_corpus.py --watch")
PAUSE_GUARD = "~/astcss-tune/npu-pause-guard.sh"
PAUSE_LEASE = "~/astcss-tune/npu-pause.lease"


def _ssh(cmd, timeout=40):
    out = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", EMBED_HOST, cmd],
                         capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError("ssh %s exit %s: %s" % (EMBED_HOST, out.returncode, (out.stderr or out.stdout)[:200]))
    return out.stdout.strip()


class EmbedPause:
    """Stop the NPU embedding job while device models run (decided 2026-09-14).

    A chat request that overlapped the job's batches hung 108 s, the runtime dropped
    the chat model and recreated the embedder, and the job got a 504 and a 500 at the
    same moment. Pausing the job removes the overlap entirely. SIGSTOP/SIGCONT only:
    the job's shards are written atomically and failed batches are retried or
    re-picked. A guard on the embedding host resumes the job if this process stops
    renewing the lease for 10 minutes, so a killed run cannot leave it stopped."""

    def __init__(self, log):
        self.log, self.pid, self.active, self.renewed = log, None, False, 0.0

    def __enter__(self):
        self.active = True
        pid = _ssh("pgrep -f '%s' | head -1 || true" % EMBED_MATCH)
        if not pid:
            self.log("embed pause: no embedding job on %s; nothing to pause" % EMBED_HOST)
            return self
        state = _ssh("touch %s && (nohup %s %s %s >/dev/null 2>&1 < /dev/null &) && kill -STOP %s && sleep 1 "
                     "&& awk '/^State:/{print $2}' /proc/%s/status" % (PAUSE_LEASE, PAUSE_GUARD, pid, PAUSE_LEASE, pid, pid))
        self.pid, self.renewed = pid, time.time()
        self.log("embed pause: SIGSTOP pid %s on %s, state %s, lease guard running" % (pid, EMBED_HOST, state))
        return self

    def renew(self):
        if self.pid and time.time() - self.renewed > 120:
            try:
                _ssh("touch %s" % PAUSE_LEASE)
                self.renewed = time.time()
            except Exception as e:
                self.log("embed pause: lease renewal failed (%s)" % e)

    def __exit__(self, *exc):
        if self.pid:
            try:
                state = _ssh("rm -f %s; kill -CONT %s; sleep 1; awk '/^State:/{print $2}' /proc/%s/status"
                             % (PAUSE_LEASE, self.pid, self.pid))
                self.log("embed pause: SIGCONT pid %s, state %s" % (self.pid, state))
            except Exception as e:
                self.log("embed pause: RESUME FAILED (%s); the guard resumes it within 10 min" % e)
        self.active, self.pid = False, None
        return False


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
    text = "".join(content)
    if not text.strip():
        # Stage 3: a request that straddled a runtime restart returned 200 with no content
        # after 108 s. An empty answer is a failure to answer, never a wrong answer.
        raise RuntimeError("empty response after %.1fs (finish_reason=%s, reasoning_chars=%d)"
                           % (time.time() - t0, finish, len("".join(reasoning))))
    return {"content": text, "reasoning_chars": len("".join(reasoning)),
            "latency_s": round(time.time() - t0, 2),
            "first_token_s": round(first - t0, 2) if first else None,
            "completion_tokens": usage.get("completion_tokens"), "finish_reason": finish}


def claude_chat(model, card_path, nl, cwd, timeout=300):
    """One request to an Anthropic model through `claude -p`, as a control arm.

    The card replaces the system prompt; tools, skills, MCP servers and settings
    sources are all off, and it runs from an empty directory so no CLAUDE.md is
    discovered (a probe measured 1082 input tokens: card plus request, nothing
    else). A tool use or error is an error, never an answer."""
    cmd = ["claude", "-p", "--tools", "", "--disable-slash-commands", "--setting-sources", "",
           "--strict-mcp-config", "--no-session-persistence", "--output-format", "json",
           "--model", model, "--system-prompt-file", card_path]
    t0 = time.time()
    proc = subprocess.run(cmd, input=nl, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        raise RuntimeError("claude -p exit %s: %s" % (proc.returncode, (proc.stdout or proc.stderr)[:300]))
    items = data if isinstance(data, list) else [data]
    results = [x for x in items if x.get("type") == "result"]
    if not results:
        raise RuntimeError("claude -p gave no result event (exit %s)" % proc.returncode)
    res = results[-1]
    tool_uses = sum(1 for x in items if x.get("type") == "assistant"
                    for c in (x.get("message", {}).get("content") or [])
                    if isinstance(c, dict) and c.get("type") == "tool_use")
    if res.get("is_error") or tool_uses:
        raise RuntimeError("claude -p: %s (tool_uses=%d)" % (str(res.get("result"))[:200], tool_uses))
    if not (res.get("result") or "").strip():
        raise RuntimeError("claude -p: empty result")
    usage = res.get("usage") or {}
    return {"content": res.get("result") or "", "reasoning_chars": 0,
            "latency_s": round(time.time() - t0, 2), "first_token_s": None,
            "completion_tokens": usage.get("output_tokens"), "input_tokens": usage.get("input_tokens"),
            "finish_reason": res.get("stop_reason"), "cost_usd": res.get("total_cost_usd")}


def run_cloud(model, card_path, todo, fh, log, workers=4):
    """Cloud models don't touch the device, so they skip loading and NPU yielding and
    run a few requests at a time. Latency includes ~4 s of CLI start-up: it is not
    comparable to device latency."""
    cwd = tempfile.mkdtemp(prefix="qualify-cloud-")
    log("%s: cloud via claude -p, %d pairs, %d at a time" % (model, len(todo), workers))

    def ask(p):
        row = {"model": model, "id": p["id"], "thinking": "n/a", "nl": p["nl"]}
        try:
            row.update(claude_chat(model, card_path, p["nl"], cwd))
            row["prediction"] = extract(row["content"])
        except Exception as e:
            row["error"] = "%s: %s" % (type(e).__name__, str(e)[:300])
        return row

    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        for row in ex.map(ask, todo):
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            log("%s %-7s %6ss %-40s %s" % (model[:24], row["id"], row.get("latency_s", "-"),
                                           (row.get("prediction") or "")[:40], row.get("error", "")[:80]))


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
    for model, all_rows in by_model.items():
        # A request the device refused is not a wrong answer: rates are over answered
        # pairs only, and refusals are counted in their own column.
        rs = answered = [r for r in all_rows if not r.get("error")]
        row = {"model": model, "n": len(rs), "request_errors": len(all_rows) - len(answered),
               "executes": sum(r["executes"] for r in rs), "exec_match": sum(r["exec_match"] for r in rs),
               "exact": sum(r["exact"] for r in rs),
               "by_tier": {t: [sum(r["exec_match"] for r in rs if r["tier"] == t), sum(1 for r in rs if r["tier"] == t)]
                           for t in sorted({r["tier"] for r in rs})},
               "median_latency_s": statistics.median([r["latency_s"] for r in answered]) if answered else None,
               "mean_completion_tokens": (statistics.mean([r["completion_tokens"] for r in answered if r.get("completion_tokens")])
                                          if any(r.get("completion_tokens") for r in answered) else None),
               "thinking": all_rows[0].get("thinking")}
        summary.append(row)
    summary.sort(key=lambda s: (-s["exec_match"], s["median_latency_s"] or 1e9))
    return summary


def print_summary(summary):
    tiers = sorted({t for s in summary for t in s["by_tier"]})
    print("\n%-42s %4s %4s %6s %6s %6s  %s  %8s %6s %s" % ("model", "n", "err", "exec", "match", "exact",
          " ".join("T%-5s" % t for t in tiers), "med s", "tok", "think"))
    for s in summary:
        pct = lambda a: "%5.1f%%" % (100.0 * a / s["n"]) if s["n"] else "   -  "
        tier_cells = " ".join("%-6s" % ("%d/%d" % tuple(s["by_tier"].get(t, [0, 0]))) for t in tiers)
        print("%-42s %4d %4d %6s %6s %6s  %s  %8s %6s %s" % (
            s["model"][:42], s["n"], s["request_errors"], pct(s["executes"]), pct(s["exec_match"]), pct(s["exact"]), tier_cells,
            s["median_latency_s"], "%.0f" % s["mean_completion_tokens"] if s["mean_completion_tokens"] else "-",
            s["thinking"]))


def rescore(out_dir, pairs_by_id):
    rows = [json.loads(line) for line in open(os.path.join(out_dir, "responses.jsonl")) if line.strip()]
    # A resumed run re-asks pairs whose request failed: one row per (model, pair),
    # the latest answer winning over any earlier refusal.
    latest = {}
    for r in rows:
        k = (r["model"], r["id"])
        if k not in latest or not r.get("error") or latest[k].get("error"):
            latest[k] = r
    scored = score(list(latest.values()), pairs_by_id)
    meta_path = os.path.join(out_dir, "meta.json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    leaked = set(meta.get("leaked_ids") or [])
    if "leaked_ids" not in meta and meta.get("card_sha256"):
        # Runs from before leak tracking (stage 1) used card.md; recompute against it
        # only if it is still the card they ran with.
        card = open(CARD).read()
        if hashlib.sha256(card.encode()).hexdigest() == meta["card_sha256"]:
            leaked = set(leaked_ids(card, list(pairs_by_id.values())))
    with open(os.path.join(out_dir, "scores.jsonl"), "w") as fh:
        for r in scored:
            r["leaked"] = r["id"] in leaked
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = summarize([r for r in scored if not r["leaked"]])
    excluded = sorted({r["id"] for r in scored if r["leaked"]})
    if excluded:
        print("excluded %d pairs whose selector appears in the card: %s" % (len(excluded), ", ".join(excluded)))
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
    card_path = os.path.abspath(args.card or CARD)
    card = open(card_path).read()
    pairs = sample(load_pairs(), args.per_tier, args.seed)
    by_id = {p["id"]: p for p in pairs}
    cat = catalog(key)
    types = model_types(key)
    models = args.models.split(",") if args.models else sorted(cat)
    unknown = [m for m in models if m not in cat and not m.startswith("claude-")]
    if unknown:
        sys.exit("not downloaded chat models on the device: %s" % unknown)

    out_dir = args.out or os.path.join(HERE, "runs", "qualify-" + time.strftime("%Y%m%d-%H%M"))
    os.makedirs(out_dir, exist_ok=True)
    resp_path = os.path.join(out_dir, "responses.jsonl")
    done = set()
    if os.path.exists(resp_path):
        # Errors and empty answers are asked again.
        done = {(r["model"], r["id"]) for r in map(json.loads, open(resp_path))
                if not r.get("error") and (r.get("content") or "").strip()}
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
                   "card": os.path.relpath(card_path, HERE),
                   "card_sha256": hashlib.sha256(card.encode()).hexdigest(),
                   "leaked_ids": leaked_ids(card, load_pairs()),
                   "catalog_thinking": {m: cat.get(m, "cloud") for m in models}, "engine": V.engine_identity()},
                  open(meta_path, "w"), indent=2)

    original = running(key)[0]
    log("run: %d models x %d pairs -> %s (device had %s)" % (len(models), len(pairs), out_dir, original))
    # SIGTERM runs the finally below (restore models, resume embedding) instead of dying mid-run.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    has_device = any(not m.startswith("claude-") for m in models)
    pause = EmbedPause(log) if has_device and not args.no_embed_pause else None
    try:
        with open(resp_path, "a") as fh:
            for model in models:
                todo = [p for p in pairs if (model, p["id"]) not in done]
                if not todo:
                    log("%s: already complete" % model)
                    continue
                if model.startswith("claude-"):
                    run_cloud(model, card_path, todo, fh, log)
                    continue
                if pause and not pause.active:
                    pause.__enter__()
                try:
                    yield_npu(key, model, log)
                    load_s = ensure_loaded(key, model, log, types)
                    log("%s: loaded in %.0fs, %d pairs to ask" % (model, load_s, len(todo)))
                except Exception as e:
                    log("%s: LOAD FAILED %s: %s" % (model, type(e).__name__, e))
                    continue
                strikes = 0
                for p in todo:
                    body, mode = request_body(model, cat[model], card, p["nl"])
                    row = {"model": model, "id": p["id"], "thinking": mode, "nl": p["nl"]}
                    try:
                        if pause:
                            pause.renew()
                        yield_npu(key, model, log)
                        try:
                            row.update(chat(key, body))
                        except urllib.error.HTTPError as e:
                            if e.code != 503:
                                raise
                            # Stage 1: GLM-4.7-Flash was unloaded mid-run by something else.
                            log("  %s: 503 %s -- reloading, retrying once"
                                % (model, e.read().decode("utf-8", "replace")[:120]))
                            ensure_loaded(key, model, log, types)
                            yield_npu(key, model, log)
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
            # Everything that was resident, not just the first: another client may
            # have loaded a second model (stage 1 found the embedder beside 30B-Instruct).
            try:
                log("restoring %s" % original)
                ensure_loaded(key, original[0], log, types)
                for extra in original[1:]:
                    if extra not in running(key)[0]:
                        mgmt("models/%s/start" % extra, key, "POST", timeout=180)
            except Exception as e:
                log("RESTORE FAILED %s: %s" % (type(e).__name__, e))
        if pause and pause.active:
            pause.__exit__(None, None, None)
    rescore(out_dir, {p["id"]: p for p in load_pairs()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("oracle", "run", "score"))
    ap.add_argument("--models")
    ap.add_argument("--card", help="vocabulary card for the system prompt (default card.md)")
    ap.add_argument("--no-embed-pause", action="store_true",
                    help="don't pause the NPU embedding job during device runs")
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
