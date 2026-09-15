# Per-language notes for drafting training pairs

From the fixture audit (`train/audit/`): for every training fixture, what each
semantic class actually selects, and whether `.fn:has(.fn)` agrees with ground
truth. A class listed as **don't use** selects the wrong nodes in that language,
so pairs built on it would be verified against a wrong node set. Write the
specific node type instead (no leading dot).

## Every language

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

## Python — fixtures py-lackpy, py-umwelt, py-pluckit, py-blq

- Card: `card_v1c.md`, identical to the eval card.
- `.import` also counts `import_prefix`, `relative_import`, `__future__` and
  `aliased_import` sub-nodes; for "import statements" it is still the natural
  selector, but prefer `import_from_statement` / `import_statement` when the
  request names one kind.
- `.loop` includes comprehension `for_in_clause`; `.if` includes
  `conditional_expression`, `elif_clause`, `else_clause`, `if_clause`.

## Rust — fixtures rs-magic, rs-cosmic-goo, rs-rosetta

- **Don't use `.if`**: it includes the `?` error-propagation operator (133 in
  rs-magic) alongside `if_expression` and `match_arm`. Use `if_expression`,
  `match_expression`, `match_arm`.
- **Don't use `.member`**: it counts `.`, `::` and `->` tokens. Use
  `field_expression`.
- `.class` is `struct_item`, `impl_item`, `enum_item`, `trait_item`, `type_item`.
- `.call` is `call_expression` plus `macro_invocation` (`println!`, `vec!`).
- `.try`, `.catch`, `.throw` select nothing; `.jump` is `return_expression`,
  `continue_expression`, `break_expression`.

## JavaScript — fixtures js-messe, js-rosetta

- **Don't use `.import`**: one `import` statement yields `import_statement`,
  `import_clause`, `named_imports` and each `import_specifier`. Use
  `import_statement`.
- `.fn` is `arrow_function`, `function_declaration`, `function_expression`,
  `method_definition`, generator functions. `.call` includes `new_expression`.
- js-rosetta has no classes or imports.
- **`.class > .fn` matches nothing**: tree-sitter puts a `class_body` between a class and
  its methods; use `.class .fn` (descendant). `.mod > import_statement` equals bare
  `import_statement` (imports are always direct children of the module), so its `>`
  step is never load-bearing. (Found by the JavaScript drafting agent.)

## C++ — fixtures cpp-duck-hunt, cpp-duckdb-yaml, cpp-duckdb-mcp

- **Don't use `.fn`**: it matches each `function_declarator` as well as the
  `function_definition` (540 nodes for 212 definitions in cpp-duck-hunt). Use
  `function_definition`, `template_function`, `lambda_expression`.
- **Don't use `.if`**: it adds `condition_clause` and the `?` token. Use
  `if_statement`, `conditional_expression`, `switch_statement`.
- **Don't use `.import`**: it adds `system_lib_string` (the `<header>`). Use
  `preproc_include`.
- **Don't use `.member`**: it counts `::` and `->` tokens. Use `field_expression`.
- `.class` is `class_specifier`, `struct_specifier`, `enum_specifier`; `.try`,
  `.catch`, `.throw` work (`try_statement`, `catch_clause`, `throw_statement`).
  `.mod` is `namespace_definition` plus `translation_unit`.

## C — fixture c-duckhts

- **Don't use `.if`** (adds the `?` token), **`.import`** (adds
  `system_lib_string`), **`.member`** (adds `->`). Use `if_statement`,
  `conditional_expression`, `switch_statement`, `preproc_include`,
  `field_expression`.
- `.fn` is `function_definition` and `preproc_function_def`; `.class` is
  `struct_specifier`, `type_definition`, `enum_specifier`, `union_specifier`.
  `.jump` includes `goto_statement`.
- **`>` from a function or struct to its contents matches nothing**: a
  `function_definition`'s only direct child is its `compound_statement`, and struct
  fields sit inside a `field_declaration_list` (`.fn > .call`, `.fn > .var`,
  `.class > .var` are all 0). Use descendant steps; `>` works for flat relations such as
  `.mod > .class` or `preproc_ifdef > .fn`. Bare classes exceed 50 nodes on c-duckhts
  (`.fn` 272, `.call` 2,040), so T1 pairs need node types. (Found by the C drafting agent.)

## Java — fixture java-rosetta

- **Don't use `.if`** (adds the `?` token), **`.catch`** (counts `catch_type` as
  well as `catch_clause`), **`.member`** (adds `::`). Use `if_statement`,
  `ternary_expression`, `catch_clause`, `field_access`.
- `.fn` is `method_declaration`, `lambda_expression`, `constructor_declaration`;
  `.call` is `method_invocation` plus `object_creation_expression`.

## Go — fixture go-rosetta

- **Don't use `.mod`**: it counts `package_clause` as well as `source_file`.
- `.class` is `struct_type`, `interface_type`; `.loop` includes `for_clause` and
  `range_clause` inside a `for_statement`; `.if` includes switch
  `expression_case` / `default_case`. Small fixture (16 files): keep batches small.
- **Names don't bind on `.class` or `.member`**: a struct's or interface's identifier is on the
  enclosing `type_spec`, not on `struct_type`/`interface_type`, so `.class#X` and
  `.class[name...]` match nothing; `#name` works on `.fn` and `.call`.
- **`>` into a body matches nothing**: Go always puts a `block` between a loop, `if` or
  function and its statements (`.loop > .if`, `.if > .call`: 0). Use descendant steps.
  (Both found by the Go drafting agent.)

## Bash — fixtures sh-homelab, sh-mixed

- **Don't use `.call`**: it is only `command_substitution` and
  `process_substitution`, not ordinary commands. Use `command`.
- **Don't use `.member`**: it is variable expansion (`simple_expansion`,
  `expansion`).
- **Don't use `#name` on `command`**: it almost never binds (`command#echo` matches
  1 of 1,253 commands in sh-homelab). Commands can be selected, not named.
- `.fn` is `function_definition`; `.if` includes `case_item`, `elif_clause`,
  `else_clause`; `.var` is `variable_assignment`, `declaration_command`.
  No `.class`, `.import`, `.jump`, `.try`.

## SQL — fixtures sql-fledgling, sql-duckdb-mcp, sql-block-utils

- **Don't use `.fn`, `.if`, `.loop`, `.jump`, `.member`, `.import`**: they select
  nothing, or a FILTER clause (`.if`) or `::` casts (`.member`).
- **Table names bind** (corrected: an earlier version of this note said they don't, from
  one test whose prefix no table happened to have). `create_table#raw_conversations`,
  `create_table[name^="_"]` (6) on sql-fledgling and `create_table#organizations`,
  `create_table[name$="_log"]` (2) on sql-duckdb-mcp all match; `invocation#count` (22)
  binds too. (Found by the SQL drafting agent.)
- `+` rarely holds between columns (`column_definition + column_definition`: 0 on
  sql-fledgling, 1 on sql-duckdb-mcp) and `create_table > column_definition` (24) is far
  smaller than the descendant form (136): most columns sit under an intermediate node.
  Subqueries are not inside `select_expression` on sql-fledgling, so
  `select_expression:not(:has(subquery))` equals bare `select_expression` there.
- **DuckDB table macros parse as `create_table`**: `CREATE OR REPLACE MACRO f(...) AS TABLE SELECT ...`
  becomes a `create_table` named `SELECT` (23 on sql-fledgling) or `WITH` (7), so 30 of that
  fixture's 39 `create_table` nodes are macros. Don't name tables `SELECT` or `WITH`, and
  prefer sql-duckdb-mcp for requests about real tables.
- **Parser choice, not an engine defect.** These fixtures are parsed with the generic
  tree-sitter `sql` grammar (chosen by the `.sql` extension), which does not know DuckDB's
  `CREATE MACRO`. sitting_duck's separate `duckdb` language uses DuckDB's own parser and
  names them (#44): `read_ast(path, 'duckdb')` on sql-fledgling gives `create_table_macro` 70
  (find_calls, find_in_ast, ...), `create_macro` 7, `create_table` 4, and `.fn` 77. But that
  tree is statement-level (172 nodes in all, 4 `parse_error`), with almost no structure
  inside a statement. A DuckDB-dialect training set would be a separate `duckdb` fixture,
  good for definition-level pairs only.
- Statements are wrapped: `.mod > create_table` matches nothing; use a
  descendant step (`cte invocation`) rather than `>` from the file root.
- `.class` is `create_table`, `create_view`, `create_query`; `.call` is
  `invocation` (function calls, e.g. `count(...)`) and `window_function`;
  `.comp` is `select_expression`, `subquery`, `cte`; `.var` is
  `column_definition`. Prefer node types (`create_table`, `cte`, `invocation`)
  where the SQL meaning is clearer than the class name.
