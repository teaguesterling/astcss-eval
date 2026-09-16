"""Execution verifier for the Text-to-ASTCSS validation set.

House rule (SPEC.md): the engine is the verifier -- no pair enters the corpus
unless its selector executes and its node set is frozen as the reference. This
module adds the checks the engine will not do for us, because sitting_duck's
`ast_select` fails silently in both directions (issues #127, #128, #130):

  bounds         the reference returns 1..50 nodes: never 0, never the universe
  load-bearing   removing any single modifier (#id, [attr], :pseudo, a
                 combinator step) CHANGES the node set. A modifier that doesn't is
                 vacuous -- `.class:not([bases])` returns exactly what `.class`
                 does, because `[bases]` is silently ignored.
  distractors    each parses (no error) and returns a DIFFERENT node set

Everything runs through sitting_duck CLI sessions (ASTCSS_EXEC_JOBS of them), with each
fixture's AST materialised once per session and queried with ast_select_from. Identical
(fixture, selector) queries run once and their results persist in the result cache, because
every ast_select_from call costs ~6 s of planning whatever the data (sitting_duck #160).
pilot.py answers most relaxation and distractor checks from oracle.py instead, so a training
batch reaches the engine with roughly one query per pair.

Engine: see memory `astcss-eval-verifier-runtime`. Until a sitting_duck release
ships PR #129, the only runtime that executes combinators correctly is the local
HEAD build's CLI with the #129 macros loaded over it. engine_identity() records
exactly what was used; store it with every verified batch.
"""
import functools
import glob
import hashlib
import json
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SD = os.environ.get("SITTING_DUCK", os.path.expanduser("~/Projects/sitting_duck"))
CLI = os.path.join(SD, "build/release/duckdb")
EXT = os.path.join(SD, "build/release/extension/sitting_duck/sitting_duck.duckdb_extension")
MACROS = os.environ.get(
    "ASTCSS_MACROS",
    os.path.join(SD, "trees/fix/127-combinator-steps/src/sql_macros/css_selectors.sql"))

FIXTURES = {
    "py-variety": "fixtures/py-variety/*.py",
    "repo-small-py": "fixtures/repo-small-py/*.py",
}
# Training fixtures (train/fixtures/MANIFEST.json) register alongside the eval's,
# never replacing them; the eval's two entries above stay exactly as frozen.
_TRAIN_MANIFEST = os.path.join(HERE, "train", "fixtures", "MANIFEST.json")
if os.path.exists(_TRAIN_MANIFEST):
    import json as _json
    for _name in _json.load(open(_TRAIN_MANIFEST))["fixtures"]:
        FIXTURES.setdefault(_name, "train/fixtures/%s/**/*.*" % _name)
MIN_NODES, MAX_NODES = 1, 50
COMBINATORS = ("child_selector", "descendant_selector", "sibling_selector",
               "adjacent_sibling_selector")


def _q(s):
    return s.replace("'", "''")


def _sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def engine_identity():
    """What executed the selectors. Store with every batch."""
    commit = subprocess.run(["git", "-C", SD, "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    ext_mtime = os.path.getmtime(EXT) if os.path.exists(EXT) else None
    return {"cli": CLI, "extension": EXT, "extension_mtime": ext_mtime,
            "sitting_duck_checkout_head": commit, "macros": MACROS,
            "macros_sha256": _sha256_file(MACROS) if os.path.exists(MACROS) else None}


def _table(fixture):
    return "fx_" + fixture.replace("-", "_")


def _run_script(lines, timeout=None):
    """Run a CLI script; stdout and stderr MERGED so errors stay in order.

    timeout: seconds, default ASTCSS_SCRIPT_TIMEOUT or 3600. A 90-pair training batch with
    c-duckhts combinators ran past an hour in one process (2026-09-15); shard it with
    ASTCSS_EXEC_JOBS rather than only raising this."""
    if timeout is None:
        timeout = int(os.environ.get("ASTCSS_SCRIPT_TIMEOUT", "3600"))
    # A per-process cap (2026-09-15): one suite-1 verify process reached 35 GB on c-duckhts and the
    # kernel OOM-killed the run. With a cap, a runaway selector query fails as that query's error.
    limits = ["SET memory_limit='%s';" % os.environ.get("ASTCSS_DUCKDB_MEMORY", "6GB"),
              "SET threads=%d;" % int(os.environ.get("ASTCSS_DUCKDB_THREADS", "4"))]
    script = "\n".join(["LOAD '%s';" % _q(EXT)] + limits + [".read %s" % MACROS,
                        ".mode list", ".headers off"] + lines) + "\n"
    out = subprocess.run([CLI, "-unsigned", "-noheader"], input=script,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, timeout=timeout)
    return out.stdout.splitlines()


def _collect(lines, tag):
    """-> {qid: {"payload": str} | {"error": str}} for '@@BEGIN qid' blocks."""
    res, cur = {}, None
    for line in lines:
        if line.startswith("@@BEGIN "):
            cur = line[len("@@BEGIN "):].strip()
            continue
        if cur is None or cur in res:
            continue
        if line.startswith(tag + " "):
            res[cur] = {"payload": line[len(tag) + 1:]}
        elif "Error" in line:
            res[cur] = {"error": line.strip()}
    return res


# ---------------------------------------------------------------------------
# Parsing selectors and building relaxations
# ---------------------------------------------------------------------------

CALIB = ".fn#main"


def parse_selectors(selectors):
    """-> {selector: [node dict]} using sitting_duck's own CSS grammar."""
    uniq = sorted(set(selectors) | {CALIB})
    lines = []
    for i, sel in enumerate(uniq):
        lines.append("SELECT '@@BEGIN p%d';" % i)
        lines.append(
            "SELECT '@@PARSE ' || coalesce(string_agg(node_id || '|' || coalesce(parent_id, -1) || '|' || "
            "type || '|' || start_column || '|' || end_column, ';' ORDER BY node_id), '') "
            "FROM parse_ast('%s', 'css', source := 'full');" % _q(sel))   # source := 'full' adds start/end_column
    got = _collect(_run_script(lines), "@@PARSE")
    parsed = {}
    for i, sel in enumerate(uniq):
        r = got.get("p%d" % i, {"error": "no output"})
        if "error" in r:
            parsed[sel] = {"error": r["error"]}
            continue
        nodes = []
        for rec in filter(None, r["payload"].split(";")):
            parts = rec.split("|")
            if len(parts) != 5:          # a token type containing '|' would land here
                raise ValueError("unexpected parse record %r for selector %r" % (rec, sel))
            nid, pid, typ, start, end = parts
            nodes.append({"id": int(nid), "parent": int(pid), "type": typ,
                          "s": int(start), "e": int(end)})
        parsed[sel] = nodes
    return parsed


def _calibrate(parsed):
    """Find how parse_ast columns map onto Python string offsets -- measured, not assumed."""
    nodes = parsed[CALIB]
    if isinstance(nodes, dict):
        # An engine error must surface as itself, never as a Python TypeError
        # three frames later -- that is the silent-failure shape this module
        # exists to prevent.
        raise RuntimeError("calibration parse of %r failed in the engine: %s"
                           % (CALIB, nodes.get("error")))
    idn = next((n for n in nodes if n["type"] == "id_name"), None)
    if idn is None:
        raise RuntimeError("calibration parse of %r has no id_name node: %r" % (CALIB, nodes))
    for base in (0, 1):
        for end_adj in (0, 1):
            if CALIB[idn["s"] - base: idn["e"] - base + end_adj] == "main":
                return base, end_adj
    raise RuntimeError("cannot map parse_ast columns onto selector text: %r" % idn)


def relaxations(selector, nodes, base, end_adj):
    """-> [(label, relaxed_selector)], one per removable modifier outside :has/:not args."""
    if isinstance(nodes, dict):
        return []
    by_id = {n["id"]: n for n in nodes}
    kids = {}
    for n in nodes:
        kids.setdefault(n["parent"], []).append(n)
    for k in kids.values():
        k.sort(key=lambda n: n["s"])

    def in_args(n):
        p = by_id.get(n["parent"])
        while p is not None:
            if p["type"] == "arguments":
                return True
            p = by_id.get(p["parent"])
        return False

    def span(n):
        return n["s"] - base, n["e"] - base + end_adj

    out = []
    for n in nodes:
        if in_args(n):
            continue
        ch = kids.get(n["id"], [])
        cut = None
        if n["type"] == "id_selector":
            h = next((c for c in ch if c["type"] == "#"), None)
            idn = next((c for c in ch if c["type"] == "id_name"), None)
            if h and idn:
                cut = (span(h)[0], span(idn)[1], "#" + selector[span(idn)[0]:span(idn)[1]])
        elif n["type"] == "attribute_selector":
            lb = next((c for c in ch if c["type"] == "["), None)
            rb = next((c for c in reversed(ch) if c["type"] == "]"), None)
            if lb and rb:
                cut = (span(lb)[0], span(rb)[1], selector[span(lb)[0]:span(rb)[1]])
        elif n["type"] == "pseudo_class_selector":
            colon = next((c for c in ch if c["type"] == ":"), None)
            if colon:
                cut = (span(colon)[0], span(n)[1], selector[span(colon)[0]:span(n)[1]])
        elif n["type"] in COMBINATORS:
            steps = [c for c in ch if c["type"] not in (">", "+", "~")]
            if len(steps) >= 2:
                cut = (span(steps[0])[0], span(steps[-1])[0],
                       "step " + selector[span(steps[0])[0]:span(steps[0])[1]])
        if cut:
            a, b, label = cut
            relaxed = (selector[:a] + selector[b:]).strip()
            if relaxed and relaxed != selector:
                out.append(("drop " + label, relaxed))
    return out


# ---------------------------------------------------------------------------
# Executing and judging
# ---------------------------------------------------------------------------

_CACHE_UNSTABLE = ("no output", "timeout", "timed out", "out of memory", "memory limit", "interrupt")


@functools.lru_cache(maxsize=None)
def _engine_key():
    """What decides a result besides the fixture and the selector: the CLI and extension binaries
    (content hashes, so a rebuild of the same code keeps the cache and a swapped file doesn't)
    and the selector macros."""
    parts = [_sha256_file(p) if os.path.exists(p) else "missing:" + p for p in (CLI, EXT, MACROS)]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@functools.lru_cache(maxsize=None)
def _fixture_key(fx):
    """Every file the fixture's glob expands to, by path, size and mtime (fixtures are pinned copies)."""
    pattern = os.path.join(HERE, FIXTURES[fx])
    h = hashlib.sha256()
    for f in sorted(glob.glob(pattern, recursive=True)):
        st = os.stat(f)
        h.update(("%s\0%d\0%d\n" % (os.path.relpath(f, HERE), st.st_size, st.st_mtime_ns)).encode())
    return h.hexdigest()


class _ResultCache:
    """Engine results keyed on (engine, fixture content, selector) in a sqlite file under workspace/
    (ASTCSS_ENGINE_CACHE_DIR). Deterministic errors (a refused selector) are cached; timeouts,
    missing output and memory errors are not. ASTCSS_ENGINE_CACHE=0 turns it off."""

    def __init__(self):
        import sqlite3
        d = os.environ.get("ASTCSS_ENGINE_CACHE_DIR", os.path.join(HERE, "workspace", "cache"))
        os.makedirs(d, exist_ok=True)
        self.db = sqlite3.connect(os.path.join(d, "engine-results.sqlite"), timeout=120)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS results (engine TEXT, fixture TEXT, selector TEXT, "
                        "payload TEXT, created REAL, PRIMARY KEY (engine, fixture, selector))")
        self.engine = _engine_key()

    def get(self, fx, sel):
        row = self.db.execute("SELECT payload FROM results WHERE engine=? AND fixture=? AND selector=?",
                              (self.engine, _fixture_key(fx), sel)).fetchone()
        return json.loads(row[0]) if row else None

    def put_many(self, items):
        rows = []
        for fx, sel, res in items:
            if "error" in res and any(u in res["error"].lower() for u in _CACHE_UNSTABLE):
                continue
            rows.append((self.engine, _fixture_key(fx), sel, json.dumps(res), time.time()))
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO results VALUES (?, ?, ?, ?, ?)", rows)


def execute(queries):
    """queries: [(qid, fixture, selector)] -> {qid: {"nodes": [...]} | {"error": str}}

    Identical (fixture, selector) queries run once, and results come from the result cache
    when this engine already answered them (_ResultCache). Measured 2026-09-15 on the
    sd-20260914-1835 engine: parsing all of c-duckhts costs 0.16 s, but every ast_select_from
    costs ~6 s of planning whatever the table size (the same on a 1-node table), so the
    number of distinct engine calls is what verification time is made of.

    ASTCSS_EXEC_JOBS=N splits the remaining queries across N CLI processes; sharding is
    near-linear. Each shard parses its own fixtures; results are identical to a single process."""
    cache = _ResultCache() if os.environ.get("ASTCSS_ENGINE_CACHE", "1") != "0" else None
    res, first, todo = {}, {}, []
    for qid, fx, sel in queries:
        hit = cache.get(fx, sel) if cache else None
        if hit is not None:
            res[qid] = hit
        elif (fx, sel) not in first:
            first[(fx, sel)] = qid
            todo.append((qid, fx, sel))
    got = _execute_sharded(todo) if todo else {}
    if cache and todo:
        cache.put_many([(fx, sel, got[qid]) for qid, fx, sel in todo if qid in got])
    for qid, fx, sel in queries:
        if qid not in res:
            res[qid] = got.get(first[(fx, sel)], {"error": "no output for query"})
    return res


def _execute_sharded(queries):
    jobs = int(os.environ.get("ASTCSS_EXEC_JOBS", "1"))
    if jobs > 1 and len(queries) > 1:
        import concurrent.futures
        shards = [queries[i::jobs] for i in range(min(jobs, len(queries)))]
        res = {}
        with concurrent.futures.ThreadPoolExecutor(len(shards)) as ex:
            for part in ex.map(_execute_one, shards):
                res.update(part)
        return res
    return _execute_one(queries)


def _execute_one(queries):
    lines = []
    for fx in sorted({f for _, f, _ in queries}):
        pattern = os.path.join(HERE, FIXTURES[fx])
        if not glob.glob(pattern, recursive=True):
            raise FileNotFoundError(pattern)
        lines.append("CREATE TABLE %s AS SELECT * FROM read_ast('%s');" % (_table(fx), _q(pattern)))
    for qid, fx, sel in queries:
        lines.append("SELECT '@@BEGIN %s';" % qid)
        lines.append(
            "SELECT '@@ROWS ' || coalesce(string_agg(regexp_replace(file_path, '.*/', '') || ':' || node_id, ',' "
            "ORDER BY file_path, node_id), '') FROM ast_select_from('%s', '%s');" % (_table(fx), _q(sel)))
    got = _collect(_run_script(lines), "@@ROWS")
    res = {}
    for qid, _, _ in queries:
        r = got.get(qid, {"error": "no output for query"})
        res[qid] = r if "error" in r else {"nodes": [k for k in r["payload"].split(",") if k]}
    return res


def _digest(nodes):
    return hashlib.sha256(",".join(nodes).encode()).hexdigest()


def verify(pairs):
    """pairs: dicts with id, fixture, selector, optional distractors.

    -> {pair_id: {"ok": bool, "reasons": [...], "reference": {...}, "relaxations": [...], "distractors": [...]}}
    """
    parsed = parse_selectors([p["selector"] for p in pairs])
    base, end_adj = _calibrate(parsed)
    queries, plan = [], {}
    for p in pairs:
        pid, fx = p["id"], p["fixture"]
        queries.append((pid + ":ref", fx, p["selector"]))
        rel = relaxations(p["selector"], parsed.get(p["selector"]), base, end_adj)
        for i, (label, sel) in enumerate(rel):
            queries.append(("%s:rel%d" % (pid, i), fx, sel))
        for i, sel in enumerate(p.get("distractors", [])):
            queries.append(("%s:dis%d" % (pid, i), fx, sel))
        plan[pid] = rel
    got = execute(queries)

    report = {}
    for p in pairs:
        pid, reasons = p["id"], []
        ref = got[pid + ":ref"]
        entry = {"ok": False, "reasons": reasons, "relaxations": [], "distractors": []}
        report[pid] = entry
        if "error" in ref:
            reasons.append("reference errors: " + ref["error"])
            continue
        nodes = ref["nodes"]
        entry["reference"] = {"count": len(nodes), "sha256": _digest(nodes), "nodes": nodes}
        if not MIN_NODES <= len(nodes) <= MAX_NODES:
            reasons.append("reference returns %d nodes (need %d..%d)" % (len(nodes), MIN_NODES, MAX_NODES))
        for i, (label, sel) in enumerate(plan[pid]):
            r = got["%s:rel%d" % (pid, i)]
            if "error" in r:
                verdict = "inconclusive: relaxed selector errors"
                reasons.append("%s -> %s" % (label, verdict))
            elif r["nodes"] == nodes:
                verdict = "VACUOUS: same %d nodes without it" % len(nodes)
                reasons.append("%s is not load-bearing" % label)
            else:
                verdict = "load-bearing (%d -> %d nodes)" % (len(nodes), len(r["nodes"]))
            entry["relaxations"].append({"label": label, "selector": sel, "verdict": verdict})
        for i, sel in enumerate(p.get("distractors", [])):
            r = got["%s:dis%d" % (pid, i)]
            if "error" in r:
                verdict = "REJECTED: distractor does not parse/execute"
                reasons.append("distractor %r errors" % sel)
            elif r["nodes"] == nodes:
                verdict = "REJECTED: distractor matches the reference"
                reasons.append("distractor %r matches the reference" % sel)
            else:
                verdict = "ok (%d nodes)" % len(r["nodes"])
            entry["distractors"].append({"selector": sel, "verdict": verdict})
        entry["ok"] = not reasons
    return report


if __name__ == "__main__":
    # Self-test: each gate on a pair whose behaviour was observed by hand first.
    cases = [
        {"id": "accept", "fixture": "py-variety", "selector": ".fn#main",
         "distractors": [".class#main", ".fn#mian"]},
        {"id": "vacuous", "fixture": "py-variety", "selector": ".class:not([bases])"},
        # 46 nodes: inside the 1..50 bound, and its :not(:has()) is load-bearing -> accepted
        {"id": "in-bounds", "fixture": "py-variety", "selector": ".fn:not(:has(.call))"},
        # 84 nodes: over the upper bound
        {"id": "too-many", "fixture": "py-variety", "selector": ".fn"},
        {"id": "empty", "fixture": "py-variety", "selector": ".class > .fn[name=\"__init__\"]"},
        # every __init__ is already inside a class, so the .class step changes nothing on this
        # fixture: a model that omitted it would still execution-match -> rejected
        {"id": "redundant-step", "fixture": "py-variety", "selector": ".class .fn#__init__",
         "distractors": [".class .fn"]},
    ]
    print(json.dumps({"engine": engine_identity()}, indent=2))
    rep = verify(cases)
    for c in cases:
        r = rep[c["id"]]
        ref = r.get("reference", {})
        print("\n%-10s %-34s ok=%-5s nodes=%s" % (c["id"], c["selector"], r["ok"], ref.get("count")))
        for x in r["relaxations"]:
            print("    relax  %-28s %-22s %s" % (x["label"], x["selector"], x["verdict"]))
        for x in r["distractors"]:
            print("    distr  %-51s %s" % (x["selector"], x["verdict"]))
        for why in r["reasons"]:
            print("    REASON %s" % why)
