# Drafting packet: C

Read `train/BRIEF.md` first: it has the pair format, the tiers, the engine and verifier rules,
the draft -> verify -> fix loop, and what you must not touch. This packet adds your language.

- **Target:** 80 accepted pairs, about 20 per tier (T1-T4).
- **Candidate files:** `train/candidates/c-b1.jsonl`, then `c-b1-r1.jsonl`, `c-b2.jsonl`, ...
- **Verify:** `/home/teague/.local/share/venv/bin/python pilot.py train/candidates/<batch>.jsonl <batch> train`
  (batch id = file name without `.jsonl`, run from `/home/teague/Projects/astcss-eval/trees/train/multilang`).
- **Ids:** `tr-c-t<tier>-<nnnn>`, never reused across your batches.
- **Fixtures you may use:** `c-duckhts`.

## The card the model is prompted with

Write selectors in this vocabulary. A class not on this card must not appear in your pairs.

```text
You translate a developer's plain-English request into ONE astcss selector over a C
code tree. Reply with the selector only: one line, no quotes, no backticks, no explanation.

SEMANTIC CLASSES (cross-language; prefer these)
  .fn .func .method       function or method definitions  (function_definition, preproc_function_def)
  .class                  class definitions  (struct_specifier, type_definition, enum_specifier, union_specifier)
  .mod                    the module  (translation_unit)
  .var                    variable definitions  (declaration, init_declarator, parameter_declaration, field_declaration)
  .call                   function or method calls  (call_expression, preproc_call, offsetof_expression)
  .loop                   loops  (for_statement, while_statement, do_statement)
  .jump                   return / break / continue / yield  (return_statement, goto_statement, break_statement, continue_statement)

C NODE TYPES (exact tree-sitter names, written with no dot, when no class fits)
  if_statement return_statement preproc_include function_definition

FILTERS ON A NODE (written directly after it, no space)
  #name                   exactly this name:            .fn#main   .call#malloc   .class#config_t
  [name^="x"]             name starts with x            .fn[name^="parse_"]
  [name$="x"]             name ends with x
  [name*="x"]             name contains x
  :has(S)                 contains a descendant matching S     .fn:has(.call#malloc)
  :not(:has(S))           contains no descendant matching S    .fn:not(:has(.loop))

COMBINATORS (exactly two steps; filters other than #name go on the second step only)
  A B                     B anywhere inside A          .fn#main .call
  A > B                   B is a direct child of A     .mod > .fn
  A ~ B                   B is a later sibling of A    preproc_include ~ .fn
  A + B                   B immediately follows A      .fn + .fn

EXAMPLES
  every function                              .fn
  calls to malloc                             .call#malloc
  structs whose names end with _t             .class[name$="_t"]
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


## Notes for C — fixture c-duckhts

- **Don't use `.if`** (adds the `?` token), **`.import`** (adds
  `system_lib_string`), **`.member`** (adds `->`). Use `if_statement`,
  `conditional_expression`, `switch_statement`, `preproc_include`,
  `field_expression`.
- `.fn` is `function_definition` and `preproc_function_def`; `.class` is
  `struct_specifier`, `type_definition`, `enum_specifier`, `union_specifier`.
  `.jump` includes `goto_statement`.


## Fixture inventories

Names and counts from the audit. Use real names from these lists; the verifier needs 1-50 matches.

### `c-duckhts` — 45 files from duckhts@eb2eb9ace

- **class counts** (don't use any the notes exclude): .fn 272, .class 78, .call 2040, .loop 211, .if 1569, .jump 813, .try 0, .catch 0, .throw 0, .import 522, .var 1985, .member 3629, .comp 0, .mod 45
- **functions:** main(22), print_usage(19), pool_alloc(3), pool_free(3), GET(2), SET(2), decode_qual(2), decode_seq(2), destroy_seq_bind(2), destroy_seq_init(2), ensure_buf(2), fasta_read_bind(2), fastq_read_bind(2), hts_drand48(2), hts_erand48(2), hts_lrand48(2), hts_md5_final(2), hts_md5_init(2), hts_md5_reset(2), hts_md5_update(2), hts_srand48(2), htscodecs_tls_alloc(2), htscodecs_tls_calloc(2), htscodecs_tls_free(2), nibble2base_resolve(2), plpconstructor(2), plpdestructor(2), printauxdata(2), readdata(2), register_read_fasta_function(2), register_read_fastq_function(2), seq_read_bind(2), seq_read_function(2), seq_read_init(2), set_null(2), strip_pair_suffix(2), F(1), G(1), H(1), H2(1), I(1), IF_OL(1), PLUGIN_GLOBAL(1), STATE(1), STEP(1), _dorand48(1), adopt_listen_sockets(1), body(1), check_running(1), cleanup_bamstorage(1), close_listen_sockets(1), close_logs(1), close_plugin(1), compare_hts_pair_pos_t(1), copy_raw(1), count_char(1), cpu_supports_neon(1), cram_stats_add(1), cram_stats_create(1), cram_stats_del(1)
- **classes:** addrinfo(4), data(4), epoll_event(4), plpconf(4), RefFile(3), hts_path_itr(3), stat(3), RefFiles(2), aarch64_sysctl_cpu_id(2), datacache(2), dirent(2), hFILE(2), htsExactFormat(2), orderedwrite(2), seq_bind_data_t(2), seq_init_data_t(2), Listeners(1), Logfile(1), Logfiles(1), Poll_wrap(1), cram_encoding(1), fai_format_options(1), hFILE_plugin(1), hFILE_scheme_handler(1), htsLogLevel(1), htsRealnFlags(1), hts_md5_context(1), hts_md5_u32plus(1), kh_reg_t(1), option(1), reglist(1), reglist_t(1), sockaddr(1), tls_pool(1), tm(1), ubyte_t(1), xyz(1)
- **calls:** printf(200), fprintf(103), free(94), STEP(64), GET(48), sam_close(39), sam_open(32), strlen(32), malloc(30), vep_free(28), error(27), strcmp(27), memcpy(22), sam_hdr_destroy(22), sam_hdr_read(22), snprintf(22), calloc(21), sam_read1(20), bam_destroy1(19), bam_init1(19), print_usage(19), duckdb_free(18), IF_OL(17), bam_seqi(17), kputc(17), SET(16), memset(16), strerror(16), bam_get_seq(15), kputs(15), sam_hdr_write(14), sam_write1(14), assert(13), bam_aux2i(12), bam_auxB2i(12), bam_get_qname(12), duckdb_bind_add_result_column(12), duckdb_vector_assign_string_element(12), hexval(12), kh_val(12), kputsn(12), strchr(12), strstr(12), realloc(11), close(10), dehex(10), duckdb_create_logical_type(10), duckdb_data_chunk_set_size(10), duckdb_destroy_logical_type(10), rint(10), set_null(10), hgetc(9), perror(9), vep_malloc(9), duckdb_init_set_error(8), kh_end(8), bam_aux_type(7), bam_get_qual(7), bam_aux_get(6), duckdb_bind_set_error(6)
- **frequent node types:** identifier(11674), number_literal(2278), expression_statement(2163), argument_list(2041), call_expression(2038), binary_expression(1988), =(1834), field_identifier(1460), parenthesized_expression(1455), assignment_expression(1350), field_expression(1344), *(1213), compound_statement(1156), primitive_type(1099), ->(1084), if_statement(960), pointer_declarator(837), comment(821), subscript_expression(793), string_content(774), string_literal(721), declaration(676), type_identifier(667), init_declarator(626), parameter_declaration(521), escape_sequence(497), return_statement(462), null(412), NULL(412), pointer_expression(408), ==(334), char_literal(325), preproc_include(291), update_expression(291), #include(291), <(286), &(283), parameter_list(275), function_declarator(273), ++(265), function_definition(258), unary_expression(254), character(241), !(239), system_lib_string(231)
