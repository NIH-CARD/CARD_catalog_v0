"""
Code Repositories page - Browse and evaluate research code.

Features:
- LLM-based code quality scoring
- FAIR compliance data integration
- Deduplicated data types and tooling
- Creative search with keyword matching
- Export capabilities
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import sys

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from config import COLORS, SESSION_KEYS, HELP_TEXT
from utils.data_loader import (
    load_code_repos,
    load_fair_compliance,
    merge_fair_compliance,
    get_unique_values,
    filter_dataframe,
    search_across_columns
)
from utils.graph_builder import (
    build_knowledge_graph,
    create_interactive_graph,
    get_graph_statistics,
    get_edge_details,
    filter_graph_by_degree
)
from utils.llm_utils import (
    batch_score_repositories,
    test_api_connection,
    analyze_repositories,
    summarize_knowledge_graph,
    deep_dive_code_analysis
)
from utils.export_utils import (
    export_dataframe_csv,
    export_dataframe_tsv,
    export_dataframe_json,
    export_text_summary
)

# Page config
st.set_page_config(
    page_title="Code Repositories - CARD Catalog",
    page_icon="💻",
    layout="wide"
)

# Load custom CSS
css_file = Path(__file__).parent.parent / "assets" / "style.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def main():
    """Main code repositories page."""

    st.title("💻 Code Repositories")
    st.markdown(
        "Explore GitHub repositories related to neuroscience research with AI-powered quality scoring and FAIR compliance tracking."
    )

    # Load data
    code_df = load_code_repos()
    fair_df = load_fair_compliance()

    if code_df.empty:
        st.error("No code repository data available. Please check data files.")
        return

    # Merge FAIR compliance data
    df = merge_fair_compliance(code_df, fair_df)

    # Store original dataframe
    if 'original_code_df' not in st.session_state:
        st.session_state['original_code_df'] = df.copy()

    # Sidebar controls
    with st.sidebar:
        st.markdown("### App Controls")
        if st.button("🔄 Restart App", help="Restart the Streamlit application"):
            st.rerun()
        if st.button("🗑️ Clear Cache", help="Clear cached data and reload"):
            st.cache_data.clear()
            st.rerun()
            st.rerun()
        st.markdown("---")

    # Sidebar filters
    st.sidebar.header("Filters")

    # Keyword search
    search_term = st.sidebar.text_input(
        "🔍 Search across all columns",
        help="Search repository names, summaries, languages, etc."
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

    # Language filter
    languages = get_unique_values(df, "Languages", delimiter=",")
    selected_languages = st.sidebar.multiselect(
        "Programming Languages",
        options=languages,
        help="Filter by programming languages used"
    )

    # Data types filter (deduplicated)
    data_types = get_unique_values(df, "Data Types", delimiter=",")
    selected_data_types = st.sidebar.multiselect(
        "Data Types",
        options=data_types,
        help="Filter by data types used"
    )

    # Tooling filter (deduplicated)
    tooling = get_unique_values(df, "Tooling", delimiter=",")
    selected_tooling = st.sidebar.multiselect(
        "Tools & Frameworks",
        options=tooling,
        help="Filter by tools and frameworks used"
    )

    # Biomedical relevance filter
    if "Biomedical Relevance" in df.columns:
        relevance_options = ["YES", "NO", "UNCLEAR"]
        selected_relevance = st.sidebar.multiselect(
            "Biomedical Relevance",
            options=relevance_options,
            help="Filter by biomedical research relevance"
        )
    else:
        selected_relevance = []

    # FAIR score filter
    if "FAIR Score" in df.columns:
        min_fair_score = st.sidebar.slider(
            "Minimum FAIR Score",
            min_value=0,
            max_value=10,
            value=0,
            help="Filter by minimum FAIR compliance score (10 = perfect)"
        )
    else:
        min_fair_score = 0

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
    if selected_languages:
        filters["Languages"] = selected_languages
    if selected_data_types:
        filters["Data Types"] = selected_data_types
    if selected_tooling:
        filters["Tooling"] = selected_tooling

    if filters:
        filtered_df = filter_dataframe(filtered_df, filters)

    # Biomedical relevance filter
    if selected_relevance:
        mask = filtered_df["Biomedical Relevance"].apply(
            lambda x: any(rel in str(x).upper() for rel in selected_relevance)
        )
        filtered_df = filtered_df[mask]

    # FAIR score filter
    if min_fair_score > 0 and "FAIR Score" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["FAIR Score"] >= min_fair_score]

    # Store filtered dataframe
    st.session_state[SESSION_KEYS["code_filtered"]] = filtered_df

    # Display count
    st.info(f"Showing {len(filtered_df)} of {len(df)} repositories")

    # Main content tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Table View",
        "📋 Browse Repositories",
        "🕸️ Knowledge Graph",
        "🤖 AI Analysis",
        "📥 Export"
    ])

    # Tab 1: Table View
    with tab1:
        st.subheader("Repositories Table")

        if filtered_df.empty:
            st.warning("No repositories match the current filters.")
        else:
            # Display full dataframe as interactive table
            st.dataframe(
                filtered_df,
                width="stretch",
                height=600
            )

    # Tab 2: Browse Repositories
    with tab2:
        st.subheader("Repository Catalog")

        if filtered_df.empty:
            st.warning("No repositories match the current filters.")
        else:
            # Display as expandable records
            for idx, row in filtered_df.iterrows():
                repo_link = row.get('Repository Link', 'Unknown')
                study = row.get('Study Name', 'Unknown Study')
                abbrev = row.get('Abbreviation', 'N/A')

                # Extract repo name from link
                repo_name = repo_link.split('/')[-1] if '/' in repo_link else repo_link

                with st.expander(f"**{repo_name}** - {study} ({abbrev})"):
                    # Repository link
                    st.markdown(f"**Repository:** [{repo_link}]({repo_link})")

                    col1, col2 = st.columns(2)

                    with col1:
                        # Basic info
                        owner = row.get('Owner', 'N/A')
                        st.markdown(f"**Owner:** {owner}")

                        languages = row.get('Languages', 'N/A')
                        st.markdown(f"**Languages:** {languages}")

                        data_types_str = row.get('Data Types', 'N/A')
                        st.markdown(f"**Data Types:** {data_types_str}")

                        tooling_str = row.get('Tooling', 'N/A')
                        st.markdown(f"**Tooling:** {tooling_str}")

                    with col2:
                        # Relevance and scores
                        relevance = row.get('Biomedical Relevance', 'N/A')
                        st.markdown(f"**Biomedical Relevance:** {relevance}")

                        # FAIR score
                        if "FAIR Score" in row:
                            fair_score = row.get('FAIR Score', 'N/A')
                            st.markdown(f"**FAIR Score:** {fair_score}/10")

                        # LLM scores if available
                        if "LLM Cleanliness Score" in row:
                            st.markdown(f"**Cleanliness:** {row.get('LLM Cleanliness Score', 'N/A')}/10")
                        if "LLM Completeness Score" in row:
                            st.markdown(f"**Completeness:** {row.get('LLM Completeness Score', 'N/A')}/10")
                        if "LLM Runnable Score" in row:
                            st.markdown(f"**Run-out-of-box:** {row.get('LLM Runnable Score', 'N/A')}/10")

                    # Summary
                    summary = row.get('Code Summary', '')
                    if summary:
                        with st.expander("View Summary"):
                            st.markdown(summary)

                    # FAIR issues
                    if "FAIR Issues" in row and row.get('FAIR Issues'):
                        with st.expander("View FAIR Compliance Issues"):
                            st.markdown(row.get('FAIR Issues'))

                    # Contributors
                    contributors = row.get('Contributors', '')
                    if contributors:
                        with st.expander("View Contributors"):
                            st.markdown(contributors)

    # Tab 3: Knowledge Graph
    with tab3:
        st.subheader("Repository Network")

        if filtered_df.empty:
            st.warning("No repositories to visualize.")
        else:
            st.markdown("""
            Visualize relationships between code repositories based on shared features.
            Common words are automatically filtered from text fields to improve connection quality.
            """)

            # Graph settings
            st.markdown("#### Graph Settings")

            col1, col2, col3 = st.columns(3)

            with col1:
                # Get all column names (excluding internal columns)
                available_columns = [col for col in filtered_df.columns
                                   if col not in ['index', 'Repository Link']]

                # Default features: Languages, Data Types, Tooling, FAIR Issues, Diseases Included
                default_features = ["Languages", "Data Types", "Tooling", "FAIR Issues", "Diseases Included"]
                default_selection = [f for f in default_features if f in available_columns]
                if not default_selection:
                    default_selection = available_columns[:3] if len(available_columns) >= 3 else available_columns

                connection_features = st.multiselect(
                    "Select features to create connections",
                    options=available_columns,
                    default=default_selection,
                    help="Select which repository attributes should create connections. Text fields automatically filter common words."
                )

            with col2:
                min_shared_features = st.slider(
                    "Minimum shared features",
                    min_value=1,
                    max_value=min(len(connection_features), 5) if connection_features else 1,
                    value=2 if connection_features and len(connection_features) >= 2 else 1,
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
                    # Build graph using Repository Link as unique identifier
                    filtered_df_graph = filtered_df.copy()
                    # Create shorter IDs for display
                    filtered_df_graph['Repo ID'] = filtered_df_graph['Repository Link'].apply(
                        lambda x: x.split('/')[-1] if '/' in str(x) else str(x)
                    )

                    G = build_knowledge_graph(
                        filtered_df_graph,
                        connection_features=connection_features,
                        name_column="Repo ID",
                        delimiter=",",  # Code repos use comma delimiter
                        min_shared_features=min_shared_features
                    )

                    # Filter by minimum connections
                    if min_connections > 0:
                        G = filter_graph_by_degree(G, min_degree=min_connections)

                    # Store graph data for AI analysis in other tab
                    st.session_state['code_graph_data'] = G

                    # Get statistics
                    stats = get_graph_statistics(G)

                    # Display statistics
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Repositories", stats["num_nodes"])
                    col2.metric("Connections", stats["num_edges"])
                    col3.metric("Avg Connections", f"{stats['avg_degree']:.1f}")
                    col4.metric("Components", stats["num_components"])

                    if stats["num_nodes"] > 0 and stats["num_edges"] > 0:
                        # Create and display graph
                        # Note: Code repos don't have FAIR compliance in same way, so we'll use default coloring
                        fig = create_interactive_graph(G, title="Code Repository Network", color_by="fair_compliance")
                        st.plotly_chart(fig, use_container_width=False)

                        # Edge details in expander
                        with st.expander("View Connection Details"):
                            edge_df = get_edge_details(G)
                            if not edge_df.empty:
                                st.dataframe(edge_df)
                            else:
                                st.info("No connection details available.")

                        # Top connected repositories
                        if stats["top_nodes"]:
                            st.markdown("#### Most Connected Repositories")
                            top_nodes_df = pd.DataFrame(
                                stats["top_nodes"],
                                columns=["Repository", "Connections"]
                            )
                            st.dataframe(top_nodes_df)
                    else:
                        st.warning(
                            "No connections found with current settings. "
                            "Try reducing the minimum shared features or selecting different connection features."
                        )

    # Tab 4: AI Analysis
    with tab4:
        st.subheader("AI-Powered Repository Analysis")

        with st.expander("ℹ️ About AI Analysis", expanded=False):
            st.markdown("""
            **What it does:**
            - Analyzes programming languages, technologies, and research focus across repositories
            - Identifies code quality patterns and FAIR compliance trends
            - Highlights collaboration and reusability opportunities
            - Provides detailed quality and FAIR scoring for individual repositories

            **What it queries:**
            - Repository metadata (languages, data types, tooling)
            - Biomedical relevance assessments
            - FAIR compliance scores and issues
            - Code summaries and documentation quality

            **Comparative Analysis:**
            - Compares filtered repositories to the full catalog
            - Identifies unique characteristics of your selection
            - Contextualizes findings within computational neuroscience trends

            **Powered by:** Claude Sonnet 4.5 AI model
            """)

        if filtered_df.empty:
            st.warning("No repositories to analyze.")
        else:
            # Section 1: General Repository Analysis
            st.markdown("### General Repository Analysis")
            st.info(f"Ready to analyze {len(filtered_df)} of {len(df)} repositories ({len(filtered_df)/len(df)*100:.1f}% of catalog)")

            col1, col2 = st.columns([3, 1])

            with col2:
                if st.button("🤖 Analyze Repositories", type="primary"):
                    # Pass both filtered and full dataset for comparison
                    analysis = analyze_repositories(filtered_df, full_df=df)

                    if analysis:
                        st.session_state['repo_analysis_result'] = analysis

            # Display analysis if available
            if 'repo_analysis_result' in st.session_state:
                st.markdown("---")
                st.markdown("#### Analysis Results")
                st.markdown(st.session_state['repo_analysis_result'])

                # Add download button for analysis
                st.download_button(
                    label="📥 Download Analysis",
                    data=st.session_state['repo_analysis_result'],
                    file_name="repository_analysis.txt",
                    mime="text/plain",
                    help="Download the AI analysis as a text file"
                )

            st.markdown("---")

            # Section 2: Detailed Code Quality & FAIR Scoring
            with st.expander("#### Detailed Code Quality & FAIR Scoring", expanded=False):
                st.markdown(HELP_TEXT["llm_generated"])

                st.info(
                    "Generate AI-powered quality scores for code repositories. "
                    "This may take several minutes depending on the number of repositories."
                )

                # Check API connection
                col1, col2 = st.columns([3, 1])

                with col2:
                    if st.button("🔌 Test API"):
                        if test_api_connection():
                            st.success("API connection successful!")
                        else:
                            st.error("API connection failed. Check your API key.")

                st.markdown("---")

                # Scoring controls
                st.markdown("**Generate Quality Scores**")

                if st.button("🔬 Code Deep Dive", type="primary", help="Comprehensive analysis of code quality, completeness, and runnability"):
                    with st.spinner(f"Performing deep dive analysis on {len(filtered_df)} repositories..."):
                        # Perform comprehensive analysis
                        analysis = deep_dive_code_analysis(filtered_df)

                        if analysis:
                            st.session_state['code_deep_dive_result'] = analysis
                            st.success("Code deep dive complete!")
                            st.rerun()

                # Display deep dive results if available
                if 'code_deep_dive_result' in st.session_state:
                    st.markdown("---")
                    st.markdown("#### Deep Dive Analysis Results")
                    st.markdown(st.session_state['code_deep_dive_result'])

                    # Add download button
                    st.download_button(
                        label="📥 Download Deep Dive Report",
                        data=st.session_state['code_deep_dive_result'],
                        file_name="code_deep_dive_report.txt",
                        mime="text/plain",
                        help="Download the comprehensive code quality analysis"
                    )

                st.markdown("---")

                # Display score statistics if available
                score_columns = ["LLM Cleanliness Score", "LLM Completeness Score", "LLM Runnable Score"]
                available_scores = [col for col in score_columns if col in filtered_df.columns]

                if available_scores:
                    st.markdown("**Score Statistics**")

                    for score_col in available_scores:
                        # Convert to numeric, excluding N/A
                        numeric_scores = pd.to_numeric(
                            filtered_df[score_col],
                            errors='coerce'
                        ).dropna()

                        if not numeric_scores.empty:
                            col1, col2, col3, col4 = st.columns(4)

                            with col1:
                                st.metric(
                                    score_col.replace("LLM ", "").replace(" Score", ""),
                                    f"{numeric_scores.mean():.1f}/10"
                                )
                            with col2:
                                st.metric("Median", f"{numeric_scores.median():.1f}/10")
                            with col3:
                                st.metric("Min", f"{numeric_scores.min():.0f}/10")
                            with col4:
                                st.metric("Max", f"{numeric_scores.max():.0f}/10")

                    # Top scored repositories
                    st.markdown("**Top Scored Repositories**")

                    for score_col in available_scores:
                        numeric_df = filtered_df.copy()
                        numeric_df[score_col] = pd.to_numeric(
                            numeric_df[score_col],
                            errors='coerce'
                        )

                        top_repos = numeric_df.nlargest(5, score_col)[
                            ["Repository Link", "Study Name", score_col]
                        ]

                        if not top_repos.empty:
                            st.markdown(f"**{score_col}**")
                            st.dataframe(top_repos)

                st.markdown("---")

                # FAIR Compliance section
                st.markdown("**FAIR Compliance Distribution**")

                # FAIR score distribution
                if "FAIR Score" in filtered_df.columns:
                    col1, col2, col3, col4 = st.columns(4)

                    numeric_scores = pd.to_numeric(
                        filtered_df["FAIR Score"],
                        errors='coerce'
                    ).dropna()

                    if not numeric_scores.empty:
                        with col1:
                            st.metric("Average FAIR Score", f"{numeric_scores.mean():.1f}/10")
                        with col2:
                            st.metric("Median", f"{numeric_scores.median():.1f}/10")
                        with col3:
                            perfect_count = (numeric_scores == 10).sum()
                            st.metric("Perfect Scores", perfect_count)
                        with col4:
                            issues_count = (numeric_scores < 10).sum()
                            st.metric("With Issues", issues_count)

                        # Score histogram
                        score_counts = numeric_scores.value_counts().sort_index()
                        st.bar_chart(score_counts)

                # Common FAIR issues
                if "FAIR Issues" in filtered_df.columns:
                    st.markdown("**Common FAIR Issues**")

                    all_issues = []
                    for issues in filtered_df["FAIR Issues"].dropna():
                        if issues:
                            issue_list = [i.strip() for i in str(issues).split(";")]
                            all_issues.extend(issue_list)

                    if all_issues:
                        issue_counts = pd.Series(all_issues).value_counts().head(10)
                        st.dataframe(
                            pd.DataFrame({
                                "Issue Type": issue_counts.index,
                                "Count": issue_counts.values
                            }),
                        )

            # Section 3: Knowledge Graph Analysis
            if 'code_graph_data' in st.session_state:
                st.markdown("---")
                st.markdown("### Knowledge Graph Analysis")

                if st.button("🤖 Analyze Knowledge Graph"):
                    G = st.session_state['code_graph_data']
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
                        st.session_state['code_kg_summary'] = summary
                        st.markdown(summary)

                # Display saved summary and download button
                if 'code_kg_summary' in st.session_state:
                    st.download_button(
                        label="📥 Download Graph Summary",
                        data=st.session_state['code_kg_summary'],
                        file_name="code_knowledge_graph_summary.txt",
                        mime="text/plain",
                        help="Download the knowledge graph insights as a text file"
                    )

    # Tab 5: Export
    with tab5:
        st.subheader("Export Repository Information")

        if filtered_df.empty:
            st.warning("No repositories to export.")
        else:
            st.markdown(f"**Export {len(filtered_df)} filtered repositories**")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Export as Structured Data")

                st.download_button(
                    label="📥 Export as CSV",
                    data=export_dataframe_csv(filtered_df),
                    file_name="repositories_export.csv",
                    mime="text/csv",
                    help="Export filtered repositories as CSV file"
                )

                st.download_button(
                    label="📥 Export as TSV",
                    data=export_dataframe_tsv(filtered_df),
                    file_name="repositories_export.tsv",
                    mime="text/tab-separated-values",
                    help="Export filtered repositories as TSV file"
                )

                st.download_button(
                    label="📥 Export as JSON",
                    data=export_dataframe_json(filtered_df),
                    file_name="repositories_export.json",
                    mime="application/json",
                    help="Export filtered repositories as JSON file"
                )

            with col2:
                st.markdown("#### Export as Text Summary")

                summary_text = export_text_summary(filtered_df, "CARD Code Repositories Summary")

                st.download_button(
                    label="📥 Export Summary as Text",
                    data=summary_text,
                    file_name="repositories_summary.txt",
                    mime="text/plain",
                    help="Export filtered repositories as formatted text"
                )


if __name__ == "__main__":
    main()
