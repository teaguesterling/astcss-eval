"""Build the mutator card: selector vocabulary + operation table + two worked examples.

Assembled rather than hand-written so the selector half stays byte-identical to card_v1c.md,
which is the validated vocabulary every good result in this project used.

Three things are deliberate, each from a surface-study failure:

  * ARITY IS PROSE, NEVER A BRACKETED TOKEN. The first surface card wrote `remove [0]` under a
    heading "argument count in brackets"; Qwen3-4B transcribed the annotation straight into its
    answers in four of five surfaces, which fabricated an entire ranking.
  * ARGUMENT KEYS ARE NAMED EXPLICITLY. The PSS arm was scored against key names its card never
    supplied, so the model generalised `to:` everywhere. Five of its fourteen failures were that.
  * TWO worked examples, fixed shape, so arms stay comparable.

    python3 mutator/card.py > mutator/card_mut.md
"""
import os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HEADER = """\
You turn a developer's plain-English request into ONE mutation over a Python code tree.

A mutation is written jQuery-style: a selector that picks the nodes, then the operation to apply.

    $('<selector>').<operation>(<arguments>)

Reply with the mutation only: one line, no explanation, no backticks.
"""

OPS = """
OPERATIONS AND WHAT EACH TAKES

  addComment      the comment text. Optionally pos: "before", "inside" or "after"
                  (default is before the node). The comment marker is added for you --
                  write the text, not the # or //.
  addArg          one argument expression, added to a call
  removeArg       the name of a keyword argument to drop from a call
  addParam        one parameter, added to a function definition
  removeParam     the name of a parameter to drop from a function definition
  wrapCall        the name of a function to wrap the selected expression in
  setCondition    the new condition expression
  setReturn       the new return expression
  append          code to add at the END of the selected node's body
  prepend         code to add at the START of the selected node's body
  rename          the new name
  addImport       the whole import line to add

  wrapInTry       takes no argument of its own. Follow it with one or more
                  .on(exception, body) clauses IN ORDER, and optionally .finally(body).
                  Order matters: a narrow exception must come before a broad one.

NAMED ARGUMENTS
  Where an operation takes more than one thing, name them: pos, anchor, code.
  Everything else is a single positional argument.
"""

EXAMPLES = """
EXAMPLES

  rename the helper function to run
    -> $('.fn#helper').rename("run")

  wrap save in a try that returns None on KeyError and logs anything else
    -> $('.fn#save').wrapInTry().on("KeyError", "return None").on("Exception", "log.exception('save failed')")
"""

def vocabulary():
    """card_v1c's selector vocabulary, verbatim from the first heading onward. Its opening
    'reply with the selector only' instruction contradicts a mutation task, so it is dropped."""
    text = open(os.path.join(HERE, "card_v1c.md")).read()
    i = text.find("SEMANTIC CLASSES")
    return text[i:] if i > 0 else text

def build():
    return HEADER + "\n" + vocabulary().rstrip() + "\n" + OPS + EXAMPLES

if __name__ == "__main__":
    sys.stdout.write(build())
