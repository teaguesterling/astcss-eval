"""Harvest real code edits from Claude Code transcripts, to seed a mutation corpus.

Two goals (Teague, 2026-09-16):
  1. training pairs -- a real edit WITH the request that motivated it
  2. an operation vocabulary -- what kinds of mutation do we actually perform?

Edit tool calls carry {file_path, old_string, new_string}: a before/after pair at a known
path. That is better ground truth than a sed invocation, and it sidesteps the "what to edit
to" problem entirely, because the replacement text is recorded.

Secrets: transcripts contain whatever was on screen. Paths that look like credential stores
are skipped outright, and long hex/base64 runs are redacted inside the retained strings.

usage: python3 extract_edits.py <transcripts_root> <out.jsonl> [machine_label]
"""
import json, os, re, sys, collections

SECRET_PATH = re.compile(r"(\.env|credential|\.pem$|\.key$|secret|token|\.ssh/|id_rsa|\.netrc)", re.I)
LONG_TOKEN = re.compile(r"\b[A-Za-z0-9+/_-]{32,}\b")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
BASH_EDIT = re.compile(r"\b(sed\s+-i|perl\s+-[a-z]*i|awk\b.*>|patch\s|git\s+apply|ed\s+-s|"
                       r"\btee\b|\bmv\b|\bcp\b|rename\b|\bsd\b|comby|ast-grep|jq\s+.*>|yq\s+-i)")

def redact(s, cap=4000):
    if not isinstance(s, str): return ""
    s = LONG_TOKEN.sub("<REDACTED>", s)
    return s[:cap]

def classify(old, new):
    """First-pass operation vocabulary. This histogram is the point of the exercise."""
    o, n = (old or "").strip(), (new or "").strip()
    if not o and n: return "insert"
    if o and not n: return "delete"
    if o == n:      return "noop"
    if o in n:
        pre, post = n.split(o, 1)[0], n.split(o, 1)[1]
        if pre.strip() and post.strip(): return "wrap"
        if post.strip():                 return "append"
        if pre.strip():                  return "prepend"
    if n in o:                           return "shrink"
    ow, nw = o.split(), n.split()
    if len(ow) == len(nw) and sum(a != b for a, b in zip(ow, nw)) == 1: return "rename_token"
    if abs(len(ow) - len(nw)) <= 2 and o.splitlines()[:1] != n.splitlines()[:1]: return "signature_edit"
    return "replace"

def walk(root):
    for dirpath, _, names in os.walk(root):
        for nm in names:
            if nm.endswith(".jsonl"): yield os.path.join(dirpath, nm)

def blocks_before(cont, idx, since):
    """Narration ADJACENT to this tool_use: text appearing after the PREVIOUS tool_use only.

    First attempt collected every text block from the start of the content array, which meant
    an assistant turn with one preamble and six tool calls gave all six the same string -- the
    turn's opening prose, describing none of the edits. That is 100% attachment and 0% signal,
    and it would teach a model to map unrelated prose onto an edit.

    Taking only text since the previous tool_use yields nothing for batched calls. That is the
    honest answer: those edits have no per-edit description, and are labelled intent_scope
    "none" rather than back-filled.
    """
    prose, think = [], []
    for c in cont[since:idx]:
        if not isinstance(c, dict):
            continue
        if c.get("type") == "text" and c.get("text"):
            prose.append(c["text"])
        elif c.get("type") == "thinking" and c.get("thinking"):
            think.append(c["thinking"])
    return " ".join(prose).strip(), " ".join(think).strip()


def text_of(content):
    if isinstance(content, str): return content
    if isinstance(content, list):
        return " ".join(c.get("text","") for c in content
                        if isinstance(c, dict) and c.get("type")=="text")
    return ""

def main():
    root, out = sys.argv[1], sys.argv[2]
    machine = sys.argv[3] if len(sys.argv) > 3 else os.uname().nodename
    files = list(walk(root))
    with_intent = 0
    ops = collections.Counter(); exts = collections.Counter()
    kept = skipped = bash_kept = 0
    with open(out, "w") as fh:
        for f in files:
            last_user = ""
            prev_assistant = ""
            prev_thinking = ""
            shared_n = 0
            think_n = 0
            try: lines = open(f, errors="replace").read().splitlines()
            except Exception: continue
            for line in lines:
                line = line.strip()
                if not line: continue
                try: r = json.loads(line)
                except Exception: continue
                msg = r.get("message") or {}
                if r.get("type") == "user" or msg.get("role") == "user":
                    t = text_of(msg.get("content"))
                    if t and not t.startswith("<") and len(t) < 2000: last_user = t.strip()
                cont = msg.get("content")
                if not isinstance(cont, list): continue
                # Assistant messages here are EITHER prose OR tool calls, never both, so the
                # intent for a call is the most recent prose message. How many calls share it
                # is the signal: the first consumer is plausibly describing this edit, later
                # ones inherit a preamble that describes the turn. Marked, not hidden.
                since = 0
                for idx, c in enumerate(cont):
                    if not (isinstance(c, dict) and c.get("type") == "tool_use"):
                        continue
                    inline, inline_think = blocks_before(cont, idx, since)
                    since = idx + 1
                    # Edit has NO description field, and the prose preceding a call is status
                    # narration to the user. The agent's real per-edit reasoning is in the
                    # thinking message just before the call -- persisted in 5,023 messages here.
                    thinking = inline_think or prev_thinking
                    think_scope = ("inline" if inline_think else
                                   "first" if (prev_thinking and think_n == 0) else
                                   "shared" if prev_thinking else "none")
                    think_n += 1
                    intent = inline or prev_assistant
                    if inline:                      scope = "inline"
                    elif prev_assistant and shared_n == 0: scope = "first"
                    elif prev_assistant:            scope = "shared"
                    else:                           scope = "none"
                    shared_n += 1
                    name, inp = c.get("name"), (c.get("input") or {})
                    if name == "Bash":
                        pass
                    if name in EDIT_TOOLS:
                        path = str(inp.get("file_path") or inp.get("notebook_path") or "")
                        if not path or SECRET_PATH.search(path): skipped += 1; continue
                        old = inp.get("old_string") or inp.get("old_source") or ""
                        new = inp.get("new_string") or inp.get("new_source") or inp.get("content") or ""
                        op = classify(old, new)
                        ops[op] += 1
                        ext = os.path.splitext(path)[1].lower() or "(none)"
                        exts[ext] += 1
                        kept += 1
                        fh.write(json.dumps({"machine": machine, "kind": "edit", "tool": name,
                            "op": op, "ext": ext, "file_path": path, "ts": r.get("timestamp"),
                            "intent": redact(intent, 900), "intent_scope": scope,
                            "thinking": redact(thinking, 900), "think_scope": think_scope,
                            "request": redact(last_user, 600),
                            "old": redact(old), "new": redact(new)}) + "\n")
                        if intent: with_intent += 1
                    elif name == "Bash":
                        cmd = str(inp.get("command") or "")
                        if cmd and BASH_EDIT.search(cmd) and not SECRET_PATH.search(cmd):
                            bash_kept += 1
                            fh.write(json.dumps({"machine": machine, "kind": "bash",
                                "ts": r.get("timestamp"), "intent": redact(intent, 900),
                                "intent_scope": scope,
                                "description": redact(str(inp.get("description") or ""), 300),
                                "thinking": redact(thinking, 900), "think_scope": think_scope,
                                "request": redact(last_user, 600),
                                "command": redact(cmd, 800)}) + "\n")
                if msg.get("role") == "assistant" and isinstance(cont, list):
                    t = text_of(cont)
                    if t.strip():
                        prev_assistant = t.strip()
                        shared_n = 0
                    th = " ".join(c.get("thinking","") for c in cont
                                  if isinstance(c, dict) and c.get("type") == "thinking").strip()
                    if th:
                        prev_thinking = th
                        think_n = 0
    print("transcripts scanned : %d" % len(files))
    print("edit records kept   : %d   (skipped for secret-ish path: %d)" % (kept, skipped))
    print("bash edit commands  : %d" % bash_kept)
    print("edits WITH agent intent: %d  (%.0f%%)" % (with_intent, 100.0*with_intent/max(kept,1)))
    print("\noperation histogram (the vocabulary question):")
    for o, c in ops.most_common(): print("  %-16s %6d  %4.1f%%" % (o, c, 100.0*c/max(kept,1)))
    print("\ntop file types:")
    for e, c in exts.most_common(12): print("  %-10s %6d" % (e, c))
    print("\n-> %s" % out)

if __name__ == "__main__":
    main()
