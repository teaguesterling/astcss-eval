-- Fluent API SQL Macro for DuckDB + sitting_duck
-- Parses JavaScript Fluent Calls into Declarative Instruction Lists
-- e.g. $('selector').op1(args).op2(args) -> {selector: '...', operations: [{op: '...', args: [...]}]}

CREATE OR REPLACE MACRO parse_fluent_call(fluent_expr) AS TABLE (
  WITH parsed_ast AS (
    SELECT *
    FROM parse_ast_list_table(fluent_expr, 'javascript')
  ),
  selectors AS (
    SELECT trim(coalesce(nullif(a.name, ''), a.peek), '"''') AS target_selector
    FROM parsed_ast a
    WHERE a.parent_id IN (
      SELECT node_id FROM parsed_ast WHERE parent_id IN (
        SELECT node_id FROM parsed_ast WHERE type = 'call_expression' AND name = '$'
      ) AND type = 'arguments'
    ) AND a.type NOT IN ('(', ')')
    LIMIT 1
  ),
  -- Select chained method calls (exclude argument calls like fromFile('...'))
  chain_calls AS (
    SELECT c.node_id, c.name AS op, c.depth
    FROM parsed_ast c
    JOIN parsed_ast p ON p.node_id = c.parent_id
    WHERE c.type = 'call_expression' 
      AND c.name != '$'
      AND p.type IN ('expression_statement', 'member_expression', 'program')
  ),
  call_ops AS (
    SELECT 
      c.node_id,
      c.op,
      c.depth,
      (
        SELECT list(trim(arg.peek, '"''') ORDER BY arg.node_id ASC)
        FROM parsed_ast args
        JOIN parsed_ast arg ON arg.parent_id = args.node_id
        WHERE args.parent_id = c.node_id 
          AND args.type = 'arguments' 
          AND arg.type NOT IN ('(', ')', ',')
      ) AS args
    FROM chain_calls c
  )
  SELECT 
    fluent_expr AS input_expr,
    (SELECT target_selector FROM selectors LIMIT 1) AS target_selector,
    list({'op': c.op, 'args': coalesce(c.args, [])} ORDER BY c.depth DESC) AS operations
  FROM call_ops c
);
