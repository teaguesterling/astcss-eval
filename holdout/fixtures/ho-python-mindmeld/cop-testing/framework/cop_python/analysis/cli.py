#!/usr/bin/env python3
"""
Command-line interface for the COP static analysis toolkit.

This module provides a command-line interface for extracting COP annotations
from Python code, building a concept graph, and exporting it to various formats.
"""

import os
import sys
import argparse
import json
from typing import Dict, List, Any, Optional
from pathlib import Path

from .extractor import extract_annotations_from_file, extract_annotations_from_directory
from .graph import ConceptGraph, NodeType, EdgeType
from .exporter import JSONLExporter, DuckDBLoader
from .test_extractor import extract_test_relationships_from_file, extract_test_relationships_from_directory


def extract_command(args):
    """Extract COP annotations from Python code."""
    path = args.path
    recursive = not args.no_recursive
    output_file = args.output
    
    # Parse default annotations
    default_annotations = {}
    if hasattr(args, 'default_implementation_status') and args.default_implementation_status:
        default_annotations["implementation_status"] = args.default_implementation_status
    if hasattr(args, 'default_risk') and args.default_risk:
        default_annotations["risk"] = args.default_risk
    
    if os.path.isfile(path):
        annotations = extract_annotations_from_file(path, default_annotations=default_annotations)
    else:
        annotations = extract_annotations_from_directory(path, recursive, default_annotations=default_annotations)
    
    # Print summary
    print(f"Found {len(annotations)} annotations:")
    
    # Group by type and track defaults
    by_type = {}
    defaults_count = 0
    for anno in annotations:
        if anno.annotation_type not in by_type:
            by_type[anno.annotation_type] = {"total": 0, "defaults": 0}
        by_type[anno.annotation_type]["total"] += 1
        if anno.metadata.get("is_default", False):
            by_type[anno.annotation_type]["defaults"] += 1
            defaults_count += 1
    
    for anno_type, counts in by_type.items():
        total = counts["total"]
        defaults = counts["defaults"]
        if defaults > 0:
            print(f"- {anno_type}: {total} ({defaults} defaults)")
        else:
            print(f"- {anno_type}: {total}")
    
    if defaults_count > 0:
        print(f"\nTotal default annotations added: {defaults_count}")
    
    # Export to JSON if requested
    if output_file:
        with open(output_file, 'w') as f:
            json.dump([anno._asdict() for anno in annotations], f, indent=2)
        print(f"Annotations exported to {output_file}")
    
    return 0


def build_command(args):
    """Build a concept graph from Python code."""
    path = args.path
    recursive = not args.no_recursive
    output_file = args.output
    
    # Parse default annotations
    default_annotations = {}
    if hasattr(args, 'default_implementation_status') and args.default_implementation_status:
        default_annotations["implementation_status"] = args.default_implementation_status
    if hasattr(args, 'default_risk') and args.default_risk:
        default_annotations["risk"] = args.default_risk
    
    # Extract annotations
    if os.path.isfile(path):
        annotations = extract_annotations_from_file(path, default_annotations=default_annotations)
    else:
        annotations = extract_annotations_from_directory(path, recursive, default_annotations=default_annotations)
    
    # Build graph
    graph = ConceptGraph()
    graph.build_from_annotations(annotations)
    
    # Print summary
    component_count = len([n for n in graph.nodes.values() if n.node_type == NodeType.COMPONENT])
    annotation_count = len([n for n in graph.nodes.values() if n.node_type == NodeType.ANNOTATION])
    edge_count = len(graph.edges)
    
    print(f"Built concept graph:")
    print(f"- {component_count} components")
    print(f"- {annotation_count} annotations")
    print(f"- {edge_count} relationships")
    
    # Export to JSON if requested
    if output_file:
        graph.export_to_json(output_file)
        print(f"Graph exported to {output_file}")
    
    return 0


def export_command(args):
    """Export a concept graph to JSONL files."""
    path = args.path
    recursive = not args.no_recursive
    output_dir = args.output_dir
    db_path = args.db
    
    # Parse default annotations
    default_annotations = {}
    if hasattr(args, 'default_implementation_status') and args.default_implementation_status:
        default_annotations["implementation_status"] = args.default_implementation_status
    if hasattr(args, 'default_risk') and args.default_risk:
        default_annotations["risk"] = args.default_risk
    
    # Extract annotations
    if os.path.isfile(path):
        annotations = extract_annotations_from_file(path, default_annotations=default_annotations)
    else:
        annotations = extract_annotations_from_directory(path, recursive, default_annotations=default_annotations)
    
    # Build graph
    graph = ConceptGraph()
    graph.build_from_annotations(annotations)
    
    # Export to JSONL
    exporter = JSONLExporter(output_dir)
    counts = exporter.export_graph(graph)
    
    # Print summary
    print(f"Exported concept graph to {output_dir}:")
    print(f"- Nodes: {sum(counts['nodes'].values())}")
    for node_type, count in counts['nodes'].items():
        print(f"  - {node_type}: {count}")
    print(f"- Edges: {sum(counts['edges'].values())}")
    for edge_type, count in counts['edges'].items():
        print(f"  - {edge_type}: {count}")
    
    # Load into DuckDB if requested
    if db_path:
        try:
            print(f"Loading data into DuckDB at {db_path}...")
            loader = DuckDBLoader(db_path)
            loader.load_from_jsonl(output_dir)
            print("Loading complete")
        except ImportError:
            print("Skipping DuckDB loading: DuckDB not installed")
            print("To use this feature, install duckdb with: pip install duckdb")
    
    return 0


def load_command(args):
    """Load JSONL files into DuckDB."""
    jsonl_dir = args.jsonl_dir
    db_path = args.db
    
    # Load into DuckDB
    try:
        loader = DuckDBLoader(db_path)
        counts = loader.load_from_jsonl(jsonl_dir)
        
        # Print summary
        print(f"Loaded concept graph into DuckDB at {db_path}:")
        print(f"- Nodes: {sum(counts['nodes'].values())}")
        for node_type, count in counts['nodes'].items():
            print(f"  - {node_type}: {count}")
        print(f"- Edges: {sum(counts['edges'].values())}")
        for edge_type, count in counts['edges'].items():
            print(f"  - {edge_type}: {count}")
    except ImportError:
        print("Error: DuckDB not installed")
        print("To use this feature, install duckdb with: pip install duckdb")
        return 1
    
    return 0


def test_extract_command(args):
    """Extract test relationships from Python test code."""
    path = args.path
    recursive = not args.no_recursive
    output_file = args.output
    
    # Extract test relationships
    if os.path.isfile(path):
        relationships = extract_test_relationships_from_file(path)
    else:
        relationships = extract_test_relationships_from_directory(path, recursive)
    
    # Print summary
    print(f"Found {len(relationships)} test relationships:")
    
    # Group by test type and target component
    by_type = {}
    by_component = {}
    annotation_tests = 0
    
    for rel in relationships:
        # Count by test type
        test_type = rel.test_type
        if test_type not in by_type:
            by_type[test_type] = 0
        by_type[test_type] += 1
        
        # Count by target component
        component = rel.target_component
        if component not in by_component:
            by_component[component] = 0
        by_component[component] += 1
        
        # Count annotation tests
        if rel.annotation_ref:
            annotation_tests += 1
    
    # Print statistics
    print("\nBy test type:")
    for test_type, count in by_type.items():
        print(f"- {test_type}: {count}")
    
    print(f"\nTarget components: {len(by_component)}")
    if len(by_component) <= 10:  # Show details if not too many
        for component, count in sorted(by_component.items()):
            print(f"- {component}: {count} tests")
    
    print(f"Tests with annotation references: {annotation_tests}")
    
    # Export to JSON if requested
    if output_file:
        with open(output_file, 'w') as f:
            json.dump([rel._asdict() for rel in relationships], f, indent=2)
        print(f"Test relationships exported to {output_file}")
    
    return 0


def test_build_command(args):
    """Build a concept graph with both annotations and test relationships."""
    path = args.path
    test_path = args.test_path or path  # Use same path for tests if not specified
    recursive = not args.no_recursive
    output_file = args.output
    
    # Parse default annotations
    default_annotations = {}
    if hasattr(args, 'default_implementation_status') and args.default_implementation_status:
        default_annotations["implementation_status"] = args.default_implementation_status
    if hasattr(args, 'default_risk') and args.default_risk:
        default_annotations["risk"] = args.default_risk
    
    # Extract annotations
    if os.path.isfile(path):
        annotations = extract_annotations_from_file(path, default_annotations=default_annotations)
    else:
        annotations = extract_annotations_from_directory(path, recursive, default_annotations=default_annotations)
    
    # Extract test relationships
    if os.path.isfile(test_path):
        test_relationships = extract_test_relationships_from_file(test_path)
    else:
        test_relationships = extract_test_relationships_from_directory(test_path, recursive)
    
    # Build graph
    graph = ConceptGraph()
    graph.build_from_annotations(annotations)
    graph.build_from_test_relationships(test_relationships)
    
    # Print summary
    component_count = len([n for n in graph.nodes.values() if n.node_type == NodeType.COMPONENT])
    annotation_count = len([n for n in graph.nodes.values() if n.node_type == NodeType.ANNOTATION])
    test_count = len([n for n in graph.nodes.values() if n.node_type == NodeType.TEST])
    edge_count = len(graph.edges)
    
    print(f"Built concept graph:")
    print(f"- {component_count} components")
    print(f"- {annotation_count} annotations")
    print(f"- {test_count} tests")
    print(f"- {edge_count} relationships")
    
    # Show verification statistics
    verified_components = 0
    for node in graph.nodes.values():
        if node.node_type == NodeType.COMPONENT:
            status = graph.get_verification_status(node.id)
            if status["has_tests"]:
                verified_components += 1
    
    if component_count > 0:
        verification_rate = (verified_components / component_count) * 100
        print(f"- {verified_components}/{component_count} components have tests ({verification_rate:.1f}%)")
    
    # Export to JSON if requested
    if output_file:
        graph.export_to_json(output_file)
        print(f"Graph exported to {output_file}")
    
    return 0


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="cop-analysis",
        description="COP static analysis toolkit",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Extract command
    extract_parser = subparsers.add_parser("extract", help="Extract COP annotations")
    extract_parser.add_argument("path", help="File or directory to analyze")
    extract_parser.add_argument("--no-recursive", action="store_true", help="Don't scan directories recursively")
    extract_parser.add_argument("--output", help="Output file for annotations (JSON)")
    extract_parser.add_argument("--default-implementation-status", help="Default implementation status for components without one")
    extract_parser.add_argument("--default-risk", help="Default risk level for components without one")
    extract_parser.set_defaults(func=extract_command)
    
    # Build command
    build_parser = subparsers.add_parser("build", help="Build concept graph")
    build_parser.add_argument("path", help="File or directory to analyze")
    build_parser.add_argument("--no-recursive", action="store_true", help="Don't scan directories recursively")
    build_parser.add_argument("--output", help="Output file for graph (JSON)")
    build_parser.add_argument("--default-implementation-status", help="Default implementation status for components without one")
    build_parser.add_argument("--default-risk", help="Default risk level for components without one")
    build_parser.set_defaults(func=build_command)
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export concept graph to JSONL files")
    export_parser.add_argument("path", help="File or directory to analyze")
    export_parser.add_argument("--no-recursive", action="store_true", help="Don't scan directories recursively")
    export_parser.add_argument("--output-dir", required=True, help="Output directory for JSONL files")
    export_parser.add_argument("--db", help="DuckDB database file for loading (optional)")
    export_parser.add_argument("--default-implementation-status", help="Default implementation status for components without one")
    export_parser.add_argument("--default-risk", help="Default risk level for components without one")
    export_parser.set_defaults(func=export_command)
    
    # Load command
    load_parser = subparsers.add_parser("load", help="Load JSONL files into DuckDB")
    load_parser.add_argument("jsonl_dir", help="Directory containing JSONL files")
    load_parser.add_argument("--db", required=True, help="DuckDB database file")
    load_parser.set_defaults(func=load_command)
    
    # Test extract command
    test_extract_parser = subparsers.add_parser("test-extract", help="Extract test relationships from Python test code")
    test_extract_parser.add_argument("path", help="File or directory to analyze")
    test_extract_parser.add_argument("--no-recursive", action="store_true", help="Don't scan directories recursively")
    test_extract_parser.add_argument("--output", help="Output file for test relationships (JSON)")
    test_extract_parser.set_defaults(func=test_extract_command)
    
    # Test build command
    test_build_parser = subparsers.add_parser("test-build", help="Build concept graph with both annotations and tests")
    test_build_parser.add_argument("path", help="File or directory to analyze for annotations")
    test_build_parser.add_argument("--test-path", help="File or directory to analyze for tests (defaults to same as path)")
    test_build_parser.add_argument("--no-recursive", action="store_true", help="Don't scan directories recursively")
    test_build_parser.add_argument("--output", help="Output file for graph (JSON)")
    test_build_parser.add_argument("--default-implementation-status", help="Default implementation status for components without one")
    test_build_parser.add_argument("--default-risk", help="Default risk level for components without one")
    test_build_parser.set_defaults(func=test_build_command)
    
    # Parse arguments and run command
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())