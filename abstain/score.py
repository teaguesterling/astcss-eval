"""Score abstention as a 2x2, because one number hides the trade.

    answerable + right selector      CORRECT
    answerable + wrong selector      error
    answerable + declined            OVER-REFUSAL   <- the cost of teaching abstention
    unanswerable + declined          CORRECT REFUSAL
    unanswerable + a selector        INVENTION      <- what we are trying to remove

A model that declines everything scores perfectly on invention and terribly on over-refusal.
Reporting both is the only honest way to read it.
"""
import json, os, re, sys, glob, collections
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import verify as V

pairs = {}
for f in glob.glob(os.path.join(HERE, "abstain/pairs/accepted-*.jsonl")):
    for l in open(f):
        if l.strip():
            r = json.loads(l); pairs[r["id"]] = r

DECLINE = re.compile(r'^\s*(NONE|CANNOT|N/?A)\b', re.I)

def main():
    print("%-22s %5s | %-26s | %-26s" % ("run", "n", "ANSWERABLE (16)", "UNANSWERABLE (33)"))
    print("%-22s %5s | %7s %7s %9s | %9s %9s" % ("", "", "right", "wrong", "over-ref", "declined", "invented"))
    for d in sys.argv[1:]:
        rp = os.path.join(HERE, d, "responses.jsonl")
        if not os.path.exists(rp): print("%-22s (no responses)" % d); continue
        resp = {}
        for l in open(rp):
            if l.strip():
                r = json.loads(l); resp[r["id"]] = (r.get("response") or r.get("prediction") or "").strip()
        # one engine pass over every selector actually offered for an answerable pair
        q, want = [], {}
        for pid, p in pairs.items():
            got = resp.get(pid, "")
            if p["answerable"] and got and not DECLINE.match(got):
                q.append((pid, p["fixture"], got)); want[pid] = p["reference"]["sha256"]
        ex = V.execute(q) if q else {}
        c = collections.Counter(); misfire = []
        for pid, p in pairs.items():
            got = resp.get(pid, "")
            declined = bool(DECLINE.match(got))
            if p["answerable"]:
                if declined: c["over"] += 1; misfire.append(("OVER-REFUSED", pid, p["nl"], got))
                else:
                    r = ex.get(pid, {})
                    if "error" not in r and V._digest(r.get("nodes", [])) == want.get(pid): c["right"] += 1
                    else: c["wrong"] += 1
            else:
                if declined: c["decl"] += 1
                else: c["inv"] += 1; misfire.append(("INVENTED", pid, p["nl"], got))
        n = len(pairs)
        print("%-22s %5d | %6d  %6d  %8d | %8d  %8d" % (
            d.split("/")[-1], n, c["right"], c["wrong"], c["over"], c["decl"], c["inv"]))
        for kind, pid, nl, got in misfire[:6]:
            print("      %-13s %-34s -> %s" % (kind, nl[:34], got[:40]))
if __name__ == "__main__":
    main()
