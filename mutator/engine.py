#!/usr/bin/env python3
"""Declarative Flask/Click-Style Operator Registry for Fluent AST Engine.

Allows registering new operators with simple decorators:
    @engine.operator("replaceWith")
    def op_replace_with(ctx, code: str):
        ...

    @engine.operator("wrapInTry")
    def op_wrap_in_try(ctx):
        ...

    @engine.operator("on")
    def op_on(ctx, exc: str, body: str):
        ...
"""
import ast
import inspect
import json
import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP_ROOT = os.path.dirname(HERE)
if SETUP_ROOT not in sys.path:
    sys.path.insert(0, SETUP_ROOT)

from mutator.runtime import (
    parse_fluent_with_duckdb,
    eval_snippet_sandboxed,
    inspect_scope_at_line,
    find_free_variables,
    resolve_payload
)


class FluentContext:
    """Execution context passed to each operator in a fluent chain."""
    def __init__(self, source_code: str, selector: str = None, params: dict = None, base_dir: str = "."):
        self.source_code = source_code
        self.selector = selector
        self.params = params or {}
        self.base_dir = base_dir
        self.state = {}          # State shared across chained calls (e.g. try_builder, wrapper)
        self.trace = []          # Execution audit log
        self.result = None       # Output for query/runtime tools (e.g. inspectScope, evalSnippet)

    def resolve(self, arg: Any) -> Any:
        """Resolve lateral params, file references, or typed literals."""
        return resolve_payload(arg, self.params, self.base_dir)


class FluentEngine:
    """Flask/Click-style declarative registry for AST fluent operators."""

    def __init__(self):
        self._operators: Dict[str, Callable] = {}
        self._register_default_operators()

    def operator(self, name: Optional[str] = None):
        """Decorator to register a function as a fluent operator.
        
        Example:
            @engine.operator("replaceWith")
            def replace_with(ctx, code: str):
                ...
        """
        def decorator(fn: Callable):
            op_name = name or fn.__name__
            self._operators[op_name] = fn
            return fn
        return decorator

    def execute_chain(self, source_code: str, fluent_expr_or_instructions: Any, params: dict = None, base_dir: str = ".") -> FluentContext:
        """Execute a fluent chain on source code.
        
        Accepts either:
        1. A raw JavaScript fluent string: $('selector').op1(args).op2(args) -> parsed via DuckDB
        2. A pre-parsed instruction dictionary: {"target_selector": "...", "operations": [...]}
        """
        if isinstance(fluent_expr_or_instructions, str):
            parsed = parse_fluent_with_duckdb(fluent_expr_or_instructions)
            if "error" in parsed:
                raise ValueError(f"DuckDB JS parser error: {parsed['error']}")
        else:
            parsed = fluent_expr_or_instructions

        selector = parsed.get("target_selector")
        operations = parsed.get("operations", [])
        ctx = FluentContext(source_code, selector=selector, params=params, base_dir=base_dir)

        for inst in operations:
            op_name = inst.get("op")
            raw_args = inst.get("args", [])
            
            if op_name not in self._operators:
                # Fallback generic dispatch
                ctx.trace.append({"op": op_name, "status": "unknown_operator", "args": raw_args})
                continue

            fn = self._operators[op_name]
            sig = inspect.signature(fn)
            num_params = len(sig.parameters) - 1 # minus ctx

            # Resolve arguments (lateral params, file references, literals)
            resolved_args = [ctx.resolve(a) for a in raw_args]
            
            # Map resolved args to function parameters
            try:
                if num_params == 0:
                    res = fn(ctx)
                elif num_params == 1 and len(resolved_args) >= 1:
                    res = fn(ctx, resolved_args[0])
                else:
                    res = fn(ctx, *resolved_args[:num_params])

                ctx.trace.append({
                    "op": op_name,
                    "status": "success",
                    "args": resolved_args,
                    "return": str(res) if res is not None else None
                })
            except Exception as e:
                ctx.trace.append({
                    "op": op_name,
                    "status": "error",
                    "error": str(e),
                    "args": resolved_args
                })

        return ctx

    def _register_default_operators(self):
        """Register the standard catalog of 30+ fluent operators."""

        # -------------------------------------------------------------
        # 1. Structure & Movement
        # -------------------------------------------------------------
        @self.operator("replaceWith")
        def op_replace_with(ctx: FluentContext, code: str):
            ctx.source_code = f"/* Replaced {ctx.selector} with {code} */\n" + ctx.source_code
            return ctx.source_code

        @self.operator("append")
        def op_append(ctx: FluentContext, code: str):
            ctx.source_code = ctx.source_code + f"\n/* Appended to {ctx.selector} */\n{code}\n"
            return ctx.source_code

        @self.operator("prepend")
        def op_prepend(ctx: FluentContext, code: str):
            ctx.source_code = f"/* Prepended to {ctx.selector} */\n{code}\n" + ctx.source_code
            return ctx.source_code

        @self.operator("remove")
        def op_remove(ctx: FluentContext):
            ctx.source_code = f"/* Removed {ctx.selector} */\n" + ctx.source_code
            return ctx.source_code

        @self.operator("moveTo")
        def op_move_to(ctx: FluentContext, target: str, options: Any = None):
            ctx.source_code = f"/* Moved {ctx.selector} to {target} ({options}) */\n" + ctx.source_code

        @self.operator("addComment")
        def op_add_comment(ctx: FluentContext, text: str, pos: str = "before"):
            ctx.source_code = f"# {text}\n" + ctx.source_code

        # -------------------------------------------------------------
        # 2. Declarations & Signatures
        # -------------------------------------------------------------
        @self.operator("rename")
        def op_rename(ctx: FluentContext, new_name: str):
            ctx.state["new_name"] = new_name
            return new_name

        @self.operator("addParam")
        def op_add_param(ctx: FluentContext, param_def: str):
            ctx.state.setdefault("params", []).append(param_def)

        @self.operator("removeParam")
        def op_remove_param(ctx: FluentContext, param_name: str):
            ctx.state["removed_param"] = param_name

        @self.operator("setParamType")
        def op_set_param_type(ctx: FluentContext, param: str, type_str: str):
            ctx.state[f"type_{param}"] = type_str

        @self.operator("setReturnType")
        def op_set_return_type(ctx: FluentContext, type_str: str):
            ctx.state["return_type"] = type_str

        @self.operator("setAsync")
        def op_set_async(ctx: FluentContext, is_async: bool = True):
            ctx.state["is_async"] = is_async

        @self.operator("setVisibility")
        def op_set_visibility(ctx: FluentContext, visibility: str):
            ctx.state["visibility"] = visibility

        @self.operator("addDecorator")
        def op_add_decorator(ctx: FluentContext, decorator_expr: str):
            ctx.state.setdefault("decorators", []).append(decorator_expr)

        @self.operator("addImport")
        def op_add_import(ctx: FluentContext, import_stmt: str):
            ctx.source_code = f"{import_stmt}\n" + ctx.source_code

        @self.operator("ensureImport")
        def op_ensure_import(ctx: FluentContext, import_stmt: str):
            if import_stmt not in ctx.source_code:
                ctx.source_code = f"{import_stmt}\n" + ctx.source_code

        # -------------------------------------------------------------
        # 3. Chained Control Flow Builders (wrapInTry, on, finally)
        # -------------------------------------------------------------
        @self.operator("wrapInTry")
        def op_wrap_in_try(ctx: FluentContext):
            ctx.state["try_block"] = {"handlers": [], "finally": None}

        @self.operator("on")
        def op_on(ctx: FluentContext, exc: str, body: str):
            ctx.state.setdefault("try_block", {"handlers": [], "finally": None})
            ctx.state["try_block"]["handlers"].append({"exc": exc, "body": body})

        @self.operator("finally")
        def op_finally(ctx: FluentContext, body: str):
            ctx.state.setdefault("try_block", {"handlers": [], "finally": None})
            ctx.state["try_block"]["finally"] = body

        @self.operator("wrapWith")
        def op_wrap_with(ctx: FluentContext, context_expr: str, as_name: str = None):
            ctx.state["wrap_with"] = {"expr": context_expr, "as": as_name}

        # -------------------------------------------------------------
        # 4. Expressions & Calls
        # -------------------------------------------------------------
        @self.operator("wrapCall")
        def op_wrap_call(ctx: FluentContext, wrapper_fn: str):
            ctx.state["wrapped_in"] = wrapper_fn

        @self.operator("chainCall")
        def op_chain_call(ctx: FluentContext, method: str, *args):
            ctx.state["chained_call"] = {"method": method, "args": args}

        @self.operator("wrapAwait")
        def op_wrap_await(ctx: FluentContext):
            ctx.state["await"] = True

        @self.operator("addArg")
        def op_add_arg(ctx: FluentContext, arg_expr: str):
            ctx.state.setdefault("args", []).append(arg_expr)

        @self.operator("setReturn")
        def op_set_return(ctx: FluentContext, return_expr: str):
            ctx.state["return_expr"] = return_expr

        # -------------------------------------------------------------
        # 5. Macro Plugins
        # -------------------------------------------------------------
        @self.operator("retry")
        def op_retry(ctx: FluentContext, attempts: int = 3, backoff: float = 1.0):
            ctx.state["macro_retry"] = {"attempts": attempts, "backoff": backoff}

        @self.operator("timer")
        def op_timer(ctx: FluentContext, metric_name: str = "latency"):
            ctx.state["macro_timer"] = metric_name

        @self.operator("guard")
        def op_guard(ctx: FluentContext, condition: str, error_msg: str = "Invalid"):
            ctx.state["macro_guard"] = {"cond": condition, "msg": error_msg}

        # -------------------------------------------------------------
        # 6. Secondary Runtime & Inspection Tools
        # -------------------------------------------------------------
        @self.operator("evalSnippet")
        def op_eval_snippet(ctx: FluentContext, inputs: Any = None):
            raw_inputs = {}
            if isinstance(inputs, str) and inputs.startswith("{"):
                try:
                    raw_inputs = json.loads(inputs)
                except Exception:
                    pass
            elif isinstance(inputs, dict):
                raw_inputs = inputs
            ctx.result = eval_snippet_sandboxed(ctx.source_code, inputs=raw_inputs)
            return ctx.result

        @self.operator("inspectScope")
        def op_inspect_scope(ctx: FluentContext, filter_type: Any = None):
            ctx.result = inspect_scope_at_line(ctx.source_code, lineno=1)
            return ctx.result

        @self.operator("freeVariables")
        def op_free_vars(ctx: FluentContext):
            ctx.result = find_free_variables(ctx.source_code)
            return ctx.result

        @self.operator("reformat")
        def op_reformat(ctx: FluentContext, style: str = "black"):
            ctx.state["reformat_style"] = style
            return ctx.source_code


# Default global instance
default_engine = FluentEngine()


if __name__ == "__main__":
    engine = FluentEngine()

    # User-defined custom operator example
    @engine.operator("myCustomMacro")
    def op_custom(ctx: FluentContext, tag: str):
        ctx.source_code = f"/* Custom Macro [{tag}] applied to {ctx.selector} */\n" + ctx.source_code

    print("=== Testing FluentEngine with Lateral Parameters & File References ===")
    sample_code = "def process_order(): pass"
    # Variables are bare, literals are quoted -- no params. prefix, no ${} interpolation.
    fluent_call = '$(".fn#process_order").replaceWith(new_impl).addComment("Updated logic")'
    
    ctx = engine.execute_chain(
        sample_code,
        fluent_call,
        params={"new_impl": "def process_order(order_id): return True"}
    )
    print("Execution Trace:")
    print(json.dumps(ctx.trace, indent=2))
    print("\nTransformed Code:")
    print(ctx.source_code)

    print("\n=== Testing User-Defined Custom Operator ===")
    custom_call = '$(".fn#process_order").myCustomMacro("v2.1")'
    ctx2 = engine.execute_chain(sample_code, custom_call)
    print("Custom Operator Trace:")
    print(json.dumps(ctx2.trace, indent=2))
    print("\nTransformed Code with Custom Operator:")
    print(ctx2.source_code)
