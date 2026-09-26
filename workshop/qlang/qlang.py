"""A tiny query language, as nested JSON, executed over a fixed in-memory table.

    {"where":    {"color": "red", "price": {"lt": 20}},
     "order_by": {"price": "asc"},
     "limit":    3,
     "select":   ["name", "price"]}

Four clauses, all optional, applied in that order: filter, sort, truncate, project.
No dependency -- a workshop should not open with a pip install.

WHY NESTED, AND WHY FOUR CLAUSES. A flat mini-language (a cron expression, say) is small
enough that a thousand training rows enumerate it, so a fine-tune goes straight to 100% and
there is no curve to observe and no dial worth turning. Four separable clauses give four
separable failure modes: a model can get the filter right and the ordering wrong, and the
per-clause scores say so. That differential is the thing worth teaching.

EQUIVALENCE IS BEHAVIOURAL. Two queries are the same query when they return the same rows
in the same order from the same table -- never when they happen to be the same string.
On integer prices `{"price": {"gt": 10}}` and `{"price": {"gte": 11}}` are one query.
"""
import json

FIELDS = ("name", "color", "price", "stock", "category")
OPS = ("eq", "ne", "gt", "gte", "lt", "lte", "in")


class QueryError(ValueError):
    pass


#: The table. Small enough to print on a slide, varied enough that different queries
#: return different rows -- which is what makes execution comparison meaningful.
TABLE = [
    {"name": "anvil", "color": "black", "price": 45, "stock": 3, "category": "tools"},
    {"name": "awl", "color": "brown", "price": 7, "stock": 22, "category": "tools"},
    {"name": "bucket", "color": "grey", "price": 9, "stock": 14, "category": "garden"},
    {"name": "chisel", "color": "silver", "price": 18, "stock": 9, "category": "tools"},
    {"name": "clamp", "color": "red", "price": 12, "stock": 31, "category": "tools"},
    {"name": "dibber", "color": "brown", "price": 6, "stock": 40, "category": "garden"},
    {"name": "file", "color": "silver", "price": 11, "stock": 17, "category": "tools"},
    {"name": "fork", "color": "green", "price": 15, "stock": 12, "category": "garden"},
    {"name": "gauge", "color": "brass", "price": 34, "stock": 2, "category": "measuring"},
    {"name": "hoe", "color": "green", "price": 21, "stock": 8, "category": "garden"},
    {"name": "kettle", "color": "copper", "price": 38, "stock": 5, "category": "kitchen"},
    {"name": "ladle", "color": "silver", "price": 8, "stock": 26, "category": "kitchen"},
    {"name": "level", "color": "yellow", "price": 27, "stock": 6, "category": "measuring"},
    {"name": "mallet", "color": "brown", "price": 14, "stock": 11, "category": "tools"},
    {"name": "mandoline", "color": "white", "price": 42, "stock": 4, "category": "kitchen"},
    {"name": "peeler", "color": "red", "price": 5, "stock": 48, "category": "kitchen"},
    {"name": "plane", "color": "black", "price": 52, "stock": 2, "category": "tools"},
    {"name": "pot", "color": "terracotta", "price": 4, "stock": 60, "category": "garden"},
    {"name": "rake", "color": "green", "price": 19, "stock": 7, "category": "garden"},
    {"name": "rasp", "color": "silver", "price": 13, "stock": 15, "category": "tools"},
    {"name": "ruler", "color": "yellow", "price": 3, "stock": 55, "category": "measuring"},
    {"name": "scale", "color": "white", "price": 29, "stock": 6, "category": "measuring"},
    {"name": "sieve", "color": "silver", "price": 10, "stock": 19, "category": "kitchen"},
    {"name": "spade", "color": "green", "price": 24, "stock": 9, "category": "garden"},
    {"name": "spatula", "color": "black", "price": 6, "stock": 33, "category": "kitchen"},
    {"name": "square", "color": "brass", "price": 16, "stock": 10, "category": "measuring"},
    {"name": "tamper", "color": "brown", "price": 23, "stock": 5, "category": "garden"},
    {"name": "tongs", "color": "silver", "price": 9, "stock": 21, "category": "kitchen"},
    {"name": "trowel", "color": "red", "price": 8, "stock": 28, "category": "garden"},
    {"name": "vice", "color": "black", "price": 61, "stock": 1, "category": "tools"},
    {"name": "whisk", "color": "silver", "price": 7, "stock": 35, "category": "kitchen"},
    {"name": "wrench", "color": "red", "price": 17, "stock": 13, "category": "tools"},
]


def _match(row, field, cond):
    if field not in FIELDS:
        raise QueryError("unknown field %r" % field)
    v = row[field]
    if not isinstance(cond, dict):                 # bare value means equality
        return v == cond
    if len(cond) != 1:
        raise QueryError("a condition takes exactly one operator, got %r" % sorted(cond))
    (op, arg), = cond.items()
    if op not in OPS:
        raise QueryError("unknown operator %r" % op)
    if op == "in":
        if not isinstance(arg, list):
            raise QueryError("'in' takes a list, got %r" % type(arg).__name__)
        return v in arg
    if op in ("gt", "gte", "lt", "lte") and not isinstance(v, (int, float)):
        raise QueryError("%r is not comparable with %r" % (field, op))
    return {"eq": v == arg, "ne": v != arg, "gt": v > arg,
            "gte": v >= arg, "lt": v < arg, "lte": v <= arg}[op]


def run(query, table=None):
    """Execute a query -> the list of result rows, in order. Raises QueryError if malformed."""
    table = TABLE if table is None else table
    if not isinstance(query, dict):
        raise QueryError("a query is an object, got %s" % type(query).__name__)
    extra = set(query) - {"where", "order_by", "limit", "select"}
    if extra:
        raise QueryError("unknown clause(s): %s" % ", ".join(sorted(extra)))

    rows = list(table)
    where = query.get("where")
    if where is not None:
        if not isinstance(where, dict):
            raise QueryError("'where' is an object, got %s" % type(where).__name__)
        rows = [r for r in rows if all(_match(r, f, c) for f, c in where.items())]

    order = query.get("order_by")
    if order is not None:
        if not isinstance(order, dict) or len(order) != 1:
            raise QueryError("'order_by' takes exactly one field")
        (field, direction), = order.items()
        if field not in FIELDS:
            raise QueryError("unknown field %r" % field)
        if direction not in ("asc", "desc"):
            raise QueryError("direction is 'asc' or 'desc', got %r" % direction)
        # name is the tiebreak so the order is total and the comparison deterministic.
        rows.sort(key=lambda r: (r[field], r["name"]), reverse=(direction == "desc"))

    limit = query.get("limit")
    if limit is not None:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise QueryError("'limit' is a non-negative integer, got %r" % (limit,))
        rows = rows[:limit]

    select = query.get("select")
    if select is not None:
        if not isinstance(select, list) or not select:
            raise QueryError("'select' is a non-empty list of field names")
        for f in select:
            if f not in FIELDS:
                raise QueryError("unknown field %r in select" % f)
        rows = [{f: r[f] for f in select} for r in rows]
    return rows


def parse(text):
    """The first JSON object in a model's reply, or None. Tolerates fences and chatter."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("```")[1] if "```" in s[3:] else s[3:]
        s = s[4:] if s.lower().startswith("json") else s
    start = s.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(s[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except ValueError:
                    return None
    return None


def equivalent(a, b, table=None):
    """Do these two queries return the same rows in the same order?"""
    try:
        return run(a, table) == run(b, table)
    except (QueryError, TypeError):
        return False
