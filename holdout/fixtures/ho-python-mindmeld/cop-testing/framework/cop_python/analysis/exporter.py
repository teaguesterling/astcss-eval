"""
Exporter for COP annotations and concept graph to JSONL files.

This module provides functionality to export extracted COP annotations
and concept graph data to line-delimited JSON files for easy import
into DuckDB with DuckPGQ for graph queries.
"""

import os
import json
from typing import Dict, List, Any, Optional, Set, Union
from pathlib import Path
from datetime import datetime

from .extractor import AnnotationInfo
from .graph import ConceptGraph, Node, Edge, NodeType, EdgeType


class JSONLExporter:
    """Exports concept graph data to JSONL files."""
    
    def __init__(self, output_dir: str):
        """
        Initialize a new JSONL exporter.
        
        Args:
            output_dir: Directory to save the JSONL files
        """
        self.output_dir = output_dir
        # Create directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
    
    def _get_file_path(self, node_or_edge_type: Union[NodeType, EdgeType]) -> str:
        """Get file path for a node or edge type."""
        return os.path.join(self.output_dir, f"{node_or_edge_type}.jsonl")
    
    def export_graph(self, graph: ConceptGraph) -> Dict[str, int]:
        """
        Export a concept graph to JSONL files.
        
        Args:
            graph: The concept graph to export
            
        Returns:
            Dictionary with counts of exported items by type
        """
        # Group nodes by type
        nodes_by_type: Dict[NodeType, List[Node]] = {}
        for node in graph.nodes.values():
            if node.node_type not in nodes_by_type:
                nodes_by_type[node.node_type] = []
            nodes_by_type[node.node_type].append(node)
        
        # Group edges by type
        edges_by_type: Dict[EdgeType, List[Edge]] = {}
        for edge in graph.edges:
            if edge.edge_type not in edges_by_type:
                edges_by_type[edge.edge_type] = []
            edges_by_type[edge.edge_type].append(edge)
        
        # Export nodes
        node_counts = {}
        for node_type, nodes in nodes_by_type.items():
            count = self._export_nodes(nodes, node_type)
            node_counts[node_type] = count
        
        # Export edges
        edge_counts = {}
        for edge_type, edges in edges_by_type.items():
            count = self._export_edges(edges, edge_type)
            edge_counts[edge_type] = count
        
        # Create metadata file
        metadata = {
            "exported_at": datetime.now().isoformat(),
            "node_counts": node_counts,
            "edge_counts": edge_counts,
            "total_nodes": sum(node_counts.values()),
            "total_edges": sum(edge_counts.values())
        }
        
        with open(os.path.join(self.output_dir, "metadata.json"), 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return {
            "nodes": node_counts,
            "edges": edge_counts
        }
    
    def _export_nodes(self, nodes: List[Node], node_type: NodeType) -> int:
        """
        Export nodes of a specific type to a JSONL file.
        
        Args:
            nodes: List of nodes to export
            node_type: Type of the nodes
            
        Returns:
            Number of nodes exported
        """
        file_path = self._get_file_path(node_type)
        
        with open(file_path, 'w') as f:
            for node in nodes:
                # Ensure ID is included
                data = node.to_dict()
                f.write(json.dumps(data) + '\n')
        
        return len(nodes)
    
    def _export_edges(self, edges: List[Edge], edge_type: EdgeType) -> int:
        """
        Export edges of a specific type to a JSONL file.
        
        Args:
            edges: List of edges to export
            edge_type: Type of the edges
            
        Returns:
            Number of edges exported
        """
        file_path = self._get_file_path(edge_type)
        
        with open(file_path, 'w') as f:
            for edge in edges:
                # Ensure source and target are included
                data = edge.to_dict()
                f.write(json.dumps(data) + '\n')
        
        return len(edges)


class DuckDBLoader:
    """Load concept graph data into DuckDB with DuckPGQ support."""
    
    def __init__(self, db_path: str):
        """
        Initialize a new DuckDB loader.
        
        Args:
            db_path: Path to the DuckDB database file
        """
        self.db_path = db_path
    
    def create_schema(self) -> None:
        """Create the schema for the concept graph in DuckDB."""
        # Import duckdb here so it's not a required dependency
        try:
            import duckdb
        except ImportError:
            raise ImportError("DuckDB not installed. Install with: pip install duckdb")
        
        # Connect to database
        conn = duckdb.connect(self.db_path)
        
        # Enable PGQ extension if available
        try:
            conn.execute("LOAD duckpgq;")
            conn.execute("CALL duckpgq_init();")
        except Exception as e:
            print(f"Warning: Could not initialize DuckPGQ extension: {e}")
            print("Graph queries may not be available.")
        
        # Create node tables for each type
        for node_type in NodeType:
            conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {node_type}_nodes (
                id VARCHAR PRIMARY KEY,
                data STRUCT(
                    type VARCHAR,
                    COLUMNS(*)
                )
            );
            """)
        
        # Create edge tables for each type
        for edge_type in EdgeType:
            conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {edge_type}_edges (
                source VARCHAR,
                target VARCHAR,
                data STRUCT(
                    type VARCHAR,
                    COLUMNS(*)
                )
            );
            """)
        
        conn.close()
    
    def load_from_jsonl(self, jsonl_dir: str) -> Dict[str, int]:
        """
        Load concept graph data from JSONL files into DuckDB.
        
        Args:
            jsonl_dir: Directory containing the JSONL files
            
        Returns:
            Dictionary with counts of loaded items by type
        """
        try:
            import duckdb
        except ImportError:
            raise ImportError("DuckDB not installed. Install with: pip install duckdb")
        
        # Connect to database
        conn = duckdb.connect(self.db_path)
        
        # Create schema if it doesn't exist
        self.create_schema()
        
        # Load nodes
        node_counts = {}
        for node_type in NodeType:
            file_path = os.path.join(jsonl_dir, f"{node_type}.jsonl")
            if not os.path.exists(file_path):
                continue
            
            # Load JSONL file into table
            conn.execute(f"""
            INSERT INTO {node_type}_nodes
            SELECT json->>'id' as id, json as data
            FROM read_json_auto('{file_path}', format='auto')
            """)
            
            # Get count
            result = conn.execute(f"SELECT COUNT(*) FROM {node_type}_nodes").fetchone()
            node_counts[node_type] = result[0] if result else 0
        
        # Load edges
        edge_counts = {}
        for edge_type in EdgeType:
            file_path = os.path.join(jsonl_dir, f"{edge_type}.jsonl")
            if not os.path.exists(file_path):
                continue
            
            # Load JSONL file into table
            conn.execute(f"""
            INSERT INTO {edge_type}_edges
            SELECT json->>'source' as source, json->>'target' as target, json as data
            FROM read_json_auto('{file_path}', format='auto')
            """)
            
            # Get count
            result = conn.execute(f"SELECT COUNT(*) FROM {edge_type}_edges").fetchone()
            edge_counts[edge_type] = result[0] if result else 0
        
        conn.close()
        
        return {
            "nodes": node_counts,
            "edges": edge_counts
        }


if __name__ == "__main__":
    # Simple CLI for testing
    import argparse
    from .extractor import extract_annotations_from_directory
    from .graph import ConceptGraph
    
    parser = argparse.ArgumentParser(description="Export concept graph to JSONL files")
    parser.add_argument("directory", help="Directory to analyze")
    parser.add_argument("--output", required=True, help="Output directory for JSONL files")
    parser.add_argument("--db", help="DuckDB database file for loading (optional)")
    args = parser.parse_args()
    
    # Extract annotations
    print(f"Extracting annotations from {args.directory}...")
    annotations = extract_annotations_from_directory(args.directory)
    print(f"Found {len(annotations)} annotations")
    
    # Build graph
    print("Building concept graph...")
    graph = ConceptGraph()
    graph.build_from_annotations(annotations)
    
    # Export to JSONL
    print(f"Exporting graph to JSONL files in {args.output}...")
    exporter = JSONLExporter(args.output)
    counts = exporter.export_graph(graph)
    
    print("Export complete:")
    print(f"- Nodes: {sum(counts['nodes'].values())}")
    for node_type, count in counts['nodes'].items():
        print(f"  - {node_type}: {count}")
    print(f"- Edges: {sum(counts['edges'].values())}")
    for edge_type, count in counts['edges'].items():
        print(f"  - {edge_type}: {count}")
    
    # Load into DuckDB if requested
    if args.db:
        try:
            print(f"Loading data into DuckDB at {args.db}...")
            loader = DuckDBLoader(args.db)
            loader.load_from_jsonl(args.output)
            print("Loading complete")
        except ImportError:
            print("Skipping DuckDB loading: DuckDB not installed")
            print("To use this feature, install duckdb with: pip install duckdb")