# Drafting packet: Java

Read `train/BRIEF.md` first: it has the pair format, the tiers, the engine and verifier rules,
the draft -> verify -> fix loop, and what you must not touch. This packet adds your language.

- **Target:** 60 accepted pairs, about 15 per tier (T1-T4).
- **Candidate files:** `train/candidates/java-b1.jsonl`, then `java-b1-r1.jsonl`, `java-b2.jsonl`, ...
- **Verify:** `/home/teague/.local/share/venv/bin/python pilot.py train/candidates/<batch>.jsonl <batch> train`
  (batch id = file name without `.jsonl`, run from `/home/teague/Projects/astcss-eval/trees/train/multilang`).
- **Ids:** `tr-java-t<tier>-<nnnn>`, never reused across your batches.
- **Fixtures you may use:** `java-rosetta`.

## The card the model is prompted with

Write selectors in this vocabulary. A class not on this card must not appear in your pairs.

```text
You translate a developer's plain-English request into ONE astcss selector over a Java
code tree. Reply with the selector only: one line, no quotes, no backticks, no explanation.

SEMANTIC CLASSES (cross-language; prefer these)
  .fn .func .method       function or method definitions  (method_declaration, lambda_expression, constructor_declaration, static_initializer)
  .class                  class definitions  (class_declaration, interface_declaration)
  .mod                    the module  (program, package_declaration)
  .var                    variable definitions  (variable_declarator, local_variable_declaration, formal_parameter, field_declaration)
  .call                   function or method calls  (method_invocation, object_creation_expression)
  .import                 import statements  (import_declaration)
  .loop                   loops  (for_statement, while_statement, do_statement)
  .jump                   return / break / continue / yield  (return_statement)
  .try .throw             try blocks, except handlers, raise, finally  (throw_statement, try_statement, try_with_resources_statement)

JAVA NODE TYPES (exact tree-sitter names, written with no dot, when no class fits)
  method_declaration import_declaration return_statement if_statement class_declaration
  lambda_expression

FILTERS ON A NODE (written directly after it, no space)
  #name                   exactly this name:            .fn#main   .call#println   .class#Config
  [name^="x"]             name starts with x            .fn[name^="get"]
  [name$="x"]             name ends with x
  [name*="x"]             name contains x
  :has(S)                 contains a descendant matching S     .fn:has(.call#println)
  :not(:has(S))           contains no descendant matching S    .fn:not(:has(.try))

COMBINATORS (exactly two steps; filters other than #name go on the second step only)
  A B                     B anywhere inside A          .class#Config .fn
  A > B                   B is a direct child of A     .mod > .import
  A ~ B                   B is a later sibling of A    .import ~ .class
  A + B                   B immediately follows A      .fn + .fn

EXAMPLES
  every method                                .fn
  calls to println                            .call#println
  classes whose names end with Exception      .class[name$="Exception"]
  methods of the Config class                 .class#Config .fn
  methods without a try block                 .fn:not(:has(.try))
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


## Notes for Java — fixture java-rosetta

- **Don't use `.if`** (adds the `?` token), **`.catch`** (counts `catch_type` as
  well as `catch_clause`), **`.member`** (adds `::`). Use `if_statement`,
  `ternary_expression`, `catch_clause`, `field_access`.
- `.fn` is `method_declaration`, `lambda_expression`, `constructor_declaration`;
  `.call` is `method_invocation` plus `object_creation_expression`.


## Fixture inventories

Names and counts from the audit. Use real names from these lists; the verifier needs 1-50 matches.

### `java-rosetta` — 30 files from sitting_duck@1a10b7d3d

- **class counts** (don't use any the notes exclude): .fn 70, .class 25, .call 225, .loop 17, .if 47, .jump 27, .try 4, .catch 12, .throw 5, .import 33, .var 206, .member 101, .comp 0, .mod 32
- **functions:** main(20), factorial(4), methodB(3), methodC(3), fib(2), methodA(2), Beer(1), applyAsLong(1), beerCheck(1), bottles(1), factorialBig(1), factorialPositive(1), factorialRec(1), fibInner(1), fibStream(1), fibTailRec(1), get(1), goToStore(1), impl(1), itFibN(1), nextInt(1), onTakeClick(1), party(1), putLastOnWall(1), putOnWall(1), run(1), solve(1), song(1), sum(1), takeOneDown(1)
- **classes:** Beer(4), FizzBuzz(3), HundredDoors(3), Example(2), FizzBuzzJdk12(2), AplusB(1), ExampleImpl(1), Factorial(1), FibUtil(1), Fibonacci(1), IterativeFactorial(1), LargeFactorial(1), NineNineBottles(1), RecursiveFactorial(1), Sum2(1), SumDif(1)
- **calls:** println(40), append(8), nextLine(6), printf(6), contains(5), factorial(5), multiply(5), toString(5), add(4), close(4), nextInt(4), parseInt(4), equals(3), impl(3), iterate(3), limit(3), mapToObj(3), nextToken(3), pow(3), reduce(3), beerCheck(2), bottles(2), defaultCharset(2), fibInner(2), forEach(2), map(2), nextBigInteger(2), put(2), putOnWall(2), range(2), rangeClosed(2), setText(2), signum(2), song(2), split(2), toLowerCase(2), valueOf(2), addActionListener(1), apply(1), collect(1), compareTo(1), computeIfAbsent(1), dispose(1), equalsIgnoreCase(1), exit(1), factorialRec(1), fibStream(1), filter(1), flatMap(1), flip(1), flush(1), forEachOrdered(1), format(1), getAsLong(1), goToStore(1), joining(1), nextLong(1), pack(1), party(1), putLastOnWall(1)
- **frequent node types:** identifier(1079), argument_list(225), method_invocation(194), binary_expression(161), expression_statement(148), decimal_integer_literal(137), type_identifier(125), =(111), block(108), string_fragment(90), modifiers(89), string_literal(87), field_access(83), integral_type(81), variable_declarator(80), scoped_identifier(74), +(71), formal_parameters(55), method_declaration(54), local_variable_declaration(53), formal_parameter(51), assignment_expression(47), parenthesized_expression(46), import_declaration(33), object_creation_expression(31), program(30), void_type(29), return_statement(27), if_statement(26), class_body(25), long(24), dimensions(24), class_declaration(24), ->(22), array_type(21), ==(18), escape_sequence(18), field_declaration(16), update_expression(15), lambda_expression(14), else(14), <(14), >(13), *(13), %(11)
