#!/usr/bin/env python3
"""
COP Static Analysis Tutorial - Complete Walkthrough Script

This script demonstrates all capabilities of the COP toolkit using the tutorial e-commerce project.
Run this script to see the complete analysis workflow in action.
"""

import subprocess
import json
import os
from pathlib import Path
from collections import Counter
from decimal import Decimal


def run_command(cmd, description):
    """Run a command and print its output"""
    print(f"\n{'='*60}")
    print(f"🔍 {description}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}")
    print()
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return None


def analyze_annotations(annotations_file):
    """Analyze the extracted annotations"""
    print(f"\n{'='*60}")
    print("📊 ANNOTATION ANALYSIS")
    print(f"{'='*60}")
    
    with open(annotations_file, 'r') as f:
        annotations = json.load(f)
    
    print(f"Total annotations found: {len(annotations)}")
    
    # Count by type
    type_counts = Counter(ann['annotation_type'] for ann in annotations)
    print("\nAnnotation types:")
    for ann_type, count in type_counts.items():
        print(f"  {ann_type}: {count}")
    
    # Risk analysis
    risk_annotations = [ann for ann in annotations if ann['annotation_type'] == 'risk']
    if risk_annotations:
        risk_levels = Counter(ann['properties'].get('level', 'UNKNOWN') for ann in risk_annotations)
        print(f"\nRisk level distribution:")
        for level, count in risk_levels.items():
            print(f"  {level}: {count}")
    
    # Find high-risk components
    high_risk = [ann for ann in risk_annotations if ann['properties'].get('level') == 'HIGH']
    if high_risk:
        print(f"\n🚨 HIGH RISK Components ({len(high_risk)}):")
        for ann in high_risk:
            component = ann['component_name']
            details = ann['properties'].get('details', 'No details')
            print(f"  - {component}: {details}")
    
    # Files with most annotations
    file_counts = Counter(ann['file_path'] for ann in annotations)
    print(f"\nFiles with most annotations:")
    for file_path, count in file_counts.most_common(5):
        filename = os.path.basename(file_path)
        print(f"  {filename}: {count}")


def analyze_test_relationships(test_file):
    """Analyze the extracted test relationships"""
    print(f"\n{'='*60}")
    print("🧪 TEST RELATIONSHIP ANALYSIS")
    print(f"{'='*60}")
    
    with open(test_file, 'r') as f:
        tests = json.load(f)
    
    print(f"Total test relationships found: {len(tests)}")
    
    # Count by test type
    test_types = Counter(test['test_type'] for test in tests)
    print("\nTest types:")
    for test_type, count in test_types.items():
        print(f"  {test_type}: {count}")
    
    # Components with tests
    tested_components = set(test['target_component'] for test in tests)
    print(f"\nComponents with tests: {len(tested_components)}")
    
    # Test files
    test_files = Counter(os.path.basename(test['file_path']) for test in tests)
    print(f"\nTest files:")
    for file_name, count in test_files.items():
        print(f"  {file_name}: {count}")


def analyze_concept_graph(graph_file):
    """Analyze the concept graph"""
    print(f"\n{'='*60}")
    print("🔗 CONCEPT GRAPH ANALYSIS")
    print(f"{'='*60}")
    
    with open(graph_file, 'r') as f:
        graph = json.load(f)
    
    nodes = graph['nodes']
    edges = graph['edges']
    
    print(f"Total nodes: {len(nodes)}")
    print(f"Total edges: {len(edges)}")
    
    # Node type distribution
    node_types = Counter(node['type'] for node in nodes)
    print(f"\nNode types:")
    for node_type, count in node_types.items():
        print(f"  {node_type}: {count}")
    
    # Edge type distribution
    edge_types = Counter(edge['type'] for edge in edges)
    print(f"\nRelationship types:")
    for edge_type, count in edge_types.items():
        print(f"  {edge_type}: {count}")
    
    # Find components with most annotations
    component_nodes = [node for node in nodes if node['type'] == 'component']
    component_annotation_counts = {}
    
    for edge in edges:
        if edge['type'] == 'has_annotation':
            source = edge['source_id']
            if source not in component_annotation_counts:
                component_annotation_counts[source] = 0
            component_annotation_counts[source] += 1
    
    # Get top components by annotation count
    top_components = sorted(component_annotation_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    print(f"\nComponents with most annotations:")
    for comp_id, count in top_components:
        # Find component name
        comp_node = next((node for node in component_nodes if node['id'] == comp_id), None)
        if comp_node:
            name = comp_node['name']
            print(f"  {name}: {count} annotations")


def analyze_graph_data(graph_data_dir):
    """Analyze the JSONL graph data"""
    print(f"\n{'='*60}")
    print("📈 GRAPH DATABASE ANALYSIS")
    print(f"{'='*60}")
    
    nodes_file = os.path.join(graph_data_dir, 'nodes.jsonl')
    edges_file = os.path.join(graph_data_dir, 'edges.jsonl')
    summary_file = os.path.join(graph_data_dir, 'graph_summary.json')
    
    if os.path.exists(summary_file):
        with open(summary_file, 'r') as f:
            summary = json.load(f)
        
        print("Graph Summary:")
        for key, value in summary.items():
            if key != 'created_at':
                print(f"  {key}: {value}")
    
    # Count nodes and edges
    if os.path.exists(nodes_file):
        with open(nodes_file, 'r') as f:
            nodes = [json.loads(line) for line in f]
        print(f"\nNodes in JSONL: {len(nodes)}")
    
    if os.path.exists(edges_file):
        with open(edges_file, 'r') as f:
            edges = [json.loads(line) for line in f]
        print(f"Edges in JSONL: {len(edges)}")


def find_verification_gaps(annotations_file, test_file):
    """Find components with invariants but no tests"""
    print(f"\n{'='*60}")
    print("🔍 VERIFICATION GAP ANALYSIS")
    print(f"{'='*60}")
    
    with open(annotations_file, 'r') as f:
        annotations = json.load(f)
    
    with open(test_file, 'r') as f:
        tests = json.load(f)
    
    # Find components with invariants
    invariant_components = set()
    for ann in annotations:
        if ann['annotation_type'] == 'invariant':
            invariant_components.add(ann['component_name'])
    
    # Find tested components
    tested_components = set(test['target_component'] for test in tests)
    
    # Find gaps
    untested_invariants = invariant_components - tested_components
    
    print(f"Components with invariants: {len(invariant_components)}")
    print(f"Components with tests: {len(tested_components)}")
    print(f"Components with invariants but no tests: {len(untested_invariants)}")
    
    if untested_invariants:
        print("\nComponents needing test coverage:")
        for comp in sorted(list(untested_invariants)[:10]):  # Show first 10
            print(f"  - {comp}")
        if len(untested_invariants) > 10:
            print(f"  ... and {len(untested_invariants) - 10} more")


def main():
    """Run the complete tutorial analysis"""
    print("🚀 COP Static Analysis Toolkit - Tutorial Walkthrough")
    print("=" * 60)
    print("This script demonstrates the complete analysis workflow using")
    print("the tutorial e-commerce project as an example.")
    
    # Ensure we're in the right directory
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    tutorial_src = "examples/tutorial_ecommerce/src/"
    tutorial_tests = "examples/tutorial_ecommerce/tests/"
    
    # Step 1: Extract annotations
    run_command([
        "python", "-m", "cop_python.analysis.cli", "extract",
        tutorial_src, "--output", "tutorial_annotations.json"
    ], "Extracting COP annotations from source code")
    
    # Step 2: Extract test relationships
    run_command([
        "python", "-m", "cop_python.analysis.cli", "test-extract",
        tutorial_tests, "--output", "tutorial_test_relationships.json"
    ], "Extracting test relationships from test files")
    
    # Step 3: Build concept graph
    run_command([
        "python", "-m", "cop_python.analysis.cli", "test-build",
        tutorial_src, "--test-path", tutorial_tests,
        "--output", "tutorial_concept_graph.json"
    ], "Building integrated concept graph with verification tracking")
    
    # Step 4: Export for graph database
    run_command([
        "python", "-m", "cop_python.analysis.cli", "export",
        tutorial_src, "--output-dir", "tutorial_graph_data/"
    ], "Exporting data for graph database analysis")
    
    # Analysis Phase
    print(f"\n{'='*60}")
    print("📊 ANALYSIS PHASE")
    print(f"{'='*60}")
    
    # Analyze results
    if os.path.exists("tutorial_annotations.json"):
        analyze_annotations("tutorial_annotations.json")
    
    if os.path.exists("tutorial_test_relationships.json"):
        analyze_test_relationships("tutorial_test_relationships.json")
    
    if os.path.exists("tutorial_concept_graph.json"):
        analyze_concept_graph("tutorial_concept_graph.json")
    
    if os.path.exists("tutorial_graph_data/"):
        analyze_graph_data("tutorial_graph_data/")
    
    # Verification gap analysis
    if (os.path.exists("tutorial_annotations.json") and 
        os.path.exists("tutorial_test_relationships.json")):
        find_verification_gaps("tutorial_annotations.json", "tutorial_test_relationships.json")
    
    # Final summary
    print(f"\n{'='*60}")
    print("✅ TUTORIAL COMPLETE!")
    print(f"{'='*60}")
    print("You have successfully analyzed the tutorial e-commerce project using")
    print("all capabilities of the COP Static Analysis Toolkit!")
    print()
    print("📁 Generated files:")
    print("  - tutorial_annotations.json")
    print("  - tutorial_test_relationships.json") 
    print("  - tutorial_concept_graph.json")
    print("  - tutorial_graph_data/ (JSONL files)")
    print()
    print("📖 Next steps:")
    print("  - Explore the generated JSON files")
    print("  - Load the JSONL data into DuckDB for advanced queries")
    print("  - Apply these techniques to your own codebase")
    print("  - Read the full documentation in TUTORIAL.md")


if __name__ == "__main__":
    main()