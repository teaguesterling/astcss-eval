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
    a, b = sorted(rnd.sample(range(0, 24), 2))
    if a == b:
        b = min(23, b + 1)
    m = rnd.choice([0, 30])
    return "%d %d-%d * * *" % (m, a, b), rnd.choice([
        "every hour between %s and %s" % (clock(a, m), clock(b, m)),
        "hourly from %s to %s" % (clock(a, m), clock(b, m))])


def every_n_hours(rnd):
    n = rnd.choice([2, 3, 4, 6, 8, 12])
    m = rnd.choice([0, 30])
    return "%d */%d * * *" % (m, n), rnd.choice([
        "every %d hours" % n, "once every %d hours" % n])


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


def rows(shapes, n, seed):
    rnd = random.Random(seed)
    seen, out = set(), []
    while len(out) < n:
        expr, text = rnd.choice(shapes)(rnd)
        if (expr, text) in seen:
            continue
        seen.add((expr, text))
        out.append({"messages": [{"role": "system", "content": CARD},
                                 {"role": "user", "content": text},
                                 {"role": "assistant", "content": expr}]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--train", type=int, default=1200)
    ap.add_argument("--valid", type=int, default=150)
    ap.add_argument("--eval", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    # mlx_lm expects train.jsonl and valid.jsonl in one directory.
    for name, data in (("train", rows(TRAIN_SHAPES, a.train, a.seed)),
                       ("valid", rows(TRAIN_SHAPES, a.valid, a.seed + 1)),
                       ("eval", rows(EVAL_SHAPES, a.eval, a.seed + 2))):
        with open(os.path.join(a.out, name + ".jsonl"), "w") as fh:
            for r in data:
                fh.write(json.dumps(r) + "\n")
        print("%-6s %4d rows -> %s/%s.jsonl" % (name, len(data), a.out, name))
    open(os.path.join(a.out, "card.md"), "w").write(CARD)


if __name__ == "__main__":
    main()
