"""Per-request context construction: the card plus the training examples nearest the request.

A static examples block (card_v1c_fewshot.md) shows every request the same ten pairs.
Retrieval shows each request the K verified training pairs whose wording is closest,
so "classes with a speak method" sees "classes that define validate" rather than
"calls to mkdir".

Similarity is TF-IDF cosine over the training request and its paraphrases, with
identifier-like tokens split (GitHubClient -> git hub client) so names count less than
the shape words around them. Deterministic, no device, no embedding model.

Held-out rules, on top of the drafting gate that already rejected training pairs that
repeat an eval request or (tier 2+) an eval answer:
- an example whose selector is the asking pair's own reference is never shown, whatever
  its tier (a retrieved `.catch` for "every except handler" would hand over a tier-1
  answer the static card only lists among twenty others);
- every response records the example ids it was shown, so any later leak audit can be
  done per pair.
"""
import collections
import glob
import json
import math
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOP = set("a an the of in on to for with that this these those any all every each is are be do does "
           "which what where me show find list give there here it its by from as and or".split())


def tokens(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    return [w for w in re.findall(r"[a-z]+", text.lower().replace("_", " ")) if w not in STOP]


def portable(css):
    """Only semantic classes, names and filters: no bare node type, which is language-specific
    (a Rust `if_expression` would mislead a Python request)."""
    steps = re.sub(r"\[[^\]]*\]|#[\w]+|:not\(|:has\(|\)", " ", css)
    return all(tok.startswith(".") for tok in re.findall(r"[^\s>~+]+", steps))


class Retriever:
    """langs: languages whose pairs are candidates. Python has 26 selector shapes and no
    [name*=] or :not(:has) pair, so other_portable=True also admits other languages' pairs
    whose selector uses only semantic classes (see portable())."""

    def __init__(self, langs=("python",), other_portable=False):
        self.pairs = []
        for path in sorted(glob.glob(os.path.join(HERE, "train/pairs/accepted-*.jsonl"))):
            for line in open(path):
                if line.strip():
                    p = json.loads(line)
                    lang = p["id"].split("-")[1]
                    if not langs or lang in langs or (other_portable and portable(p["css"])):
                        self.pairs.append(p)
        docs = [tokens(" ".join([p["nl"]] + (p.get("paraphrases") or []))) for p in self.pairs]
        df = collections.Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        self.vecs = [self._vec(d) for d in docs]

    def _vec(self, toks):
        tf = collections.Counter(toks)
        v = {t: c * self.idf.get(t, 0.0) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def nearest(self, request, k, exclude_css=()):
        q = self._vec(tokens(request))
        scored = []
        for p, v in zip(self.pairs, self.vecs):
            if p["css"] in exclude_css:
                continue
            scored.append((sum(x * v.get(t, 0.0) for t, x in q.items()), p["id"], p))
        scored.sort(key=lambda s: (-s[0], s[1]))
        out, seen_css = [], set()
        for score, _, p in scored:
            # One example per selector: five "calls to X" pairs teach no more than one.
            if p["css"] in seen_css:
                continue
            seen_css.add(p["css"])
            out.append(p)
            if len(out) == k:
                break
        return out


def with_examples(card, examples):
    """card + example lines in the card's own EXAMPLES format (the card ends with that section)."""
    lines = ["  %-44s%s" % (p["nl"], p["css"]) if len(p["nl"]) < 44 else "  %s  %s" % (p["nl"], p["css"])
             for p in examples]
    return card + "\n".join(lines) + ("\n" if lines else "")
