"""Generate the cron corpus. The EXPRESSION is sampled first; the English is rendered FROM it,
so the label is correct by construction rather than by annotation.

    python3 make_corpus.py --out data --train 1200 --valid 150 --eval 120

Held-out-ness is by SHAPE, not by string: the eval draws from shape families the training set
never uses, so a model cannot pass by memorising phrasings.
"""
import argparse, json, os, random

DOWS = [("Monday", 1), ("Tuesday", 2), ("Wednesday", 3), ("Thursday", 4),
        ("Friday", 5), ("Saturday", 6), ("Sunday", 0)]
MONTHS = [("January", 1), ("February", 2), ("March", 3), ("April", 4), ("May", 5), ("June", 6),
          ("July", 7), ("August", 8), ("September", 9), ("October", 10), ("November", 11),
          ("December", 12)]


def clock(h, m):
    ampm = "am" if h < 12 else "pm"
    hh = h % 12 or 12
    return "%d%s" % (hh, ampm) if m == 0 else "%d:%02d%s" % (hh, m, ampm)


def every_n_minutes(rnd):
    n = rnd.choice([2, 5, 10, 15, 20, 30])
    return "*/%d * * * *" % n, rnd.choice([
        "every %d minutes" % n, "run it every %d minutes" % n,
        "kick off a job every %d minutes, all day" % n])


def daily_at(rnd):
    h, m = rnd.randrange(24), rnd.choice([0, 0, 15, 30, 45])
    return "%d %d * * *" % (m, h), rnd.choice([
        "every day at %s" % clock(h, m), "daily at %s" % clock(h, m),
        "once a day, %s" % clock(h, m)])


def weekday_at(rnd):
    h, m = rnd.randrange(6, 22), rnd.choice([0, 0, 30])
    return "%d %d * * 1-5" % (m, h), rnd.choice([
        "every weekday at %s" % clock(h, m),
        "at %s Monday through Friday" % clock(h, m),
        "on business days at %s" % clock(h, m)])


def one_dow(rnd):
    name, d = rnd.choice(DOWS)
    h, m = rnd.randrange(24), rnd.choice([0, 30])
    return "%d %d * * %d" % (m, h, d), rnd.choice([
        "every %s at %s" % (name, clock(h, m)),
        "%ss at %s" % (name, clock(h, m)),
        "once a week, %s at %s" % (name, clock(h, m))])


def monthly_dom(rnd):
    dom = rnd.choice([1, 1, 2, 5, 10, 15, 20, 28])
    h, m = rnd.randrange(24), rnd.choice([0, 30])
    ord_ = {1: "1st", 2: "2nd", 3: "3rd"}.get(dom, "%dth" % dom)
    return "%d %d %d * *" % (m, h, dom), rnd.choice([
        "on the %s of every month at %s" % (ord_, clock(h, m)),
        "monthly, the %s at %s" % (ord_, clock(h, m))])


def hourly_at(rnd):
    m = rnd.choice([0, 5, 15, 30, 45])
    return "%d * * * *" % m, rnd.choice([
        "every hour at %d past" % m if m else "at the top of every hour",
        "hourly, %d minutes past the hour" % m if m else "every hour on the hour"])


def hours_window(rnd):
    """Phrasings are INCLUSIVE on both ends and say so.

    'every hour between 6am and 12pm' was the first wording here and it is ambiguous --
    a reader can reasonably exclude the endpoint, and a 4B model did. An eval item whose
    English admits two defensible answers measures the wording, not the model."""
    a, b = sorted(rnd.sample(range(0, 24), 2))
    if a == b:
        b = min(23, b + 1)
    m = rnd.choice([0, 30])
    return "%d %d-%d * * *" % (m, a, b), rnd.choice([
        "hourly from %s through %s inclusive" % (clock(a, m), clock(b, m)),
        "every hour from %s to %s, including %s" % (clock(a, m), clock(b, m), clock(b, m))])


def every_n_hours(rnd):
    """The minute must be RECOVERABLE FROM THE ENGLISH.

    The first version of this sampled minute 0 or 30 and rendered only 'every 6 hours',
    so 7 of 120 eval items could not be answered from their request at any skill level --
    a free 5.8% ceiling penalty on every model. Either state the minute or fix it at 0."""
    n = rnd.choice([2, 3, 4, 6, 8, 12])
    m = rnd.choice([0, 30])
    if m == 0:
        return "0 */%d * * *" % n, rnd.choice([
            "every %d hours on the hour" % n, "once every %d hours, on the hour" % n])
    return "%d */%d * * *" % (m, n), rnd.choice([
        "every %d hours at half past" % n, "once every %d hours, %d minutes past" % (n, m)])


def in_month(rnd):
    name, mo = rnd.choice(MONTHS)
    dom = rnd.choice([1, 15])
    h = rnd.randrange(24)
    return "0 %d %d %d *" % (h, dom, mo), rnd.choice([
        "on %s %d at %s" % (name, dom, clock(h, 0)),
        "once a year, %s %d at %s" % (name, dom, clock(h, 0))])


def weekend_at(rnd):
    h, m = rnd.randrange(24), rnd.choice([0, 30])
    return "%d %d * * 6,0" % (m, h), rnd.choice([
        "weekends at %s" % clock(h, m),
        "Saturdays and Sundays at %s" % clock(h, m)])


TRAIN_SHAPES = [every_n_minutes, daily_at, weekday_at, one_dow, monthly_dom, hourly_at]
EVAL_SHAPES = [hours_window, every_n_hours, in_month, weekend_at]

CARD = """You turn a plain-English schedule into ONE standard five-field cron expression.

    minute hour day-of-month month day-of-week

Each field is `*` (every value), a number, a range `1-5`, a step `*/15` or `1-5/2`,
or a comma list of those. Day-of-week runs 0-6 with 0 = Sunday. Do not use names.

Reply with the expression only: one line, five fields, no explanation, no backticks.

Examples
    every 5 minutes                  -> */5 * * * *
    every day at 3am                 -> 0 3 * * *
    every weekday at 6:30pm          -> 30 18 * * 1-5
    Tuesdays at noon                 -> 0 12 * * 2
"""


def pool(shapes, n, seed, taken=None):
    """n DISTINCT (request, label) pairs, excluding anything in `taken`.

    The first version of this deduplicated per call, so train and valid were drawn
    independently from the same generator and 80.7% of the validation split turned out to
    be verbatim training rows. The trained model then scored 100% on it, and the val loss
    fell to 0.0001, and neither number meant anything. Dedup has to be GLOBAL across splits.
    """
    rnd = random.Random(seed)
    seen = set(taken or ())
    out, stall = [], 0
    while len(out) < n:
        pair = rnd.choice(shapes)(rnd)
        if pair in seen:
            stall += 1
            if stall > 20000:
                raise SystemExit("cannot draw %d distinct pairs from these shapes; got %d"
                                 % (n, len(out)))
            continue
        stall = 0
        seen.add(pair)
        out.append(pair)
    return out


def as_rows(pairs):
    return [{"messages": [{"role": "system", "content": CARD},
                          {"role": "user", "content": text},
                          {"role": "assistant", "content": expr}]} for expr, text in pairs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--train", type=int, default=1200)
    ap.add_argument("--valid", type=int, default=150)
    ap.add_argument("--eval", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    # mlx_lm expects train.jsonl + valid.jsonl; the PyTorch trainer in the companion article
    # expects train.jsonl + val.jsonl. Writing BOTH names costs nothing and means the same
    # directory feeds either toolchain -- worth doing in a workshop repo where somebody will
    # inevitably try the other one.
    # One pool per shape group, partitioned -- so valid holds UNSEEN INSTANCES of the
    # training shapes, and eval holds unseen SHAPES. Two different questions, two splits.
    train_pairs = pool(TRAIN_SHAPES, a.train, a.seed)
    valid_pairs = pool(TRAIN_SHAPES, a.valid, a.seed + 1, taken=train_pairs)
    eval_pairs = pool(EVAL_SHAPES, a.eval, a.seed + 2)
    assert not (set(train_pairs) & set(valid_pairs)), "train/valid overlap"
    assert not ({t for _, t in train_pairs} & {t for _, t in eval_pairs}), "train/eval overlap"
    splits = (("train", as_rows(train_pairs)),
              ("valid", as_rows(valid_pairs)),
              ("eval", as_rows(eval_pairs)))
    for name, data in splits:
        names = [name] + (["val"] if name == "valid" else [])
        for alias in names:
            with open(os.path.join(a.out, alias + ".jsonl"), "w") as fh:
                for r in data:
                    fh.write(json.dumps(r) + "\n")
        print("%-6s %4d rows -> %s" % (name, len(data),
              ", ".join("%s/%s.jsonl" % (a.out, x) for x in names)))
    open(os.path.join(a.out, "card.md"), "w").write(CARD)


if __name__ == "__main__":
    main()
