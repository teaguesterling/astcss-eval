"""
Code metrics system for the COP static analysis.

This module provides classes for calculating various code metrics,
such as complexity, size, and dependency metrics.
"""

import ast
from typing import Dict, List, Any, Optional, Set, Union


class MetricsProvider:
    """Base class for code metrics providers."""
    
    def calculate_metrics(self, component_type: str, ast_node: ast.AST, 
                          file_path: str) -> Dict[str, Any]:
        """
        Calculate metrics for a component.
        
        Args:
            component_type: Type of the component (function, class, module)
            ast_node: AST node for the component
            file_path: Path to the file containing the component
            
        Returns:
            Dictionary of metrics
        """
        raise NotImplementedError("Subclasses must implement calculate_metrics")


class ComplexityMetricsProvider(MetricsProvider):
    """Provides complexity metrics for code components."""
    
    def calculate_metrics(self, component_type: str, ast_node: ast.AST, 
                          file_path: str) -> Dict[str, Any]:
        """
        Calculate complexity metrics for a component.
        
        Args:
            component_type: Type of the component (function, class, module)
            ast_node: AST node for the component
            file_path: Path to the file containing the component
            
        Returns:
            Dictionary of complexity metrics
        """
        # Only calculate complexity metrics for functions and methods
        if component_type not in ("function", "method"):
            return {}
            
        # Calculate cyclomatic complexity
        complexity = self._calculate_cyclomatic_complexity(ast_node)
        
        # Calculate cognitive complexity
        cognitive_complexity = self._calculate_cognitive_complexity(ast_node)
        
        return {
            "cyclomatic_complexity": complexity,
            "cognitive_complexity": cognitive_complexity
        }
    
    def _calculate_cyclomatic_complexity(self, node: ast.AST) -> int:
        """
        Calculate cyclomatic complexity of a function.
        
        Cyclomatic complexity measures the number of linearly independent paths 
        through the code. It's calculated as the number of decision points + 1.
        
        Args:
            node: AST node for the function
            
        Returns:
            Cyclomatic complexity value
        """
        # Start with base complexity of 1
        complexity = 1
        
        # Count control flow statements
        for child in ast.walk(node):
            # If, While, For statements
            if isinstance(child, (ast.If, ast.While, ast.For)):
                complexity += 1
            
            # Boolean operations (and, or)
            elif isinstance(child, ast.BoolOp):
                # Each boolean operator in a chain adds complexity
                complexity += len(child.values) - 1
            
            # Try/except blocks
            elif isinstance(child, ast.Try):
                # Each except handler adds complexity
                complexity += len(child.handlers)
        
        return complexity
    
    def _calculate_cognitive_complexity(self, node: ast.AST) -> int:
        """
        Calculate cognitive complexity of a function.
        
        Cognitive complexity is a measure of how difficult the code is to understand.
        It considers nesting levels, control flow complexity, and structural complexity.
        
        Args:
            node: AST node for the function
            
        Returns:
            Cognitive complexity value
        """
        class CognitiveComplexityVisitor(ast.NodeVisitor):
            def __init__(self):
                self.complexity = 0
                self.nesting_level = 0
            
            def visit_If(self, node):
                self.complexity += 1 + self.nesting_level  # Basic + nesting
                self.nesting_level += 1
                self.generic_visit(node)
                self.nesting_level -= 1
            
            def visit_For(self, node):
                self.complexity += 1 + self.nesting_level
                self.nesting_level += 1
                self.generic_visit(node)
                self.nesting_level -= 1
            
            def visit_While(self, node):
                self.complexity += 1 + self.nesting_level
                self.nesting_level += 1
                self.generic_visit(node)
                self.nesting_level -= 1
            
            def visit_Try(self, node):
                self.complexity += 1  # Just for the try block
                self.nesting_level += 1
                self.generic_visit(node)
                self.nesting_level -= 1
            
            def visit_ExceptHandler(self, node):
                self.complexity += 1  # Each except adds complexity
                self.generic_visit(node)
            
            def visit_BoolOp(self, node):
                # For boolean operations, add complexity for each operator
                self.complexity += len(node.values) - 1
                self.generic_visit(node)
            
            def visit_Compare(self, node):
                # For multiple comparisons like a < b < c
                self.complexity += len(node.ops) - 1
                self.generic_visit(node)
        
        visitor = CognitiveComplexityVisitor()
        visitor.visit(node)
        return visitor.complexity


class SizeMetricsProvider(MetricsProvider):
    """Provides size-related metrics for code components."""
    
    def calculate_metrics(self, component_type: str, ast_node: ast.AST, 
                         file_path: str) -> Dict[str, Any]:
        """
        Calculate size metrics for a component.
        
        Args:
            component_type: Type of the component (function, class, module)
            ast_node: AST node for the component
            file_path: Path to the file containing the component
            
        Returns:
            Dictionary of size metrics
        """
        # Calculate lines of code
        loc = self._count_lines(ast_node)
        
        # Count statements
        statements = self._count_statements(ast_node)
        
        metrics = {
            "lines_of_code": loc,
            "statement_count": statements,
        }
        
        # Additional metrics based on component type
        if component_type == "class":
            metrics.update(self._calculate_class_metrics(ast_node))
        elif component_type in ("function", "method"):
            metrics.update(self._calculate_function_metrics(ast_node))
        
        return metrics
    
    def _count_lines(self, node: ast.AST) -> int:
        """
        Count the number of lines in a node.
        
        Args:
            node: AST node
            
        Returns:
            Number of lines
        """
        if hasattr(node, 'end_lineno') and hasattr(node, 'lineno'):
            return node.end_lineno - node.lineno + 1
        return 0
    
    def _count_statements(self, node: ast.AST) -> int:
        """
        Count the number of statements in a node.
        
        Args:
            node: AST node
            
        Returns:
            Number of statements
        """
        count = 0
        for child in ast.walk(node):
            if isinstance(child, (ast.Assign, ast.AugAssign, ast.Return, 
                                ast.Raise, ast.Assert, ast.Import, 
                                ast.ImportFrom, ast.Expr, ast.If, ast.For,
                                ast.While, ast.Try, ast.With)):
                count += 1
        return count
    
    def _calculate_class_metrics(self, node: ast.ClassDef) -> Dict[str, Any]:
        """
        Calculate class-specific metrics.
        
        Args:
            node: AST node for the class
            
        Returns:
            Dictionary of class metrics
        """
        # Count methods
        method_count = 0
        
        # Count attributes
        attribute_count = 0
        
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method_count += 1
            elif isinstance(item, ast.Assign):
                attribute_count += len(item.targets)
        
        return {
            "method_count": method_count,
            "attribute_count": attribute_count
        }
    
    def _calculate_function_metrics(self, node: ast.FunctionDef) -> Dict[str, Any]:
        """
        Calculate function-specific metrics.
        
        Args:
            node: AST node for the function
            
        Returns:
            Dictionary of function metrics
        """
        # Count parameters
        arg_count = len(node.args.args)
        
        # Count local variables
        variables = self._count_local_variables(node)
        
        # Count returns
        returns = self._count_returns(node)
        
        return {
            "parameter_count": arg_count,
            "local_variable_count": variables,
            "return_count": returns
        }
    
    def _count_local_variables(self, node: ast.FunctionDef) -> int:
        """
        Count local variables defined in a function.
        
        Args:
            node: AST node for the function
            
        Returns:
            Number of local variables
        """
        # Track assigned names to avoid counting the same variable multiple times
        variable_names = set()
        
        for child in ast.walk(node):
            # Count regular assignments
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        variable_names.add(target.id)
            
            # Count assignments in for loops
            elif isinstance(child, ast.For):
                if isinstance(child.target, ast.Name):
                    variable_names.add(child.target.id)
            
            # Count with statement assignments
            elif isinstance(child, ast.With):
                for item in child.items:
                    if hasattr(item, 'optional_vars') and isinstance(item.optional_vars, ast.Name):
                        variable_names.add(item.optional_vars.id)
        
        return len(variable_names)
    
    def _count_returns(self, node: ast.FunctionDef) -> int:
        """
        Count return statements in a function.
        
        Args:
            node: AST node for the function
            
        Returns:
            Number of return statements
        """
        count = 0
        for child in ast.walk(node):
            if isinstance(child, ast.Return):
                count += 1
        return count


class DependencyMetricsProvider(MetricsProvider):
    """Provides dependency-related metrics for code components."""
    
    def calculate_metrics(self, component_type: str, ast_node: ast.AST, 
                         file_path: str) -> Dict[str, Any]:
        """
        Calculate dependency metrics for a component.
        
        Args:
            component_type: Type of the component (function, class, module)
            ast_node: AST node for the component
            file_path: Path to the file containing the component
            
        Returns:
            Dictionary of dependency metrics
        """
        metrics = {}
        
        # Module-level import metrics
        if component_type == "module":
            import_count, external_count = self._count_imports(ast_node)
            metrics.update({
                "import_count": import_count,
                "external_dependency_count": external_count
            })
        
        # For functions and methods, calculate call metrics
        if component_type in ("function", "method"):
            function_calls = self._count_function_calls(ast_node)
            metrics.update({
                "function_call_count": function_calls
            })
        
        return metrics
    
    def _count_imports(self, node: ast.Module) -> tuple[int, int]:
        """
        Count imports in a module.
        
        Args:
            node: AST node for the module
            
        Returns:
            Tuple of (total import count, external dependency count)
        """
        import_count = 0
        external_count = 0
        
        for child in ast.walk(node):
            if isinstance(child, ast.Import):
                import_count += len(child.names)
                # Assuming anything not in stdlib is external
                for name in child.names:
                    module_name = name.name.split('.')[0]
                    if not self._is_stdlib(module_name):
                        external_count += 1
            elif isinstance(child, ast.ImportFrom):
                if child.module:  # Avoid None for 'from . import x'
                    import_count += len(child.names)
                    module_name = child.module.split('.')[0]
                    if not self._is_stdlib(module_name):
                        external_count += len(child.names)
        
        return import_count, external_count
    
    def _is_stdlib(self, module_name: str) -> bool:
        """
        Check if a module is part of the standard library.
        
        Args:
            module_name: Name of the module
            
        Returns:
            True if the module is part of the standard library, False otherwise
        """
        # This is a simplified approach, a more comprehensive approach would be to use
        # sys.stdlib_module_names from Python 3.10+
        stdlib_modules = {
            "abc", "argparse", "ast", "asyncio", "base64", "collections",
            "concurrent", "contextlib", "copy", "csv", "datetime", "decimal",
            "difflib", "enum", "functools", "glob", "gzip", "hashlib",
            "http", "importlib", "inspect", "io", "itertools", "json",
            "logging", "math", "multiprocessing", "os", "pathlib", "pickle",
            "random", "re", "shutil", "signal", "socket", "sqlite3",
            "statistics", "string", "subprocess", "sys", "tempfile",
            "threading", "time", "traceback", "typing", "unittest", "urllib",
            "uuid", "warnings", "xml", "zipfile"
        }
        
        return module_name in stdlib_modules or module_name.startswith("_")
    
    def _count_function_calls(self, node: ast.AST) -> int:
        """
        Count function calls in a node.
        
        Args:
            node: AST node
            
        Returns:
            Number of function calls
        """
        count = 0
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                count += 1
        return count


# Register all metrics providers
def get_default_metrics_providers() -> List[MetricsProvider]:
    """
    Get the default set of metrics providers.
    
    Returns:
        List of metrics provider instances
    """
    return [
        ComplexityMetricsProvider(),
        SizeMetricsProvider(),
        DependencyMetricsProvider()
    ]