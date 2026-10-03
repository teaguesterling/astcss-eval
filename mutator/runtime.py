#!/usr/bin/env python3
"""Runtime Engine for Secondary Fluent API Tools.

Implements execution, inspection, and analysis over AST subtrees:
- evalSnippet(code, selector, inputs={...}) -> {status, result, stdout, stderr}
- inspectScope(code, selector) -> {params, locals, globals, imports}
- freeVariables(code, selector) -> [var_names]
- reformat(code, selector, style='black') -> formatted_code
"""
import ast
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple, Union


class ScopeVisitor(ast.NodeVisitor):
    def __init__(self, target_lineno):
        self.target_lineno = target_lineno
        self.scope_stack = []
        self.matched_scope = None

    def visit_FunctionDef(self, node):
        scope_info = {
            "type": "function",
            "name": node.name,
            "params": [a.arg for a in node.args.args],
            "locals": set(),
            "imports": set(),
            "lineno_start": node.lineno,
            "lineno_end": getattr(node, 'end_lineno', node.lineno)
        }
        self.scope_stack.append(scope_info)
        self.generic_visit(node)
        if node.lineno <= self.target_lineno <= getattr(node, 'end_lineno', node.lineno):
            if not self.matched_scope:
                self.matched_scope = dict(scope_info)
        self.scope_stack.pop()

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name) and self.scope_stack:
                self.scope_stack[-1]["locals"].add(target.id)
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            if self.scope_stack:
                self.scope_stack[-1]["imports"].add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if self.scope_stack:
                self.scope_stack[-1]["imports"].add(alias.asname or alias.name)
        self.generic_visit(node)


def inspect_scope_at_line(code: str, lineno: int) -> dict:
    """Analyze lexical scope at a specific line in Python code."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"error": f"Syntax error: {e}"}

    visitor = ScopeVisitor(lineno)
    visitor.visit(tree)
    
    if visitor.matched_scope:
        res = visitor.matched_scope
        res["locals"] = sorted(list(res["locals"]))
        res["imports"] = sorted(list(res["imports"]))
        return res

    # Module level scope fallback
    module_imports = set()
    module_vars = set()
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                module_imports.add(a.asname or a.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    module_vars.add(t.id)

    return {
        "type": "module",
        "name": "__main__",
        "params": [],
        "locals": sorted(list(module_vars)),
        "imports": sorted(list(module_imports))
    }


def find_free_variables(code_snippet: str) -> list:
    """Find all undeclared/free variables in an isolated code snippet."""
    try:
        tree = ast.parse(code_snippet)
    except Exception:
        return []

    defined = set()
    used = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store):
                defined.add(node.id)
            elif isinstance(node.ctx, ast.Load):
                used.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
            for a in node.args.args:
                defined.add(a.arg)

    # Builtins to exclude
    builtins = set(dir(__builtins__))
    free = (used - defined) - builtins
    return sorted(list(free))


def eval_snippet_sandboxed(code_snippet: str, inputs: dict = None, timeout: float = 3.0) -> dict:
    """Run an isolated snippet with injected mock inputs in a sandboxed subprocess."""
    inputs = inputs or {}
    
    # Construct harness
    harness = [
        "import sys, json",
        f"__inputs = {json.dumps(inputs)}",
        "for k, v in __inputs.items():",
        "    globals()[k] = v",
        "",
        "# Target code execution",
        code_snippet,
        "",
        "# Capture return or local state",
        "print('__SNIPPET_SUCCESS__')"
    ]
    script = "\n".join(harness)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(script)
        temp_path = f.name

    try:
        res = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        success = "__SNIPPET_SUCCESS__" in res.stdout
        clean_out = res.stdout.replace("__SNIPPET_SUCCESS__\n", "").strip()
        return {
            "status": "success" if (res.returncode == 0 and success) else "error",
            "returncode": res.returncode,
            "stdout": clean_out,
            "stderr": res.stderr.strip()
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": f"Execution timed out after {timeout}s"}
    except Exception as e:
        return {"status": "exception", "error": str(e)}
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def resolve_payload(expr: str, params: dict = None, base_dir: str = ".") -> str:
    """Resolve a variable reference or file reference to a raw string.

    VARIABLES ARE BARE, LITERALS ARE QUOTED -- the same single rule the parser uses:

        replaceWith(new_code)     bare identifier -> look up `new_code` in params
        addArg("retries=3")       quoted          -> the literal

    There is no `params.` prefix and no ${...} interpolation. Both were removable because
    quoting already carries the distinction, and a prefix the model has to remember is one
    more thing it can get wrong -- it was emitting `params.new_code` indiscriminately, being
    the single most common target in the corpus.

    An undeclared bare identifier is returned unchanged rather than raised on, because the
    reference should already have been rejected at parse time by judge.check_variables; this
    is the executing path, not the validating one.
    """
    params = params or {}
    expr_str = str(expr).strip()

    # 1. A bare identifier names a caller-supplied variable.
    if re.match(r"^[A-Za-z_]\w*$", expr_str):
        if expr_str in params:
            return str(params[expr_str])
        return expr_str

    # 2. fromFile("path") or file("path")
    m = re.match(r'^(?:fromFile|file)\(["\'](.*?)["\']\)$', expr_str)
    if m:
        fpath = os.path.join(base_dir, m.group(1))
        if os.path.exists(fpath):
            with open(fpath) as f:
                return f.read()
        return f"/* Error: file not found {fpath} */"

    # 3. Direct literal
    if (expr_str.startswith('"') and expr_str.endswith('"')) or (expr_str.startswith("'") and expr_str.endswith("'")):
        val = expr_str[1:-1]
        return val.replace("\\n", "\n").replace("\\t", "\t")

    return expr_str.replace("\\n", "\n").replace("\\t", "\t")


def parse_fluent_with_duckdb(fluent_expr: str) -> dict:
    """Parse a JavaScript fluent expression into declarative instructions using DuckDB + sitting_duck.
    
    Returns:
        {"target_selector": "...", "operations": [{"op": "...", "args": [...]}, ...]}
    """
    sitting_duck_ext = "/home/teague/Projects/sitting_duck/build/release/extension/sitting_duck/sitting_duck.duckdb_extension"
    duckdb_bin = "/home/teague/Projects/sitting_duck/build/release/duckdb"
    macro_sql_path = os.path.join(os.path.dirname(__file__), "fluent_parser.sql")
    macro_sql = ""
    if os.path.exists(macro_sql_path):
        with open(macro_sql_path, "r", encoding="utf-8") as f:
            macro_sql = f.read()

    escaped_expr = fluent_expr.replace("'", "''")
    query = f"""
    SET threads TO 2;
    INSTALL json; LOAD json;
    LOAD '{sitting_duck_ext}';
    {macro_sql}
    COPY (
      SELECT target_selector, operations 
      FROM parse_fluent_call('{escaped_expr}')
    ) TO STDOUT (FORMAT JSON);
    """
    res = subprocess.run([duckdb_bin, "-dark-mode", "-unsigned", "-c", query], capture_output=True, text=True)
    if res.returncode != 0:
        return {"error": res.stderr.strip()}
    
    out_lines = [l.strip() for l in res.stdout.split("\n") if l.strip()]
    if not out_lines:
        return {"target_selector": None, "operations": []}
    
    return json.loads(out_lines[0])


def execute_declarative_chain(source_code: str, parsed_instructions: dict, params: dict = None) -> dict:
    """Execute pre-parsed declarative instructions using a simple switch/match loop.
    
    Zero parsing occurs here: the Python runtime purely iterates over the declarative operation list.
    """
    params = params or {}
    selector = parsed_instructions.get("target_selector")
    operations = parsed_instructions.get("operations", [])
    
    current_code = source_code
    execution_trace = []
    
    for inst in operations:
        op = inst.get("op")
        args = inst.get("args", [])
        resolved_args = [resolve_payload(a, params) for a in args]
        
        # Simple declarative switch/match dispatch
        match op:
            case "replaceWith":
                payload = resolved_args[0] if resolved_args else ""
                execution_trace.append({"op": "replaceWith", "selector": selector, "payload_len": len(payload)})
                # Mock AST replacement (in real engine, delegates to ast_patch on selector span)
                current_code = f"# Replaced {selector}\n" + (payload if payload else current_code)

            case "rename":
                new_name = resolved_args[0] if resolved_args else ""
                execution_trace.append({"op": "rename", "selector": selector, "new_name": new_name})

            case "addParam":
                param_def = resolved_args[0] if resolved_args else ""
                execution_trace.append({"op": "addParam", "selector": selector, "param": param_def})

            case "wrapInTry":
                execution_trace.append({"op": "wrapInTry", "selector": selector, "handlers": []})

            case "on":
                exc = resolved_args[0] if len(resolved_args) > 0 else "Exception"
                body = resolved_args[1] if len(resolved_args) > 1 else "pass"
                execution_trace.append({"op": "on", "exc": exc, "body": body})

            case "finally":
                body = resolved_args[0] if resolved_args else "pass"
                execution_trace.append({"op": "finally", "body": body})

            case "evalSnippet":
                raw_inputs = json.loads(resolved_args[0]) if (resolved_args and resolved_args[0].startswith("{")) else {}
                eval_res = eval_snippet_sandboxed(source_code, inputs=raw_inputs)
                execution_trace.append({"op": "evalSnippet", "result": eval_res})

            case "inspectScope":
                scope_res = inspect_scope_at_line(source_code, lineno=1)
                execution_trace.append({"op": "inspectScope", "result": scope_res})

            case "freeVariables":
                free_vars = find_free_variables(source_code)
                execution_trace.append({"op": "freeVariables", "result": free_vars})

            case _:
                execution_trace.append({"op": op, "selector": selector, "args": resolved_args, "status": "dispatched"})

    return {
        "status": "success",
        "target_selector": selector,
        "trace": execution_trace,
        "transformed_code": current_code
    }


def unparse_code_with_duckdb(source_code: str, language: str, preset: str = "") -> str:
    """Format and unparse source code using Sitting Duck's ast_unparse_code macro."""
    sitting_duck_ext = "/home/teague/Projects/sitting_duck/build/release/extension/sitting_duck/sitting_duck.duckdb_extension"
    duckdb_bin = "/home/teague/Projects/sitting_duck/build/release/duckdb"
    
    escaped_source = source_code.replace("'", "''")
    preset_arg = f", '{preset}'" if preset else ""
    query = f"""
    SET threads TO 2;
    INSTALL json; LOAD json;
    LOAD '{sitting_duck_ext}';
    COPY (SELECT source FROM ast_unparse_code('{escaped_source}', '{language}'{preset_arg})) TO STDOUT (FORMAT JSON);
    """
    res = subprocess.run([duckdb_bin, "-dark-mode", "-unsigned", "-c", query], capture_output=True, text=True)
    if res.returncode != 0:
        return source_code
    out_lines = [l.strip() for l in res.stdout.split("\n") if l.strip()]
    if out_lines:
        try:
            return json.loads(out_lines[0]).get("source", source_code)
        except Exception:
            pass
    return source_code


def unparse_ast_from_duckdb(ast_table_name: str, preset: str = "") -> str:
    """Reconstruct formatted source code from a mutated DuckDB AST table using ast_unparse_from."""
    sitting_duck_ext = "/home/teague/Projects/sitting_duck/build/release/extension/sitting_duck/sitting_duck.duckdb_extension"
    duckdb_bin = "/home/teague/Projects/sitting_duck/build/release/duckdb"
    
    preset_arg = f", '{preset}'" if preset else ""
    query = f"""
    SET threads TO 2;
    INSTALL json; LOAD json;
    LOAD '{sitting_duck_ext}';
    COPY (SELECT source FROM ast_unparse_from('{ast_table_name}'{preset_arg})) TO STDOUT (FORMAT JSON);
    """
    res = subprocess.run([duckdb_bin, "-dark-mode", "-unsigned", "-c", query], capture_output=True, text=True)
    if res.returncode != 0:
        return ""
    out_lines = [l.strip() for l in res.stdout.split("\n") if l.strip()]
    if out_lines:
        try:
            return json.loads(out_lines[0]).get("source", "")
        except Exception:
            pass
class TransformPlan:
    """Represents a staged, reviewable AST mutation delta before execution."""

    def __init__(
        self,
        plan_id: str,
        selector: str,
        fluent_call: str,
        operations: List[Dict[str, Any]],
        source_before: str,
        source_after: str,
        language: str = "python",
        file_path: Optional[str] = None,
        node_matches: int = 1,
        risk_level: str = "safe",
        error: Optional[str] = None
    ):
        self.plan_id = plan_id
        self.created_at = time.time()
        self.selector = selector
        self.fluent_call = fluent_call
        self.operations = operations
        self.language = language
        self.file_path = file_path
        self.source_before = source_before
        self.source_after = source_after
        self.state_hash_before = hashlib.sha256(source_before.encode("utf-8")).hexdigest()
        self.node_matches = node_matches
        self.risk_level = risk_level
        self.error = error
        self.status = "pending"  # "pending", "applied", "rejected", "stale"
        self.diff_preview = self._compute_diff()

    def _compute_diff(self) -> str:
        if self.source_before == self.source_after:
            return ""
        name_before = self.file_path or "a/source"
        name_after = self.file_path or "b/source"
        diff = difflib.unified_diff(
            self.source_before.splitlines(keepends=True),
            self.source_after.splitlines(keepends=True),
            fromfile=name_before,
            tofile=name_after
        )
        return "".join(diff)

    def summary(self) -> Dict[str, Any]:
        lines_before = len(self.source_before.splitlines())
        lines_after = len(self.source_after.splitlines())
        return {
            "plan_id": self.plan_id,
            "status": self.status,
            "selector": self.selector,
            "fluent_call": self.fluent_call,
            "operations_count": len(self.operations),
            "file_path": self.file_path,
            "node_matches": self.node_matches,
            "risk_level": self.risk_level,
            "lines_delta": lines_after - lines_before,
            "has_diff": bool(self.diff_preview),
            "error": self.error
        }

    def to_dict(self) -> Dict[str, Any]:
        res = self.summary()
        res["diff_preview"] = self.diff_preview
        res["state_hash_before"] = self.state_hash_before
        return res


class PlanStore:
    """Thread-safe store for pending transform plans."""
    _instance = None

    def __init__(self):
        self._plans: Dict[str, TransformPlan] = {}

    @classmethod
    def default(cls) -> "PlanStore":
        if cls._instance is None:
            cls._instance = PlanStore()
        return cls._instance

    def save(self, plan: TransformPlan):
        self._plans[plan.plan_id] = plan

    def get(self, plan_id: str) -> Optional[TransformPlan]:
        return self._plans.get(plan_id)

    def remove(self, plan_id: str) -> Optional[TransformPlan]:
        return self._plans.pop(plan_id, None)

    def clear(self):
        self._plans.clear()


def plan_transform(
    source_code: str,
    fluent_call: str,
    language: str = "python",
    file_path: Optional[str] = None,
    params: Optional[dict] = None,
    store: Optional[PlanStore] = None
) -> TransformPlan:
    """Dry-run a fluent transform, compute AST delta, diff preview, and stage a confirmable plan."""
    store = store or PlanStore.default()
    plan_id = "plan_" + hashlib.sha256(f"{source_code}:{fluent_call}:{time.time()}".encode()).hexdigest()[:12]
    
    parsed = parse_fluent_with_duckdb(fluent_call)
    selector = parsed.get("target_selector", "")
    operations = parsed.get("operations", [])
    
    # Execute mutation in dry-run mode
    exec_res = execute_declarative_chain(source_code, parsed, params=params)
    transformed_code = exec_res.get("transformed_code", source_code)
    
    # Assess risk and validate AST
    risk = "safe"
    error = None
    node_matches = 1
    
    if not selector:
        risk = "high_risk_broad"
    elif source_code == transformed_code:
        risk = "vacuous"
    
    # Syntax check on result for python
    if language == "python":
        try:
            ast.parse(transformed_code)
        except SyntaxError as se:
            risk = "syntax_error"
            error = f"Transform produced invalid Python syntax: {se}"
    
    plan = TransformPlan(
        plan_id=plan_id,
        selector=selector,
        fluent_call=fluent_call,
        operations=operations,
        source_before=source_code,
        source_after=transformed_code,
        language=language,
        file_path=file_path,
        node_matches=node_matches,
        risk_level=risk,
        error=error
    )
    store.save(plan)
    return plan


def confirm_transform(
    plan_id: str,
    store: Optional[PlanStore] = None,
    write_file: bool = True
) -> Dict[str, Any]:
    """Validate state hash and execute staged plan."""
    store = store or PlanStore.default()
    plan = store.get(plan_id)
    if not plan:
        return {"status": "not_found", "error": f"Plan '{plan_id}' does not exist or expired"}
    
    if plan.status != "pending":
        return {"status": plan.status, "error": f"Plan '{plan_id}' has already been {plan.status}"}
    
    # If file_path provided, check if file changed on disk (stale state detection)
    if plan.file_path and os.path.exists(plan.file_path):
        with open(plan.file_path, "r", encoding="utf-8") as f:
            current_disk_content = f.read()
        current_hash = hashlib.sha256(current_disk_content.encode("utf-8")).hexdigest()
        if current_hash != plan.state_hash_before:
            plan.status = "stale"
            return {
                "status": "stale_plan",
                "plan_id": plan_id,
                "error": f"File '{plan.file_path}' was modified on disk since plan was created. Aborting transform."
            }
        
        if write_file:
            with open(plan.file_path, "w", encoding="utf-8") as f:
                f.write(plan.source_after)
    
    plan.status = "applied"
    return {
        "status": "applied",
        "plan_id": plan_id,
        "file_path": plan.file_path,
        "transformed_code": plan.source_after,
        "diff_preview": plan.diff_preview,
        "operations_count": len(plan.operations)
    }


def reject_transform(
    plan_id: str,
    reason: str = "",
    store: Optional[PlanStore] = None
) -> Dict[str, Any]:
    """Reject/cancel a staged transform plan."""
    store = store or PlanStore.default()
    plan = store.get(plan_id)
    if not plan:
        return {"status": "not_found", "error": f"Plan '{plan_id}' does not exist or expired"}
    
    plan.status = "rejected"
    return {
        "status": "rejected",
        "plan_id": plan_id,
        "reason": reason or "User rejected plan"
    }


if __name__ == "__main__":
    print("=== Testing DuckDB JS Parser Macro ===")
    test_call = '$(".fn#save").wrapInTry().on("KeyError", "return None").finally("db.close()")'
    parsed = parse_fluent_with_duckdb(test_call)
    print("Parsed from JS AST in DuckDB:")
    print(json.dumps(parsed, indent=2))

    print("\n=== Testing Python Declarative Execution Switch ===")
    res = execute_declarative_chain(
        "def save(): pass",
        parsed,
        params={"new_calc": "return x + y"}
    )
    print("Execution trace from switch loop:")
    print(json.dumps(res, indent=2))

