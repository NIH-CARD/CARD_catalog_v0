"""
Human Cellular Models page - Browse iNDI iPSC collection.

Features:
- Search across all text columns
- Multi-select filters for Gene, Condition, and Parental Line
- Clickable procurement links
- Expandable long text columns
- Export as CSV and JSON
- Statistics dashboard
- Mint theme styling
"""

import streamlit as st
import pandas as pd
from pathlib import Path
import sys

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from config import COLORS, SESSION_KEYS
from utils.data_loader import (
    load_indi_inventory,
    get_unique_values,
    filter_dataframe,
    search_across_columns
)
from utils.export_utils import (
    export_dataframe_csv,
    export_dataframe_json
)
from utils.llm_utils import analyze_cellular_models

# Page config
st.set_page_config(
    page_title="Human Cellular Models - CARD Catalog",
    page_icon="🧬",
    layout="wide"
)

# Load custom CSS
css_file = Path(__file__).parent.parent / "assets" / "style.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def truncate_text(text: str, max_length: int = 200) -> str:
    """
    Truncate text to max_length characters.

    Args:
        text: Text to truncate
        max_length: Maximum length

    Returns:
        Truncated text with ellipsis if needed
    """
    if not text or pd.isna(text):
        return ""

    text_str = str(text).strip()
    if len(text_str) <= max_length:
        return text_str

    return text_str[:max_length] + "..."


def main():
    """Main Human Cellular Models page."""

    st.title("🧬 Human Cellular Models")
    st.markdown(
        """
        Browse the **iNDI (iPSC Neurodegenerative Disease Initiative)** collection of human
        induced pluripotent stem cell (iPSC) lines for neurodegenerative disease research.
        These cellular models provide critical tools for studying disease mechanisms and
        developing therapeutic interventions.
        """
    )

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

    # Load data
    df = load_indi_inventory()

    if df.empty:
        st.error("No iNDI inventory data available. Please check data files.")
        return

    # Store original dataframe
    if 'original_indi_df' not in st.session_state:
        st.session_state['original_indi_df'] = df.copy()

    # Sidebar filters
    st.sidebar.header("Filters")

    # Keyword search
    search_term = st.sidebar.text_input(
        "🔍 Search across all columns",
        help="Enter keywords to search across all fields (case-insensitive, fuzzy matching)"
    )

    # Gene filter
    genes = sorted(df["Gene"].unique().tolist()) if "Gene" in df.columns else []
    genes = [g for g in genes if g and str(g).strip()]
    selected_genes = st.sidebar.multiselect(
        "Gene",
        options=genes,
        help="Filter by gene"
    )

    # Condition filter
    conditions = sorted(df["Condition"].unique().tolist()) if "Condition" in df.columns else []
    conditions = [c for c in conditions if c and str(c).strip() and str(c) != "0"]
    selected_conditions = st.sidebar.multiselect(
        "Condition",
        options=conditions,
        help="Filter by disease condition"
    )

    # Parental Line filter
    parental_lines = sorted(df["Parental Line"].unique().tolist()) if "Parental Line" in df.columns else []
    parental_lines = [p for p in parental_lines if p and str(p).strip()]
    selected_parental_lines = st.sidebar.multiselect(
        "Parental Line",
        options=parental_lines,
        help="Filter by parental cell line"
    )

    st.sidebar.markdown("---")

    # Apply filters
    filtered_df = df.copy()

    # Keyword search first (across all columns)
    if search_term:
        filtered_df = search_across_columns(filtered_df, search_term)

    # Apply other filters
    if selected_genes:
        filtered_df = filtered_df[filtered_df["Gene"].isin(selected_genes)]

    if selected_conditions:
        filtered_df = filtered_df[filtered_df["Condition"].isin(selected_conditions)]

    if selected_parental_lines:
        filtered_df = filtered_df[filtered_df["Parental Line"].isin(selected_parental_lines)]

    # Store filtered dataframe in session state
    st.session_state["indi_filtered_df"] = filtered_df

    # Statistics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Cell Lines", len(filtered_df))

    with col2:
        unique_genes = filtered_df["Gene"].nunique() if "Gene" in filtered_df.columns else 0
        st.metric("Unique Genes", unique_genes)

    with col3:
        # Count non-zero, non-empty conditions
        if "Condition" in filtered_df.columns:
            unique_conditions = len([c for c in filtered_df["Condition"].unique()
                                   if c and str(c).strip() and str(c) != "0"])
        else:
            unique_conditions = 0
        st.metric("Unique Conditions", unique_conditions)

    with col4:
        unique_lines = filtered_df["Parental Line"].nunique() if "Parental Line" in filtered_df.columns else 0
        st.metric("Unique Parental Lines", unique_lines)

    # Display count
    st.info(f"Showing {len(filtered_df)} of {len(df)} cell lines")

    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Data Table",
        "📋 Browse Cell Lines",
        "🤖 AI Analysis",
        "📥 Export"
    ])

    # Tab 1: Data Table
    with tab1:
        st.subheader("Filterable Data Table")

        if filtered_df.empty:
            st.warning("No cell lines match the current filters.")
        else:
            # Prepare display dataframe with truncated long columns
            display_df = filtered_df.copy()

            # Truncate long text columns for display
            if 'About this gene' in display_df.columns:
                display_df['About this gene'] = display_df['About this gene'].apply(
                    lambda x: truncate_text(x, 150)
                )

            if 'About this variant' in display_df.columns:
                display_df['About this variant'] = display_df['About this variant'].apply(
                    lambda x: truncate_text(x, 150)
                )

            # Keep Procurement link as plain URL (Streamlit will auto-link it)
            if 'Procurement link' in display_df.columns:
                display_df['Procurement link'] = display_df['Procurement link'].apply(
                    lambda x: str(x) if x and str(x).strip() else ""
                )

            # Display dataframe
            st.dataframe(
                display_df,
                width="stretch",
                height=600
            )

            st.info("Note: Long text columns are truncated in the table view. Use the Browse tab to see full details.")

    # Tab 2: Browse Cell Lines
    with tab2:
        st.subheader("Cell Line Catalog")

        if filtered_df.empty:
            st.warning("No cell lines match the current filters.")
        else:
            # Display as expandable records
            for idx, row in filtered_df.iterrows():
                product_code = row.get('Product Code', 'Unknown')
                gene = row.get('Gene', 'N/A')
                variant = row.get('Gene Variant', 'N/A')
                condition = row.get('Condition', 'N/A')

                # Format condition display
                if condition == "0" or not condition or str(condition).strip() == "":
                    condition_display = "Control/Wildtype"
                else:
                    condition_display = condition

                with st.expander(f"**{product_code}** - {gene} {variant} ({condition_display})"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Product Code:** {product_code}")
                        st.markdown(f"**Gene:** {gene}")
                        st.markdown(f"**Gene Variant:** {variant}")
                        st.markdown(f"**Genotype:** {row.get('Genotype', 'N/A')}")
                        st.markdown(f"**dbSNP:** {row.get('dbSNP', 'N/A')}")
                        st.markdown(f"**Condition:** {condition_display}")

                    with col2:
                        st.markdown(f"**Parental Line:** {row.get('Parental Line', 'N/A')}")
                        st.markdown(f"**Other Names:** {row.get('Other Names', 'N/A')}")
                        st.markdown(f"**Genome Assembly:** {row.get('Genome Assembly', 'N/A')}")

                        # Procurement link - make clickable
                        procurement_link = row.get('Procurement link', '')
                        if procurement_link and str(procurement_link).strip():
                            st.markdown(f"**Procurement:** {procurement_link}")
                        else:
                            st.markdown(f"**Procurement:** N/A")

                    # Genomic information
                    st.markdown("---")
                    st.markdown("**Genomic Details:**")

                    protospacer = row.get('Protospacer Sequence', 'N/A')
                    st.markdown(f"- **Protospacer Sequence:** `{protospacer}`")

                    genomic_coord = row.get('Genomic Coordinate', 'N/A')
                    st.markdown(f"- **Genomic Coordinate:** {genomic_coord}")

                    genomic_seq = row.get('Genomic Sequence', 'N/A')
                    if genomic_seq and len(str(genomic_seq)) > 100:
                        st.markdown(f"- **Genomic Sequence:** `{truncate_text(genomic_seq, 100)}`")
                        with st.expander("View full sequence"):
                            st.code(genomic_seq, language="text")
                    else:
                        st.markdown(f"- **Genomic Sequence:** `{genomic_seq}`")

                    # About this gene - expandable
                    about_gene = row.get('About this gene', '')
                    if about_gene and str(about_gene).strip():
                        with st.expander("📖 About this gene"):
                            st.markdown(about_gene)

                    # About this variant - expandable
                    about_variant = row.get('About this variant', '')
                    if about_variant and str(about_variant).strip():
                        with st.expander("🧬 About this variant"):
                            st.markdown(about_variant)

    # Tab 3: AI Analysis
    with tab3:
        st.subheader("AI-Powered Cellular Models Analysis")

        st.markdown("""
        Use AI to analyze the filtered cellular models collection. The analysis includes:
        - **Disease & Gene Distribution**: Compare subset to full catalog
        - **Gene Function Analysis**: Insights from gene/variant descriptions
        - **Pathway & Interaction Analysis**: Biological pathways and protein interactions
        - **Publications of Interest**: Recent relevant research focused on neurodegeneration
        - **Utility for Functional & Precision Medicine**: CRISPR models and clinical insights
        """)

        if filtered_df.empty:
            st.warning("No cell lines to analyze. Please adjust filters.")
        else:
            col1, col2 = st.columns([1, 3])

            with col1:
                if st.button("🤖 Analyze Cellular Models", type="primary"):
                    # Store full df for comparison
                    full_df = st.session_state.get('original_indi_df', df)

                    # Run analysis
                    analysis_result = analyze_cellular_models(filtered_df, full_df)

                    if analysis_result:
                        st.session_state["indi_analysis_result"] = analysis_result
                        st.success("Analysis complete!")
                    else:
                        st.error("Analysis failed. Please check your API configuration.")

            with col2:
                st.info(f"Ready to analyze {len(filtered_df)} cell lines")

            # Display results
            if "indi_analysis_result" in st.session_state:
                st.markdown("---")
                st.markdown("### Analysis Results")

                analysis_text = st.session_state["indi_analysis_result"]
                st.markdown(analysis_text)

                # Download button
                st.download_button(
                    label="📥 Download Analysis Report",
                    data=analysis_text,
                    file_name=f"indi_cellular_models_analysis_{len(filtered_df)}_lines.txt",
                    mime="text/plain",
                    help="Download the AI analysis as a text file"
                )

    # Tab 4: Export
    with tab4:
        st.subheader("Export Cell Line Data")

        if filtered_df.empty:
            st.warning("No cell lines to export.")
        else:
            st.markdown(f"**Export {len(filtered_df)} filtered cell lines**")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Export as CSV")
                st.markdown("Export filtered cell line data as CSV file for use in spreadsheet applications.")

                st.download_button(
                    label="📥 Download CSV",
                    data=export_dataframe_csv(filtered_df),
                    file_name="indi_cell_lines_export.csv",
                    mime="text/csv",
                    help="Export filtered cell lines as CSV file"
                )

            with col2:
                st.markdown("#### Export as JSON")
                st.markdown("Export filtered cell line data as JSON file for programmatic access.")

                st.download_button(
                    label="📥 Download JSON",
                    data=export_dataframe_json(filtered_df),
                    file_name="indi_cell_lines_export.json",
                    mime="application/json",
                    help="Export filtered cell lines as JSON file"
                )

            # Summary statistics
            st.markdown("---")
            st.markdown("#### Export Summary")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**Genes in Export:**")
                gene_counts = filtered_df["Gene"].value_counts().head(10)
                for gene, count in gene_counts.items():
                    st.markdown(f"- {gene}: {count}")

            with col2:
                st.markdown("**Conditions in Export:**")
                condition_counts = filtered_df["Condition"].value_counts().head(10)
                for condition, count in condition_counts.items():
                    condition_display = "Control/Wildtype" if condition == "0" or not condition else condition
                    st.markdown(f"- {condition_display}: {count}")

            with col3:
                st.markdown("**Parental Lines in Export:**")
                line_counts = filtered_df["Parental Line"].value_counts().head(10)
                for line, count in line_counts.items():
                    st.markdown(f"- {line}: {count}")


if __name__ == "__main__":
    main()
