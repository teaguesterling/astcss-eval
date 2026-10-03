#!/usr/bin/env python3
"""Polyglot MicroDSL Template Expander for AST Transformations.

Loads language-specific rewrite templates (e.g. microdsl/python.yaml, microdsl/rust.yaml)
and expands capture variables (${target}, ${body|indent(4)}, ${handlers|map_join(...)})
into clean, formatted source code.
"""
import os
import re
from typing import Any, Dict, List, Optional
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
MICRODSL_DIR = os.path.join(HERE, "microdsl")


CANONICAL_ALIASES: Dict[str, List[str]] = {
    # Metadata / Annotations / Decorators / Attributes
    "annotate": ["addDecorator", "addAnnotation", "addAttribute", "decorate"],
    "addDecorator": ["annotate", "addAnnotation", "addAttribute", "decorate"],
    "addAnnotation": ["addDecorator", "annotate", "addAttribute", "decorate"],
    "addAttribute": ["addDecorator", "annotate", "addAnnotation", "decorate"],
    "decorate": ["addDecorator", "annotate", "addAnnotation", "addAttribute"],

    # Imports / Inclusions / Modules
    "import": ["addImport", "ensureImport", "addInclude", "ensureInclude", "use"],
    "addImport": ["import", "ensureImport", "addInclude", "ensureInclude", "use"],
    "ensureImport": ["addImport", "import", "ensureInclude", "addInclude"],
    "addInclude": ["addImport", "import", "ensureImport", "ensureInclude"],
    "ensureInclude": ["addInclude", "addImport", "import", "ensureImport"],
    "use": ["addImport", "import", "ensureImport"],

    # Async / Await
    "async": ["setAsync"],
    "setAsync": ["async"],
    "await": ["wrapAwait"],
    "wrapAwait": ["await"],

    # Control Flow & Scoping
    "try": ["wrapInTry"],
    "tryCatch": ["wrapInTry"],
    "wrapInTry": ["try", "tryCatch"],
    "with": ["wrapWith"],
    "wrapWith": ["with"],

    # Assertions
    "assert": ["addAssertion"],
    "addAssertion": ["assert"],

    # Calls & Returns
    "call": ["wrapCall"],
    "wrapCall": ["call"],
    "return": ["setReturn"],
    "setReturn": ["return"],
}


class MicroDSLEngine:
    """Evaluates and expands MicroDSL templates per language with canonical alias support."""

    def __init__(self, rules_dir: str = MICRODSL_DIR):
        self.rules_dir = rules_dir
        self.rules_by_lang: Dict[str, Dict[str, Any]] = {}
        self._load_all_rules()

    def _load_all_rules(self):
        if not os.path.exists(self.rules_dir):
            return
        for fname in os.listdir(self.rules_dir):
            if fname.endswith(".yaml") or fname.endswith(".yml"):
                lang = os.path.splitext(fname)[0]
                fpath = os.path.join(self.rules_dir, fname)
                try:
                    with open(fpath) as f:
                        data = yaml.safe_load(f)
                        if data and "operators" in data:
                            self.rules_by_lang[lang] = data["operators"]
                except Exception as e:
                    print(f"Warning: failed to load MicroDSL rules from {fpath}: {e}")

    def get_template(self, lang: str, op_name: str) -> Optional[str]:
        """Retrieve the raw rewrite template for a given language and operator, resolving aliases."""
        lang_rules = self.rules_by_lang.get(lang.lower(), {})
        
        # 1. Direct lookup
        op_def = lang_rules.get(op_name)
        if isinstance(op_def, dict) and "rewrite" in op_def:
            return op_def.get("rewrite")
        
        # 2. Canonical alias resolution
        aliases = CANONICAL_ALIASES.get(op_name, [])
        for alias in aliases:
            op_def = lang_rules.get(alias)
            if isinstance(op_def, dict) and "rewrite" in op_def:
                return op_def.get("rewrite")
                
        return None

    def expand(self, template_str: str, captures: Dict[str, Any], **kwargs) -> str:
        """Expand placeholders (${var}, ${body|indent(N)}, ${list|map_join(...)}) in template."""
        context = dict(captures)
        context.update(kwargs)

        def replace_var(expr: str) -> str:
            expr = expr.strip()
            # Check for filter pipe: ${body|indent(4)}
            if "|" in expr:
                var_name, filter_expr = [p.strip() for p in expr.split("|", 1)]
                val = context.get(var_name, "")
                return self._apply_filter(val, filter_expr, context)
            
            val = context.get(expr, "")
            return str(val) if val is not None else ""

        # Balanced brace scanner with quote awareness
        res = []
        i = 0
        n = len(template_str)
        while i < n:
            if template_str[i:i+2] == "${":
                depth = 1
                j = i + 2
                in_quote = None
                while j < n and depth > 0:
                    ch = template_str[j]
                    if in_quote:
                        if ch == "\\" and j + 1 < n:
                            j += 2
                            continue
                        elif ch == in_quote:
                            in_quote = None
                    else:
                        if ch in ('"', "'"):
                            in_quote = ch
                        elif ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                    if depth == 0:
                        break
                    j += 1
                if depth == 0:
                    var_expr = template_str[i+2:j]
                    res.append(replace_var(var_expr))
                    i = j + 1
                    continue
            res.append(template_str[i])
            i += 1

        # Clean up empty lines left by absent optional clauses
        raw_lines = "".join(res).splitlines()
        out_lines = []
        for i, line in enumerate(raw_lines):
            if not line.strip():
                # If next line is a closing brace or closing handler, skip the blank line
                if i + 1 < len(raw_lines) and raw_lines[i+1].strip().startswith(("}", "catch", "except", "finally", "Ok(", "Err(", "cleanup:")):
                    continue
            out_lines.append(line)
        return "\n".join(out_lines)

    def _apply_filter(self, value: Any, filter_expr: str, context: Dict[str, Any]) -> str:
        """Apply a template filter like indent(4), map_join(...), if_present(...)."""
        filter_expr = filter_expr.strip()

        # 1. indent(N)
        m_indent = re.match(r'^indent\((\d+)\)$', filter_expr)
        if m_indent:
            n = int(m_indent.group(1))
            prefix = " " * n
            lines = str(value).split("\n")
            return "\n".join(prefix + l if l.strip() else l for l in lines)

        # 2. map_join("template")
        if filter_expr.startswith("map_join(") and filter_expr.endswith(")"):
            inner = filter_expr[9:-1]
            if (inner.startswith('"') and inner.endswith('"')) or (inner.startswith("'") and inner.endswith("'")):
                inner = inner[1:-1]
            # Unescape newlines
            inner = inner.replace("\\n", "\n")
            if isinstance(value, list):
                res = []
                for item in value:
                    if isinstance(item, dict):
                        # Replace {key} with item[key]
                        formatted = re.sub(r'\{(\w+)\}', lambda m: str(item.get(m.group(1), "")), inner)
                        res.append(formatted)
                return "\n".join(res)
            return ""

        # 3. if_present("template")
        if filter_expr.startswith("if_present(") and filter_expr.endswith(")"):
            inner = filter_expr[11:-1]
            if (inner.startswith('"') and inner.endswith('"')) or (inner.startswith("'") and inner.endswith("'")):
                inner = inner[1:-1]
            inner = inner.replace("\\n", "\n")
            if value:
                if isinstance(value, dict):
                    return re.sub(r'\{(\w+)\}', lambda m: str(value.get(m.group(1), "")), inner)
                return re.sub(r'\{(\w+)\}', lambda m: str(value), inner)
            return ""

        return str(value)


    def validate_examples(self) -> Dict[str, Any]:
        """Runs declarative test suites defined in YAML examples across all languages.
        
        Returns:
            {"total": int, "passed": int, "failed": int, "errors": List[str]}
        """
        results = {"total": 0, "passed": 0, "failed": 0, "errors": []}
        for lang, ops in self.rules_by_lang.items():
            for op_name, op_def in ops.items():
                if not isinstance(op_def, dict):
                    continue
                examples = []
                if "example" in op_def and isinstance(op_def["example"], dict):
                    examples.append(op_def["example"])
                elif "examples" in op_def and isinstance(op_def["examples"], list):
                    examples.extend(op_def["examples"])
                
                tpl = op_def.get("rewrite")
                if not tpl or not examples:
                    continue

                for idx, ex in enumerate(examples):
                    results["total"] += 1
                    ctx = dict(ex.get("context") or ex.get("input") or {})
                    if "target" in ex:
                        ctx["target"] = ex["target"]
                    if "args" in ex and isinstance(ex["args"], dict):
                        ctx.update(ex["args"])
                    
                    expected = ex.get("expected") or ex.get("to") or ""
                    actual = self.expand(tpl, ctx)
                    
                    if actual.strip() == str(expected).strip():
                        results["passed"] += 1
                    else:
                        results["failed"] += 1
                        results["errors"].append(
                            f"[{lang}:{op_name} (ex {idx+1})] Mismatch:\n"
                            f"Expected:\n{expected}\n"
                            f"Actual:\n{actual}"
                        )
        return results


# Global default engine instance
default_microdsl = MicroDSLEngine()


if __name__ == "__main__":
    engine = MicroDSLEngine()
    
    # Test 1: Python Decorator expansion
    py_tpl = engine.get_template("python", "addDecorator")
    print("Python Decorator Template:", repr(py_tpl))
    out1 = engine.expand(py_tpl, {"decorator": "timer('calc')", "target": "def calculate(): return 42"})
    print("\nExpanded Decorator:")
    print(out1)

    # Test 2: Python WrapInTry with handlers and finally
    try_tpl = engine.get_template("python", "wrapInTry")
    print("\nPython WrapInTry Template:")
    out2 = engine.expand(try_tpl, {
        "body": "res = db.query(sql)\nreturn res",
        "handlers": [
            {"exc": "KeyError", "body": "return None"},
            {"exc": "Exception", "body": "log.error('failed')"}
        ],
        "finally": "db.close()"
    })
    print(out2)
