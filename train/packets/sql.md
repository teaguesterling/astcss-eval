# Drafting packet: SQL

Read `train/BRIEF.md` first: it has the pair format, the tiers, the engine and verifier rules,
the draft -> verify -> fix loop, and what you must not touch. This packet adds your language.

- **Target:** 80 accepted pairs, about 20 per tier (T1-T4).
- **Candidate files:** `train/candidates/sql-b1.jsonl`, then `sql-b1-r1.jsonl`, `sql-b2.jsonl`, ...
- **Verify:** `/home/teague/.local/share/venv/bin/python pilot.py train/candidates/<batch>.jsonl <batch> train`
  (batch id = file name without `.jsonl`, run from `/home/teague/Projects/astcss-eval/trees/train/multilang`).
- **Ids:** `tr-sql-t<tier>-<nnnn>`, never reused across your batches.
- **Fixtures you may use:** `sql-block-utils`, `sql-duckdb-mcp`, `sql-fledgling`.

## The card the model is prompted with

Write selectors in this vocabulary. A class not on this card must not appear in your pairs.

```text
You translate a developer's plain-English request into ONE astcss selector over a SQL
code tree. Reply with the selector only: one line, no quotes, no backticks, no explanation.

SEMANTIC CLASSES (cross-language; prefer these)
  .class                  class definitions  (create_table, create_query, create_view, create_type)
  .mod                    the module  (program, create_schema)
  .var                    variable definitions  (column_definition, create_role)
  .call                   function or method calls  (invocation, window_function)
  .comp                   comprehensions and generator expressions  (select_expression, subquery, cte, window_specification)

SQL NODE TYPES (exact tree-sitter names, written with no dot, when no class fits)
  select_expression column_definition create_table subquery create_query
  cte filter_expression create_view

FILTERS ON A NODE (written directly after it, no space)
  #name                   exactly this name:            invocation#count
  [name^="x"]             name starts with x            invocation[name^="json_"]
  [name$="x"]             name ends with x
  [name*="x"]             name contains x
  :has(S)                 contains a descendant matching S     cte:has(invocation#count)
  :not(:has(S))           contains no descendant matching S    select_expression:not(:has(subquery))

COMBINATORS (exactly two steps; filters other than #name go on the second step only)
  A B                     B anywhere inside A          cte invocation
  A > B                   B is a direct child of A     create_table > column_definition
  A ~ B                   B is a later sibling of A    column_definition ~ column_definition
  A + B                   B immediately follows A      column_definition + column_definition

EXAMPLES
  every table definition                      create_table
  calls to count                              invocation#count
  function calls whose names start with json  invocation[name^="json_"]
  function calls inside a CTE                 cte invocation
  selects with no subquery                    select_expression:not(:has(subquery))
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


## Notes for SQL — fixtures sql-fledgling, sql-duckdb-mcp, sql-block-utils

- **Don't use `.fn`, `.if`, `.loop`, `.jump`, `.member`, `.import`**: they select
  nothing, or a FILTER clause (`.if`) or `::` casts (`.member`).
- **Table definitions carry no name**: `create_table[name^="s"]` matches nothing
  in sql-fledgling. `#name` does bind on `invocation` (`invocation#count`: 22).
- Statements are wrapped: `.mod > create_table` matches nothing; use a
  descendant step (`cte invocation`) rather than `>` from the file root.
- `.class` is `create_table`, `create_view`, `create_query`; `.call` is
  `invocation` (function calls, e.g. `count(...)`) and `window_function`;
  `.comp` is `select_expression`, `subquery`, `cte`; `.var` is
  `column_definition`. Prefer node types (`create_table`, `cte`, `invocation`)
  where the SQL meaning is clearer than the class name.


## Fixture inventories

Names and counts from the audit. Use real names from these lists; the verifier needs 1-50 matches.

### `sql-block-utils` — 8 files from duckdb_duck_block_utils@64ca966b0

- **class counts** (don't use any the notes exclude): .fn 0, .class 2, .call 419, .loop 0, .if 0, .jump 0, .try 0, .catch 0, .throw 0, .import 0, .var 0, .member 20, .comp 32, .mod 7
- **functions:** (none)
- **classes:** all_fixtures(1)
- **calls:** db_text(83), db_list_item(61), db_paragraph(48), db_heading(38), db_bold(28), db_inline_code(28), db_list(28), db_code(19), db_link(16), db_assemble(14), db_blockquote(10), db_italic(9), count(6), db_hr(5), db_image(5), db_raw(4), bar(2), db_blocks_validate(2), tp_sparkline(2), db_blocks_to_text(1), db_math(1), db_query_table(1), db_render_blocks(1), db_strikethrough(1), db_subscript(1), db_superscript(1), duck_blocks_to_pandoc_ast(1), list(1), tp_bar(1), tp_density(1)
- **frequent node types:** term(791), literal(578), identifier(532), object_reference(434), invocation(419), ERROR(204), comment(194), list(72), field(46), select_expression(25), column(21), relation(20), subscript(20), statement(14), *(12), all_fields(12), subquery(7), program(7), keyword_level(7), binary_expression(6), keyword_read(4), >=(4), =(4), op_other(4), marginalia(3), <(3), !=(3), order_by(2), keyword_encoding(2), order_target(2), direction(1), create_query(1), create_view(1), keyword_valid(1), set_operation(1), >(1)

### `sql-duckdb-mcp` — 13 files from duckdb_mcp@c8e35a3cf

- **class counts** (don't use any the notes exclude): .fn 0, .class 54, .call 111, .loop 0, .if 7, .jump 0, .try 0, .catch 0, .throw 0, .import 0, .var 115, .member 37, .comp 94, .mod 13
- **functions:** (none)
- **classes:** SELECT(5), products(3), customers(2), order_items(2), orders(2), activity_log(1), audit_log(1), branch_summary(1), customer_orders(1), daily_metrics(1), daily_summary(1), documents(1), inventory_status(1), order_details(1), org_summary(1), organizations(1), product_sales(1), project_health(1), projects(1), recent_activity(1), recent_commits(1), safe_user_summary(1), sensitive_data(1), task_board(1), tasks(1), test_users(1), user_summary(1), users(1), weekly_metrics(1)
- **calls:** COUNT(31), NOW(11), mcp_render_template(8), SUM(7), mcp_register_template(7), COALESCE(4), mcp_server_start(4), count(3), mcp_get_server_template(3), ROUND(2), fake_email(2), fake_first_name(2), fake_last_name(2), fake_uuid(2), mcp_list_server_templates(2), mcp_list_templates(2), parse_sql(2), AVG(1), MAX(1), NULLIF(1), extract_front_matter(1), fake_city(1), fake_country(1), fake_phone(1), git_branches(1), git_log(1), http_get(1), http_post(1), mcp_publish_tool(1), random(1), range(1), read_text(1), split_part(1), trim(1)
- **frequent node types:** identifier(1230), literal(841), object_reference(471), term(321), comment(306), field(268), list(127), binary_expression(114), column_definition(113), invocation(111), statement(104), column(86), ERROR(83), select_expression(82), =(82), relation(63), int(43), ::(35), column_definitions(27), *(26), timestamp(24), create_table(24), all_fields(20), create_query(16), create_view(14), program(13), subquery(12), table_option(12), <(10), !=(9), op_other(8), decimal(8), filter_expression(7), group_by(7), :=(7), >=(5), -(3), interval(3), <=(3), order_by(3), order_target(3), direction(3), >(2), +(2), keyword_inet(2)

### `sql-fledgling` — 21 files from fledgling@c27d670c8

- **class counts** (don't use any the notes exclude): .fn 0, .class 55, .call 343, .loop 0, .if 9, .jump 0, .try 0, .catch 0, .throw 0, .import 0, .var 95, .member 31, .comp 163, .mod 20
- **functions:** (none)
- **classes:** SELECT(23), WITH(7), _help_sections(1), _macros(1), _module_registry(1), _ordered_macros(1), _resources(1), _tools(1), file_pattern(1), fts.collections(1), fts.content(1), raw_conversations(1)
- **calls:** trim(73), COALESCE(33), count(22), getvariable(16), LIST(12), read_ast(11), replace(9), regexp_extract(8), semantic_type_to_string(8), sum(7), max(6), is_function_definition(5), git_uri(4), is_definition(4), json_object(4), json_type(4), last(4), list_contains(4), mcp_publish_tool(4), resolve(4), row_number(4), tool_calls(4), ast_select(3), chr(3), is_conditional(3), is_loop(3), list(3), min(3), query(3), ON(2), avg(2), doc_outline(2), file_changes(2), find_calls(2), find_definitions(2), glob(2), is_import(2), len(2), length(2), mcp_server_start(2), read_lines(2), read_markdown_sections(2), token_usage(2), unnest(2), _is_code_file(1), age(1), any_value(1), ast_callers(1), ast_exports(1), ast_imports(1), ast_qualified_name_as_string(1), bash_commands(1), changed_function_summary(1), code_structure(1), content_blocks(1), format(1), function_callers(1), git_branches(1), git_log(1), git_tags(1)
- **frequent node types:** identifier(2563), term(1035), comment(931), field(908), object_reference(897), ERROR(699), literal(454), binary_expression(390), invocation(338), statement(128), relation(125), select_expression(112), :=(110), column_definition(93), =(91), op_other(82), order_target(47), column_definitions(43), *(42), create_table(39), /(38), order_by(29), all_fields(28), ::(27), +(27), cte(26), set_statement(24), keyword_read(23), program(19), -(19), is_not(19), !=(18), subquery(17), create_query(15), direction(14), >(14), group_by(13), parenthesized_expression(11), filter_expression(9), int(9), table_option(9), <=(9), keyword_level(6), list(6), keyword_role(5)
