"""
Export utilities for generating downloadable files.
Supports CSV, TSV, JSON, and Excel formats.
"""

import pandas as pd
import io
from typing import Optional
import json

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import EXPORT_FORMATS


def export_dataframe_csv(df: pd.DataFrame) -> str:
    """
    Export DataFrame to CSV string.

    Args:
        df: DataFrame to export

    Returns:
        CSV string
    """
    return df.to_csv(index=False)


def export_dataframe_tsv(df: pd.DataFrame) -> str:
    """
    Export DataFrame to TSV string.

    Args:
        df: DataFrame to export

    Returns:
        TSV string
    """
    return df.to_csv(index=False, sep='\t')


def export_dataframe_json(df: pd.DataFrame) -> str:
    """
    Export DataFrame to JSON string.

    Args:
        df: DataFrame to export

    Returns:
        JSON string
    """
    return df.to_json(orient='records', indent=2)


def export_dataframe_excel(df: pd.DataFrame) -> bytes:
    """
    Export DataFrame to Excel bytes.

    Args:
        df: DataFrame to export

    Returns:
        Excel file bytes
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')
    return output.getvalue()


def export_text_summary(df: pd.DataFrame, title: str = "Data Summary") -> str:
    """
    Export DataFrame as formatted text summary.

    Args:
        df: DataFrame to export
        title: Title for the summary

    Returns:
        Formatted text string
    """
    lines = [
        "=" * 80,
        title.center(80),
        "=" * 80,
        "",
        f"Total Records: {len(df)}",
        "",
        "=" * 80,
        ""
    ]

    # Add records
    for idx, row in df.iterrows():
        lines.append(f"Record {idx + 1}:")
        lines.append("-" * 80)

        for col in df.columns:
            value = row[col]
            if pd.notna(value) and str(value).strip():
                # Format multiline values
                if '\n' in str(value):
                    lines.append(f"{col}:")
                    for line in str(value).split('\n'):
                        lines.append(f"  {line}")
                else:
                    lines.append(f"{col}: {value}")

        lines.append("")

    return "\n".join(lines)


def export_graph_summary(
    graph_stats: dict,
    edge_details: Optional[pd.DataFrame] = None
) -> str:
    """
    Export knowledge graph summary as text.

    Args:
        graph_stats: Dictionary with graph statistics
        edge_details: Optional DataFrame with edge details

    Returns:
        Formatted text string
    """
    lines = [
        "=" * 80,
        "Knowledge Graph Summary".center(80),
        "=" * 80,
        "",
        f"Nodes (Datasets): {graph_stats.get('num_nodes', 0)}",
        f"Edges (Connections): {graph_stats.get('num_edges', 0)}",
        f"Graph Density: {graph_stats.get('density', 0):.4f}",
        f"Average Connections per Node: {graph_stats.get('avg_degree', 0):.2f}",
        f"Maximum Connections: {graph_stats.get('max_degree', 0)}",
        f"Connected Components: {graph_stats.get('num_components', 0)}",
        "",
        "=" * 80,
        "Most Connected Datasets:",
        "-" * 80,
    ]

    # Add top connected nodes
    top_nodes = graph_stats.get('top_nodes', [])
    for node, degree in top_nodes:
        lines.append(f"  {node}: {degree} connections")

    # Add edge details if provided
    if edge_details is not None and not edge_details.empty:
        lines.extend([
            "",
            "=" * 80,
            "Connection Details:",
            "-" * 80,
        ])

        for idx, row in edge_details.head(20).iterrows():
            lines.append(f"\n{row['Node 1']} <-> {row['Node 2']}")
            lines.append(f"  Weight: {row['Weight']}")
            lines.append(f"  Shared: {row['Shared Features']}")

        if len(edge_details) > 20:
            lines.append(f"\n... and {len(edge_details) - 20} more connections")

    return "\n".join(lines)


def get_export_filename(base_name: str, format: str) -> str:
    """
    Generate appropriate filename with extension.

    Args:
        base_name: Base filename without extension
        format: Export format (csv, tsv, json, excel, txt)

    Returns:
        Filename with extension
    """
    format = format.lower()

    extensions = {
        "csv": ".csv",
        "tsv": ".tsv",
        "json": ".json",
        "excel": ".xlsx",
        "txt": ".txt"
    }

    extension = extensions.get(format, ".txt")

    # Clean base name
    base_name = base_name.replace(" ", "_")

    return f"{base_name}{extension}"


def get_mime_type(format: str) -> str:
    """
    Get MIME type for export format.

    Args:
        format: Export format

    Returns:
        MIME type string
    """
    format = format.lower()

    mime_types = {
        "csv": "text/csv",
        "tsv": "text/tab-separated-values",
        "json": "application/json",
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "txt": "text/plain"
    }

    return mime_types.get(format, "text/plain")


def prepare_export_data(
    df: pd.DataFrame,
    format: str,
    is_text_summary: bool = False,
    title: Optional[str] = None
) -> tuple:
    """
    Prepare data for export in specified format.

    Args:
        df: DataFrame to export
        format: Export format
        is_text_summary: Whether to export as text summary
        title: Title for text summary

    Returns:
        Tuple of (data, mime_type, filename_extension)
    """
    format = format.lower()

    if is_text_summary:
        data = export_text_summary(df, title or "Data Summary")
        return data, "text/plain", "txt"

    if format == "csv":
        data = export_dataframe_csv(df)
        return data, "text/csv", "csv"

    elif format == "tsv":
        data = export_dataframe_tsv(df)
        return data, "text/tab-separated-values", "tsv"

    elif format == "json":
        data = export_dataframe_json(df)
        return data, "application/json", "json"

    elif format == "excel":
        data = export_dataframe_excel(df)
        return data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"

    else:
        # Default to CSV
        data = export_dataframe_csv(df)
        return data, "text/csv", "csv"


def create_metadata_summary(df: pd.DataFrame) -> dict:
    """
    Create metadata summary for a DataFrame.

    Args:
        df: DataFrame

    Returns:
        Dictionary with metadata
    """
    metadata = {
        "total_records": len(df),
        "columns": list(df.columns),
        "column_count": len(df.columns),
        "data_types": df.dtypes.astype(str).to_dict(),
        "null_counts": df.isnull().sum().to_dict(),
        "memory_usage_mb": df.memory_usage(deep=True).sum() / (1024 * 1024)
    }

    return metadata


def export_with_metadata(df: pd.DataFrame, format: str = "json") -> str:
    """
    Export DataFrame with metadata.

    Args:
        df: DataFrame to export
        format: Export format (currently only supports JSON)

    Returns:
        JSON string with data and metadata
    """
    metadata = create_metadata_summary(df)

    export_data = {
        "metadata": metadata,
        "data": df.to_dict(orient='records')
    }

    return json.dumps(export_data, indent=2)
