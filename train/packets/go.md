# Drafting packet: Go

Read `train/BRIEF.md` first: it has the pair format, the tiers, the engine and verifier rules,
the draft -> verify -> fix loop, and what you must not touch. This packet adds your language.

- **Target:** 50 accepted pairs, about 12 per tier (T1-T4).
- **Candidate files:** `train/candidates/go-b1.jsonl`, then `go-b1-r1.jsonl`, `go-b2.jsonl`, ...
- **Verify:** `/home/teague/.local/share/venv/bin/python pilot.py train/candidates/<batch>.jsonl <batch> train`
  (batch id = file name without `.jsonl`, run from `/home/teague/Projects/astcss-eval/trees/train/multilang`).
- **Ids:** `tr-go-t<tier>-<nnnn>`, never reused across your batches.
- **Fixtures you may use:** `go-rosetta`.

## The card the model is prompted with

Write selectors in this vocabulary. A class not on this card must not appear in your pairs.

```text
You translate a developer's plain-English request into ONE astcss selector over a Go
code tree. Reply with the selector only: one line, no quotes, no backticks, no explanation.

SEMANTIC CLASSES (cross-language; prefer these)
  .fn .func .method       function or method definitions  (function_declaration, method_declaration, method_elem, func_literal)
  .class                  class definitions  (struct_type, interface_type)
  .var                    variable definitions  (short_var_declaration, parameter_declaration, var_spec, var_declaration)
  .call                   function or method calls  (call_expression, type_conversion_expression)
  .member                 attribute access  (selector_expression, index_expression, slice_expression)
  .import                 import statements  (import_spec, import_declaration)
  .if                     conditionals  (if_statement, expression_case, expression_switch_statement, default_case)
  .loop                   loops  (for_statement, for_clause, range_clause)
  .jump                   return / break / continue / yield  (return_statement)

GO NODE TYPES (exact tree-sitter names, written with no dot, when no class fits)
  function_declaration return_statement import_spec for_statement import_declaration
  if_statement var_declaration

FILTERS ON A NODE (written directly after it, no space)
  #name                   exactly this name:            .fn#main   .call#Println
  [name^="x"]             name starts with x            .fn[name^="parse"]
  [name$="x"]             name ends with x
  [name*="x"]             name contains x
  :has(S)                 contains a descendant matching S     .fn:has(.call#Println)
  :not(:has(S))           contains no descendant matching S    .fn:not(:has(.loop))

COMBINATORS (exactly two steps; filters other than #name go on the second step only)
  A B                     B anywhere inside A          .fn#main .call
  A > B                   B is a direct child of A     source_file > function_declaration
  A ~ B                   B is a later sibling of A    .import ~ .fn
  A + B                   B immediately follows A      .fn + .fn

EXAMPLES
  every function                              .fn
  calls to Println                            .call#Println
  functions whose names start with parse      .fn[name^="parse"]
  calls made inside main                      .fn#main .call
  functions without loops                     .fn:not(:has(.loop))
```

## Notes for every language

- **Don't use** `.arith`, `.cmp`, `.logic`, `.bool`, `.comment`, `.str`.
  Operators count tokens by text (#131), `.bool` is `LITERAL_ATOMIC` (#132),
  `.comment` is the whole METADATA kind: in C/C++ it includes `#include`,
  `type_qualifier`, `storage_class_specifier`, access specifiers; in Rust
  `visibility_modifier`, `attribute_item`, `mutable_specifier`; in Java `modifiers`
  (#134). `.str` counts `string_content` and `escape_sequence` as extra nodes.
- **`:has` / `:not(:has)`**: the verifier checks every such candidate against
  ground truth and rejects disagreements. The engine counts keyword tokens inside
  `:has` (#133). Measured `.fn:has(.fn)` truth vs engine: Python 6-32 vs 182-271,
  Rust 9-46 vs 33-215, JavaScript 37-54 vs 85-89, Go 2 vs 35. C, C++ (except
  1 extra in duckdb-yaml), Java, Bash and SQL agree. Avoid `X:has(X)`.


## Notes for Go — fixture go-rosetta

- **Don't use `.mod`**: it counts `package_clause` as well as `source_file`.
- `.class` is `struct_type`, `interface_type`; `.loop` includes `for_clause` and
  `range_clause` inside a `for_statement`; `.if` includes switch
  `expression_case` / `default_case`. Small fixture (16 files): keep batches small.


## Fixture inventories

Names and counts from the audit. Use real names from these lists; the verifier needs 1-50 matches.

### `go-rosetta` — 16 files from sitting_duck@1a10b7d3d

- **class counts** (don't use any the notes exclude): .fn 38, .class 4, .call 107, .loop 33, .if 22, .jump 26, .try 0, .catch 0, .throw 0, .import 37, .var 74, .member 83, .comp 0, .mod 29
- **functions:** main(14), factorial(4), Cry(3), Kind(3), Name(3), fib(2), bprint(1), fibNumber(1), fibSequence(1), lfactorial(1), numberName(1), pluralizeFirst(1), slur(1)
- **classes:** (none)
- **calls:** Println(15), Printf(12), slur(12), factorial(7), Print(6), NewInt(4), bottles(3), len(3), numberName(3), pluralizeFirst(3), Fields(2), Intn(2), Join(2), bprint(2), int64(2), Add(1), Cry(1), Exp2(1), Gamma(1), Kind(1), Lgamma(1), Mod(1), Modf(1), Mul(1), MulRange(1), Name(1), NewFloat(1), Now(1), Scan(1), Seed(1), SetInt64(1), SetMantExp(1), Sprintf(1), Sqrt(1), UnixNano(1), f(1), fib(1), fibNumber(1), float64(1), int(1), lfactorial(1), make(1), string(1)
- **frequent node types:** identifier(372), expression_list(129), call_expression(106), argument_list(106), interpreted_string_literal(100), interpreted_string_literal_content(98), int_literal(84), field_identifier(81), statement_list(74), selector_expression(68), block(65), type_identifier(63), binary_expression(58), literal_element(46), parameter_list(45), expression_statement(39), :=(36), short_var_declaration(35), function_declaration(27), return_statement(26), import_spec(23), parameter_declaration(21), package_identifier(19), for_statement(17), source_file(16), for_clause(15), import_declaration(14), package_clause(13), escape_sequence(12), index_expression(12), ++(11), inc_statement(11), assignment_statement(10), =(10), +(10), comment(10), if_statement(9), ==(9), expression_case(8), literal_value(8), <(8), <=(8), -(7), var_declaration(7), var_spec(7)
