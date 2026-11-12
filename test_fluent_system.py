#!/usr/bin/env python3
"""End-to-End Test Suite for Polyglot Fluent AST Engine and MicroDSL.

Tests:
1. DuckDB JS Fluent Macro Parser (zero-regex decomposition)
2. Lateral Parameter & File References (params.key, fromFile)
3. Polyglot MicroDSL Template Expander (Python, Rust, TypeScript)
4. Flask/Click-Style Declarative Operator Registry (FluentEngine)
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from mutator.runtime import (
    parse_fluent_with_duckdb,
    eval_snippet_sandboxed,
    inspect_scope_at_line,
    find_free_variables,
    resolve_payload,
    plan_transform,
    confirm_transform,
    reject_transform,
    PlanStore
)
from mutator.engine import FluentEngine, FluentContext
from mutator.microdsl import MicroDSLEngine


class TestFluentEngine(unittest.TestCase):

    def setUp(self):
        self.engine = FluentEngine()
        self.microdsl = MicroDSLEngine()

    def test_01_duckdb_fluent_parser(self):
        """Test DuckDB JS AST parser on multi-step fluent chain."""
        fluent_call = '$(".fn#save@target").wrapInTry().on("KeyError", "return None").finally("db.close()")'
        parsed = parse_fluent_with_duckdb(fluent_call)
        
        self.assertEqual(parsed.get("target_selector"), ".fn#save@target")
        ops = parsed.get("operations", [])
        self.assertEqual(len(ops), 3)
        self.assertEqual(ops[0]["op"], "wrapInTry")
        self.assertEqual(ops[1]["op"], "on")
        self.assertEqual(ops[1]["args"], ["KeyError", "return None"])
        self.assertEqual(ops[2]["op"], "finally")
        self.assertEqual(ops[2]["args"], ["db.close()"])

    def test_02_lateral_parameter_resolution(self):
        """Test resolving lateral parameters and file references."""
        params = {"new_impl": "def run(): return 42"}
        
        res1 = resolve_payload("params.new_impl", params=params)
        self.assertEqual(res1, "def run(): return 42")
        
        res2 = resolve_payload("'inline literal'", params=params)
        self.assertEqual(res2, "inline literal")

    def test_03_microdsl_expansion(self):
        """Test polyglot MicroDSL template expansion across Python and Rust."""
        # Python Decorator
        py_tpl = self.microdsl.get_template("python", "addDecorator")
        expanded_py = self.microdsl.expand(py_tpl, {
            "decorator": "login_required",
            "target": "def profile(): pass"
        })
        self.assertIn("@login_required", expanded_py)
        self.assertIn("def profile(): pass", expanded_py)

        # Rust WrapAwait
        rs_tpl = self.microdsl.get_template("rust", "wrapAwait")
        expanded_rs = self.microdsl.expand(rs_tpl, {
            "target": "fetch_user(id)"
        })
        self.assertEqual(expanded_rs, "fetch_user(id).await")

    def test_04_declarative_operator_execution(self):
        """Test executing fluent chain through declarative FluentEngine."""
        source = "def process(): pass"
        call = '$(".fn#process").replaceWith(params.handler).addComment("Auto-generated")'
        
        ctx = self.engine.execute_chain(
            source,
            call,
            params={"handler": "def process(): return True"}
        )
        
        self.assertEqual(ctx.selector, ".fn#process")
        self.assertEqual(len(ctx.trace), 2)
        self.assertEqual(ctx.trace[0]["status"], "success")
        self.assertEqual(ctx.trace[1]["status"], "success")
        self.assertIn("Auto-generated", ctx.source_code)

    def test_05_runtime_tools(self):
        """Test secondary runtime execution and scope inspection tools."""
        # eval_snippet
        run_res = eval_snippet_sandboxed("x = a + b\nprint(f'Sum: {x}')", inputs={"a": 10, "b": 25})
        self.assertEqual(run_res["status"], "success")
        self.assertEqual(run_res["stdout"], "Sum: 35")

        # inspect_scope
        sample_code = "def calc(x):\n    y = x * 2\n    return y\n"
        scope = inspect_scope_at_line(sample_code, 2)
        self.assertEqual(scope["name"], "calc")
        self.assertIn("x", scope["params"])
        self.assertIn("y", scope["locals"])


    def test_06_polyglot_suite_expansion(self):
        """Test MicroDSL rules across Go, C, C++, Java, JavaScript, and SQL."""
        # Go: wrapInTry (if err != nil)
        go_tpl = self.microdsl.get_template("go", "wrapInTry")
        expanded_go = self.microdsl.expand(go_tpl, {
            "body": "res, err := doWork()",
            "handlers": [{"exc": "DatabaseError"}],
            "finally": "cleanup"
        })
        self.assertIn("if err != nil", expanded_go)
        self.assertIn("DatabaseError", expanded_go)
        self.assertIn("defer cleanup()", expanded_go)

        # C: addInclude and wrapInTry
        c_inc_tpl = self.microdsl.get_template("c", "addInclude")
        expanded_c_inc = self.microdsl.expand(c_inc_tpl, {"header": "stdio.h", "target": "int main() {}"})
        self.assertIn("#include <stdio.h>", expanded_c_inc)

        c_try_tpl = self.microdsl.get_template("c", "wrapInTry")
        expanded_c_try = self.microdsl.expand(c_try_tpl, {
            "body": "__rc = init_driver();",
            "handlers": [{"body": "return -1;"}],
            "finally": "free_driver();"
        })
        self.assertIn("int __rc = 0;", expanded_c_try)
        self.assertIn("if (__rc != 0)", expanded_c_try)
        self.assertIn("cleanup:", expanded_c_try)

        # C++: addNamespace and wrapWith RAII guard
        cpp_ns_tpl = self.microdsl.get_template("cpp", "addNamespace")
        expanded_cpp_ns = self.microdsl.expand(cpp_ns_tpl, {"ns": "duckdb", "target": "class Engine {};"})
        self.assertIn("namespace duckdb {", expanded_cpp_ns)

        cpp_wrap_tpl = self.microdsl.get_template("cpp", "wrapWith")
        expanded_cpp_wrap = self.microdsl.expand(cpp_wrap_tpl, {
            "guard_type": "std::lock_guard<std::mutex>",
            "resource": "mtx_",
            "body": "data_.push_back(item);"
        })
        self.assertIn("std::lock_guard<std::mutex> __guard(mtx_);", expanded_cpp_wrap)

        # Java: addDecorator and wrapWith try-with-resources
        java_dec_tpl = self.microdsl.get_template("java", "addDecorator")
        expanded_java_dec = self.microdsl.expand(java_dec_tpl, {
            "annotation": "Override",
            "target": "public void run() {}"
        })
        self.assertIn("@Override", expanded_java_dec)

        java_wrap_tpl = self.microdsl.get_template("java", "wrapWith")
        expanded_java_wrap = self.microdsl.expand(java_wrap_tpl, {
            "resource_type": "BufferedReader",
            "var_name": "reader",
            "init_expr": "new BufferedReader(new FileReader(path))",
            "body": "String line = reader.readLine();"
        })
        self.assertIn("try (BufferedReader reader = new BufferedReader(new FileReader(path)))", expanded_java_wrap)

        # JavaScript: setAsync and wrapAwait
        js_async_tpl = self.microdsl.get_template("javascript", "setAsync")
        expanded_js_async = self.microdsl.expand(js_async_tpl, {"target": "function fetchUser() {}"})
        self.assertIn("async function fetchUser() {}", expanded_js_async)

        # SQL: wrapWithCTE and wrapInTransaction
        sql_cte_tpl = self.microdsl.get_template("sql", "wrapWithCTE")
        expanded_sql_cte = self.microdsl.expand(sql_cte_tpl, {
            "cte_name": "ranked_users",
            "cte_query": "SELECT id, score FROM users",
            "target": "SELECT * FROM ranked_users WHERE score > 90;"
        })
        self.assertIn("WITH ranked_users AS (", expanded_sql_cte)
        self.assertIn("SELECT * FROM ranked_users WHERE score > 90;", expanded_sql_cte)

        sql_tx_tpl = self.microdsl.get_template("sql", "wrapInTransaction")
        expanded_sql_tx = self.microdsl.expand(sql_tx_tpl, {
            "target": "UPDATE accounts SET balance = balance - 100 WHERE id = 1;\nUPDATE accounts SET balance = balance + 100 WHERE id = 2;"
        })
        self.assertIn("BEGIN TRANSACTION;", expanded_sql_tx)
        self.assertIn("COMMIT;", expanded_sql_tx)

    def test_07_canonical_aliases(self):
        """Test that generic alias names (annotate, import, assert, await) resolve correctly."""
        # 1. C: calling 'addImport' or 'import' resolves to 'addInclude' template
        c_tpl = self.microdsl.get_template("c", "import")
        self.assertIsNotNone(c_tpl)
        expanded_c = self.microdsl.expand(c_tpl, {"header": "math.h", "target": ""})
        self.assertIn("#include <math.h>", expanded_c)

        # 2. Rust: calling 'annotate' or 'decorate' resolves to Rust attribute #[...]
        rs_tpl = self.microdsl.get_template("rust", "annotate")
        self.assertIsNotNone(rs_tpl)
        expanded_rs = self.microdsl.expand(rs_tpl, {"attr": "derive(Debug)", "target": "struct Foo;"})
        self.assertIn("#[derive(Debug)]", expanded_rs)

        # 3. Java: calling 'annotate' resolves to Java annotation @...
        java_tpl = self.microdsl.get_template("java", "annotate")
        self.assertIsNotNone(java_tpl)
        expanded_java = self.microdsl.expand(java_tpl, {"annotation": "Deprecated", "target": "void old() {}"})
        self.assertIn("@Deprecated", expanded_java)

        # 4. JS: calling 'await' resolves to 'wrapAwait'
        js_tpl = self.microdsl.get_template("javascript", "await")
        self.assertIsNotNone(js_tpl)
        expanded_js = self.microdsl.expand(js_tpl, {"target": "getData()"})
        self.assertEqual(expanded_js, "await getData()")

    def test_08_declarative_yaml_examples(self):
        """Test that all 85 embedded YAML examples across 9 languages pass validation."""
        res = self.microdsl.validate_examples()
        self.assertGreater(res["total"], 80)
        self.assertEqual(res["failed"], 0, f"YAML Example Failures: {res['errors']}")
        self.assertEqual(res["passed"], res["total"])

    def test_09_plan_transform_preview(self):
        """Test dry-run transform planning with diff preview and risk assessment."""
        sample_code = "def fetch_data():\n    return 42\n"
        fluent_call = '$(".fn#fetch_data").replaceWith("def fetch_data():\\n    return 100\\n")'
        
        plan = plan_transform(sample_code, fluent_call, language="python")
        self.assertTrue(plan.plan_id.startswith("plan_"))
        self.assertEqual(plan.status, "pending")
        self.assertEqual(plan.risk_level, "safe")
        self.assertTrue(plan.diff_preview != "")
        self.assertIn("-    return 42", plan.diff_preview)
        self.assertIn("+    return 100", plan.diff_preview)
        self.assertIn("+# Replaced .fn#fetch_data", plan.diff_preview)

        summary = plan.summary()
        self.assertEqual(summary["status"], "pending")
        self.assertTrue(summary["has_diff"])

    def test_10_confirm_and_stale_detection(self):
        """Test confirming a plan and detecting stale disk changes."""
        import tempfile
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".py") as tf:
            tf.write("def calculate():\n    return 1\n")
            tf_path = tf.name

        try:
            with open(tf_path) as f:
                initial_code = f.read()
            plan = plan_transform(
                initial_code,
                '$(".fn#calculate").replaceWith("def calculate():\\n    return 2\\n")',
                file_path=tf_path
            )

            # 1. Reject flow
            reject_res = reject_transform(plan.plan_id, reason="User cancelled edit")
            self.assertEqual(reject_res["status"], "rejected")

            # 2. Fresh plan and confirm
            plan2 = plan_transform(
                initial_code,
                '$(".fn#calculate").replaceWith("def calculate():\\n    return 2\\n")',
                file_path=tf_path
            )
            confirm_res = confirm_transform(plan2.plan_id, write_file=True)
            self.assertEqual(confirm_res["status"], "applied")
            with open(tf_path) as f:
                updated_content = f.read()
            self.assertIn("Replaced .fn#calculate", updated_content)

            # 3. Stale detection: create plan3, modify file underneath, attempt confirm
            plan3 = plan_transform(
                updated_content,
                '$(".fn#calculate").replaceWith("def calculate():\\n    return 3\\n")',
                file_path=tf_path
            )
            # Out-of-band write
            with open(tf_path, "w") as f:
                f.write("def calculate():\n    # out of band edit\n    return 99\n")

            stale_res = confirm_transform(plan3.plan_id)
            self.assertEqual(stale_res["status"], "stale_plan")
            self.assertIn("modified on disk", stale_res["error"])
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
