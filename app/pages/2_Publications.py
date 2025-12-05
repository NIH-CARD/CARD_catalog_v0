"""
Publications page - Browse and search scientific publications.

Features:
- Fixed PMC links (no duplicates)
- Normalized author names
- Keyword search
- Filtered browsing
- Export capabilities
- AI analysis
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import sys

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from config import COLORS, SESSION_KEYS, HELP_TEXT
from utils.data_loader import (
    load_publications,
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
from utils.llm_utils import analyze_publications, summarize_knowledge_graph
from utils.export_utils import (
    export_dataframe_csv,
    export_dataframe_tsv,
    export_dataframe_json,
    export_text_summary,
    export_graph_summary
)

# Page config
st.set_page_config(
    page_title="Publications - CARD Catalog",
    page_icon="📚",
    layout="wide"
)

# Load custom CSS
css_file = Path(__file__).parent.parent / "assets" / "style.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def main():
    """Main publications page."""

    st.title("📚 Scientific Publications")
    st.markdown(
        "Explore scientific literature from PubMed Central related to cataloged neuroscience studies."
    )

    # Load data
    df = load_publications()

    if df.empty:
        st.error("No publication data available. Please check data files.")
        return

    # Calculate data completeness stats
    total_pubs = len(df)
    pubs_with_links = len(df[df['PubMed Central Link'].astype(str).str.strip() != ''])
    pubs_without_links = total_pubs - pubs_with_links
    pubs_no_abstract = len(df[df['Abstract'].astype(str).str.strip() == ''])
    pubs_no_keywords = len(df[df['Keywords'].astype(str).str.strip() == ''])

    with st.expander("ℹ️ About Publication Data Completeness", expanded=False):
        st.markdown(f"""
        **Data Availability Overview:**
        - **PMC Full-Text Links:** {pubs_with_links} of {total_pubs} ({pubs_with_links/total_pubs*100:.1f}%)
        - **Abstracts:** {total_pubs - pubs_no_abstract} of {total_pubs} ({(total_pubs - pubs_no_abstract)/total_pubs*100:.1f}%)
        - **Keywords:** {total_pubs - pubs_no_keywords} of {total_pubs} ({(total_pubs - pubs_no_keywords)/total_pubs*100:.1f}%)

        **Why Some Data is Missing:**

        *PMC Links ({pubs_without_links} missing):*
        - Journal paywalls and subscription-only access
        - Publisher policies preventing open access
        - Embargo periods not yet expired
        - Publications indexed in PubMed but not deposited in PMC

        *Abstracts ({pubs_no_abstract} missing):*
        - Some older publications lack digitized abstracts
        - Certain publication types (editorials, letters) may not have abstracts
        - Data entry limitations in PubMed database

        *Keywords ({pubs_no_keywords} missing):*
        - Not all journals require author-supplied keywords
        - Older publications often lack keyword indexing
        - Some publication types don't use keywords

        **Note:** All publications include at minimum: title, authors, study association, and disease/modality information.
        """)


    # Store original dataframe
    if 'original_pubs_df' not in st.session_state:
        st.session_state['original_pubs_df'] = df.copy()

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
        help="Search titles, abstracts, authors, keywords, etc."
    )

    # Study filter
    studies = sorted(df["Study Name"].unique().tolist()) if "Study Name" in df.columns else []
    selected_studies = st.sidebar.multiselect(
        "Studies",
        options=studies,
        help="Filter by associated study"
    )

    # Disease filter
    diseases = get_unique_values(df, "Diseases Included", delimiter=";")
    selected_diseases = st.sidebar.multiselect(
        "Diseases",
        options=diseases,
        help="Filter by diseases studied"
    )

    # Coarse data types filter
    if "Coarse Data Types" in df.columns:
        coarse_types = get_unique_values(df, "Coarse Data Types", delimiter=",")
        selected_coarse = st.sidebar.multiselect(
            "Coarse Data Types",
            options=coarse_types,
            help="Filter by high-level data categories"
        )
    else:
        selected_coarse = []

    # Granular data types filter
    if "Granular Data Types" in df.columns:
        granular_types = get_unique_values(df, "Granular Data Types", delimiter=";")
        selected_granular = st.sidebar.multiselect(
            "Granular Data Types",
            options=granular_types,
            help="Filter by specific data modalities"
        )
    else:
        selected_granular = []

    # Keyword filter
    keywords = get_unique_values(df, "Keywords", delimiter=";")
    if keywords:
        selected_keywords = st.sidebar.multiselect(
            "Keywords",
            options=keywords[:100],  # Limit for performance
            help="Filter by publication keywords"
        )
    else:
        selected_keywords = []

    st.sidebar.markdown("---")

    # Apply filters
    filtered_df = df.copy()

    # Keyword search first
    if search_term:
        filtered_df = search_across_columns(filtered_df, search_term)

    # Apply other filters
    filters = {}
    if selected_studies:
        filters["Study Name"] = selected_studies
    if selected_diseases:
        filters["Diseases Included"] = selected_diseases
    if selected_coarse:
        filters["Coarse Data Types"] = selected_coarse
    if selected_granular:
        filters["Granular Data Types"] = selected_granular
    if selected_keywords:
        filters["Keywords"] = selected_keywords

    if filters:
        filtered_df = filter_dataframe(filtered_df, filters)

    # Store filtered dataframe
    st.session_state[SESSION_KEYS["pubs_filtered"]] = filtered_df

    # Display count
    st.info(f"Showing {len(filtered_df)} of {len(df)} publications")

    # Main content tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Table View",
        "📋 Browse Publications",
        "🕸️ Knowledge Graph",
        "🤖 AI Analysis",
        "📥 Export"
    ])

    # Tab 1: Table View
    with tab1:
        st.subheader("Publications Table")

        if filtered_df.empty:
            st.warning("No publications match the current filters.")
        else:
            # Display full dataframe as interactive table
            st.dataframe(
                filtered_df,
                width="stretch",
                height=600
            )

    # Tab 2: Browse Publications
    with tab2:
        st.subheader("Publication Catalog")

        if filtered_df.empty:
            st.warning("No publications match the current filters.")
        else:
            # Display as expandable records
            for idx, row in filtered_df.iterrows():
                title = row.get('Title', 'Untitled')
                study = row.get('Study Name', 'Unknown Study')
                abbrev = row.get('Abbreviation', 'N/A')

                with st.expander(f"**{title}**"):
                    # Study info
                    st.markdown(f"**Study:** {study} ({abbrev})")

                    # Authors
                    authors = row.get('Authors', 'N/A')
                    if authors:
                        st.markdown(f"**Authors:** {authors}")

                    # Affiliations
                    affiliations = row.get('Affiliations', '')
                    if affiliations:
                        with st.expander("View Affiliations"):
                            st.markdown(affiliations)

                    col1, col2 = st.columns(2)

                    with col1:
                        # Diseases
                        diseases_str = row.get('Diseases Included', 'N/A')
                        st.markdown(f"**Diseases:** {diseases_str}")

                        # Data modalities
                        modalities = row.get('Data Modalities', 'N/A')
                        st.markdown(f"**Data Modalities:** {modalities}")

                    with col2:
                        # Keywords
                        keywords_str = row.get('Keywords', 'N/A')
                        st.markdown(f"**Keywords:** {keywords_str}")

                        # PMC Link - Fixed to remove duplicates
                        pmc_link = row.get('PubMed Central Link', '')
                        if pmc_link:
                            st.markdown(f"**Link:** [View on PubMed Central]({pmc_link})")

                    # Abstract
                    abstract = row.get('Abstract', '')
                    if abstract:
                        with st.expander("Read Abstract"):
                            st.markdown(abstract)

    # Tab 3: Knowledge Graph
    with tab3:
        st.subheader("Publication Relationship Network")

        st.info("Interactive knowledge graph showing connections between publications based on shared studies, diseases, and data types.")

        if filtered_df.empty:
            st.warning("No publications to visualize.")
        else:
            # Graph settings
            st.markdown("#### Graph Settings")

            col1, col2, col3 = st.columns(3)

            with col1:
                connection_features = st.multiselect(
                    "Select features to create connections",
                    options=["Study Name", "Diseases Included", "Coarse Data Types", "Granular Data Types", "Authors", "Affiliations", "Keywords", "Abstract"],
                    default=["Study Name", "Diseases Included"],
                    help="Publications will be connected if they share values in selected features (common words filtered)"
                )

            with col2:
                min_shared_features = st.slider(
                    "Minimum shared features",
                    min_value=1,
                    max_value=8,
                    value=2,
                    help="Number of different features that must be shared to create a connection"
                )

            with col3:
                min_connections = st.slider(
                    "Minimum connections to display",
                    min_value=0,
                    max_value=10,
                    value=0,
                    help="Filter out nodes with fewer connections"
                )

            if not connection_features:
                st.warning("Please select at least one feature to create graph connections.")
            else:
                with st.spinner("Building knowledge graph..."):
                    # Build graph (will use Study Name as identifier since publications don't have unique names)
                    # Create a unique identifier for each publication
                    filtered_df_graph = filtered_df.copy()
                    filtered_df_graph['Publication ID'] = filtered_df_graph['Study Name'] + " - " + filtered_df_graph['Title'].str[:50]

                    G = build_knowledge_graph(
                        filtered_df_graph,
                        connection_features=connection_features,
                        name_column="Publication ID",
                        min_shared_features=min_shared_features
                    )

                    # Filter by minimum connections
                    if min_connections > 0:
                        G = filter_graph_by_degree(G, min_degree=min_connections)

                    # Get statistics
                    stats = get_graph_statistics(G)

                    # Display statistics
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Publications", stats["num_nodes"])
                    col2.metric("Connections", stats["num_edges"])
                    col3.metric("Avg Connections", f"{stats['avg_degree']:.1f}")
                    col4.metric("Components", stats["num_components"])

                    if stats["num_nodes"] > 0 and stats["num_edges"] > 0:
                        # Create and display graph with completeness-based coloring
                        fig = create_interactive_graph(G, title="Publication Network", color_by="completeness")
                        st.plotly_chart(fig)

                        # Edge details in expander
                        with st.expander("View Connection Details"):
                            edge_df = get_edge_details(G)
                            if not edge_df.empty:
                                st.dataframe(edge_df)

                        # Store graph data for AI analysis in other tab
                        st.session_state['pubs_graph_data'] = G
                        st.session_state['pubs_graph_stats'] = stats

                    else:
                        st.warning("No connections found with current settings. Try adjusting filters or connection features.")

    # Tab 4: AI Analysis
    with tab4:
        st.subheader("AI-Powered Publication Analysis")

        with st.expander("ℹ️ About AI Analysis", expanded=False):
            st.markdown("""
            **What it does:**
            - Analyzes major research themes across your selected/filtered publications
            - Identifies active research areas and collaboration trends
            - Highlights key findings and emerging directions

            **What it queries:**
            - Study associations and publication metadata
            - Authors, affiliations, and keywords
            - Titles and abstracts

            **Comparative Analysis:**
            - Compares filtered publications to the full catalog
            - Identifies unique characteristics of your selection
            - Contextualizes findings within broader research landscape

            **Powered by:** Claude Sonnet 4.5 AI model
            """)

        if filtered_df.empty:
            st.warning("No publications to analyze.")
        else:
            st.info(f"Ready to analyze {len(filtered_df)} of {len(df)} publications ({len(filtered_df)/len(df)*100:.1f}% of catalog)")

            col1, col2 = st.columns([3, 1])

            with col2:
                if st.button("🤖 Analyze Publications", type="primary"):
                    analysis = analyze_publications(filtered_df, full_df=df)

                    if analysis:
                        st.session_state['pubs_analysis_result'] = analysis

            # Display analysis if available
            if 'pubs_analysis_result' in st.session_state:
                st.markdown("---")
                st.markdown("#### Analysis Results")
                st.markdown(st.session_state['pubs_analysis_result'])

                # Add download button for analysis
                st.download_button(
                    label="📥 Download Analysis",
                    data=st.session_state['pubs_analysis_result'],
                    file_name="publication_analysis.txt",
                    mime="text/plain",
                    help="Download the AI analysis as a text file"
                )

            # Knowledge Graph AI Summary (if graph exists)
            if 'pubs_graph_data' in st.session_state and 'pubs_graph_stats' in st.session_state:
                st.markdown("---")
                st.markdown("#### Knowledge Graph Insights")

                if st.button("🤖 Analyze Knowledge Graph"):
                    G = st.session_state['pubs_graph_data']
                    stats = st.session_state['pubs_graph_stats']
                    edge_details = get_edge_details(G)

                    # Generate summary with connection drivers
                    summary = summarize_knowledge_graph(
                        stats,
                        filtered_df=filtered_df,
                        full_df=df,
                        edge_details=edge_details
                    )

                    if summary:
                        st.session_state['pubs_kg_summary'] = summary
                        st.markdown(summary)

                # Display saved summary and download button
                if 'pubs_kg_summary' in st.session_state:
                    st.download_button(
                        label="📥 Download Graph Summary",
                        data=st.session_state['pubs_kg_summary'],
                        file_name="publications_kg_summary.txt",
                        mime="text/plain",
                        help="Download the knowledge graph insights as a text file"
                    )

            # Statistics
            st.markdown("---")
            st.markdown("#### Publication Statistics")

            col1, col2, col3 = st.columns(3)

            with col1:
                # Top studies by publication count
                study_counts = filtered_df["Study Name"].value_counts().head(10)
                st.markdown("**Top Studies by Publications**")
                for study, count in study_counts.items():
                    st.markdown(f"- {study}: {count}")

            with col2:
                # Top keywords
                if "Keywords" in filtered_df.columns:
                    all_keywords = []
                    for keywords in filtered_df["Keywords"].dropna():
                        if keywords:
                            all_keywords.extend([k.strip() for k in str(keywords).split(";")])

                    if all_keywords:
                        keyword_counts = pd.Series(all_keywords).value_counts().head(10)
                        st.markdown("**Top Keywords**")
                        for keyword, count in keyword_counts.items():
                            st.markdown(f"- {keyword}: {count}")

            with col3:
                # Top diseases
                if "Diseases Included" in filtered_df.columns:
                    all_diseases = []
                    for diseases in filtered_df["Diseases Included"].dropna():
                        if diseases:
                            all_diseases.extend([d.strip() for d in str(diseases).split(";")])

                    if all_diseases:
                        disease_counts = pd.Series(all_diseases).value_counts().head(10)
                        st.markdown("**Top Diseases Studied**")
                        for disease, count in disease_counts.items():
                            st.markdown(f"- {disease}: {count}")

    # Tab 5: Export
    with tab5:
        st.subheader("Export Publication Information")

        if filtered_df.empty:
            st.warning("No publications to export.")
        else:
            st.markdown(f"**Export {len(filtered_df)} filtered publications**")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Export as Structured Data")

                st.download_button(
                    label="📥 Export as CSV",
                    data=export_dataframe_csv(filtered_df),
                    file_name="publications_export.csv",
                    mime="text/csv",
                    help="Export filtered publications as CSV file"
                )

                st.download_button(
                    label="📥 Export as TSV",
                    data=export_dataframe_tsv(filtered_df),
                    file_name="publications_export.tsv",
                    mime="text/tab-separated-values",
                    help="Export filtered publications as TSV file"
                )

                st.download_button(
                    label="📥 Export as JSON",
                    data=export_dataframe_json(filtered_df),
                    file_name="publications_export.json",
                    mime="application/json",
                    help="Export filtered publications as JSON file"
                )

            with col2:
                st.markdown("#### Export as Text Summary")

                summary_text = export_text_summary(filtered_df, "CARD Publications Summary")

                st.download_button(
                    label="📥 Export Summary as Text",
                    data=summary_text,
                    file_name="publications_summary.txt",
                    mime="text/plain",
                    help="Export filtered publications as formatted text"
                )

                # Export bibliography format
                st.markdown("#### Export Citation List")

                # Create simple citation list
                citations = []
                for idx, row in filtered_df.iterrows():
                    authors = row.get('Authors', 'Unknown')
                    title = row.get('Title', 'Untitled')
                    pmc_link = row.get('PubMed Central Link', '')

                    # Simple citation format
                    citation = f"{authors}. {title}."
                    if pmc_link:
                        citation += f" {pmc_link}"

                    citations.append(citation)

                citation_text = "\n\n".join(citations)

                st.download_button(
                    label="📥 Export Citations",
                    data=citation_text,
                    file_name="publications_citations.txt",
                    mime="text/plain",
                    help="Export publication citations as text"
                )


if __name__ == "__main__":
    main()
