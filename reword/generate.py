"""Reword the sample with one generator, batched, with the identifier guard applied per item.

BATCHED because a process spawn per request (claude -p) or a model swap per request (the
Tiiny serves one model at a time) would dominate the cost. A numbered list in, a numbered list
out, matched by NUMBER -- never by position, since a generator that drops or merges an item
would silently shift every later answer onto the wrong query.

Backends:
  tiiny:<model>    the device's OpenAI endpoint, bearer from pcsvr auth_data
  claude:<model>   `claude -p --model <model>`
  ollama:<model>   the local daemon (contends with training for VRAM -- run these after)
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request

SYS = """You rewrite a developer's code-search request using different words.

Rules, for every item:
- Keep the meaning EXACTLY. Definitions stay definitions; call sites stay call sites.
- Change the wording substantially. Do not reuse the original's phrasing.
- Copy every identifier (function, class, variable name) EXACTLY, character for character.
- Keep it a REQUEST, not a sentence about one.

Reply with a numbered list, one rewritten request per line, exactly `N. <request>`, in the
same numbering as the input. No preamble, no commentary, no blank lines."""

def idents(css):
    out = set(re.findall(r'#([A-Za-z_][\w$?!]*)', css))
    out |= set(re.findall(r'=\s*"([^"]+)"', css))
    out |= set(re.findall(r':(?:calls|called-by)\(([A-Za-z_][\w$?!]*)\)', css))
    return out

def tiiny_key():
    import glob as g
    m = g.glob(os.path.expanduser("~/.local/share/tiiny-pcsvr/auth_data/*.json"))
    return json.load(open(m[0]))["auth_key"] if m else os.environ.get("TIINY_AUTH_KEY", "")

def call_tiiny(model, prompt, timeout=600):
    body = json.dumps({"model": model, "max_tokens": 3000, "temperature": 0.9,
                       "messages": [{"role": "system", "content": SYS},
                                    {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("http://api.tiiny/v1/chat/completions", data=body,
        headers={"content-type": "application/json", "Authorization": "Bearer " + tiiny_key()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["choices"][0]["message"]["content"]

def call_claude(model, prompt, timeout=600):
    p = subprocess.run(["claude", "-p", SYS + "\n\n" + prompt, "--model", model],
                       capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[:200])
    return p.stdout

def call_ollama(model, prompt, timeout=900):
    body = json.dumps({"model": model, "stream": False, "options": {"temperature": 0.9},
                       "messages": [{"role": "system", "content": SYS},
                                    {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["message"]["content"]

BACKENDS = {"tiiny": call_tiiny, "claude": call_claude, "ollama": call_ollama}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True, help="backend:model, e.g. claude:haiku")
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--sample", default="reword/sample.jsonl")
    a = ap.parse_args()
    backend, model = a.gen.split(":", 1)
    fn = BACKENDS[backend]
    rows = [json.loads(l) for l in open(a.sample) if l.strip()]
    out, stats = [], {"asked": 0, "parsed": 0, "lost_ident": 0, "unchanged": 0, "errors": 0}
    t0 = time.time()
    for i in range(0, len(rows), a.batch):
        chunk = rows[i:i + a.batch]
        prompt = "\n".join("%d. %s" % (j + 1, r["nl"]) for j, r in enumerate(chunk))
        stats["asked"] += len(chunk)
        try:
            txt = fn(model, prompt)
        except Exception as e:
            stats["errors"] += len(chunk)
            print("  batch %d failed: %s" % (i // a.batch, str(e)[:100]), file=sys.stderr)
            continue
        got = {}
        for line in txt.splitlines():
            m = re.match(r'\s*(\d+)[.)]\s+(.+)', line.strip())
            if m: got[int(m.group(1))] = m.group(2).strip().strip('"')
        for j, r in enumerate(chunk):
            t = got.get(j + 1)
            if not t: continue
            stats["parsed"] += 1
            if " ".join(t.lower().split()) == " ".join(r["nl"].lower().split()):
                stats["unchanged"] += 1; continue
            missing = [n for n in idents(r["css"]) if n not in t]
            if missing:
                stats["lost_ident"] += 1; continue
            out.append(dict(r, reworded=t, generator=a.gen))
        print("  %d/%d kept=%d %.0fs" % (i + len(chunk), len(rows), len(out), time.time() - t0),
              flush=True)
    os.makedirs("reword/out", exist_ok=True)
    p = "reword/out/%s.jsonl" % a.gen.replace(":", "_").replace("/", "_")
    with open(p, "w") as fh:
        for r in out: fh.write(json.dumps(r) + "\n")
    print("%-28s kept %3d of %d  %s  -> %s" % (a.gen, len(out), len(rows), stats, p))

if __name__ == "__main__":
    main()
