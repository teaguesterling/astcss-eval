# A jQuery-style AST mutator grammar, grounded in mined edits

*Draft, 2026-09-16. Every operation below is justified by a count from 4,823 real edits mined out
of Claude Code transcripts (`editmine/`), diffed by AST (`editmine/astdiff.sql`). Operations that
sound good but nobody performs are called out as such.*

    $(<astcss-selector>).<op>(<args>)[.<op>(<args>)]*

The selector half is **astcss, unchanged**. That is the whole point: it reuses the trained selector
model, the card vocabulary, `ast_select`, and the execution-verified frame. Only the right-hand
side is new.

## The operations, by measured frequency

AST node-type deltas over 2,184 language-mapped edits (added / removed):

| op | node-type evidence | added | removed |
|---|---|---|---|
| `addComment(text, pos?)` | comment | 1140 | 53 |
| `addArg(expr)` / `removeArg(name)` | argument_list, arguments | 1083 | 122 |
| `wrapCall(fn)` / `wrap(before, after)` | call_expression | 1081 | 125 |
| `setCondition(expr)` | if_statement, else/elif | 641 | 83 |
| `setReturn(expr)` | return_statement | 629 | 57 |
| `addParam(p)` / `removeParam(name)` | parameter_declaration, parameters | 435 | 36 |
| `append(code)` / `prepend(code)` | function_definition et al | 430 | 43 |
| `wrapInTry(handler)` | try/catch/except | 137 | 14 |
| `addImport(module)` | preproc_include, import_statement | 125 | 7 |
| `rename(newName)` | (line-mined) | 220 | - |
| `remove()` | (line-mined) | 3 | - |

**Two operations that read well and nobody performs.** Block-level `wrap` occurs 16 times in 4,823
edits, and `delete` 3 times. Expression-level wrapping (`option.first` -> `CompatNameStr(option.first)`)
is the common case at ~1,081, so `wrapCall` earns its place and `wrap(before, after)` does not.

**Two counts not to trust yet.** `comment` leads for the same reason it did under line diffing: a
node-type delta fires on ANY change in comment count, so a large rewrite touching a comment is
counted. The true pure-addComment rate measured 1.6% line-wise. And `arg` + `call/wrap` at ~1,080
each are near-certainly the same operation double-counted, since adding an argument changes
`argument_list` AND its enclosing `call_expression`.

## Design decisions the data forces

**Arguments are named once arity > 1.** The PSS experiment showed positional arguments wrapping
across line breaks is exactly what hid `addArg`/`addParam` from line-based detection, and keyed
arguments are what made PSS representable at arity 2. So: `insertBefore(anchor: ".jump", code: "x = 1")`,
not two positionals.

**`addComment` derives its syntax from the node's language.** `#` for Python/shell, `//` for the C
family and Rust/JS, `--` for SQL. This is the single most language-derivable operation in the set
and the strongest ergonomic case for a declarative op: the model supplies intent, the engine
supplies lexical form. Placement defaults to *before the node*; `pos` accepts `before|inside|after`.

**Composition is shallow.** 275 mined edits carry two operations, 47 three, 11 four. Chains should
be expected at length 2-3, not 10. The commonest pair is comment + wrapCall.

**No `move`.** It spans two separate Edit calls (delete here, insert there), so it is invisible to
any per-edit classifier and only 2 in-record reorders were found. Out of scope until cross-edit
correlation exists.

## Verification, unchanged from the selector frame

Apply with `ast_patch` (byte-exact, pure, refuses overlapping edits), then **re-parse the patched
source and compare node tables** -- not the byte text, since indentation is inherited and would
measure whitespace agreement rather than correctness. Three outcomes as before: verified /
`pending_engine:<issue>` / rejected.

## Training data from our own edits

Mined edits carry `old`/`new` but no selector, so each must have a named definition recoverable
from its `old` fragment to become a pair. `parse_ast_list_table` exposes `name`, `qualified_name`
(full class->method path) and `scope`, so synthesis is mechanical where a definition is present.
The argument side is likewise mechanical for `addParam`/`removeParam`, since `parameters` is a
typed struct list rather than text to be parsed.

The request text remains the open problem, as with selectors: per-edit agent intent exists in only
64 records across both machines (thinking blocks), so requests should be back-translated from the
diff with the wording model and the existing back-translation gate.
