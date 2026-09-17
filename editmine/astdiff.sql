-- AST-diff mining as ONE query: which operations do real edits actually perform?
--
-- Line-based diffing hid addArg/addParam/wrap_expression because they wrap across line breaks,
-- and my first pass concluded only 26.7% of `replace` decomposes. That was a property of the
-- METHOD. parse_ast_list_table(code, lang) takes a COLUMN, so both sides of every edit can be
-- parsed in a single set-based query and compared by node-type multiset.
--
--   duckdb -unsigned < editmine/astdiff.sql
INSTALL json; LOAD json;
LOAD '/home/teague/Projects/sitting_duck/build/release/extension/sitting_duck/sitting_duck.duckdb_extension';

CREATE OR REPLACE VIEW edits AS
SELECT row_number() OVER () AS pair_id, ext, old, new,
       CASE ext WHEN '.py'  THEN 'python' WHEN '.cpp' THEN 'cpp'  WHEN '.hpp' THEN 'cpp'
                WHEN '.rs'  THEN 'rust'   WHEN '.sh'  THEN 'bash' WHEN '.mjs' THEN 'javascript'
                WHEN '.js'  THEN 'javascript' WHEN '.jsx' THEN 'javascript' WHEN '.ts' THEN 'typescript'
                WHEN '.go'  THEN 'go'     WHEN '.java' THEN 'java' WHEN '.c' THEN 'c' WHEN '.h' THEN 'c' END AS lang
FROM read_json_auto('workspace/editmine/edits-*.jsonl', union_by_name=true, ignore_errors=true)
WHERE kind = 'edit' AND tool = 'Edit'
  AND old IS NOT NULL AND new IS NOT NULL AND length(trim(old)) > 0 AND length(trim(new)) > 0;

-- node-type counts per side, in one pass over each column
CREATE OR REPLACE TABLE side_counts AS
SELECT pair_id, ext, 'old' AS side, t.type, count(*) AS n
  FROM edits e, LATERAL parse_ast_list_table(e.old, e.lang) t WHERE e.lang IS NOT NULL GROUP BY 1,2,3,4
UNION ALL
SELECT pair_id, ext, 'new', t.type, count(*)
  FROM edits e, LATERAL parse_ast_list_table(e.new, e.lang) t WHERE e.lang IS NOT NULL GROUP BY 1,2,3,4;

-- asymmetric node-type deltas = the operation performed
CREATE OR REPLACE TABLE deltas AS
SELECT pair_id, ext, type,
       sum(CASE WHEN side='new' THEN n ELSE 0 END) - sum(CASE WHEN side='old' THEN n ELSE 0 END) AS delta
FROM side_counts GROUP BY 1,2,3 HAVING delta <> 0;

.print '=== operations by node-type delta (AST, not lines) ==='
SELECT CASE
         WHEN type IN ('parameter_declaration','parameters','parameter','formal_parameters') THEN 'param'
         WHEN type IN ('argument_list','arguments','argument')                                THEN 'arg'
         WHEN type IN ('call_expression','call')                                              THEN 'call/wrap'
         WHEN type IN ('comment','line_comment','block_comment')                              THEN 'comment'
         WHEN type IN ('preproc_include','import_statement','import_from_statement','use_declaration') THEN 'import'
         WHEN type IN ('try_statement','catch_clause','except_clause')                        THEN 'error_handling'
         WHEN type IN ('return_statement','return')                                           THEN 'return'
         WHEN type IN ('if_statement','else_clause','elif_clause')                            THEN 'condition'
         WHEN type IN ('function_definition','function_declarator','function_item','method_definition') THEN 'function'
       END AS op,
       sum(CASE WHEN delta > 0 THEN 1 ELSE 0 END) AS added_in,
       sum(CASE WHEN delta < 0 THEN 1 ELSE 0 END) AS removed_in
FROM deltas WHERE op IS NOT NULL GROUP BY 1 ORDER BY added_in DESC;

.print ''
.print '=== coverage: how many edits carry at least one named op? ==='
SELECT count(DISTINCT pair_id) FILTER (WHERE type IN (
         'parameter_declaration','parameters','argument_list','arguments','call_expression','call',
         'comment','preproc_include','import_statement','try_statement','except_clause','return_statement',
         'if_statement','function_definition','function_declarator')) AS named,
       (SELECT count(*) FROM edits WHERE lang IS NOT NULL) AS total
FROM deltas;
