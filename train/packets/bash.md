# Drafting packet: Bash

Read `train/BRIEF.md` first: it has the pair format, the tiers, the engine and verifier rules,
the draft -> verify -> fix loop, and what you must not touch. This packet adds your language.

- **Target:** 60 accepted pairs, about 15 per tier (T1-T4).
- **Candidate files:** `train/candidates/bash-b1.jsonl`, then `bash-b1-r1.jsonl`, `bash-b2.jsonl`, ...
- **Verify:** `/home/teague/.local/share/venv/bin/python pilot.py train/candidates/<batch>.jsonl <batch> train`
  (batch id = file name without `.jsonl`, run from `/home/teague/Projects/astcss-eval/trees/train/multilang`).
- **Ids:** `tr-bash-t<tier>-<nnnn>`, never reused across your batches.
- **Fixtures you may use:** `sh-homelab`, `sh-mixed`.

## The card the model is prompted with

Write selectors in this vocabulary. A class not on this card must not appear in your pairs.

```text
You translate a developer's plain-English request into ONE astcss selector over a Bash
code tree. Reply with the selector only: one line, no quotes, no backticks, no explanation.

SEMANTIC CLASSES (cross-language; prefer these)
  .fn .func .method       function or method definitions  (function_definition)
  .mod                    the module  (program)
  .var                    variable definitions  (variable_assignment, declaration_command, unset_command)
  .if                     conditionals  (if_statement, else_clause, case_item, case_statement)
  .loop                   loops  (for_statement, while_statement)

BASH NODE TYPES (exact tree-sitter names, written with no dot, when no class fits)
  command if_statement declaration_command pipeline function_definition
  for_statement

FILTERS ON A NODE (written directly after it, no space)
  #name                   exactly this name:            .fn#main
  [name^="x"]             name starts with x            .fn[name^="install_"]
  [name$="x"]             name ends with x
  [name*="x"]             name contains x
  :has(S)                 contains a descendant matching S     .fn:has(.loop)
  :not(:has(S))           contains no descendant matching S    .fn:not(:has(.if))

COMBINATORS (exactly two steps; filters other than #name go on the second step only)
  A B                     B anywhere inside A          .fn#main command
  A > B                   B is a direct child of A     .mod > .fn
  A ~ B                   B is a later sibling of A    .var ~ .fn
  A + B                   B immediately follows A      .fn + .fn

EXAMPLES
  every function                              .fn
  every command                               command
  functions whose names start with install    .fn[name^="install_"]
  commands run inside main                    .fn#main command
  functions without conditionals              .fn:not(:has(.if))
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


## Notes for Bash — fixtures sh-homelab, sh-mixed

- **Don't use `.call`**: it is only `command_substitution` and
  `process_substitution`, not ordinary commands. Use `command`.
- **Don't use `.member`**: it is variable expansion (`simple_expansion`,
  `expansion`).
- **Don't use `#name` on `command`**: it almost never binds (`command#echo` matches
  1 of 1,253 commands in sh-homelab). Commands can be selected, not named.
- `.fn` is `function_definition`; `.if` includes `case_item`, `elif_clause`,
  `else_clause`; `.var` is `variable_assignment`, `declaration_command`.
  No `.class`, `.import`, `.jump`, `.try`.


## Fixture inventories

Names and counts from the audit. Use real names from these lists; the verifier needs 1-50 matches.

### `sh-homelab` — 19 files from homelab@ec2c55d87

- **class counts** (don't use any the notes exclude): .fn 12, .class 0, .call 78, .loop 21, .if 94, .jump 0, .try 0, .catch 0, .throw 0, .import 0, .var 146, .member 475, .comp 0, .mod 19
- **functions:** in_list(2), add(1), add_bind(1), banner(1), del(1), do_rm(1), fmt_uuid(1), gather(1), is_inboth(1), recon(1), run_user(1)
- **classes:** (none)
- **calls:** (none)
- **frequent node types:** word(1132), "(1108), variable_name(634), command(592), command_name(592), string(554), comment(460), simple_expansion(430), string_content(358), number(187), =(148), variable_assignment(130), file_redirect(130), redirected_statement(117), list(93), test_command(77), command_substitution(69), $((69), ||(59), test_operator(56), >(55), >&(54), if_statement(54), compound_statement(46), binary_expression(46), expansion(45), ${(45), unary_expression(45), file_descriptor(43), raw_string(39), &&(34), else_clause(26), :-(22), do_group(21), program(19), pipeline(19), for_statement(18), subscript(16), declaration_command(15), >>(13), !(13), heredoc_content(13), function_definition(12), process_substitution(9), special_variable_name(9)

### `sh-mixed` — 6 files from duckhts@eb2eb9ace

- **class counts** (don't use any the notes exclude): .fn 8, .class 0, .call 15, .loop 1, .if 21, .jump 0, .try 0, .catch 0, .throw 0, .import 0, .var 56, .member 145, .comp 0, .mod 6
- **functions:** capture_licenses(1), copy_if_exists(1), download_if_missing(1), extract_tar_bz2(1), require_cmd(1), reset_dir(1), run_compiler(1), run_test(1)
- **classes:** (none)
- **calls:** (none)
- **frequent node types:** "(264), word(201), variable_name(190), string(132), simple_expansion(125), command(102), command_name(102), comment(84), string_content(83), =(46), variable_assignment(45), expansion(20), ${(20), command_substitution(15), redirected_statement(14), if_statement(13), file_redirect(12), number(12), declaration_command(11), `(10), $((10), >(9), compound_statement(9), test_command(9), test_operator(8), list(8), function_definition(8), raw_string(7), unary_expression(7), &&(7), <<(6), heredoc_body(6), heredoc_start(6), heredoc_redirect(6), heredoc_end(6), program(6), ]](5), [[(5), subscript(4), else_clause(4), >&(3), file_descriptor(3), extglob_pattern(2), binary_expression(2), pipeline(2)
