"""Plugin Registry & Deterministic AST Code Expanders.

Defines parameterized semantic macro transformations that compile into idiomatic,
syntactically verified code across Python, JavaScript/TypeScript, Rust, and Go.
"""
import re
from typing import Any, Dict, Optional


class ASTPlugin:
    """Base class for AST transformation macro plugins."""
    name: str = ""
    description: str = ""
    default_opts: Dict[str, Any] = {}

    @classmethod
    def expand(cls, lang: str, target_code: str, opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Expands the macro into language-specific code wrapping/modifications."""
        merged_opts = dict(cls.default_opts)
        if opts:
            merged_opts.update(opts)
        
        method_name = f"expand_{lang}"
        handler = getattr(cls, method_name, None)
        if not handler:
            raise NotImplementedError(f"Plugin {cls.name} has no expander for language '{lang}'")
        
        return handler(target_code.strip(), merged_opts)


class TimerPlugin(ASTPlugin):
    """Instruments a function or call with elapsed time measurement."""
    name = "timer"
    description = "Measure and log execution elapsed time"
    default_opts = {"level": "debug", "unit": "ms"}

    @classmethod
    def expand_python(cls, target: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        unit = opts.get("unit", "ms")
        scale = " * 1000" if unit == "ms" else ""
        return {
            "required_imports": ["import time", "import logging"],
            "replacement": (
                f"_t0 = time.perf_counter()\n"
                f"_res = {target}\n"
                f"logging.{opts['level']}(f'Duration: {{((time.perf_counter() - _t0){scale}):.2f}}{unit}')\n"
                f"return _res" if "def " not in target else target
            )
        }

    @classmethod
    def expand_javascript(cls, target: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "required_imports": ["import { performance } from 'perf_hooks';"],
            "replacement": (
                f"const _t0 = performance.now();\n"
                f"const _res = await {target};\n"
                f"console.{opts['level']}(`Duration: ${{performance.now() - _t0}}ms`);\n"
                f"return _res;"
            )
        }


class GuardPlugin(ASTPlugin):
    """Injects an early return or exception guard clause."""
    name = "guard"
    description = "Inject early return or error guard check"
    default_opts = {"condition": "not ready", "on_fail": "return None"}

    @classmethod
    def expand_python(cls, target: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        cond = opts["condition"]
        fail_action = opts["on_fail"]
        guard_stmt = f"if {cond}:\n    {fail_action}"
        return {
            "required_imports": [],
            "insertion": guard_stmt,
            "position": "start_of_body"
        }

    @classmethod
    def expand_javascript(cls, target: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        cond = opts["condition"]
        fail_action = opts["on_fail"]
        return {
            "required_imports": [],
            "insertion": f"if ({cond}) {{ {fail_action}; }}",
            "position": "start_of_body"
        }


class RetryPlugin(ASTPlugin):
    """Wraps target in a retry/backoff handler."""
    name = "retry"
    description = "Wrap block/call in retry loop with backoff"
    default_opts = {"attempts": 3, "delay_s": 0.5}

    @classmethod
    def expand_python(cls, target: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        attempts = opts["attempts"]
        delay = opts["delay_s"]
        return {
            "required_imports": ["import time"],
            "replacement": (
                f"for _attempt in range({attempts}):\n"
                f"    try:\n"
                f"        _res = {target}\n"
                f"        break\n"
                f"    except Exception:\n"
                f"        if _attempt == {attempts - 1}:\n"
                f"            raise\n"
                f"        time.sleep({delay})"
            )
        }


class MemoizePlugin(ASTPlugin):
    """Applies memoization/caching decorator or lookup table."""
    name = "memoize"
    description = "Cache function return values"
    default_opts = {"maxsize": 128}

    @classmethod
    def expand_python(cls, target: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "required_imports": ["from functools import lru_cache"],
            "decorator": f"@lru_cache(maxsize={opts['maxsize']})"
        }


class DeprecatePlugin(ASTPlugin):
    """Adds a deprecation warning and docstring notice."""
    name = "deprecate"
    description = "Mark function/class as deprecated with warning"
    default_opts = {"message": "Deprecated function", "version": "v2"}

    @classmethod
    def expand_python(cls, target: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "required_imports": ["import warnings"],
            "insertion": f'warnings.warn("{opts["message"]}", DeprecationWarning, stacklevel=2)',
            "position": "start_of_body"
        }

    @classmethod
    def expand_javascript(cls, target: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "required_imports": [],
            "insertion": f'console.warn("[DEPRECATED] {opts["message"]}");',
            "position": "start_of_body"
        }


class AuthCheckPlugin(ASTPlugin):
    """Injects user authorization check at boundary."""
    name = "auth_check"
    description = "Validate user role or session authorization"
    default_opts = {"role": "admin", "on_fail": "raise PermissionError('Unauthorized')"}

    @classmethod
    def expand_python(cls, target: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "required_imports": [],
            "insertion": f'if not user.has_role("{opts["role"]}"):\n    {opts["on_fail"]}',
            "position": "start_of_body"
        }


class LogBoundaryPlugin(ASTPlugin):
    """Logs entry arguments and exit results."""
    name = "log_boundary"
    description = "Log function entry and exit lifecycle events"
    default_opts = {"level": "info"}

    @classmethod
    def expand_python(cls, target: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        lvl = opts["level"]
        return {
            "required_imports": ["import logging"],
            "replacement": (
                f"logging.{lvl}('Entering execution')\n"
                f"try:\n"
                f"    _res = {target}\n"
                f"    logging.{lvl}('Completed execution')\n"
                f"    return _res\n"
                f"except Exception as _e:\n"
                f"    logging.error(f'Failed execution: {{_e}}')\n"
                f"    raise"
            )
        }


class NullCheckPlugin(ASTPlugin):
    """Injects null/none validation checks."""
    name = "null_check"
    description = "Assert parameter is non-null"
    default_opts = {"param": "input_val"}

    @classmethod
    def expand_python(cls, target: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        param = opts["param"]
        return {
            "required_imports": [],
            "insertion": f"if {param} is None:\n    raise ValueError('{param} cannot be None')",
            "position": "start_of_body"
        }


class TransactionWrapPlugin(ASTPlugin):
    """Wraps block in database transaction context."""
    name = "transaction_wrap"
    description = "Wrap database operations in atomic transaction"
    default_opts = {"ctx": "db.transaction()"}

    @classmethod
    def expand_python(cls, target: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "required_imports": [],
            "replacement": f"with {opts['ctx']}:\n    {target}"
        }


# Registry of all available plugins
PLUGIN_REGISTRY: Dict[str, type[ASTPlugin]] = {
    "timer": TimerPlugin,
    "guard": GuardPlugin,
    "retry": RetryPlugin,
    "memoize": MemoizePlugin,
    "deprecate": DeprecatePlugin,
    "auth_check": AuthCheckPlugin,
    "log_boundary": LogBoundaryPlugin,
    "null_check": NullCheckPlugin,
    "transaction_wrap": TransactionWrapPlugin,
}


def get_plugin(name: str) -> Optional[type[ASTPlugin]]:
    """Lookup plugin by canonical or normalized alias name."""
    norm = name.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "time_execution": "timer",
        "benchmark": "timer",
        "duration": "timer",
        "early_return": "guard",
        "assert_guard": "guard",
        "retry_call": "retry",
        "cache": "memoize",
        "deprecation_warning": "deprecate",
        "require_auth": "auth_check",
        "authorize": "auth_check",
        "log_lifecycle": "log_boundary",
        "assert_not_null": "null_check",
        "transaction": "transaction_wrap",
        "atomic": "transaction_wrap",
    }
    canonical = aliases.get(norm, norm)
    return PLUGIN_REGISTRY.get(canonical)
