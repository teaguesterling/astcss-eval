"""Generate the query corpus. The QUERY is sampled first and the English rendered from it,
so labels are correct by construction.

    python3 make_corpus.py --out data --train 1200 --valid 150 --eval 150

HELD OUT BY COMBINATION, NOT BY ELEMENT -- which is the whole point.

The cron version of this workshop held out whole shape FAMILIES: the eval asked for a range
in a field that never once held a range in training. Nothing transferred, at any model size,
because nothing could. 0% before, 0% after, and no curve to observe.

Here every ELEMENT of every eval query appears somewhere in training -- equality filters,
comparisons, `in` lists, ordering, limits, projections -- and only the COMBINATION is new.
A model that has seen {where_eq, order_by} and {order_by, limit} separately is being asked
for {where_eq, order_by, limit}. That is a fair compositional question with a reachable
answer, and it should produce partial credit rather than a floor or a ceiling.
"""
import argparse
import json
import os
import random

CARD = """You turn a plain-English request about a product table into ONE query, as JSON.

The table has: name (text), color (text), price (whole dollars), stock (whole number),
category (text, one of tools / garden / kitchen / measuring).

A query is an object with any of these four clauses, all optional:

    "where"    {field: value}  or  {field: {op: value}}   ops: eq ne gt gte lt lte in
                                                          ("in" takes a list)
                                   several fields are ANDed together
    "order_by" {field: "asc"}  or  {field: "desc"}        exactly one field
    "limit"    a whole number
    "select"   a list of field names

Reply with the JSON object only: no explanation, no backticks.

Examples
    red items                          -> {"where": {"color": "red"}}
    anything under $10                 -> {"where": {"price": {"lt": 10}}}
    most expensive first               -> {"order_by": {"price": "desc"}}
    just the names                     -> {"select": ["name"]}
"""

COLORS = ["red", "green", "silver", "black", "brown", "yellow", "white", "brass"]
CATS = ["tools", "garden", "kitchen", "measuring"]


# ---- clause builders: each returns (clause_dict, english_fragment) ----------------

def c_where_eq(rnd):
    if rnd.random() < 0.5:
        v = rnd.choice(COLORS)
        return {"where": {"color": v}}, rnd.choice(["%s items" % v, "everything %s" % v,
                                                    "the %s ones" % v])
    v = rnd.choice(CATS)
    return {"where": {"category": v}}, rnd.choice(["%s" % v, "items in %s" % v,
                                                   "the %s category" % v])


def c_where_cmp(rnd):
    if rnd.random() < 0.6:
        op, n = rnd.choice([("lt", rnd.choice([10, 15, 20, 25])),
                            ("gt", rnd.choice([20, 25, 30, 40]))])
        word = "under $%d" % n if op == "lt" else "over $%d" % n
        return {"where": {"price": {op: n}}}, rnd.choice(
            [word, "anything %s" % word, "priced %s" % word])
    op, n = rnd.choice([("lt", rnd.choice([5, 10, 15])), ("gt", rnd.choice([20, 30, 40]))])
    word = "fewer than %d in stock" % n if op == "lt" else "more than %d in stock" % n
    return {"where": {"stock": {op: n}}}, rnd.choice([word, "items with %s" % word])


def c_where_in(rnd):
    if rnd.random() < 0.5:
        a, b = rnd.sample(COLORS, 2)
        return {"where": {"color": {"in": [a, b]}}}, rnd.choice(
            ["either %s or %s" % (a, b), "%s and %s items" % (a, b)])
    a, b = rnd.sample(CATS, 2)
    return {"where": {"category": {"in": [a, b]}}}, rnd.choice(
        ["%s or %s" % (a, b), "anything in %s or %s" % (a, b)])


def c_order(rnd):
    field, direction = rnd.choice([("price", "asc"), ("price", "desc"),
                                   ("stock", "asc"), ("stock", "desc")])
    word = {("price", "asc"): ["cheapest first", "sorted by price, lowest first"],
            ("price", "desc"): ["most expensive first", "priciest first"],
            ("stock", "asc"): ["least stocked first", "sorted by stock, lowest first"],
            ("stock", "desc"): ["best stocked first", "most in stock first"]}[(field, direction)]
    return {"order_by": {field: direction}}, rnd.choice(word)


def c_limit(rnd):
    n = rnd.choice([2, 3, 4, 5, 10])
    return {"limit": n}, rnd.choice(["just %d" % n, "the first %d" % n, "top %d" % n])


def c_select(rnd):
    fields = rnd.choice([["name"], ["name", "price"], ["name", "stock"],
                         ["name", "color"], ["name", "price", "stock"]])
    if len(fields) == 1:
        word = rnd.choice(["just the names", "names only"])
    elif len(fields) == 2:
        word = rnd.choice(["showing %s and %s" % (fields[0], fields[1]),
                           "with just %s and %s" % (fields[0], fields[1])])
    else:
        word = "showing %s, %s and %s" % tuple(fields)
    return {"select": fields}, word


# ---- shapes: ordered tuples of clause builders -----------------------------------

W_EQ, W_CMP, W_IN, ORD, LIM, SEL = (c_where_eq, c_where_cmp, c_where_in,
                                    c_order, c_limit, c_select)

#: Every element appears here, and every PAIR the eval needs is here too.
TRAIN_SHAPES = [(W_EQ,), (W_CMP,), (W_IN,), (ORD,), (LIM,), (SEL,),
                (W_EQ, SEL), (ORD, LIM), (W_EQ, ORD), (W_CMP, LIM)]

#: Combinations only. No new element, no new operator, no new field.
EVAL_SHAPES = [(W_EQ, ORD, LIM), (W_CMP, ORD, SEL), (W_IN, ORD, LIM),
               (W_EQ, LIM, SEL), (W_CMP, ORD, LIM, SEL)]


def build(shape, rnd):
    query, parts = {}, []
    for fn in shape:
        clause, words = fn(rnd)
        # two where-builders in one shape would collide; the shapes above never do that
        if "where" in clause and "where" in query:
            query["where"].update(clause["where"])
        else:
            query.update(clause)
        parts.append(words)
    return query, ", ".join(parts)


def pool(shapes, n, seed, taken=None):
    """n distinct (english, query-json) pairs, excluding anything in `taken`.

    Dedup is GLOBAL across splits. The cron corpus deduplicated per call and 80.7% of its
    validation split turned out to be verbatim training rows; the model scored 100% on it
    and the number meant nothing.
    """
    rnd = random.Random(seed)
    seen = set(taken or ())
    out, stall = [], 0
    while len(out) < n:
        query, words = build(rnd.choice(shapes), rnd)
        pair = (words, json.dumps(query, sort_keys=False))
        if pair in seen:
            stall += 1
            if stall > 40000:
                raise SystemExit("cannot draw %d distinct pairs; got %d" % (n, len(out)))
            continue
        stall = 0
        seen.add(pair)
        out.append(pair)
    return out


def as_rows(pairs):
    return [{"messages": [{"role": "system", "content": CARD},
                          {"role": "user", "content": words},
                          {"role": "assistant", "content": q}]} for words, q in pairs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--train", type=int, default=1200)
    ap.add_argument("--valid", type=int, default=150)
    ap.add_argument("--eval", type=int, default=150)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    train = pool(TRAIN_SHAPES, a.train, a.seed)
    valid = pool(TRAIN_SHAPES, a.valid, a.seed + 1, taken=train)
    ev = pool(EVAL_SHAPES, a.eval, a.seed + 2)
    assert not (set(train) & set(valid)), "train/valid overlap"
    assert not ({w for w, _ in train} & {w for w, _ in ev}), "train/eval request overlap"

    # mlx_lm wants valid.jsonl; the PyTorch trainer wants val.jsonl. Write both.
    for name, pairs in (("train", train), ("valid", valid), ("eval", ev)):
        aliases = [name] + (["val"] if name == "valid" else [])
        for alias in aliases:
            with open(os.path.join(a.out, alias + ".jsonl"), "w") as fh:
                for r in as_rows(pairs):
                    fh.write(json.dumps(r) + "\n")
        print("%-6s %4d rows -> %s" % (name, len(pairs),
              ", ".join("%s/%s.jsonl" % (a.out, x) for x in aliases)))
    open(os.path.join(a.out, "card.md"), "w").write(CARD)
    # The trainer writes a run.json beside every checkpoint and folds this in, so that in
    # three weeks a directory of adapters still says which corpus produced which. Without
    # it the trainer saves the epoch weights and THEN dies on the missing file -- which is
    # how the first run of this corpus ended: a valid epoch-1 adapter and a traceback.
    json.dump({"name": "qlang-workshop-v1",
               "task": "plain English -> a four-clause query as JSON over a fixed table",
               "generator": "make_corpus.py --train %d --valid %d --eval %d --seed %d"
                            % (a.train, a.valid, a.eval, a.seed),
               "labels": "correct by construction: the query is sampled first, the English "
                         "rendered from it",
               "held_out": "by clause COMBINATION, not by element -- every element of every "
                           "eval query appears in training; asserted in main()",
               "equivalence": "behavioural: same rows in the same order from the same table",
               "card": "data/card.md",
               "rows": {"train": a.train, "valid": a.valid, "eval": a.eval}},
              open(os.path.join(a.out, "manifest.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
