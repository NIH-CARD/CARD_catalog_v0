"""
Knowledge graph generation and visualization utilities.
Creates interactive network graphs from dataset relationships.
"""

import pandas as pd
import networkx as nx
import plotly.graph_objects as go
from typing import List, Dict, Tuple, Optional
import numpy as np
import streamlit as st

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import (
    GRAPH_LAYOUT_SETTINGS,
    GRAPH_NODE_SETTINGS,
    GRAPH_EDGE_SETTINGS,
    MAX_GRAPH_NODES,
    COLORS
)


def build_knowledge_graph(
    df: pd.DataFrame,
    connection_features: List[str],
    name_column: str = "Study Name",
    delimiter: str = ";",
    min_shared_features: int = 2
) -> nx.Graph:
    """
    Build a knowledge graph from a DataFrame based on shared features.

    Args:
        df: DataFrame containing the data
        connection_features: List of column names to use for creating connections
        name_column: Column name to use as node labels
        delimiter: Delimiter for parsing multi-value columns
        min_shared_features: Minimum number of shared features required to create an edge (default: 2)

    Returns:
        NetworkX graph object
    """
    G = nx.Graph()

    # Note: No size limit - graph construction is fast enough for full datasets

    # Add nodes
    for idx, row in df.iterrows():
        node_name = row.get(name_column, f"Item_{idx}")

        # Create node attributes
        attributes = {
            "index": idx,
            "label": node_name
        }

        # Add all row data as attributes
        for col in df.columns:
            attributes[col] = row[col]

        G.add_node(node_name, **attributes)

    # Add edges based on shared features
    nodes = list(G.nodes())

    for i, node1 in enumerate(nodes):
        for node2 in nodes[i + 1:]:
            # Check for shared features
            shared_features = []

            for feature in connection_features:
                if feature not in df.columns:
                    continue

                # Get values for both nodes
                val1 = G.nodes[node1].get(feature, "")
                val2 = G.nodes[node2].get(feature, "")

                # Determine if stopwords should be removed for this feature
                # Apply to text-heavy fields like summaries, descriptions, etc.
                text_fields = ['Code Summary', 'Summary', 'Description', 'Abstract',
                              'Languages', 'Tools/Packages', 'Tooling', 'Data Types',
                              'FAIR Issues', 'Biomedical Relevance']
                remove_stopwords = any(field in feature for field in text_fields)

                # Parse multi-value fields
                items1 = set(parse_delimited_field(val1, delimiter, remove_stopwords=remove_stopwords))
                items2 = set(parse_delimited_field(val2, delimiter, remove_stopwords=remove_stopwords))

                # Find intersection
                shared = items1.intersection(items2)

                if shared:
                    shared_features.append({
                        "feature": feature,
                        "shared_values": list(shared)
                    })

            # Add edge only if minimum shared features threshold is met
            if len(shared_features) >= min_shared_features:
                G.add_edge(
                    node1,
                    node2,
                    weight=len(shared_features),
                    shared_features=shared_features
                )

    return G


def get_stopwords() -> set:
    """
    Get common words to filter out from knowledge graph connections.

    Returns:
        Set of stopwords
    """
    return {
        # Common articles, prepositions, conjunctions
        'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
        'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'should', 'could', 'may', 'might', 'must', 'can',
        # Common general words
        'data', 'analysis', 'study', 'research', 'using', 'based', 'method',
        'methods', 'approach', 'approaches', 'model', 'models', 'system',
        'systems', 'tool', 'tools', 'use', 'used', 'uses', 'application',
        'applications', 'code', 'software', 'program', 'programs', 'package',
        'packages', 'library', 'libraries', 'framework', 'frameworks',
        # Short words (likely not meaningful)
        'i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x',
        'vs', 'etc', 'eg', 'ie'
    }


def parse_delimited_field(field: str, delimiter: str = ";", remove_stopwords: bool = False) -> List[str]:
    """
    Parse a delimited field into a list of items.

    Args:
        field: Delimited string
        delimiter: Delimiter character
        remove_stopwords: Whether to filter out common stopwords

    Returns:
        List of parsed items
    """
    if not field or pd.isna(field) or field == "":
        return []

    items = [item.strip() for item in str(field).split(delimiter)]
    items = [item for item in items if item]

    if remove_stopwords:
        stopwords = get_stopwords()
        items = [item for item in items if item.lower() not in stopwords and len(item) > 2]

    return items


def calculate_graph_layout(G: nx.Graph) -> Dict[str, Tuple[float, float]]:
    """
    Calculate node positions for graph visualization.
    Uses spring layout for better distribution.

    Args:
        G: NetworkX graph

    Returns:
        Dictionary mapping node names to (x, y) positions
    """
    if len(G.nodes()) == 0:
        return {}

    # Use spring layout with custom parameters
    pos = nx.spring_layout(
        G,
        k=GRAPH_LAYOUT_SETTINGS["k"],
        iterations=GRAPH_LAYOUT_SETTINGS["iterations"],
        scale=GRAPH_LAYOUT_SETTINGS["scale"],
        seed=42  # For reproducibility
    )

    return pos


def create_interactive_graph(
    G: nx.Graph,
    title: str = "Knowledge Graph",
    color_by: str = "fair_compliance"
) -> go.Figure:
    """
    Create an interactive Plotly graph visualization.

    Args:
        G: NetworkX graph
        title: Graph title
        color_by: Color nodes by "fair_compliance" or "completeness"

    Returns:
        Plotly figure object
    """
    if len(G.nodes()) == 0:
        # Return empty figure
        fig = go.Figure()
        fig.add_annotation(
            text="No data to display",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=20, color=COLORS["grey"])
        )
        return fig

    # Calculate layout
    pos = calculate_graph_layout(G)

    # Calculate node sizes based on degree (number of connections)
    degrees = dict(G.degree())
    max_degree = max(degrees.values()) if degrees else 1

    # Create edge traces
    edge_traces = []

    for edge in G.edges(data=True):
        node1, node2, data = edge
        x0, y0 = pos[node1]
        x1, y1 = pos[node2]

        # Edge width based on weight (more prominent scaling)
        weight = data.get('weight', 1)
        # Scale edge width more aggressively: weight 2 -> min, weight 5+ -> max
        normalized_weight = min((weight - 1) / 4, 1)  # Normalize 1-5 to 0-1
        edge_width = GRAPH_EDGE_SETTINGS["edge_width_min"] + (
            normalized_weight * (GRAPH_EDGE_SETTINGS["edge_width_max"] - GRAPH_EDGE_SETTINGS["edge_width_min"])
        )

        # Build hover text for edge showing shared features
        shared_features = data.get('shared_features', [])
        hover_text = f"<b>Connection strength: {weight}</b><br>"
        for sf in shared_features[:3]:  # Show first 3 shared features
            shared_vals = ', '.join(sf['shared_values'][:2])  # Show first 2 values
            if len(sf['shared_values']) > 2:
                shared_vals += f" (+{len(sf['shared_values'])-2} more)"
            hover_text += f"{sf['feature']}: {shared_vals}<br>"

        edge_trace = go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode='lines',
            line=dict(
                width=edge_width,
                color=COLORS["grey"]
            ),
            opacity=GRAPH_EDGE_SETTINGS["edge_opacity"],
            hoverinfo='text',
            text=hover_text,
            showlegend=False
        )
        edge_traces.append(edge_trace)

    # Create node trace
    node_x = []
    node_y = []
    node_text = []
    node_size = []
    node_color = []

    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)

        # Node info for hover
        node_attrs = G.nodes[node]

        # Detect node type: publication, code repository, or dataset
        is_publication = 'Title' in node_attrs and 'Authors' in node_attrs
        is_code_repo = 'Repository Link' in node_attrs and 'Languages' in node_attrs

        if is_code_repo:
            # Code repository hover info: Repo name, Link, Languages, FAIR Issues
            repo_name = node
            hover_text = f"<b>{repo_name}</b><br>"

            # Add repository link
            repo_link = node_attrs.get('Repository Link', '')
            if repo_link and str(repo_link).strip():
                hover_text += f"Link: {repo_link}<br>"

            # Add languages
            languages = str(node_attrs.get('Languages', ''))
            if languages:
                if len(languages) > 50:
                    languages = languages[:47] + "..."
                hover_text += f"Languages: {languages}<br>"

            # Add FAIR issues if present
            fair_issues = str(node_attrs.get('FAIR Issues', ''))
            if fair_issues and fair_issues.strip():
                if len(fair_issues) > 60:
                    fair_issues = fair_issues[:57] + "..."
                hover_text += f"FAIR Issues: {fair_issues}<br>"

            # Add other key attributes
            for key in ['Study Name', 'Data Types', 'Tooling']:
                if key in node_attrs and node_attrs[key]:
                    value = str(node_attrs[key])
                    if len(value) > 50:
                        value = value[:47] + "..."
                    hover_text += f"{key}: {value}<br>"

        elif is_publication:
            # Publication hover info: Title, Authors (truncated), Link
            title = node_attrs.get('Title', node)
            hover_text = f"<b>{title}</b><br>"

            # Add truncated author list
            authors = str(node_attrs.get('Authors', ''))
            if authors:
                author_list = authors.split(';')
                if len(author_list) > 3:
                    truncated_authors = '; '.join(author_list[:3]) + f' (+{len(author_list)-3} more)'
                else:
                    truncated_authors = authors
                hover_text += f"Authors: {truncated_authors}<br>"

            # Add PMC link if available
            pmc_link = node_attrs.get('PubMed Central Link', '')
            if pmc_link and str(pmc_link).strip():
                hover_text += f"Link: {pmc_link}<br>"

            # Add key publication attributes
            for key in ['Study Name', 'Diseases Included']:
                if key in node_attrs and node_attrs[key]:
                    value = str(node_attrs[key])
                    if len(value) > 60:
                        value = value[:57] + "..."
                    hover_text += f"{key}: {value}<br>"
        else:
            # Dataset hover info (original behavior)
            hover_text = f"<b>{node}</b><br>"
            for key in ['Abbreviation', 'Diseases Included', 'Data Modalities', 'FAIR Compliance Notes']:
                if key in node_attrs and node_attrs[key]:
                    value = str(node_attrs[key])
                    # Truncate long values
                    if len(value) > 80:
                        value = value[:77] + "..."
                    hover_text += f"{key}: {value}<br>"

        # Add connection count
        degree = degrees[node]
        hover_text += f"Connections: {degree}"

        node_text.append(hover_text)

        # Node size based on connections
        size = GRAPH_NODE_SETTINGS["node_size_min"] + (
            (degree / max_degree) *
            (GRAPH_NODE_SETTINGS["node_size_max"] - GRAPH_NODE_SETTINGS["node_size_min"])
        )
        node_size.append(size)

        # Color based on specified attribute
        if color_by == "completeness":
            # Color by data completeness (0-100%)
            completeness = node_attrs.get('Data Completeness', 50)  # Default to 50% if not found
            color_value = completeness / 100 * 3  # Scale to 0-3 range
        else:
            # Color based on FAIR compliance keywords (default)
            fair_notes = node_attrs.get('FAIR Compliance Notes', '').lower()
            if 'strong' in fair_notes or 'excellent' in fair_notes:
                color_value = 3  # Dark green
            elif 'good' in fair_notes:
                color_value = 2  # Medium green
            elif 'moderate' in fair_notes or 'fair' in fair_notes:
                color_value = 1  # Light green
            elif 'limited' in fair_notes or 'poor' in fair_notes or 'weak' in fair_notes:
                color_value = 0  # Very light/yellow
            else:
                color_value = 1.5  # Default/unknown
        node_color.append(color_value)

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode='markers',
        hoverinfo='text',
        text=node_text,
        marker=dict(
            size=node_size,
            color=node_color,
            colorscale=[
                [0, "#FFE6B3"],      # Light yellow - Poor/Limited
                [0.33, "#D4FFD4"],   # Light green - Moderate/Fair
                [0.67, "#98FF98"],   # Medium green - Good
                [1, "#228B22"]       # Dark green - Strong/Excellent
            ],
            line=dict(width=1, color=COLORS["grey"]),
            colorbar=dict(
                title="Data<br>Completeness" if color_by == "completeness" else "FAIR<br>Compliance",
                thickness=15,
                len=0.7,
                tickvals=[0, 1, 2, 3],
                ticktext=["0%", "33%", "67%", "100%"] if color_by == "completeness" else ["Limited", "Moderate", "Good", "Strong"]
            ),
            opacity=GRAPH_NODE_SETTINGS["node_opacity"]
        ),
        showlegend=False
    )

    # Create figure
    fig = go.Figure(data=edge_traces + [node_trace])

    # Update layout
    fig.update_layout(
        title=dict(
            text=title,
            x=0.5,
            xanchor='center',
            font=dict(size=20, color=COLORS["black"])
        ),
        showlegend=False,
        hovermode='closest',
        margin=dict(b=20, l=20, r=20, t=60),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor=COLORS["white"],
        paper_bgcolor=COLORS["white"],
        height=700,
        dragmode='pan'
    )

    # Add modebar buttons for better interactivity
    fig.update_layout(
        modebar_add=['select2d', 'lasso2d']
    )

    return fig


def get_graph_statistics(G: nx.Graph) -> Dict[str, any]:
    """
    Calculate statistics for a knowledge graph.

    Args:
        G: NetworkX graph

    Returns:
        Dictionary with graph statistics
    """
    if len(G.nodes()) == 0:
        return {
            "num_nodes": 0,
            "num_edges": 0,
            "density": 0,
            "avg_degree": 0,
            "max_degree": 0,
            "num_components": 0,
            "top_nodes": []
        }

    degrees = dict(G.degree())

    # Get top connected nodes
    top_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:10]

    stats = {
        "num_nodes": G.number_of_nodes(),
        "num_edges": G.number_of_edges(),
        "density": nx.density(G),
        "avg_degree": sum(degrees.values()) / len(degrees) if degrees else 0,
        "max_degree": max(degrees.values()) if degrees else 0,
        "num_components": nx.number_connected_components(G),
        "top_nodes": top_nodes
    }

    return stats


def export_adjacency_matrix(G: nx.Graph) -> pd.DataFrame:
    """
    Export graph as an adjacency matrix.

    Args:
        G: NetworkX graph

    Returns:
        DataFrame with adjacency matrix
    """
    if len(G.nodes()) == 0:
        return pd.DataFrame()

    # Get adjacency matrix
    adj_matrix = nx.to_pandas_adjacency(G)

    return adj_matrix


def get_edge_details(G: nx.Graph) -> pd.DataFrame:
    """
    Get detailed information about all edges in the graph.

    Args:
        G: NetworkX graph

    Returns:
        DataFrame with edge details
    """
    if len(G.edges()) == 0:
        return pd.DataFrame()

    edge_data = []

    for node1, node2, data in G.edges(data=True):
        shared_features = data.get('shared_features', [])

        # Format shared features
        features_str = "; ".join([
            f"{sf['feature']}: {', '.join(sf['shared_values'])}"
            for sf in shared_features
        ])

        edge_data.append({
            "Node 1": node1,
            "Node 2": node2,
            "Weight": data.get('weight', 1),
            "Shared Features": features_str
        })

    return pd.DataFrame(edge_data)


def filter_graph_by_degree(G: nx.Graph, min_degree: int = 1) -> nx.Graph:
    """
    Filter graph to only include nodes with at least min_degree connections.

    Args:
        G: NetworkX graph
        min_degree: Minimum number of connections

    Returns:
        Filtered graph
    """
    # Get nodes with sufficient degree
    degrees = dict(G.degree())
    nodes_to_keep = [node for node, degree in degrees.items() if degree >= min_degree]

    # Create subgraph
    G_filtered = G.subgraph(nodes_to_keep).copy()

    return G_filtered


def get_connected_components(G: nx.Graph) -> List[List[str]]:
    """
    Get connected components (clusters) in the graph.

    Args:
        G: NetworkX graph

    Returns:
        List of components, each containing node names
    """
    components = list(nx.connected_components(G))

    # Sort by size
    components = sorted(components, key=len, reverse=True)

    return [list(component) for component in components]


def get_central_nodes(G: nx.Graph, n: int = 10) -> List[Tuple[str, float]]:
    """
    Get most central nodes using betweenness centrality.

    Args:
        G: NetworkX graph
        n: Number of top nodes to return

    Returns:
        List of (node, centrality) tuples
    """
    if len(G.nodes()) == 0:
        return []

    # Calculate betweenness centrality
    centrality = nx.betweenness_centrality(G)

    # Sort and get top n
    top_central = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:n]

    return top_central
