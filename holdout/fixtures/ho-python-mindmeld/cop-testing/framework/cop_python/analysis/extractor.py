"""
Static analysis for extracting COP annotations from Python code.

This module uses Python's ast module to parse Python source code and
extract COP annotations without executing the code.
"""

import ast
import os
import sys
import inspect
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional, Set, Union, NamedTuple

from cop_python.analysis.metrics import get_default_metrics_providers, MetricsProvider


class AnnotationInfo(NamedTuple):
    """Information about a COP annotation."""
    annotation_type: str  # Type of annotation (invariant, risk, etc)
    component_name: str   # Fully qualified name of the component
    component_type: str   # Function, class, method, etc
    file_path: str        # Path to the file containing the annotation
    line_number: int      # Line number where the annotation appears
    value: Any            # Primary value of the annotation
    metadata: Dict[str, Any]  # Additional metadata for the annotation
    component_info: Dict[str, Any]  # Selective information about the component
    start_line: int       # Start line of the component definition (including decorators)
    end_line: int         # End line of the component definition
    actual_start_line: int  # Start line of the actual component (after decorators)
    metrics: Dict[str, Any] = {}  # Metrics for the component (complexity, size, etc)


class COPAnnotationVisitor(ast.NodeVisitor):
    """AST visitor to extract COP annotations from Python code."""
    
    # COP annotation decorators to detect
    COP_DECORATORS = {
        "intent", "invariant", "risk", "implementation_status", "decision"
    }
    
    def __init__(self, file_path: str, source_code: str, metrics_providers: List[MetricsProvider] = None):
        self.file_path = file_path
        self.source_code = source_code
        self.module_name = self._get_module_name(file_path)
        self.annotations = []
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
    
    def _get_component_name(self, node: Union[ast.FunctionDef, ast.ClassDef]) -> str:
        """Get fully qualified name for a component."""
        if self.current_class and isinstance(node, ast.FunctionDef):
            return f"{self.module_name}.{self.current_class}.{node.name}"
        else:
            return f"{self.module_name}.{node.name}"
    
    def _extract_decorator_args(self, decorator: ast.Call) -> Tuple[Any, Dict[str, Any]]:
        """Extract arguments from a decorator call."""
        args = []
        keywords = {}
        
        # Extract positional args
        for arg in decorator.args:
            if isinstance(arg, ast.Constant):
                args.append(arg.value)
            elif isinstance(arg, ast.Name):
                # This is a reference to a variable, we can only store the name
                args.append(f"<variable:{arg.id}>")
            else:
                # Complex expression, just note that it's an expression
                args.append("<complex_expression>")
        
        # Extract keyword args
        for kw in decorator.keywords:
            if isinstance(kw.value, ast.Constant):
                keywords[kw.arg] = kw.value.value
            elif isinstance(kw.value, ast.Name):
                keywords[kw.arg] = f"<variable:{kw.value.id}>"
            else:
                keywords[kw.arg] = "<complex_expression>"
        
        # Return primary value (first arg) and metadata (remaining args and keywords)
        primary_value = args[0] if args else None
        metadata = keywords
        if len(args) > 1:
            for i, arg in enumerate(args[1:], 1):
                metadata[f"arg{i}"] = arg
                
        return primary_value, metadata
    
    def _get_node_line_range(self, node: ast.AST) -> Tuple[int, int, int]:
        """
        Get the line range for a node including decorators.
        
        Returns:
            Tuple of (start_line, end_line, actual_start_line)
            
            start_line: First line (includes decorators)
            end_line: Last line
            actual_start_line: Line where the actual node definition starts
        """
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
    
    def _extract_component_info(self, node: ast.AST) -> Dict[str, Any]:
        """
        Extract selective information about a component.
        
        Args:
            node: AST node for the component
            
        Returns:
            Dictionary with selected component information
        """
        component_info = {}
        
        # Extract docstring (if any)
        docstring = ast.get_docstring(node)
        if docstring:
            component_info["docstring"] = docstring
        
        # Function/method specific information
        if isinstance(node, ast.FunctionDef):
            # Extract signature
            component_info["params"] = self._extract_function_params(node)
            
            # Extract return annotation if present
            if node.returns:
                component_info["returns"] = self._format_annotation(node.returns)
        
        # Class specific information
        elif isinstance(node, ast.ClassDef):
            # Extract base classes
            bases = []
            for base in node.bases:
                bases.append(self._format_expression(base))
            if bases:
                component_info["bases"] = bases
            
            # Extract method names and attribute names
            methods = []
            attributes = []
            
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append(item.name)
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            attributes.append(target.id)
            
            if methods:
                component_info["methods"] = methods
            if attributes:
                component_info["attributes"] = attributes
        
        return component_info
    
    def _extract_function_params(self, node: ast.FunctionDef) -> List[Dict[str, Any]]:
        """Extract parameter information from a function definition."""
        params = []
        
        for arg in node.args.args:
            param_info = {"name": arg.arg}
            
            if arg.annotation:
                param_info["annotation"] = self._format_annotation(arg.annotation)
            
            params.append(param_info)
        
        # Handle varargs
        if node.args.vararg:
            params.append({
                "name": f"*{node.args.vararg.arg}",
                "vararg": True
            })
        
        # Handle keyword-only args
        for arg in node.args.kwonlyargs:
            param_info = {"name": arg.arg, "kwonly": True}
            
            if arg.annotation:
                param_info["annotation"] = self._format_annotation(arg.annotation)
            
            params.append(param_info)
        
        # Handle kwargs
        if node.args.kwarg:
            params.append({
                "name": f"**{node.args.kwarg.arg}",
                "kwarg": True
            })
        
        return params
    
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
    
    def _format_expression(self, node: ast.AST) -> str:
        """Format an expression as a string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._format_expression(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            args = [self._format_expression(arg) for arg in node.args]
            func = self._format_expression(node.func)
            return f"{func}({', '.join(args)})"
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Str):  # For Python < 3.8
            return repr(node.s)
        elif hasattr(ast, 'Num') and isinstance(node, ast.Num):  # For Python < 3.8
            return repr(node.n)
        else:
            return "<complex_expression>"
            
    def _extract_metrics(self, node: ast.AST, component_type: str) -> Dict[str, Any]:
        """
        Extract metrics using all registered providers.
        
        Args:
            node: AST node for the component
            component_type: Type of the component (function, class, method)
            
        Returns:
            Dictionary with combined metrics from all providers
        """
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
    
    def _process_decorators(self, node: Union[ast.FunctionDef, ast.ClassDef]):
        """Process decorators for a function or class definition."""
        component_name = self._get_component_name(node)
        component_type = "class" if isinstance(node, ast.ClassDef) else "function"
        
        # Extract component information
        component_info = self._extract_component_info(node)
        
        # Get line range information
        start_line, end_line, actual_start_line = self._get_node_line_range(node)
        
        # Extract metrics
        metrics = self._extract_metrics(node, component_type)
        
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
                decorator_name = decorator.func.id
                if decorator_name in self.COP_DECORATORS:
                    value, metadata = self._extract_decorator_args(decorator)
                    
                    # Create annotation info
                    annotation = AnnotationInfo(
                        annotation_type=decorator_name,
                        component_name=component_name,
                        component_type=component_type,
                        file_path=self.file_path,
                        line_number=decorator.lineno,
                        value=value,
                        metadata=metadata,
                        component_info=component_info,
                        start_line=start_line,
                        end_line=end_line,
                        actual_start_line=actual_start_line,
                        metrics=metrics
                    )
                    
                    self.annotations.append(annotation)
            
            elif isinstance(decorator, ast.Name) and decorator.id in self.COP_DECORATORS:
                # Handle simple decorators without args (rare in COP)
                annotation = AnnotationInfo(
                    annotation_type=decorator.id,
                    component_name=component_name,
                    component_type=component_type,
                    file_path=self.file_path,
                    line_number=decorator.lineno,
                    value=None,
                    metadata={},
                    component_info=component_info,
                    start_line=start_line,
                    end_line=end_line,
                    actual_start_line=actual_start_line,
                    metrics=metrics
                )
                
                self.annotations.append(annotation)
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit a class definition."""
        old_class = self.current_class
        self.current_class = node.name
        
        self._process_decorators(node)
        
        # Visit class body
        for child in node.body:
            self.visit(child)
        
        self.current_class = old_class
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit a function definition."""
        self._process_decorators(node)
        
        # We don't need to visit the function body for annotations,
        # as COP annotations are applied as decorators


def _apply_default_annotations(annotations: List[AnnotationInfo], 
                              default_annotations: Dict[str, Any], 
                              file_path: str) -> List[AnnotationInfo]:
    """
    Apply default annotations to components that don't have them.
    
    Args:
        annotations: List of existing annotations
        default_annotations: Dict mapping annotation types to default values
        file_path: Path to the file being processed
        
    Returns:
        List of annotations with defaults applied
    """
    # Group annotations by component
    components: Dict[str, Dict[str, AnnotationInfo]] = {}
    for anno in annotations:
        if anno.component_name not in components:
            components[anno.component_name] = {}
        components[anno.component_name][anno.annotation_type] = anno
    
    # Create new annotations list starting with existing ones
    new_annotations = list(annotations)
    
    # For each component, check if it needs default annotations
    for component_name, component_annotations in components.items():
        # Get the first annotation to extract component info
        first_annotation = next(iter(component_annotations.values()))
        
        # Check each default annotation type
        for annotation_type, default_value in default_annotations.items():
            if annotation_type not in component_annotations:
                # Create a default annotation
                default_annotation = AnnotationInfo(
                    annotation_type=annotation_type,
                    component_name=component_name,
                    component_type=first_annotation.component_type,
                    file_path=file_path,
                    line_number=0,  # No actual line number for default annotations
                    value=default_value,
                    metadata={"is_default": True},
                    component_info=first_annotation.component_info,
                    start_line=first_annotation.start_line,
                    end_line=first_annotation.end_line,
                    actual_start_line=first_annotation.actual_start_line,
                    metrics=first_annotation.metrics
                )
                new_annotations.append(default_annotation)
    
    return new_annotations


def _infer_component_type(component_name: str) -> str:
    """
    Infer the component type from its name.
    
    Args:
        component_name: Fully qualified component name
        
    Returns:
        Inferred component type (function, method, class, etc.)
    """
    parts = component_name.split('.')
    
    # If name has multiple parts, the last part might be a method
    if len(parts) > 1:
        if len(parts) >= 3:  # module.class.method likely
            return "method"
        else:
            return "function"  # module.function likely
    
    # Single part - probably a class or module
    return "unknown"


def extract_annotations_from_file(file_path: str, 
                               metrics_providers: List[MetricsProvider] = None,
                               default_annotations: Dict[str, Any] = None) -> List[AnnotationInfo]:
    """
    Extract COP annotations from a Python file.
    
    Args:
        file_path: Path to the Python file
        metrics_providers: Optional list of metrics providers to use
        default_annotations: Optional dict mapping annotation types to default values
        
    Returns:
        List of extracted annotations
    """
    with open(file_path, 'r') as f:
        source_code = f.read()
    
    # Parse AST
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        # Log a warning but don't fail
        print(f"Warning: Syntax error in {file_path}, skipping")
        return []
    
    # Extract annotations
    visitor = COPAnnotationVisitor(file_path, source_code, metrics_providers)
    visitor.visit(tree)
    
    # Apply default annotations if specified
    annotations = visitor.annotations
    if default_annotations:
        annotations = _apply_default_annotations(annotations, default_annotations, file_path)
    
    return annotations


def extract_annotations_from_directory(directory: str, recursive: bool = True,
                                  metrics_providers: List[MetricsProvider] = None,
                                  default_annotations: Dict[str, Any] = None) -> List[AnnotationInfo]:
    """
    Extract COP annotations from all Python files in a directory.
    
    Args:
        directory: Directory to scan
        recursive: Whether to recursively scan subdirectories
        metrics_providers: Optional list of metrics providers to use
        default_annotations: Optional dict mapping annotation types to default values
        
    Returns:
        List of extracted annotations
    """
    all_annotations = []
    
    # Get Python files
    pattern = "**/*.py" if recursive else "*.py"
    for file_path in Path(directory).glob(pattern):
        file_annotations = extract_annotations_from_file(str(file_path), metrics_providers, default_annotations)
        all_annotations.extend(file_annotations)
    
    return all_annotations


if __name__ == "__main__":
    # Simple CLI for testing
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract COP annotations from Python code")
    parser.add_argument("path", help="File or directory to analyze")
    parser.add_argument("--no-recursive", action="store_true", help="Don't scan directories recursively")
    args = parser.parse_args()
    
    path = args.path
    if os.path.isfile(path):
        annotations = extract_annotations_from_file(path)
    else:
        annotations = extract_annotations_from_directory(path, not args.no_recursive)
    
    # Print findings
    for anno in annotations:
        print(f"{anno.annotation_type} in {anno.component_name} at {anno.file_path}:{anno.line_number}")
        print(f"  Value: {anno.value}")
        print(f"  Metadata: {anno.metadata}")
        print()