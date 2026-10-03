#!/usr/bin/env python3
"""Mine structural AST diffs from harvested git edits using sitting_duck in DuckDB.

Parses old and new file revisions using parse_ast_list_table, computes node-level
deltas, identifies the target AST container, and classifies the fluent operation.

Output: workspace/editmine/mined_mutations.jsonl
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP_ROOT = os.path.dirname(HERE)
DEFAULT_INPUT = os.path.join(SETUP_ROOT, "workspace", "editmine", "git_edits_smoke.jsonl")
DEFAULT_OUTPUT = os.path.join(SETUP_ROOT, "workspace", "editmine", "mined_mutations.jsonl")
SITTING_DUCK_EXT = "/home/teague/Projects/sitting_duck/build/release/extension/sitting_duck/sitting_duck.duckdb_extension"
DUCKDB_CLI = "/home/teague/Projects/sitting_duck/build/release/duckdb"


def run_mining_query(input_jsonl, output_jsonl):
    import subprocess
    os.makedirs(os.path.dirname(output_jsonl), exist_ok=True)

    sql = f"""
    SET threads TO 8;
    SET memory_limit = '8GB';
    INSTALL json; LOAD json;
    LOAD '{SITTING_DUCK_EXT}';

    CREATE OR REPLACE VIEW edits AS
    SELECT row_number() OVER () AS edit_id, repo, commit, message, file_path, lang, ext, old, new
    FROM read_json_auto('{input_jsonl}', ignore_errors=true)
    WHERE lang IS NOT NULL AND length(trim(old)) > 0 AND length(trim(new)) > 0;

    -- Count node types on old and new sides
    CREATE OR REPLACE TABLE old_nodes AS
    SELECT e.edit_id, e.repo, e.commit, e.message, e.file_path, e.lang, 'old' AS side, t.type, count(*) AS cnt
    FROM edits e, LATERAL parse_ast_list_table(e.old, e.lang) t
    GROUP BY 1,2,3,4,5,6,7,8;

    CREATE OR REPLACE TABLE new_nodes AS
    SELECT e.edit_id, e.repo, e.commit, e.message, e.file_path, e.lang, 'new' AS side, t.type, count(*) AS cnt
    FROM edits e, LATERAL parse_ast_list_table(e.new, e.lang) t
    GROUP BY 1,2,3,4,5,6,7,8;

    -- Join to find structural deltas per edit
    CREATE OR REPLACE TABLE deltas AS
    SELECT 
        coalesce(n.edit_id, o.edit_id) AS edit_id,
        coalesce(n.repo, o.repo) AS repo,
        coalesce(n.commit, o.commit) AS commit,
        coalesce(n.message, o.message) AS message,
        coalesce(n.file_path, o.file_path) AS file_path,
        coalesce(n.lang, o.lang) AS lang,
        coalesce(n.type, o.type) AS node_type,
        coalesce(n.cnt, 0) - coalesce(o.cnt, 0) AS delta
    FROM new_nodes n
    FULL OUTER JOIN old_nodes o 
      ON n.edit_id = o.edit_id AND n.type = o.type
    WHERE coalesce(n.cnt, 0) != coalesce(o.cnt, 0);

    -- Classify high-level fluent operations
    CREATE OR REPLACE TABLE classified_ops AS
    SELECT 
        edit_id, repo, commit, message, file_path, lang,
        CASE
            WHEN node_type IN ('decorator','attribute_item','attribute','annotation','meta_item') AND delta > 0 THEN 'addDecorator'
            WHEN node_type IN ('decorator','attribute_item','attribute','annotation','meta_item') AND delta < 0 THEN 'removeDecorator'
            WHEN node_type IN ('import_statement','import_from_statement','use_declaration','preproc_include','import_declaration') AND delta > 0 THEN 'addImport'
            WHEN node_type IN ('import_statement','import_from_statement','use_declaration','preproc_include','import_declaration') AND delta < 0 THEN 'removeImport'
            WHEN node_type IN ('field_declaration','property_signature','field_definition','struct_field','record_field') AND delta > 0 THEN 'addField'
            WHEN node_type IN ('field_declaration','property_signature','field_definition','struct_field','record_field') AND delta < 0 THEN 'removeField'
            WHEN node_type IN ('parameter_declaration','parameters','formal_parameters') AND delta > 0 THEN 'addParam'
            WHEN node_type IN ('parameter_declaration','parameters','formal_parameters') AND delta < 0 THEN 'removeParam'
            WHEN node_type IN ('argument_list','arguments','argument') AND delta > 0 THEN 'addArg'
            WHEN node_type IN ('argument_list','arguments','argument') AND delta < 0 THEN 'removeArg'
            WHEN node_type IN ('assert_statement','assert','test_assertion') AND delta > 0 THEN 'addAssertion'
            WHEN node_type IN ('with_statement','with_clause','using_statement') AND delta > 0 THEN 'wrapWith'
            WHEN node_type IN ('await_expression','await') AND delta > 0 THEN 'wrapAwait'
            WHEN node_type IN ('call_expression','call','method_invocation') AND delta > 0 AND (message ILIKE '%chain%' OR message ILIKE '%.then%' OR message ILIKE '%.map%') THEN 'chainCall'
            WHEN node_type IN ('call_expression','call','method_invocation') AND delta > 0 THEN 'wrapCall'
            WHEN node_type IN ('try_statement','except_clause','catch_clause') AND delta > 0 THEN 'wrapInTry'
            WHEN node_type IN ('assignment','variable_declarator','lexical_declaration','local_variable_declaration') AND delta > 0 AND (message ILIKE '%extract%' OR message ILIKE '%assign%') THEN 'extractVariable'
            WHEN node_type IN ('function_definition','function_declaration','function_item','method_declaration') AND delta > 0 AND (message ILIKE '%extract%' OR message ILIKE '%refactor%') THEN 'extractFunction'
            WHEN (message ILIKE '%move %' OR message ILIKE '%relocate%' OR message ILIKE '%reorder%') AND delta != 0 THEN 'moveTo'
            WHEN node_type IN ('comment','line_comment','block_comment') AND delta > 0 THEN 'addComment'
            WHEN node_type IN ('return_statement','return') AND delta != 0 THEN 'setReturn'
            WHEN node_type IN ('if_statement','else_clause','elif_clause') AND delta > 0 THEN 'addCondition'
            WHEN node_type IN ('visibility_modifier','export_statement') AND delta != 0 THEN 'setVisibility'
            WHEN node_type = 'async' AND delta != 0 THEN 'setAsync'
            WHEN node_type IN ('type_annotation','type_identifier','typed_parameter','return_type') AND delta != 0 THEN 'setReturnType'
            ELSE 'replace'
        END AS inferred_op,
        node_type,
        delta
    FROM deltas
    WHERE delta != 0;

    COPY (
        SELECT edit_id, repo, commit, message, file_path, lang, inferred_op, node_type, delta
        FROM classified_ops
        ORDER BY edit_id
    ) TO '{output_jsonl}' (FORMAT JSON);
    """

    res = subprocess.run([DUCKDB_CLI, "-unsigned", "-c", sql], capture_output=True, text=True)
    if res.returncode != 0:
        print("DuckDB error:", res.stderr)
        return False

    print(f"[✓] Mined AST diffs saved to {output_jsonl}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Mine AST diff operations using DuckDB")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Harvested git edits JSONL")
    parser.add_argument("--out", default=DEFAULT_OUTPUT, help="Output classified operations JSONL")
    args = parser.parse_args()

    run_mining_query(args.input, args.out)


if __name__ == "__main__":
    main()
