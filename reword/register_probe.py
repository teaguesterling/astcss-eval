"""Does register follow the PROMPT or the MODEL? Same generator, same queries, four targets."""
import json, re, subprocess, sys, statistics
SYSBASE = """You rewrite a developer's code-search request using different words.
Keep the meaning EXACTLY. Copy every identifier character for character.
%s
Reply with a numbered list, `N. <request>`, same numbering as the input. Nothing else."""
rows = [json.loads(l) for l in open("reword/sample.jsonl")][:40]
regs = json.load(open("reword/registers.json"))
prompt = "\n".join("%d. %s" % (i+1, r["nl"]) for i, r in enumerate(rows))
OPEN = ("take me to","jump to","show me","find ","where is","which ","list ","get ")
print("%-12s %5s %6s %8s %8s %8s %8s" % ("target","n","wmed","terse<=4","long>=12","quest?","imper"))
for name, instr in regs.items():
    p = subprocess.run(["claude","-p", SYSBASE % instr + "\n\n" + prompt, "--model","haiku"],
                       capture_output=True, text=True, timeout=600)
    got = [m.group(1).strip() for m in (re.match(r'\s*\d+[.)]\s+(.+)', l) for l in p.stdout.splitlines()) if m]
    if not got: print("%-12s (no output)" % name); continue
    L=[len(t.split()) for t in got]
    print("%-12s %5d %6.0f %7.0f%% %7.0f%% %7.0f%% %7.0f%%" % (name, len(got), statistics.median(L),
        100*sum(1 for t in got if len(t.split())<=4)/len(got),
        100*sum(1 for t in got if len(t.split())>=12)/len(got),
        100*sum(1 for t in got if t.rstrip().endswith("?"))/len(got),
        100*sum(1 for t in got if t.lower().startswith(OPEN))/len(got)))
    print("     e.g. %s" % got[0][:72])
