"""A five-field cron expression, expanded to the set of minutes it fires on.

No dependency: the workshop should not open with a pip install. Fields are
minute hour day-of-month month day-of-week, each one of

    *          every value
    5          one value
    1-5        an inclusive range
    */15       every 15th value from the start of the range
    1-5/2      every 2nd value across a range
    a,b,c      a comma list of any of the above

Day-of-week 0 and 7 both mean Sunday. Month and weekday names are not supported,
which keeps the grammar small enough to teach in one slide.
"""
RANGES = {"minute": (0, 59), "hour": (0, 23), "dom": (1, 31), "month": (1, 12), "dow": (0, 6)}
FIELDS = ("minute", "hour", "dom", "month", "dow")


class CronError(ValueError):
    pass


def _field(text, name):
    lo, hi = RANGES[name]
    out = set()
    for part in text.split(","):
        step = 1
        if "/" in part:
            part, _, raw = part.partition("/")
            if not raw.isdigit() or int(raw) == 0:
                raise CronError("bad step %r in %s" % (raw, name))
            step = int(raw)
        if part == "*":
            start, end = lo, hi
        elif "-" in part.lstrip("-"):
            a, _, b = part.partition("-")
            if not (a.isdigit() and b.isdigit()):
                raise CronError("bad range %r in %s" % (part, name))
            start, end = int(a), int(b)
        elif part.isdigit():
            start = end = int(part)
        else:
            raise CronError("bad term %r in %s" % (part, name))
        if name == "dow":
            start, end = (0 if start == 7 else start), (0 if end == 7 else end)
        if start > end or start < lo or end > hi:
            raise CronError("%s out of range: %r" % (name, part))
        out.update(range(start, end + 1, step))
    return frozenset(out)


def parse(expr):
    """-> {field: frozenset(values)}; raises CronError on anything malformed."""
    parts = (expr or "").strip().split()
    if len(parts) != 5:
        raise CronError("expected 5 fields, got %d" % len(parts))
    return {name: _field(text, name) for name, text in zip(FIELDS, parts)}


def signature(expr):
    """The SET OF FIRING TIMES, as a canonical object.

    This is the whole point: two different strings that fire at the same times have the
    same signature. `*/15` and `0,15,30,45` are not equal as text and are equal here.
    """
    f = parse(expr)
    return tuple(sorted(f[name]) for name in FIELDS)


def equivalent(a, b):
    """Do these two cron expressions fire at exactly the same times?"""
    try:
        return signature(a) == signature(b)
    except CronError:
        return False
