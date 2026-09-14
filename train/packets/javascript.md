# Drafting packet: JavaScript

Read `train/BRIEF.md` first: it has the pair format, the tiers, the engine and verifier rules,
the draft -> verify -> fix loop, and what you must not touch. This packet adds your language.

- **Target:** 100 accepted pairs, about 25 per tier (T1-T4).
- **Candidate files:** `train/candidates/javascript-b1.jsonl`, then `javascript-b1-r1.jsonl`, `javascript-b2.jsonl`, ...
- **Verify:** `/home/teague/.local/share/venv/bin/python pilot.py train/candidates/<batch>.jsonl <batch> train`
  (batch id = file name without `.jsonl`, run from `/home/teague/Projects/astcss-eval/trees/train/multilang`).
- **Ids:** `tr-javascript-t<tier>-<nnnn>`, never reused across your batches.
- **Fixtures you may use:** `js-messe`, `js-rosetta`.

## The card the model is prompted with

Write selectors in this vocabulary. A class not on this card must not appear in your pairs.

```text
You translate a developer's plain-English request into ONE astcss selector over a JavaScript
code tree. Reply with the selector only: one line, no quotes, no backticks, no explanation.

SEMANTIC CLASSES (cross-language; prefer these)
  .fn .func .method       function or method definitions  (arrow_function, function_declaration, method_definition, function_expression)
  .class                  class definitions  (class_declaration)
  .mod                    the module  (program)
  .var                    variable definitions  (variable_declarator, lexical_declaration, variable_declaration)
  .call                   function or method calls  (call_expression, new_expression)
  .member                 attribute access  (member_expression, subscript_expression, optional_chain)
  .if                     conditionals  (if_statement, ternary_expression, else_clause, switch_case)
  .loop                   loops  (for_in_statement, while_statement, for_statement, do_statement)
  .jump                   return / break / continue / yield  (return_statement, break_statement, continue_statement)
  .try .catch .throw      try blocks, except handlers, raise, finally  (try_statement, catch_clause, throw_statement)

JAVASCRIPT NODE TYPES (exact tree-sitter names, written with no dot, when no class fits)
  lexical_declaration return_statement if_statement arrow_function await_expression
  function_declaration export_statement for_in_statement method_definition import_statement
  variable_declaration function_expression ternary_expression while_statement

FILTERS ON A NODE (written directly after it, no space)
  #name                   exactly this name:            .fn#main   .call#fetch   .class#Config
  [name^="x"]             name starts with x            .fn[name^="handle"]
  [name$="x"]             name ends with x
  [name*="x"]             name contains x
  :has(S)                 contains a descendant matching S     .fn:has(.call#fetch)
  :not(:has(S))           contains no descendant matching S    .fn:not(:has(.try))

COMBINATORS (exactly two steps; filters other than #name go on the second step only)
  A B                     B anywhere inside A          .class#Config .fn
  A > B                   B is a direct child of A     .mod > import_statement
  A ~ B                   B is a later sibling of A    import_statement ~ .fn
  A + B                   B immediately follows A      .fn + .fn

EXAMPLES
  every function                              .fn
  calls to fetch                              .call#fetch
  classes whose names end with Error          .class[name$="Error"]
  methods of the Config class                 .class#Config .fn
  functions without a try block               .fn:not(:has(.try))
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


## Notes for JavaScript — fixtures js-messe, js-rosetta

- **Don't use `.import`**: one `import` statement yields `import_statement`,
  `import_clause`, `named_imports` and each `import_specifier`. Use
  `import_statement`.
- `.fn` is `arrow_function`, `function_declaration`, `function_expression`,
  `method_definition`, generator functions. `.call` includes `new_expression`.
- js-rosetta has no classes or imports.


## Fixture inventories

Names and counts from the audit. Use real names from these lists; the verifier needs 1-50 matches.

### `js-messe` — 24 files from git-messe-af@96dbd6b78

- **class counts** (don't use any the notes exclude): .fn 182, .class 5, .call 880, .loop 50, .if 303, .jump 215, .try 28, .catch 28, .throw 21, .import 131, .var 854, .member 1703, .comp 0, .mod 24
- **functions:** send(8), constructor(5), delete(5), get(5), list(5), put(5), generateRef(2), main(2), _createThread(1), _findThread(1), _getEvent(1), _listEvents(1), _putEvent(1), _updateThread(1), authenticate(1), cmdCancel(1), cmdClaim(1), cmdComplete(1), cmdCreate(1), cmdExport(1), cmdImport(1), cmdList(1), cmdShow(1), cmdUpdate(1), copy(1), createBaseStorage(1), createBlobStoreFromEnv(1), createR2Storage(1), createStorageFromEnv(1), detectFormat(1), ensureDirs(1), error(1), eventsToMesseAf(1), exists(1), expandTemplate(1), exportThread(1), extractAttachments(1), extractClientId(1), fetch(1), findNewRequestFiles(1), findThread(1), generateEventId(1), generateFilename(1), generateMessageRef(1), getAttachmentType(1), getClient(1), getExtensionFromMime(1), getFolderForStatus(1), getGoogleAccessToken(1), getMessageType(1), getMetadata(1), getStorageDescription(1), getThreadEvents(1), getThreads(1), httpRequest(1), importThread(1), json(1), listThreads(1), loadExecutors(1), messeAfToEvents(1)
- **classes:** BlobStore(1), FilesystemStorage(1), MesseAfStorage(1), R2Storage(1), S3Storage(1)
- **calls:** json(48), log(48), push(41), error(40), join(37), status(32), stringify(19), startsWith(18), get(17), put(17), Error(15), exit(15), slice(14), split(14), toString(14), map(13), match(11), then(10), Date(9), endsWith(9), from(9), httpRequest(9), replace(9), filter(8), list(8), includes(7), padStart(7), readFile(7), addEventListener(6), delete(6), getFolderForStatus(6), parseInt(6), readdir(6), send(6), serializeThread(6), waitUntil(6), writeFile(6), find(5), generateEventId(5), on(5), parse(5), parseThread(5), parseThreadV1(5), toUpperCase(5), trim(5), BlobStore(4), _findThread(4), cmdUpdate(4), cwd(4), getClient(4), isDirectory(4), mkdir(4), serializeThreadV1(4), toISOString(4), use(4), R2Storage(3), Set(3), URL(3), URLSearchParams(3), byteLength(3)
- **frequent node types:** identifier(3157), property_identifier(2179), member_expression(1618), arguments(880), string_fragment(855), call_expression(823), string(662), pair(565), =(504), statement_block(455), variable_declarator(428), lexical_declaration(426), expression_statement(354), binary_expression(287), comment(276), object(255), parenthesized_expression(243), if_statement(216), template_substitution(205), return_statement(196), number(157), formal_parameters(152), await_expression(145), template_string(144), ||(111), array(96), arrow_function(74), =>(74), unary_expression(72), function_declaration(68), ===(63), assignment_expression(61), !(58), new_expression(57), export_statement(51), subscript_expression(46), for_in_statement(46), shorthand_property_identifier(41), method_definition(40), optional_chain(39), import_specifier(38), /(37), import_clause(36), import_statement(36), &&(35)

### `js-rosetta` — 30 files from sitting_duck@1a10b7d3d

- **class counts** (don't use any the notes exclude): .fn 129, .class 0, .call 239, .loop 30, .if 46, .jump 58, .try 0, .catch 0, .throw 2, .import 0, .var 202, .member 195, .comp 0, .mod 30
- **functions:** range(7), factorial(4), fib(4), fizzBuzz(3), enumFromTo(2), perfectSquaresUpTo(2), replicate(2), unlines(2), Bottles(1), Just(1), Nothing(1), Tuple(1), Y(1), append(1), bool(1), bottleSong(1), caseOf(1), cycle(1), enumFrom(1), fb(1), fibonacciGenerator(1), finalDoors(1), flip(1), fmap(1), fst(1), go(1), integerFactors(1), isNull(1), length(1), liftA2(1), main(1), map(1), mapAccumL(1), product(1), snd(1), song(1), str(1), take(1), test(1), uncons(1), zip(1), zipWith(1)
- **classes:** (none)
- **calls:** log(15), map(11), floor(10), concat(8), join(8), range(8), from(7), push(7), reduce(6), Array(5), apply(5), f(5), sqrt(5), take(5), factorial(4), fn(4), getElementById(4), replace(4), uncons(4), Number(3), fib(3), filter(3), forEach(3), slice(3), Just(2), Nothing(2), Tuple(2), enumFromTo(2), fb(2), fst(2), perfectSquaresUpTo(2), replicate(2), snd(2), song(2), toString(2), unlines(2), zipWith(2), Bottles(1), String(1), Y(1), appendChild(1), caseOf(1), createElement(1), cycle(1), dn(1), entries(1), enumFrom(1), every(1), exit(1), fibonacciGenerator(1), finalDoors(1), fizzBuzz(1), fmap(1), g(1), go(1), integerFactors(1), isArray(1), isFinite(1), length(1), liftA2(1)
- **frequent node types:** identifier(966), arguments(239), call_expression(238), binary_expression(189), property_identifier(179), number(172), =(165), member_expression(150), variable_declarator(112), expression_statement(96), parenthesized_expression(93), statement_block(89), formal_parameters(88), string(88), string_fragment(86), comment(85), arrow_function(74), =>(74), +(61), return_statement(58), lexical_declaration(56), subscript_expression(45), assignment_expression(45), >(42), variable_declaration(34), -(33), <(31), program(30), array(29), function_expression(29), ?(27), ternary_expression(27), function_declaration(21), *(21), update_expression(20), pair(20), while_statement(19), jsx_opening_element(17), </(14), if_statement(14), jsx_element(14), object(14), jsx_closing_element(14), ERROR(13), /(13)
