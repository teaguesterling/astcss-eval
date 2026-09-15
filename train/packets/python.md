# Drafting packet: Python

Read `train/BRIEF.md` first: it has the pair format, the tiers, the engine and verifier rules,
the draft -> verify -> fix loop, and what you must not touch. This packet adds your language.

- **Target:** 150 accepted pairs, about 37 per tier (T1-T4).
- **Candidate files:** `train/candidates/python-b1.jsonl`, then `python-b1-r1.jsonl`, `python-b2.jsonl`, ...
- **Verify:** `/home/teague/.local/share/venv/bin/python pilot.py train/candidates/<batch>.jsonl <batch> train`
  (batch id = file name without `.jsonl`, run from `/home/teague/Projects/astcss-eval/trees/train/multilang`).
- **Ids:** `tr-python-t<tier>-<nnnn>`, never reused across your batches.
- **Fixtures you may use:** `py-blq`, `py-lackpy`, `py-pluckit`, `py-umwelt`.

## The card the model is prompted with

Write selectors in this vocabulary. A class not on this card must not appear in your pairs.

```text
You translate a developer's plain-English request into ONE astcss selector over a Python
code tree. Reply with the selector only: one line, no quotes, no backticks, no explanation.

SEMANTIC CLASSES (cross-language; prefer these)
  .fn .func .method       function or method definitions (lambdas included)
  .class                  class definitions
  .mod                    the module (file root)
  .var                    variable definitions
  .call                   function or method calls
  .member                 attribute access (a.b)
  .import                 import statements
  .if                     conditionals (if / elif / else, comprehension filters)
  .loop                   loops (for / while, comprehension for-clauses)
  .jump                   return / break / continue / yield
  .try  .catch  .throw  .finally     try blocks, except handlers, raise, finally
  .comp                   comprehensions and generator expressions
  .str  .num  .bool  .coll           string, number, true/false/None, list/dict/set/tuple literals
  .arith  .cmp  .logic    arithmetic, comparison, logical operators
  .comment                comments

PYTHON NODE TYPES (exact tree-sitter names, when no class fits)
  function_definition class_definition decorated_definition decorator lambda
  with_statement for_statement while_statement if_statement
  return_statement break_statement continue_statement
  assignment expression_statement import_statement import_from_statement

FILTERS ON A NODE (written directly after it, no space)
  #name                   exactly this name:            .fn#setup   .call#sleep   .class#User
  [name^="x"]             name starts with x            .fn[name^="test_"]
  [name$="x"]             name ends with x
  [name*="x"]             name contains x
  [params=N]              function with exactly N parameters   .fn[params=3]
  :has(S)                 contains a descendant matching S     .fn:has(.call#sleep)
  :not(:has(S))           contains no descendant matching S    .fn:not(:has(.try))

COMBINATORS (exactly two steps; filters other than #name go on the second step only)
  A B                     B anywhere inside A          .class#User .fn
  A > B                   B is a direct child of A     .mod > .class
  A ~ B                   B is a later sibling of A    .import ~ .var
  A + B                   B immediately follows A      .comment + .fn

EXAMPLES
  every function                              .fn
  calls to sleep                              .call#sleep
  classes whose names contain Test            .class[name*="Test"]
  methods of the Parser class                 .class#Parser .fn
  functions that never raise                  .fn:not(:has(.throw))
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


## Notes for Python — fixtures py-lackpy, py-umwelt, py-pluckit, py-blq

- Card: `card_v1c.md`, identical to the eval card.
- `.import` also counts `import_prefix`, `relative_import`, `__future__` and
  `aliased_import` sub-nodes; for "import statements" it is still the natural
  selector, but prefer `import_from_statement` / `import_statement` when the
  request names one kind.
- `.loop` includes comprehension `for_in_clause`; `.if` includes
  `conditional_expression`, `elif_clause`, `else_clause`, `if_clause`.


## Fixture inventories

Names and counts from the audit. Use real names from these lists; the verifier needs 1-50 matches.

### `py-blq` — 35 files from blq-cli@12b31ad91

- **class counts** (don't use any the notes exclude): .fn 183, .class 28, .call 1807, .loop 105, .if 659, .jump 291, .try 69, .catch 70, .throw 30, .import 306, .var 1335, .member 2112, .comp 39, .mod 35
- **functions:** __init__(7), collector(3), to_dict(3), wrap(3), annotate(2), execute(2), prepare(2), should_annotate(2), store(2), validate(2), __post_init__(1), _auto_init(1), _clean_data(1), _clean_full(1), _clean_orphans(1), _clean_prune(1), _clean_schema(1), _cleanup(1), _cmd_get(1), _cmd_set(1), _cmd_show(1), _cmd_unset(1), _collect_report_data(1), _edit_config(1), _execute_run(1), _extract_tag_from_command(1), _find_baseline_run(1), _find_c_style_definition(1), _find_python_definition(1), _fire_callback(1), _flags_are_write(1), _fmt_duration(1), _fmt_memory(1), _format_location(1), _format_value(1), _generate_markdown_report(1), _generate_template(1), _get_default(1), _is_default(1), _is_pid_alive(1), _is_system(1), _load_outcome(1), _match_template(1), _matches_pattern(1), _migrate_parquet_to_bird(1), _normalize_cmd(1), _output_suggestion(1), _parse_bool(1), _parse_defaults(1), _parse_int(1), _parse_list(1), _parse_timestamp(1), _parse_value(1), _reader(1), _request(1), _run_loop(1), _should_include(1), _show_suppress_list(1), _validate_one(1), acquire_lock(1)
- **classes:** Annotation(1), Annotator(1), BlqRuntimeConfig(1), BwrapEngine(1), Collector(1), CommandLock(1), CommandSpec(1), DebounceHandler(1), Definition(1), ExecutionResult(1), Executor(1), Extension(1), GitHubClient(1), GitHubError(1), LocalExecutor(1), LockHeldError(1), LogEngine(1), ParsedRef(1), ReportData(1), RunContext(1), SandboxEngine(1), SandboxExtension(1), SandboxViolation(1), SourceContextAnnotator(1), StraceProfile(1), UserConfig(1), WatchController(1), WatchSession(1)
- **calls:** print(276), get(106), append(97), getattr(68), len(57), exit(52), int(43), str(37), isinstance(35), join(30), execute(26), items(23), dumps(21), exists(21), group(19), sorted(19), ValueError(18), compile(17), field(17), split(16), ensure(15), fetchone(15), strip(15), open(14), bool(13), to_dict(13), Path(12), startswith(12), add(11), close(11), set(11), write(11), ParsedRef(10), load(10), mkdir(10), warning(10), getLogger(9), now(9), search(9), df(8), max(8), flush(7), format_duration(7), read_text(7), add_argument(6), config_path(6), debug(6), decode(6), fnmatch(6), head(6), isoformat(6), lower(6), lstrip(6), _normalize_cmd(5), cls(5), find(5), isdigit(5), killpg(5), loads(5), replace(5)
- **frequent node types:** identifier(9929), string_content(2060), expression_statement(1928), string(1914), attribute(1826), call(1807), argument_list(1803), =(1588), assignment(1075), block(1021), type(820), keyword_argument(520), comment(505), if_statement(496), dotted_name(480), none(422), interpolation(380), integer(364), comparison_operator(310), pair(260), subscript(258), return_statement(247), typed_parameter(220), function_definition(181), parameters(181), not(179), ->(175), in(171), binary_operator(168), import_from_statement(135), type_parameter(134), generic_type(134), is(116), boolean_operator(114), false(107), not_operator(104), import_statement(96), list(93), |(90), dictionary(82), except_clause(70), try_statement(69), conditional_expression(63), or(63), true(61)

### `py-lackpy` — 45 files from lackpy@6ef2df965

- **class counts** (don't use any the notes exclude): .fn 254, .class 60, .call 1487, .loop 165, .if 415, .jump 347, .try 22, .catch 22, .throw 29, .import 479, .var 1113, .member 1826, .comp 59, .mod 45
- **functions:** __init__(19), check(9), run(8), main(6), resolve(6), available(5), name(5), build(4), __repr__(3), execute(3), from_dict(3), generate(3), to_dict(3), validate(3), _namespace_desc_for(2), system_prompt_hint(2), __iter__(1), __len__(1), __new__(1), __str__(1), _apply_unified_diff(1), _ast_select_gate(1), _attrs_to_info(1), _best_cells_per_interpreter(1), _call_fixer(1), _chat_with_timeout(1), _classify(1), _clean_dsl_output(1), _collect_definitions(1), _collect_references(1), _display(1), _elide(1), _extract_path_from_body(1), _failure_modes(1), _get_class_annotations(1), _handler(1), _info_to_attrs(1), _init_config(1), _install_sigint_handler(1), _is_dict_with_keys(1), _is_int_at_least(1), _is_nonempty(1), _load(1), _log_trials(1), _markdown_contains(1), _markdown_count_at_least(1), _markdown_nonempty(1), _names_from_args(1), _names_from_target(1), _normalize_checks(1), _parse_frontmatter_block(1), _parse_hunks(1), _parse_info_string(1), _parse_int(1), _parse_profile(1), _parse_template_file(1), _pick_fence(1), _plucker_adhoc_gate(1), _pss_adhoc_gate(1), _python_adhoc_gate(1)
- **classes:** AnalysisReport(1), Assistant(1), AsyncBridge(1), BuiltinProvider(1), CallableCheck(1), Cell(1), Check(1), ConfigToolSource(1), DelegatingInterpreter(1), ErrorValue(1), ExecutionContext(1), ExecutionPlugin(1), Fallback(1), FreshFixStep(1), Frontmatter(1), GenerateDSLStep(1), GenerationResult(1), Grade(1), HarnessConfig(1), HasPromptHint(1), Hole(1), IncrementalInterpreter(1), InferenceDispatcher(1), InferenceProvider(1), InferenceStrategy(1), Interpreter(1), InterpreterCheck(1), InterpreterExecutionResult(1), InterpreterValidationResult(1), Lackey(1), LackeyMeta(1), LackpyToolWrapper(1), Ledger(1), LedgerEntry(1), Log(1), OneShotStrategy(1), ParseResult(1), PluginAdvice(1), PolicyLayer(1), PolicySource(1)
- **calls:** get(104), append(93), print(92), isinstance(57), strip(53), len(42), add_argument(41), join(32), Intent(29), field(27), sorted(23), GateResult(22), add_parser(21), split(21), str(21), add(17), update(17), Path(16), perf_counter(15), startswith(15), dumps(14), group(14), items(14), set(14), exists(12), list(12), _names_from_target(11), Sequence(10), lower(10), visit(10), getattr(9), open(9), replace(9), run(9), ValueError(8), _markdown_contains(8), defaultdict(8), validate(8), ArgumentParser(7), ValidateStep(7), compile(7), loads(7), match(7), mkdir(7), parse_args(7), RuntimeError(6), _repr_contains_all(6), _repr_contains_any(6), add_subparsers(6), count(6), enumerate(6), hasattr(6), int(6), keys(6), main(6), partial(6), read_text(6), rstrip(6), time(6), write_text(6)
- **frequent node types:** identifier(9389), string_content(1958), string(1852), =(1631), attribute(1523), call(1487), argument_list(1479), expression_statement(1384), type(1069), assignment(824), keyword_argument(806), block(798), dotted_name(532), integer(317), return_statement(305), if_statement(287), interpolation(262), subscript(241), none(239), in(231), type_parameter(226), generic_type(226), comparison_operator(225), function_definition(224), parameters(224), typed_parameter(222), ->(213), pair(199), binary_operator(167), import_from_statement(160), comment(143), list(124), boolean_operator(113), for_statement(100), not(98), escape_sequence(90), import_prefix(90), relative_import(90), dictionary(80), not_operator(74), |(72), typed_default_parameter(67), ==(66), slice(62), or(62)

### `py-pluckit` — 30 files from pluckit@99242d9a9

- **class counts** (don't use any the notes exclude): .fn 247, .class 28, .call 1171, .loop 114, .if 335, .jump 293, .try 61, .catch 52, .throw 41, .import 259, .var 959, .member 1460, .comp 41, .mod 30
- **functions:** __init__(9), main(6), from_dict(4), from_json(4), to_dict(4), to_json(4), __getattr__(3), __repr__(3), _distinct_files(3), find(3), search(3), __dir__(2), _build_parser(2), _empty_like(2), _find_root_selector(2), _open_output(2), from_argv(2), pluckins(2), source(2), to_argv(2), view(2), __enter__(1), __exit__(1), __len__(1), _assert_fts_index(1), _call_graph_query(1), _check_plausibility(1), _check_selector_plausibility(1), _cmd_init(1), _dedent_and_reindent(1), _ensure(1), _ensure_extensions(1), _ensure_index(1), _ensure_markdown_extension(1), _esc(1), _esc_like(1), _extract_lines(1), _extract_selector_node_type(1), _find_matching_paren(1), _find_stale_files(1), _flatten_composition_ops(1), _fledgling_connection(1), _format_op_line(1), _get_mutation_ops(1), _git_log_file(1), _git_read_file(1), _group_operations(1), _hash_pattern(1), _is_garbled_intent(1), _materialize(1), _new(1), _new_connection_with_fledgling(1), _node_text_at_rev(1), _output_type_from_signature(1), _package_version(1), _parse_args(1), _parse_composition(1), _parse_example_chains(1), _parse_operation(1), _parse_operations(1)
- **classes:** ASTCache(1), Calls(1), ChainOp(1), ChainValidationResult(1), Commit(1), DiffResult(1), DocSelection(1), FnAccessor(1), History(1), InterfaceInfo(1), Isolated(1), MutationEngine(1), NodeInfo(1), Operation(1), Plucker(1), PluckerError(1), Pluckin(1), PluckinRegistry(1), PluckitConfig(1), Scope(1), Search(1), Selector(1), Selectors(1), Source(1), Spec(1), TypeInfo(1), _Context(1), _ModuleFnAccessor(1)
- **calls:** append(72), get(62), print(59), sql(55), join(50), add_argument(44), choice(42), _esc(31), PluckerError(30), len(25), strip(21), int(19), replace(19), dumps(16), fetchall(15), Path(13), _new(13), fetchone(12), open(11), str(11), count(10), list(10), write(10), ChainValidationResult(9), cls(9), isinstance(9), set(9), split(9), dict(8), extend(8), getattr(8), items(8), splitlines(8), _register(7), _unregister(7), field(7), sorted(7), startswith(7), ArgumentParser(6), connect(6), loads(6), main(6), parse_args(6), _empty_like(5), add(5), dataclass(5), from_pretrained(5), getcwd(5), materialize(5), to_dict(5), values(5), AttributeError(4), Selection(4), _assert_fts_index(4), _distinct_files(4), _fledgling_connection(4), close(4), endswith(4), from_dict(4), generate(4)
- **frequent node types:** identifier(7565), string_content(3453), string(3136), attribute(1216), expression_statement(1207), call(1171), argument_list(1165), =(1147), pair(781), type(760), block(742), assignment(725), interpolation(506), comment(469), keyword_argument(412), dotted_name(380), escape_sequence(329), if_statement(275), return_statement(254), dictionary(241), none(230), subscript(221), integer(196), function_definition(193), parameters(193), comparison_operator(191), in(171), ->(171), typed_parameter(170), list(156), type_parameter(149), generic_type(149), import_from_statement(128), binary_operator(116), not(107), |(80), tuple(69), not_operator(65), typed_default_parameter(64), for_statement(64), try_statement(61), import_statement(60), boolean_operator(58), lambda(54), true(54)

### `py-umwelt` — 40 files from umwelt@6da9e119a

- **class counts** (don't use any the notes exclude): .fn 274, .class 69, .call 1891, .loop 244, .if 515, .jump 433, .try 46, .catch 55, .throw 42, .import 311, .var 1511, .member 1605, .comp 51, .mod 40
- **functions:** __init__(4), children(4), condition_met(4), get_attribute(4), get_id(4), match_type(4), array_literal(3), compile(3), format_specificity(3), json_attr(3), json_attr_list_contains(3), list_contains(3), map_literal(3), materialize(3), _hash_file(2), _is_literal(2), _span(2), reconcile(2), validate(2), _apply_excludes(1), _build_rule_block(1), _build_unknown_at_rule(1), _canonical_axis(1), _cmd_audit(1), _cmd_check(1), _cmd_compile(1), _cmd_compile_sql(1), _cmd_diff(1), _cmd_dry_run(1), _cmd_inspect(1), _cmd_materialize(1), _cmd_parse(1), _cmd_run(1), _collect_env(1), _collect_exec(1), _collect_file(1), _collect_from_raw_rules(1), _collect_mount(1), _collect_network(1), _collect_resource(1), _collect_source_declarations(1), _compile_attr_filter(1), _compile_context_qualifier(1), _compile_pseudo(1), _compile_simple(1), _compile_structural_ancestor(1), _create_resolved_entities_view(1), _create_typed_view(1), _current_state(1), _decls_equal(1), _describe_entity(1), _desugar_after_change(1), _desugar_audit(1), _desugar_budget(1), _desugar_env(1), _desugar_network(1), _desugar_source(1), _desugar_tools(1), _detect_ceiling_conflict(1), _detect_ceiling_ineffective(1)
- **classes:** ActorMatcher(1), Applied(1), AttrFilter(1), AttrSchema(1), AuditMatcher(1), AuditReport(1), BudgetEntity(1), BwrapCompilation(1), BwrapCompiler(1), BwrapResult(1), CapabilityMatcher(1), CapabilityValidator(1), Compiler(1), ComplexSelector(1), CompoundPart(1), Conflict(1), Declaration(1), Dialect(1), DirEntity(1), DuckDBDialect(1), EntityAudit(1), EntitySchema(1), EnvEntity(1), ExecEntity(1), ExecutorEntity(1), FileEntity(1), HookEntity(1), InferencerEntity(1), JobEntity(1), KitEntity(1), LackpyNamespaceCompiler(1), LintConfig(1), ManifestEntity(1), MaterializationStrategy(1), ModeEntity(1), MountEntity(1), NetworkEntity(1), NoOp(1), NsjailResult(1), ObservationEntity(1)
- **calls:** append(157), getattr(141), execute(60), get(53), register_property(51), str(48), print(44), dataclass(42), list(42), AttrSchema(41), int(38), len(37), extend(33), fetchall(32), isinstance(31), replace(31), items(29), join(29), tuple(26), add_argument(24), field(22), Path(20), _current_state(20), register_entity(20), ViewParseError(19), _span(19), set(18), _is_literal(17), strip(14), LintWarning(12), add(12), fetchone(11), setdefault(11), sorted(10), split(10), Declaration(9), RuleBlock(9), _entity_name(9), _load_default_vocabulary(9), add_parser(9), dict(9), dumps(9), parse(9), serialize(9), set_defaults(9), _parse_sel(8), lower(8), resolve(8), suppress(8), DeclaredEntity(7), RegistryError(7), WorldWarning(7), enumerate(7), parse_declaration_list(7), register_matcher(7), register_sugar(7), resolve_taxon(7), _register_matchers(6), chr(6), commit(6)
- **frequent node types:** identifier(12130), =(2182), string_content(2097), string(1976), call(1891), argument_list(1877), expression_statement(1791), type(1672), attribute(1398), keyword_argument(1182), block(1103), assignment(1040), dotted_name(541), none(490), generic_type(409), type_parameter(409), typed_parameter(408), if_statement(394), return_statement(373), comparison_operator(367), integer(320), in(304), interpolation(300), function_definition(268), parameters(268), ->(264), list(216), comment(215), subscript(200), import_from_statement(191), for_statement(186), boolean_operator(170), binary_operator(167), ==(154), tuple(153), |(149), not(121), pair(103), or(97), true(96), pattern_list(84), is(83), dictionary(80), and(73), class_definition(69)
