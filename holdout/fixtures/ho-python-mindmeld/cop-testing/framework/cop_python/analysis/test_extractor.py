"""
Test relationship extraction for the COP static analysis.

This module extracts relationships between test functions and the components
they test, enabling verification status tracking in the concept graph.
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Union, NamedTuple

from cop_python.analysis.metrics import get_default_metrics_providers, MetricsProvider


class TestRelationship(NamedTuple):
    """Information about a test-component relationship."""
    test_name: str              # Fully qualified name of the test function
    test_type: str              # Type of test (unit, integration, etc.)
    target_component: str       # Component being tested
    annotation_ref: Optional[Dict[str, Any]]  # Reference to specific annotation being tested
    file_path: str              # Path to the test file
    line_number: int            # Line number of the test function
    test_info: Dict[str, Any]   # Information about the test function (docstring, etc.)
    start_line: int             # Start line of the test function
    end_line: int               # End line of the test function
    actual_start_line: int      # Start line after decorators
    metrics: Dict[str, Any] = {}  # Metrics for the test function


class TestRelationshipExtractor(ast.NodeVisitor):
    """AST visitor to extract test-component relationships from test code."""
    
    # Test decorators to detect
    TEST_DECORATORS = {
        "test_for", "test_invariant", "test_risk", "test_decision",
        "test_implementation_status", "verify_annotation"
    }
    
    def __init__(self, file_path: str, source_code: str, metrics_providers: List[MetricsProvider] = None):
        self.file_path = file_path
        self.source_code = source_code
        self.module_name = self._get_module_name(file_path)
        self.relationships = []
        self.current_class = None
        self.metrics_providers = metrics_providers or get_default_metrics_providers()
    
    def _get_module_name(self, file_path: str) -> str:
        """Extract module name from file path."""
        file_path = os.path.abspath(file_path)
        
        # Try to get a proper module name by finding the package root
        for path in sys.path:
            if file_path.startswith(path):
                rel_path = os.path.relpath(file_path, path)
                module_path = os.path.splitext(rel_path)[0].replace(os.path.sep, '.')
                return module_path
        
        # Fallback: use file name without extension
        return os.path.splitext(os.path.basename(file_path))[0]
    
    def _get_test_name(self, node: ast.FunctionDef) -> str:
        """Get fully qualified name for a test function."""
        if self.current_class:
            return f"{self.module_name}.{self.current_class}.{node.name}"
        else:
            return f"{self.module_name}.{node.name}"
    
    def _get_node_line_range(self, node: ast.AST) -> tuple[int, int, int]:
        """Get the line range for a node including decorators."""
        lines = self.source_code.splitlines()
        
        # For actual_start_line, use the node's lineno
        actual_start_line = node.lineno
        
        # For start_line, include decorators
        start_line = actual_start_line
        if hasattr(node, 'decorator_list') and node.decorator_list:
            # Get the first decorator's line number
            first_decorator = node.decorator_list[0]
            if hasattr(first_decorator, 'lineno'):
                start_line = first_decorator.lineno
        
        # Find the end line of the node
        if hasattr(node, 'end_lineno'):
            end_line = node.end_lineno  # Python 3.8+
        else:
            # For Python < 3.8, try to estimate end line
            end_line = actual_start_line
            for child in ast.iter_child_nodes(node):
                if hasattr(child, 'lineno'):
                    if hasattr(child, 'end_lineno'):
                        end_line = max(end_line, child.end_lineno)
                    else:
                        end_line = max(end_line, child.lineno)
        
        # AST line numbers are 1-based, but we want to return 0-based line numbers
        return start_line - 1, end_line - 1, actual_start_line - 1
    
    def _extract_test_info(self, node: ast.FunctionDef) -> Dict[str, Any]:
        """Extract information about a test function."""
        test_info = {}
        
        # Extract docstring
        docstring = ast.get_docstring(node)
        if docstring:
            test_info["docstring"] = docstring
        
        # Extract function signature
        params = []
        for arg in node.args.args:
            param_info = {"name": arg.arg}
            if arg.annotation:
                param_info["annotation"] = self._format_annotation(arg.annotation)
            params.append(param_info)
        
        test_info["params"] = params
        
        # Extract return annotation if present
        if node.returns:
            test_info["returns"] = self._format_annotation(node.returns)
        
        return test_info
    
    def _format_annotation(self, node: ast.AST) -> str:
        """Format an annotation node as a string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._format_annotation(node.value)}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            return f"{self._format_annotation(node.value)}[{self._format_annotation(node.slice)}]"
        elif isinstance(node, ast.Index):
            return self._format_annotation(node.value)
        elif isinstance(node, ast.Tuple):
            elts = [self._format_annotation(elt) for elt in node.elts]
            return f"({', '.join(elts)})"
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Str):  # For Python < 3.8
            return repr(node.s)
        elif hasattr(ast, 'Num') and isinstance(node, ast.Num):  # For Python < 3.8
            return repr(node.n)
        else:
            return "<complex_annotation>"
    
    def _extract_metrics(self, node: ast.AST, component_type: str) -> Dict[str, Any]:
        """Extract metrics using all registered providers."""
        metrics = {}
        for provider in self.metrics_providers:
            try:
                provider_metrics = provider.calculate_metrics(
                    component_type, node, self.file_path
                )
                metrics.update(provider_metrics)
            except Exception as e:
                print(f"Warning: Metrics provider {provider.__class__.__name__} failed: {e}")
        
        return metrics
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit a class definition."""
        old_class = self.current_class
        self.current_class = node.name
        
        # Visit class body
        for child in node.body:
            self.visit(child)
        
        self.current_class = old_class
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit a function definition."""
        # Check if this function has test decorators
        test_relationships = self._extract_test_relationships(node)
        
        if test_relationships:
            # Extract common information for all relationships from this test
            test_name = self._get_test_name(node)
            test_info = self._extract_test_info(node)
            start_line, end_line, actual_start_line = self._get_node_line_range(node)
            metrics = self._extract_metrics(node, "function")
            
            # Create relationship objects
            for rel_info in test_relationships:
                relationship = TestRelationship(
                    test_name=test_name,
                    test_type=rel_info.get("test_type", "unit"),
                    target_component=rel_info["target_component"],
                    annotation_ref=rel_info.get("annotation_ref"),
                    file_path=self.file_path,
                    line_number=node.lineno,
                    test_info=test_info,
                    start_line=start_line,
                    end_line=end_line,
                    actual_start_line=actual_start_line,
                    metrics=metrics
                )
                
                self.relationships.append(relationship)
    
    def _extract_test_relationships(self, node: ast.FunctionDef) -> List[Dict[str, Any]]:
        """Extract test relationships from a function's decorators."""
        relationships = []
        
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
                decorator_name = decorator.func.id
                if decorator_name in self.TEST_DECORATORS:
                    rel_info = self._extract_test_decorator_info(decorator, decorator_name)
                    if rel_info:
                        relationships.append(rel_info)
            elif isinstance(decorator, ast.Name) and decorator.id in self.TEST_DECORATORS:
                # Handle simple decorators without arguments
                rel_info = {
                    "test_type": "unit",
                    "target_component": "unknown",
                    "annotation_ref": None
                }
                relationships.append(rel_info)
        
        return relationships
    
    def _extract_test_decorator_info(self, decorator: ast.Call, decorator_name: str) -> Optional[Dict[str, Any]]:
        """Extract information from a test decorator call."""
        args = decorator.args
        keywords = {kw.arg: kw.value for kw in decorator.keywords}
        
        # Basic relationship info
        rel_info = {
            "test_type": "unit",
            "target_component": None,
            "annotation_ref": None
        }
        
        # Extract target component (usually first argument)
        if args:
            target_component = self._extract_arg_value(args[0])
            rel_info["target_component"] = target_component
        
        # Extract annotation reference based on decorator type
        if decorator_name == "test_for":
            # @test_for(component, annotation_type="value")
            annotation_ref = self._extract_test_for_annotation(args, keywords)
            if annotation_ref:
                rel_info["annotation_ref"] = annotation_ref
                
        elif decorator_name in ("test_invariant", "test_risk", "test_decision"):
            # @test_invariant(component, "invariant_value")
            annotation_type = decorator_name.replace("test_", "")
            if len(args) > 1:
                annotation_value = self._extract_arg_value(args[1])
                rel_info["annotation_ref"] = {
                    "type": annotation_type,
                    "value": annotation_value
                }
        
        elif decorator_name == "test_implementation_status":
            # @test_implementation_status(component, "IMPLEMENTED")
            if len(args) > 1:
                status_value = self._extract_arg_value(args[1])
                rel_info["annotation_ref"] = {
                    "type": "implementation_status",
                    "value": status_value
                }
        
        # Extract test type from keywords
        if "test_type" in keywords:
            test_type = self._extract_arg_value(keywords["test_type"])
            rel_info["test_type"] = test_type
        
        return rel_info if rel_info["target_component"] else None
    
    def _extract_test_for_annotation(self, args: List[ast.AST], keywords: Dict[str, ast.AST]) -> Optional[Dict[str, Any]]:
        """Extract annotation reference from @test_for decorator."""
        # Look for annotation type in keywords
        for key, value in keywords.items():
            if key in ("invariant", "risk", "decision", "implementation_status"):
                annotation_value = self._extract_arg_value(value)
                return {
                    "type": key,
                    "value": annotation_value
                }
        
        return None
    
    def _extract_arg_value(self, arg: ast.AST) -> str:
        """Extract the value from an AST node representing a decorator argument."""
        if isinstance(arg, ast.Constant):
            return str(arg.value)
        elif isinstance(arg, ast.Name):
            return f"<variable:{arg.id}>"
        elif isinstance(arg, ast.Attribute):
            return f"{self._extract_arg_value(arg.value)}.{arg.attr}"
        elif isinstance(arg, ast.Str):  # For Python < 3.8
            return arg.s
        elif hasattr(ast, 'Num') and isinstance(arg, ast.Num):  # For Python < 3.8
            return str(arg.n)
        else:
            return "<complex_expression>"


def extract_test_relationships_from_file(file_path: str, 
                                        metrics_providers: List[MetricsProvider] = None) -> List[TestRelationship]:
    """
    Extract test relationships from a Python test file.
    
    Args:
        file_path: Path to the Python test file
        metrics_providers: Optional list of metrics providers to use
        
    Returns:
        List of extracted test relationships
    """
    with open(file_path, 'r') as f:
        source_code = f.read()
    
    # Parse AST
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        print(f"Warning: Syntax error in {file_path}, skipping")
        return []
    
    # Extract test relationships
    extractor = TestRelationshipExtractor(file_path, source_code, metrics_providers)
    extractor.visit(tree)
    
    return extractor.relationships


def extract_test_relationships_from_directory(directory: str, recursive: bool = True,
                                             metrics_providers: List[MetricsProvider] = None) -> List[TestRelationship]:
    """
    Extract test relationships from all Python test files in a directory.
    
    Args:
        directory: Directory to scan
        recursive: Whether to recursively scan subdirectories
        metrics_providers: Optional list of metrics providers to use
        
    Returns:
        List of extracted test relationships
    """
    all_relationships = []
    
    # Get Python test files (files starting with test_ or ending with _test.py)
    pattern = "**/*.py" if recursive else "*.py"
    for file_path in Path(directory).glob(pattern):
        file_name = file_path.name
        # Only process files that look like test files
        if file_name.startswith("test_") or file_name.endswith("_test.py") or "test" in file_name:
            relationships = extract_test_relationships_from_file(str(file_path), metrics_providers)
            all_relationships.extend(relationships)
    
    return all_relationships


if __name__ == "__main__":
    # Simple CLI for testing
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract test relationships from Python code")
    parser.add_argument("path", help="File or directory to analyze")
    parser.add_argument("--no-recursive", action="store_true", help="Don't scan directories recursively")
    args = parser.parse_args()
    
    path = args.path
    if os.path.isfile(path):
        relationships = extract_test_relationships_from_file(path)
    else:
        relationships = extract_test_relationships_from_directory(path, not args.no_recursive)
    
    # Print findings
    print(f"Found {len(relationships)} test relationships:")
    for rel in relationships:
        print(f"\nTest: {rel.test_name}")
        print(f"  Target: {rel.target_component}")
        print(f"  Type: {rel.test_type}")
        if rel.annotation_ref:
            print(f"  Tests annotation: {rel.annotation_ref['type']} = {rel.annotation_ref['value']}")
        print(f"  File: {rel.file_path}:{rel.line_number}")