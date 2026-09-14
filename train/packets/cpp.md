# Drafting packet: C++

Read `train/BRIEF.md` first: it has the pair format, the tiers, the engine and verifier rules,
the draft -> verify -> fix loop, and what you must not touch. This packet adds your language.

- **Target:** 110 accepted pairs, about 27 per tier (T1-T4).
- **Candidate files:** `train/candidates/cpp-b1.jsonl`, then `cpp-b1-r1.jsonl`, `cpp-b2.jsonl`, ...
- **Verify:** `/home/teague/.local/share/venv/bin/python pilot.py train/candidates/<batch>.jsonl <batch> train`
  (batch id = file name without `.jsonl`, run from `/home/teague/Projects/astcss-eval/trees/train/multilang`).
- **Ids:** `tr-cpp-t<tier>-<nnnn>`, never reused across your batches.
- **Fixtures you may use:** `cpp-duck-hunt`, `cpp-duckdb-mcp`, `cpp-duckdb-yaml`.

## The card the model is prompted with

Write selectors in this vocabulary. A class not on this card must not appear in your pairs.

```text
You translate a developer's plain-English request into ONE astcss selector over a C++
code tree. Reply with the selector only: one line, no quotes, no backticks, no explanation.

SEMANTIC CLASSES (cross-language; prefer these)
  .class                  class definitions  (class_specifier, struct_specifier, enum_specifier)
  .mod                    the module  (namespace_definition, translation_unit)
  .var                    variable definitions  (declaration, parameter_declaration, init_declarator, field_declaration)
  .call                   function or method calls  (call_expression)
  .loop                   loops  (while_statement, for_range_loop, for_statement)
  .jump                   return / break / continue / yield  (return_statement, continue_statement, break_statement)
  .try .catch .throw      try blocks, except handlers, raise, finally  (throw_statement, catch_clause, try_statement)

C++ NODE TYPES (exact tree-sitter names, written with no dot, when no class fits)
  if_statement return_statement function_definition preproc_include

FILTERS ON A NODE (written directly after it, no space)
  #name                   exactly this name:            function_definition#main   .call#push_back   .class#Config
  [name^="x"]             name starts with x            function_definition[name^="Parse"]
  [name$="x"]             name ends with x
  [name*="x"]             name contains x
  :has(S)                 contains a descendant matching S     function_definition:has(.throw)
  :not(:has(S))           contains no descendant matching S    function_definition:not(:has(.loop))

COMBINATORS (exactly two steps; filters other than #name go on the second step only)
  A B                     B anywhere inside A          .class#Config function_definition
  A > B                   B is a direct child of A     translation_unit > preproc_include
  A ~ B                   B is a later sibling of A    preproc_include ~ namespace_definition
  A + B                   B immediately follows A      function_definition + function_definition

EXAMPLES
  every function definition                   function_definition
  calls to push_back                          .call#push_back
  classes whose names end with Error          .class[name$="Error"]
  functions defined inside the Config class   .class#Config function_definition
  functions that never throw                  function_definition:not(:has(.throw))
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


## Notes for C++ — fixtures cpp-duck-hunt, cpp-duckdb-yaml, cpp-duckdb-mcp

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


## Fixture inventories

Names and counts from the audit. Use real names from these lists; the verifier needs 1-50 matches.

### `cpp-duck-hunt` — 45 files from duck_hunt@3bea8ca1a

- **class counts** (don't use any the notes exclude): .fn 540, .class 25, .call 1702, .loop 65, .if 1385, .jump 409, .try 11, .catch 11, .throw 11, .import 251, .var 1813, .member 4925, .comp 0, .mod 96
- **functions:** canParse(35), parse(35), getCategory(26), getFormatName(26), getName(26), getPriority(26), make_uniq(22), yyjson_arr_foreach(22), getCommandPatterns(20), stream(16), getDescription(10), iss(5), static_cast(5), MapLevelToStatus(4), parseJUnitTextImpl(3), reader(3), CalculateMessageSimilarity(2), Cast(2), CategorySupportsWorkflow(2), ClangTidyParser(2), CreateEventFromRequest(2), DetectFormat(2), DetectRootCauseCategory(2), DuckHuntFormatsBind(2), DuckHuntFormatsBindData(2), DuckHuntFormatsFunction(2), DuckHuntFormatsGlobalState(2), DuckHuntFormatsInitGlobal(2), EditDistance(2), ExtractConfigPath(2), ExtractIntField(2), ExtractJSONString(2), ExtractNestedJSONString(2), ExtractStringField(2), FormatValidationError(2), GenerateErrorFingerprint(2), GetDuckHuntFormatsFunction(2), HasRootElement(2), HasXmlDeclaration(2), IsConfigFilePath(2), IsExceptionLine(2), IsStackTraceLine(2), IsValidFormat(2), LooksLikeXml(2), MapEventNameToSeverity(2), MapJavaLevel(2), MapLevelToSeverity(2), MapStatusCodeToSeverity(2), MapStatusCodeToStatus(2), NeedsNormalization(2), NormalizeErrorMessage(2), ParseCloudTrailRecord(2), ParseContent(2), ParseContentAuto(2), ParseContentRegexp(2), ParseFile(2), ParseJsonLine(2), ParseLog4jLine(2), ParseRailsLine(2), ParseVpcFlowLine(2)
- **classes:** BanditJSONParser(1), ClangTidyParser(1), DuckDBTestParser(1), DuckHuntFormatsBindData(1), DuckHuntFormatsGlobalState(1), FailureInfo(1), HadolintTextParser(1), LcovParser(1), MochaChaiTextParser(1), MypyParser(1), PlaywrightTextParser(1), PytestParser(1), RailsRequest(1), ReadDuckHuntWorkflowLogBindData(1), ReadDuckHuntWorkflowLogGlobalState(1), ReadDuckHuntWorkflowLogLocalState(1), RuffJsonParser(1), SwiftLintJSONParser(1), SyslogParser(1), TrivyJSONParser(1), WebbedIntegration(1), WorkflowEvent(1), WorkflowLogFormat(1), XmlParserBase(1), tm(1)
- **calls:** find(234), str(227), empty(128), push_back(100), regex_search(85), yyjson_obj_get(55), SafeStoi(53), substr(37), to_string(35), size(33), Like(29), yyjson_is_str(29), length(26), yyjson_get_str(24), yyjson_doc_free(23), getline(20), registerParser(20), yyjson_is_arr(20), yyjson_is_obj(20), begin(17), EscapeJsonString(16), end(16), regex_replace(15), c_str(14), yyjson_doc_get_root(14), yyjson_read(14), find_first_not_of(12), yyjson_get_int(12), yyjson_is_num(12), regex_match(11), ExtractJSONString(10), find_last_not_of(9), IOException(8), SetValue(8), Value(8), getInstance(8), Literal(7), ExtractStringField(6), SafeStod(6), parse(6), reserve(6), transform(6), ExtractNestedJSONString(5), ReadContentFromSource(5), Regexp(5), move(5), LIST(4), SafeRegexSearch(4), SplitFormatList(4), back(4), getContentFamily(4), insert(4), isPhaseMarker(4), isSpackMarker(4), make_pair(4), min(4), yyjson_arr_get_first(4), DECLARE_PARSER_CATEGORY(3), EndsWith(3), IsConfigFilePath(3)
- **frequent node types:** identifier(7329), field_identifier(2673), field_expression(2515), namespace_identifier(2108), ::(2070), qualified_identifier(2070), =(1938), argument_list(1834), expression_statement(1782), call_expression(1702), string_literal(1569), string_content(1567), assignment_expression(1548), type_identifier(1377), binary_expression(1186), declaration(833), compound_statement(792), comment(664), number_literal(655), condition_clause(581), init_declarator(569), if_statement(551), type_qualifier(479), primitive_type(340), return_statement(336), parameter_declaration(325), parameter_list(305), escape_sequence(305), subscript_argument_list(295), subscript_expression(295), function_declarator(293), +(292), >(286), &(275), reference_declarator(269), <(252), !=(244), type_descriptor(239), template_argument_list(232), function_definition(212), template_type(201), preproc_include(184), #include(184), ==(172), ||(166)

### `cpp-duckdb-mcp` — 45 files from duckdb_mcp@c8e35a3cf

- **class counts** (don't use any the notes exclude): .fn 1509, .class 96, .call 1913, .loop 91, .if 1195, .jump 482, .try 39, .catch 41, .throw 164, .import 303, .var 2992, .member 2374, .comp 0, .mod 94
- **functions:** lock(73), GetDescription(23), static_cast(23), GetName(19), make_uniq(16), GetConnectionInfo(15), GetValue(15), Connect(13), Disconnect(13), IsConnected(13), Ping(13), GetInputSchema(11), Read(11), Receive(11), Send(11), SendAndReceive(11), Execute(9), GetMimeType(9), IsValid(8), GetSize(7), FromValue(6), GetConnection(6), ToValue(6), FormatResult(5), ListResources(5), ListTools(5), Clear(4), Error(4), FreeDocument(4), GetBool(4), GetInt(4), GetLastError(4), GetMCPConnection(4), GetResultFormat(4), GetSqlTemplate(4), GetString(4), GetValueAsString(4), Initialize(4), IsRefreshable(4), IsRunning(4), MCPPaginationIterator(4), MCPPaginationParams(4), MCPTemplate(4), Parse(4), Refresh(4), Reset(4), Scan(4), ShouldRefresh(4), Success(4), Write(4), yyjson_arr_foreach(4), yyjson_obj_foreach(4), AllowsDirectRequests(3), Cast(3), IsValidCursor(3), ParseMCPAttachParams(3), ParseMCPConfigFile(3), ParsePaginationResponse(3), RegisterTool(3), ResourceExists(3)
- **classes:** MCPConnection(7), MCPMessage(4), MCPServer(3), MCPTransport(2), ResourceProvider(2), ToolHandler(2), WebMCPTransport(2), AttachInfo(1), CallToolResult(1), DatabaseInfoToolHandler(1), DatabaseInstance(1), DescribeToolHandler(1), DocGuard(1), ExecuteToolHandler(1), ExecutionSQLToolHandler(1), ExportToolHandler(1), FdServerTransport(1), HTTPConfig(1), HTTPResponse(1), HTTPServerConfig(1), HTTPServerTransport(1), HTTPTransport(1), JSONArgumentParser(1), JSONUtils(1), ListTablesToolHandler(1), MCPCapabilities(1), MCPCatalog(1), MCPConnectionParams(1), MCPConnectionRegistry(1), MCPConnectionState(1), MCPConnectionWithPagination(1), MCPError(1), MCPFileHandle(1), MCPFileSystem(1), MCPInstanceState(1), MCPLogLevel(1), MCPLogger(1), MCPMessageType(1), MCPPaginationIterator(1), MCPPaginationParams(1)
- **calls:** empty(73), emplace_back(62), Value(58), IOException(55), c_str(52), InvalidInputException(46), push_back(45), size(43), ToString(37), find(35), type(32), NotImplementedException(31), string(29), end(28), length(27), what(26), yyjson_obj_get(26), IsNull(25), close(25), STRUCT(23), load(23), GetValue(21), Contains(18), yyjson_doc_free(18), SetValue(17), move(17), yyjson_doc_get_root(17), InternalException(16), id(16), substr(16), yyjson_get_str(16), yyjson_is_obj(16), yyjson_is_str(16), CreateObject(15), GetString(15), IsConnected(14), MCP_LOG_ERROR(13), to_string(13), yyjson_mut_strcpy(13), AddObject(12), GetChildren(12), IsError(12), FreeDocument(11), Get(10), SetError(10), IsInitialized(9), MCP_LOG_DEBUG(9), Parse(9), SendRequest(9), ValueToJSON(9), set_header(9), yyjson_mut_obj_add(9), yyjson_read(9), AddString(8), CompatResultNames(8), Format(8), GetObject(8), LIST(8), at(8), free(8)
- **frequent node types:** identifier(6568), type_identifier(2538), field_identifier(2179), argument_list(2001), call_expression(1913), field_expression(1284), compound_statement(1118), parameter_list(1039), string_literal(1027), parameter_declaration(1010), string_content(1003), comment(991), function_declarator(984), namespace_identifier(924), =(922), ::(875), qualified_identifier(875), type_qualifier(842), expression_statement(815), &(806), reference_declarator(754), field_declaration(752), primitive_type(742), declaration(707), binary_expression(622), condition_clause(508), if_statement(478), <(477), return_statement(459), init_declarator(454), >(453), type_descriptor(451), function_definition(430), template_argument_list(425), assignment_expression(374), template_type(360), *(315), number_literal(297), pointer_declarator(281), #include(249), preproc_include(249), !(229), unary_expression(229), placeholder_type_specifier(177), auto(177)

### `cpp-duckdb-yaml` — 15 files from duckdb_yaml@77b40a21e

- **class counts** (don't use any the notes exclude): .fn 299, .class 19, .call 930, .loop 46, .if 574, .jump 163, .try 30, .catch 35, .throw 40, .import 124, .var 1027, .member 1543, .comp 0, .mod 33
- **functions:** make_uniq(23), Cast(9), Execute(9), static_cast(9), MakeLimitGetter(5), MakeLimitSetter(5), Copy(4), Equals(4), YAMLTraversalBudget(4), ApplyDocumentSeparator(3), ApplySequenceLayout(3), FormatValueWithLayout(3), PostProcessForLayout(3), Register(3), YAMLBudgetScope(3), BindColumnTypes(2), ClaimNextFile(2), CopyFormatYAMLFunction(2), CopyToYAMLPlan(2), DUCKDB_CPP_EXTENSION_ENTRY(2), DetectJaggedYAMLType(2), DetectYAMLType(2), DetectYAMLTypeImpl(2), ExtractFrontmatter(2), ExtractRowNodes(2), FormatYAMLBind(2), FormatYAMLFunction(2), FromYAMLBind(2), FromYAMLFunction(2), GetData(2), GetFiles(2), GetGlobFiles(2), GetYAMLCopyFunction(2), HasKey(2), IsYAMLType(2), JSONToYAMLCast(2), LoadInternal(2), MaxThreads(2), NavigateToPath(2), ParseMultiDocumentYAML(2), ReadFileContent(2), ReadYAMLFile(2), ReadYAMLReplacement(2), RecoverPartialYAMLDocuments(2), RegisterFromYAMLFunction(2), RegisterFunction(2), RegisterLimitFunctions(2), RegisterStyleFunctions(2), RegisterValidationFunction(2), RegisterYAMLCopyFunctions(2), RegisterYAMLFrontmatterFunction(2), RegisterYAMLTypeFunctions(2), ResetFileResources(2), StripDocumentSuffixes(2), ThrowYAMLCopyParameterException(2), ValueToYAMLFunction(2), VarcharToYAMLCast(2), YAMLFrontmatterBind(2), YAMLFrontmatterFunction(2), YAMLFrontmatterInit(2)
- **classes:** FormatYAMLBindData(1), FromYAMLBindData(1), MultiDocumentMode(1), ReplacementScanData(1), TableRef(1), YAMLBudgetScope(1), YAMLFormat(1), YAMLFrontmatterBindData(1), YAMLFrontmatterLocalState(1), YAMLFrontmatterOptions(1), YAMLFunctions(1), YAMLLayout(1), YAMLReadGlobalState(1), YAMLReadLocalState(1), YAMLReadOptions(1), YAMLReader(1), YAMLSettings(1), YAMLStringStyle(1), YAMLTraversalBudget(1)
- **calls:** size(71), id(51), Value(41), push_back(30), empty(29), RegisterFunction(24), move(24), c_str(21), find(21), SetValue(19), length(19), BinderException(18), end(16), ToString(15), InvalidInputException(14), begin(14), emplace_back(14), GetValue(13), ScalarFunction(12), Lower(11), substr(11), Cast(9), Execute(9), CompatSetFallible(8), GetAlias(8), string_t(8), AddString(7), GetString(7), HasAlias(7), IOException(7), IsMap(7), Load(7), what(7), CompatExprReturnType(6), Get(6), GetSize(6), IsNumeric(6), YAMLNodeToJSON(6), insert(6), type(6), CompatIdentifierName(5), GetFileSystem(5), IsNull(5), LIST(5), ParseYAML(5), Scalar(5), YAMLType(5), stoll(5), CheckInputSize(4), CompatSetScalarNullHandling(4), DOUBLE(4), DetectYAMLTypeImpl(4), MergeStructTypes(4), Register(4), RegisterCastFunction(4), ThrowYAMLCopyParameterException(4), ValueToYAMLString(4), back(4), clear(4), transform(4)
- **frequent node types:** identifier(2980), argument_list(943), call_expression(930), field_identifier(811), type_identifier(762), field_expression(703), comment(681), namespace_identifier(642), qualified_identifier(633), ::(633), binary_expression(514), compound_statement(459), =(437), string_literal(369), string_content(357), expression_statement(343), declaration(330), parameter_declaration(310), &(298), reference_declarator(276), init_declarator(270), condition_clause(236), if_statement(220), parameter_list(198), <(193), ==(188), number_literal(177), type_descriptor(170), >(159), return_statement(149), function_declarator(148), template_argument_list(147), assignment_expression(147), primitive_type(137), subscript_argument_list(134), subscript_expression(134), placeholder_type_specifier(121), auto(121), type_qualifier(121), preproc_include(110), #include(110), field_declaration(98), else_clause(88), template_type(85), storage_class_specifier(80)
