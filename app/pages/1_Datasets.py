"""
Datasets page - Browse and explore neuroscience research datasets.

Features:
- Interactive knowledge graphs with drag and hover
- Feature-based subsetting for graph connections
- Keyword search across all columns
- Downloadable data and adjacency matrices
- AI-powered analysis
- No page reload on exports
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import sys

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from config import COLORS, SESSION_KEYS, HELP_TEXT
from utils.data_loader import (
    load_datasets,
    get_unique_values,
    filter_dataframe,
    search_across_columns
)
from utils.graph_builder import (
    build_knowledge_graph,
    create_interactive_graph,
    get_graph_statistics,
    export_adjacency_matrix,
    get_edge_details,
    filter_graph_by_degree
)
from utils.llm_utils import analyze_datasets, summarize_knowledge_graph
from utils.export_utils import (
    export_dataframe_csv,
    export_dataframe_tsv,
    export_dataframe_json,
    export_text_summary,
    export_graph_summary
)

# Page config
st.set_page_config(
    page_title="Datasets - CARD Catalog",
    page_icon="📊",
    layout="wide"
)

# Load custom CSS
css_file = Path(__file__).parent.parent / "assets" / "style.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def main():
    """Main datasets page."""

    st.title("📊 Research Datasets")
    st.markdown(
        "Explore neuroscience and brain disorder research datasets with interactive filtering and visualization."
    )

    # Load data
    df = load_datasets()

    if df.empty:
        st.error("No dataset data available. Please check data files.")
        return

    # Store original dataframe
    if 'original_datasets_df' not in st.session_state:
        st.session_state['original_datasets_df'] = df.copy()

    # Sidebar controls
    with st.sidebar:
        st.markdown("### App Controls")
        if st.button("🔄 Restart App", help="Restart the Streamlit application"):
            st.rerun()
        if st.button("🗑️ Clear Cache", help="Clear cached data and reload"):
            st.cache_data.clear()
            st.rerun()
        st.markdown("---")

    # Sidebar filters
    st.sidebar.header("Filters")

    # Keyword search
    search_term = st.sidebar.text_input(
        "🔍 Search across all columns",
        help="Enter keywords to search across all dataset fields (case-insensitive)"
    )

    # Disease filter
    diseases = get_unique_values(df, "Diseases Included", delimiter=";")
    selected_diseases = st.sidebar.multiselect(
        "Diseases",
        options=diseases,
        help="Filter by diseases studied"
    )

    # Coarse data types filter
    coarse_types = get_unique_values(df, "Coarse Data Types", delimiter=",")
    selected_coarse = st.sidebar.multiselect(
        "Coarse Data Types",
        options=coarse_types,
        help="Filter by high-level data categories (clinical, imaging, genetics, etc.)"
    )

    # Granular data types filter
    granular_types = get_unique_values(df, "Granular Data Types", delimiter=";")
    selected_granular = st.sidebar.multiselect(
        "Granular Data Types",
        options=granular_types,
        help="Filter by specific data modalities"
    )

    # Dataset type filter
    dataset_types = df["Dataset Type"].unique().tolist() if "Dataset Type" in df.columns else []
    selected_types = st.sidebar.multiselect(
        "Dataset Type",
        options=dataset_types,
        help="Filter by dataset type (Human, Model, etc.)"
    )

    st.sidebar.markdown("---")

    # Apply filters
    filtered_df = df.copy()

    # Keyword search first
    if search_term:
        filtered_df = search_across_columns(filtered_df, search_term)

    # Apply other filters
    filters = {}
    if selected_diseases:
        filters["Diseases Included"] = selected_diseases
    if selected_coarse:
        filters["Coarse Data Types"] = selected_coarse
    if selected_granular:
        filters["Granular Data Types"] = selected_granular
    if selected_types:
        filters["Dataset Type"] = selected_types

    if filters:
        filtered_df = filter_dataframe(filtered_df, filters)

    # Store filtered dataframe in session state
    st.session_state[SESSION_KEYS["datasets_filtered"]] = filtered_df

    # Display count
    st.info(f"Showing {len(filtered_df)} of {len(df)} datasets")

    # Main content tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Table View",
        "📋 Browse Datasets",
        "🕸️ Knowledge Graph",
        "🤖 AI Analysis",
        "📥 Export"
    ])

    # Tab 1: Table View
    with tab1:
        st.subheader("Dataset Table")

        if filtered_df.empty:
            st.warning("No datasets match the current filters.")
        else:
            # Display full dataframe as interactive table
            st.dataframe(
                filtered_df,
                width="stretch",
                height=600
            )

    # Tab 2: Browse Datasets
    with tab2:
        st.subheader("Dataset Catalog")

        if filtered_df.empty:
            st.warning("No datasets match the current filters.")
        else:
            # Display as expandable records
            for idx, row in filtered_df.iterrows():
                with st.expander(f"**{row.get('Study Name', 'Unknown')}** ({row.get('Abbreviation', 'N/A')})"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Diseases:** {row.get('Diseases Included', 'N/A')}")
                        st.markdown(f"**Data Modalities:** {row.get('Data Modalities', 'N/A')}")
                        st.markdown(f"**Sample Size:** {row.get('Sample Size', 'N/A')}")

                    with col2:
                        st.markdown(f"**Dataset Type:** {row.get('Dataset Type', 'N/A')}")
                        if row.get('Access URL'):
                            st.markdown(f"**Access:** [{row.get('Access URL')}]({row.get('Access URL')})")
                        st.markdown(f"**FAIR Notes:** {row.get('FAIR Compliance Notes', 'N/A')}")

    # Tab 3: Knowledge Graph
    with tab3:
        st.subheader("Dataset Relationship Network")

        st.info(HELP_TEXT["knowledge_graph"])

        if filtered_df.empty:
            st.warning("No datasets to visualize.")
        else:
            # Feature selection for connections
            st.markdown("#### Graph Settings")

            col1, col2, col3 = st.columns(3)

            with col1:
                connection_features = st.multiselect(
                    "Select features to create connections",
                    options=["Coarse Data Types", "Granular Data Types", "Diseases Included", "FAIR Compliance Notes"],
                    default=["Coarse Data Types", "Granular Data Types", "Diseases Included"],
                    help="Datasets will be connected if they share values in selected features"
                )

            with col2:
                min_shared_features = st.slider(
                    "Minimum shared features",
                    min_value=1,
                    max_value=4,
                    value=2,
                    help="Number of different features that must be shared to create a connection (reduces noise)"
                )

            with col3:
                min_connections = st.slider(
                    "Minimum connections to display",
                    min_value=0,
                    max_value=10,
                    value=0,
                    help="Filter out nodes with fewer connections (reduces clutter)"
                )

            if not connection_features:
                st.warning("Please select at least one feature to create graph connections.")
            else:
                with st.spinner("Building knowledge graph..."):
                    # Build graph
                    G = build_knowledge_graph(
                        filtered_df,
                        connection_features=connection_features,
                        name_column="Study Name",
                        min_shared_features=min_shared_features
                    )

                    # Filter by minimum connections
                    if min_connections > 0:
                        G = filter_graph_by_degree(G, min_degree=min_connections)

                    # Store graph in session state
                    st.session_state[SESSION_KEYS["graph_data"]] = G

                    # Get statistics
                    stats = get_graph_statistics(G)

                    # Display statistics
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Datasets", stats["num_nodes"])
                    col2.metric("Connections", stats["num_edges"])
                    col3.metric("Avg Connections", f"{stats['avg_degree']:.1f}")
                    col4.metric("Components", stats["num_components"])

                    # Display graph
                    if stats["num_nodes"] > 0:
                        fig = create_interactive_graph(G, title="Dataset Knowledge Graph")
                        st.plotly_chart(fig, use_container_width=False)

                        # Top connected datasets
                        if stats["top_nodes"]:
                            st.markdown("#### Most Connected Datasets")
                            top_df = pd.DataFrame(
                                stats["top_nodes"],
                                columns=["Dataset", "Connections"]
                            )
                            st.dataframe(top_df)

                        # Download adjacency matrix
                        st.markdown("#### Download Graph Data")
                        adj_matrix = export_adjacency_matrix(G)

                        col1, col2 = st.columns(2)

                        with col1:
                            st.download_button(
                                label="📥 Download Adjacency Matrix (CSV)",
                                data=adj_matrix.to_csv(),
                                file_name="dataset_adjacency_matrix.csv",
                                mime="text/csv"
                            )

                        with col2:
                            edge_details = get_edge_details(G)
                            if not edge_details.empty:
                                st.download_button(
                                    label="📥 Download Edge Details (CSV)",
                                    data=edge_details.to_csv(index=False),
                                    file_name="dataset_connections.csv",
                                    mime="text/csv"
                                )

                    else:
                        st.warning("No connections found with current settings. Try adjusting filters or connection features.")

    # Tab 4: AI Analysis
    with tab4:
        st.subheader("AI-Powered Dataset Analysis")

        with st.expander("ℹ️ About AI Analysis", expanded=False):
            st.markdown("""
            **What it does:**
            - Analyzes patterns across your selected/filtered datasets
            - Identifies common data modalities, disease focuses, and research trends
            - Highlights gaps and opportunities in the dataset landscape
            - Provides actionable recommendations for researchers

            **What it queries:**
            - Study names, abbreviations, and dataset types
            - Diseases studied and data modalities collected
            - Sample sizes and data availability
            - FAIR compliance notes

            **Comparative Analysis:**
            - Compares filtered datasets to the full catalog
            - Identifies unique characteristics of your selection
            - Contextualizes findings within broader research trends

            **Powered by:** Claude Sonnet 4.5 AI model
            """)

        if filtered_df.empty:
            st.warning("No datasets to analyze.")
        else:
            st.info(f"Ready to analyze {len(filtered_df)} of {len(df)} datasets ({len(filtered_df)/len(df)*100:.1f}% of catalog)")

            col1, col2 = st.columns([3, 1])

            with col2:
                if st.button("🤖 Analyze Datasets", type="primary"):
                    # Pass both filtered and full dataset for comparison
                    analysis = analyze_datasets(filtered_df, full_df=df)

                    if analysis:
                        st.session_state[SESSION_KEYS["analysis_result"]] = analysis

            # Display analysis if available
            if SESSION_KEYS["analysis_result"] in st.session_state:
                st.markdown("---")
                st.markdown("#### Analysis Results")
                st.markdown(st.session_state[SESSION_KEYS["analysis_result"]])

                # Add download button for analysis
                st.download_button(
                    label="📥 Download Analysis",
                    data=st.session_state[SESSION_KEYS["analysis_result"]],
                    file_name="dataset_analysis.txt",
                    mime="text/plain",
                    help="Download the AI analysis as a text file"
                )

            # Graph summary if graph exists
            if SESSION_KEYS["graph_data"] in st.session_state:
                st.markdown("---")
                st.markdown("#### Knowledge Graph Insights")

                if st.button("🤖 Summarize Graph"):
                    G = st.session_state[SESSION_KEYS["graph_data"]]
                    stats = get_graph_statistics(G)
                    edge_details = get_edge_details(G)

                    # Generate enhanced summary with connection drivers
                    summary = summarize_knowledge_graph(
                        stats,
                        filtered_df=filtered_df,
                        full_df=df,
                        edge_details=edge_details
                    )

                    if summary:
                        st.session_state['kg_summary'] = summary
                        st.markdown(summary)

                # Display saved summary and download button
                if 'kg_summary' in st.session_state:
                    st.download_button(
                        label="📥 Download Graph Summary",
                        data=st.session_state['kg_summary'],
                        file_name="knowledge_graph_summary.txt",
                        mime="text/plain",
                        help="Download the knowledge graph insights as a text file"
                    )

    # Tab 5: Export
    with tab5:
        st.subheader("Export Dataset Information")

        if filtered_df.empty:
            st.warning("No datasets to export.")
        else:
            st.markdown(f"**Export {len(filtered_df)} filtered datasets**")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Export as Structured Data")

                st.download_button(
                    label="📥 Export as CSV",
                    data=export_dataframe_csv(filtered_df),
                    file_name="datasets_export.csv",
                    mime="text/csv",
                    help="Export filtered datasets as CSV file"
                )

                st.download_button(
                    label="📥 Export as TSV",
                    data=export_dataframe_tsv(filtered_df),
                    file_name="datasets_export.tsv",
                    mime="text/tab-separated-values",
                    help="Export filtered datasets as TSV file"
                )

                st.download_button(
                    label="📥 Export as JSON",
                    data=export_dataframe_json(filtered_df),
                    file_name="datasets_export.json",
                    mime="application/json",
                    help="Export filtered datasets as JSON file"
                )

            with col2:
                st.markdown("#### Export as Text Summary")

                summary_text = export_text_summary(filtered_df, "CARD Datasets Summary")

                st.download_button(
                    label="📥 Export Summary as Text",
                    data=summary_text,
                    file_name="datasets_summary.txt",
                    mime="text/plain",
                    help="Export filtered datasets as formatted text"
                )

                # Graph export if available
                if SESSION_KEYS["graph_data"] in st.session_state:
                    st.markdown("#### Export Graph Summary")

                    G = st.session_state[SESSION_KEYS["graph_data"]]
                    stats = get_graph_statistics(G)
                    edge_details = get_edge_details(G)

                    graph_summary = export_graph_summary(stats, edge_details)

                    st.download_button(
                        label="📥 Export Graph Summary",
                        data=graph_summary,
                        file_name="dataset_graph_summary.txt",
                        mime="text/plain",
                        help="Export knowledge graph summary as text"
                    )


if __name__ == "__main__":
    main()
