"""
CARD Catalog - Collaborative Alzheimer's and Related Dementias Data Catalog

Main entry point for the Streamlit application.
This is a minimal landing page that routes to other pages.
"""

import streamlit as st
from pathlib import Path
import sys

# Add utils to path
sys.path.append(str(Path(__file__).parent))
from config import PAGE_CONFIG, COLORS, LOGOS_DIR

# Configure page
page_config = PAGE_CONFIG.copy()
page_config["page_title"] = "Welcome - CARD Catalog"
st.set_page_config(**page_config)

# Load custom CSS
css_file = Path(__file__).parent / "assets" / "style.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def main():
    """Main landing page."""

    # Sidebar controls
    with st.sidebar:
        st.markdown("### App Controls")
        if st.button("🔄 Restart App", help="Restart the Streamlit application"):
            st.rerun()
        if st.button("🗑️ Clear Cache", help="Clear cached data and reload"):
            st.cache_data.clear()
            st.rerun()

    # Logos at top
    st.markdown("<div style='text-align: center;'><h4>Supported By</h4></div>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        addi_logo = LOGOS_DIR / "ADDI.png"
        if addi_logo.exists():
            st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
            st.image(str(addi_logo), width=200)
            st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        card_logo = LOGOS_DIR / "card_logo.png"
        if card_logo.exists():
            st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
            st.image(str(card_logo), width=300)
            st.markdown("</div>", unsafe_allow_html=True)

    with col3:
        dt_logo = LOGOS_DIR / "stacked_DT.png"
        if dt_logo.exists():
            st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
            st.image(str(dt_logo), width=200)
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # Header with centered logo removed (now at top)
    # col1, col2, col3 = st.columns([1, 2, 1])

    # with col2:
    #     logo_path = LOGOS_DIR / "card_logo.png"
    #     if logo_path.exists():
    #         st.image(str(logo_path), use_container_width=True)

    st.markdown(
        f"""
        <div style='text-align: center; padding: 20px;'>
            <h1 style='color: {COLORS["black"]}; margin-bottom: 10px;'>
                CARD Catalog
            </h1>
            <h3 style='color: {COLORS["grey"]}; font-weight: normal; margin-top: 0;'>
                Collaborative Alzheimer's and Related Dementias Data Catalog
            </h3>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("---")

    # Introduction
    st.markdown(
        """
        ### Welcome to CARD Catalog

        A comprehensive catalog of datasets, publications, code repositories, and cellular models
        related to Alzheimer's Disease and Related Dementias (ADRD) research.

        **Powered by Claude Sonnet 4.5** for AI-driven insights and analysis.

        #### Features:

        - **📊 Datasets**: Browse 99 neuroscience research datasets with interactive
          knowledge graphs, coarse and granular data type filtering, and AI-powered analysis
        - **📚 Publications**: Search 860 scientific publications from PubMed Central
          (within 3 years of dataset updates) with normalized author names and fixed PMC links
        - **💻 Code**: Discover 568 GitHub repositories with AI-powered quality scoring
          (cleanliness, completeness, runnability) and FAIR compliance tracking
        - **🧬 Human Cellular Models**: Browse 626 iNDI iPSC cell lines for neurodegenerative
          disease research with detailed genotype and procurement information
        - **ℹ️ About**: Learn about our data sources, methodology, FAIR compliance tracking,
          and Claude Sonnet 4.5 AI features

        #### What's New:

        - ✨ **GNPC Update**: Global Neurodegeneration Proteomics Consortium with 35,000+ biofluid
          samples across 23 cohorts and 250+ million protein measurements
        - 📊 **Table Views**: Interactive data tables with sorting and search on all main pages
        - 🔍 **Coarse & Granular Data Types**: Filter by high-level categories or detailed modalities
        - 🏷️ **Multi-Study Datasets**: 18 datasets now tagged as Multi-study for easier filtering
        - 🤖 **Claude Sonnet 4.5**: Upgraded AI model for better analysis and insights

        #### Getting Started:

        Use the sidebar navigation to explore different sections of the catalog.
        Each section includes powerful filtering, keyword search, table views, and export capabilities.
        """
    )

    st.markdown("---")

    # Statistics overview
    col1, col2, col3, col4 = st.columns(4)

    try:
        from utils.data_loader import load_datasets, load_publications, load_code_repos, load_indi_inventory

        datasets_df = load_datasets()
        pubs_df = load_publications()
        code_df = load_code_repos()
        indi_df = load_indi_inventory()

        with col1:
            st.metric(
                label="Datasets",
                value=len(datasets_df),
                help="Total number of neuroscience datasets cataloged"
            )

        with col2:
            st.metric(
                label="Publications",
                value=len(pubs_df),
                help="Total number of scientific publications indexed"
            )

        with col3:
            st.metric(
                label="Code Repositories",
                value=len(code_df),
                help="Total number of GitHub repositories cataloged"
            )

        with col4:
            st.metric(
                label="Cell Lines",
                value=len(indi_df),
                help="Total number of iNDI iPSC cell lines available"
            )

    except Exception as e:
        st.error(f"Error loading data statistics: {e}")

    st.markdown("---")

    # Footer
    st.markdown(
        f"""
        <div style='text-align: center; color: {COLORS["grey"]}; padding: 20px;'>
            <p>
                CARD Catalog is part of the Center for Alzheimer's and Related Dementias (CARD)
                initiative to improve data sharing and collaboration in dementia research. Additional support from great collaborators such as the Alzheimer's Disease Data Initiative (ADDI), DataTecnica teammates and all the amazing workshop participants we interacted with in 2025.
            </p>
            <p style='font-size: 0.9em;'>
                Data sourced from multiple repositories and regularly updated (quarterly scrapes).
                See the About page for details on data collection and processing.
            </p>
            <p style='font-size: 0.9em;'>
                <strong>Contact:</strong> Mike A. Nalls PhD via nallsm@nih.gov | mike@datatecnica.com.  
                Find us on GitHub @ https://github.com/NIH-CARD for additional details on this project.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )



if __name__ == "__main__":
    main()
