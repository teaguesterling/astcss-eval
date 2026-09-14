# Drafting packet: Rust

Read `train/BRIEF.md` first: it has the pair format, the tiers, the engine and verifier rules,
the draft -> verify -> fix loop, and what you must not touch. This packet adds your language.

- **Target:** 110 accepted pairs, about 27 per tier (T1-T4).
- **Candidate files:** `train/candidates/rust-b1.jsonl`, then `rust-b1-r1.jsonl`, `rust-b2.jsonl`, ...
- **Verify:** `/home/teague/.local/share/venv/bin/python pilot.py train/candidates/<batch>.jsonl <batch> train`
  (batch id = file name without `.jsonl`, run from `/home/teague/Projects/astcss-eval/trees/train/multilang`).
- **Ids:** `tr-rust-t<tier>-<nnnn>`, never reused across your batches.
- **Fixtures you may use:** `rs-cosmic-goo`, `rs-magic`, `rs-rosetta`.

## The card the model is prompted with

Write selectors in this vocabulary. A class not on this card must not appear in your pairs.

```text
You translate a developer's plain-English request into ONE astcss selector over a Rust
code tree. Reply with the selector only: one line, no quotes, no backticks, no explanation.

SEMANTIC CLASSES (cross-language; prefer these)
  .fn .func .method       function or method definitions  (function_item, closure_expression, function_signature_item)
  .class                  class definitions  (impl_item, struct_item, enum_item, type_item)
  .mod                    the module  (source_file, mod_item)
  .var                    variable definitions  (let_declaration, parameter, field_declaration, enum_variant)
  .call                   function or method calls  (call_expression, macro_invocation)
  .import                 import statements  (use_declaration, use_wildcard, use_as_clause, extern_crate_declaration)
  .loop                   loops  (for_expression, while_expression, loop_expression)
  .jump                   return / break / continue / yield  (return_expression, continue_expression, break_expression)

RUST NODE TYPES (exact tree-sitter names, written with no dot, when no class fits)
  let_declaration function_item if_expression closure_expression for_expression

FILTERS ON A NODE (written directly after it, no space)
  #name                   exactly this name:            .fn#main   .call#unwrap   .class#Config
  [name^="x"]             name starts with x            .fn[name^="parse_"]
  [name$="x"]             name ends with x
  [name*="x"]             name contains x
  :has(S)                 contains a descendant matching S     .fn:has(.call#unwrap)
  :not(:has(S))           contains no descendant matching S    .fn:not(:has(.loop))

COMBINATORS (exactly two steps; filters other than #name go on the second step only)
  A B                     B anywhere inside A          .class#Config .fn
  A > B                   B is a direct child of A     .mod > .import
  A ~ B                   B is a later sibling of A    .import ~ .fn
  A + B                   B immediately follows A      .class + .class

EXAMPLES
  every function                              .fn
  calls to unwrap                             .call#unwrap
  structs and enums whose names end with Error  .class[name$="Error"]
  functions defined in the Config impl        .class#Config .fn
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


## Notes for Rust — fixtures rs-magic, rs-cosmic-goo, rs-rosetta

- **Don't use `.if`**: it includes the `?` error-propagation operator (133 in
  rs-magic) alongside `if_expression` and `match_arm`. Use `if_expression`,
  `match_expression`, `match_arm`.
- **Don't use `.member`**: it counts `.`, `::` and `->` tokens. Use
  `field_expression`.
- `.class` is `struct_item`, `impl_item`, `enum_item`, `trait_item`, `type_item`.
- `.call` is `call_expression` plus `macro_invocation` (`println!`, `vec!`).
- `.try`, `.catch`, `.throw` select nothing; `.jump` is `return_expression`,
  `continue_expression`, `break_expression`.


## Fixture inventories

Names and counts from the audit. Use real names from these lists; the verifier needs 1-50 matches.

### `rs-cosmic-goo` — 12 files from cosmic-goo@07c9bc54b

- **class counts** (don't use any the notes exclude): .fn 223, .class 6, .call 1201, .loop 23, .if 173, .jump 42, .try 0, .catch 0, .throw 0, .import 52, .var 374, .member 1855, .comp 0, .mod 20
- **functions:** bash_capture(2), fixture(2), main(2), new(2), shell_quote(2), a_bad_line_is_skipped_not_fatal(1), adverb_schema(1), adverbs_reach_the_descriptor(1), allow_lists_applicable_verbs_and_default(1), bash_capture_bytes(1), bash_exec(1), cancel(1), capture_rewrites_subject_text(1), captures_interpolate_into_adverb_values(1), chains_converters_through_a_buffer(1), clear(1), clear_drops_history(1), clipboard(1), coerces_then_runs_the_verb(1), compose_subject_candidates(1), compute(1), confirm(1), confirm_and_destructive_present_on_every_verb_default_false(1), debug_is_redacted_not_raw(1), deep_interp(1), default_depth_injects_normal_prefix(1), deliver_file(1), description(1), disabled(1), disabled_records_nothing(1), dispatch_match(1), display_view_accessors_yield_sanitized(1), esc(1), execute(1), execute_capture(1), execute_capture_bytes(1), expose(1), expose_is_raw_for_functional_use(1), fabric_choice_selects_other_route(1), falls_back_to_default_when_unspecified(1), field(1), find_adverb(1), first_matching_rule_wins(1), fmt(1), fresh_state(1), history_path(1), id(1), identity_delivers_the_subject(1), interp(1), interpolates_multiple_captures(1), is_empty(1), is_on_path(1), is_present(1), jq_object_construction_survives_so_provider_list_cmds_are_not_mangled(1), jq_shorthand_object_construction_collides_with_placeholder_grammar(1), last(1), last_returns_the_most_recent(1), literal_brace_not_a_placeholder_survives(1), lock(1), lookup(1)
- **classes:** Tainted(3), Action(1), DisplayView(1)
- **calls:** assert_eq(92), json(59), and_then(57), get(57), unwrap(50), new(45), format(40), as_str(28), is_empty(28), map(27), assert(24), to_string(23), unwrap_or(22), Some(20), join(18), iter(17), arg(16), collect(16), fixture(15), unwrap_or_default(15), as_array(12), filter(12), into(12), len(12), record(11), remove(10), resolve(10), Ok(9), push(9), remove_dir_all(9), args(8), dispatch_match(8), eprintln(8), execute_capture(8), find(8), ok(8), to_str(8), vec(8), write_subject(8), clone(7), from_utf8_lossy(7), lock(7), map_err(7), options_for(7), output(7), reg(7), subj(7), verb(7), fresh_state(6), insert(6), j(6), as_object(5), cloned(5), from(5), history_path(5), into_owned(5), lines(5), pick(5), write(5), as_bytes(4)
- **frequent node types:** identifier(2894), "(1660), call_expression(954), arguments(954), string_content(835), string_literal(830), .(728), token_tree(699), field_identifier(673), field_expression(647), !(496), line_comment(425), //(425), ::(370), &(340), expression_statement(313), =(306), scoped_identifier(296), let_declaration(271), doc_comment(265), block(247), macro_invocation(247), type_identifier(206), reference_expression(203), |(195), inner_doc_comment_marker(157), parameters(129), function_item(129), /(108), outer_doc_comment_marker(108), reference_type(106), parameter(94), closure_parameters(94), closure_expression(94), primitive_type(82), ->(73), attribute_item(64), attribute(64), <(64), #(64), match_arm(62), match_pattern(62), >(61), if_expression(60), tuple_struct_pattern(59)

### `rs-magic` — 16 files from magic@fc82f88a7

- **class counts** (don't use any the notes exclude): .fn 285, .class 23, .call 1609, .loop 32, .if 387, .jump 57, .try 0, .catch 0, .throw 0, .import 103, .var 549, .member 3102, .comp 0, .mod 40
- **functions:** new(4), is_pid_alive(2), set_mode(2), should_exclude(2), _setup_store_v5(1), _setup_store_v5_duckdb(1), add(1), aliases(1), attempt_count(1), bash_hook_functions(1), blobs_dir(1), clear(1), collect(1), collect_ci_context(1), collect_git_context(1), complete(1), complete_entry(1), complete_invocation(1), default_format(1), default_priority(1), delete_entry(1), detect(1), ensure_secure_root(1), ensure_session(1), errors_log_path(1), execute_step(1), find_current_project(1), find_project(1), generate(1), get(1), get_by_id(1), get_by_position(1), get_pending_attempts(1), glob_to_like(1), harden_dir(1), harden_file(1), harden_tree(1), header(1), hints(1), hook_functions(1), ignore_patterns(1), inactive_message(1), inactive_on_off_functions(1), init(1), into_map(1), is_empty(1), is_enabled(1), is_in_project(1), is_initialized(1), is_runner_alive(1), kill_invocation(1), lesson_capturing_commands(1), lesson_getting_started(1), lesson_query_syntax(1), lesson_shell_integration(1), lesson_viewing_output(1), lesson_working_with_errors(1), lessons(1), list_entries(1), list_lessons(1)
- **classes:** Store(3), Buffer(2), BufferMeta(2), ContextMetadata(2), FormatHint(2), FormatHints(2), ProjectInfo(2), BufferEntry(1), Error(1), Lesson(1), Mode(1), RecoveryStats(1), Result(1), Shell(1), Step(1)
- **calls:** assert_eq(144), assert(124), to_string(72), unwrap(69), new(60), Ok(51), parse_query(44), format(42), get(35), push_str(35), insert(32), json(30), var(26), execute(25), join(24), len(24), is_empty(20), iter(16), map(16), unwrap_or(16), path(14), push(14), starts_with(14), Some(13), contains(13), map_err(13), Err(12), and_then(12), collect(12), exists(12), Io(11), into(11), connection(9), create_dir_all(9), redact_command(9), parse(8), println(8), replace(8), vec(8), Config(7), Object(7), find(7), from_mode(7), open(7), set_permissions(7), write(7), SetForegroundColor(6), buffer_output_path(6), cmp(6), current_dir(6), disable_raw_mode(6), ok(6), output(6), params(6), set_mode(6), with_priority(6), with_root(6), add(5), any(5), args(5)
- **frequent node types:** identifier(5016), "(1398), .(1319), arguments(1235), call_expression(1235), field_identifier(1011), field_expression(931), token_tree(843), string_content(788), expression_statement(765), ::(716), string_literal(699), //(559), line_comment(559), !(546), scoped_identifier(543), block(462), =(452), macro_invocation(374), let_declaration(366), doc_comment(352), &(344), type_identifier(342), /(256), outer_doc_comment_marker(256), function_item(212), parameters(212), escape_sequence(176), reference_expression(169), integer_literal(169), |(151), if_expression(150), visibility_modifier(141), attribute(140), #(140), attribute_item(140), try_expression(133), ?(133), parameter(127), primitive_type(125), >(115), <(112), ->(110), type_arguments(108), generic_type(101)

### `rs-rosetta` — 18 files from sitting_duck@1a10b7d3d

- **class counts** (don't use any the notes exclude): .fn 43, .class 8, .call 102, .loop 13, .if 29, .jump 0, .try 0, .catch 0, .throw 0, .import 7, .var 32, .member 157, .comp 0, .mod 18
- **functions:** main(15), bottles_of_beer(2), on_the_wall(2), area(1), eh_personality(1), factorial_iterative(1), factorial_recursive(1), fib_tail_iter(1), fib_tail_recursive(1), fibonacci(1), fibonacci_sequence(1), fizzbuzz(1), new(1), next(1), panic_fmt(1), start(1)
- **classes:** Bottles(2), Fib(2), Item(1), Iterator(1), Shape(1), Square(1)
- **calls:** println(26), map(7), expect(4), new(4), bottles_of_beer(3), checked_add(3), into(3), print(3), enumerate(2), fib_tail_iter(2), fibonacci(2), len(2), on_the_wall(2), powi(2), read_line(2), rev(2), split_whitespace(2), stdin(2), swap(2), unwrap(2), asm(1), binary_search(1), chain(1), collect(1), factorial_recursive(1), fibonacci_sequence(1), filter(1), fold(1), for_each(1), from(1), into_iter(1), is_ok(1), is_square(1), iter(1), iter_mut(1), last(1), product(1), sqrt(1), sum(1), to_string(1), vec(1), write(1)
- **frequent node types:** identifier(274), string_content(152), "(114), escape_sequence(112), integer_literal(75), arguments(70), call_expression(70), field_identifier(66), .(61), field_expression(61), block(60), expression_statement(59), string_literal(57), token_tree(41), !(36), binary_expression(33), parameters(32), macro_invocation(32), function_item(30), primitive_type(30), =(30), type_identifier(22), |(22), ::(21), match_arm(18), mutable_specifier(18), source_file(18), match_pattern(18), scoped_identifier(17), let_declaration(17), &(15), parenthesized_expression(14), range_expression(14), ->(12), closure_parameters(11), *(11), +(11), closure_expression(11), for_expression(11), ..(10), parameter(10), tuple_pattern(9), unary_expression(8), type_arguments(7), <(7)
