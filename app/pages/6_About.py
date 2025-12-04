"""
About page - Documentation and information about CARD Catalog.

Features:
- Data sources and methodology
- FAIR compliance explanation
- LLM-generated column documentation
- Usage guidelines
"""

import streamlit as st
from pathlib import Path
import sys

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from config import COLORS, HELP_TEXT, ANTHROPIC_MODEL, DATA_FILES

# Page config
st.set_page_config(
    page_title="About - CARD Catalog",
    page_icon="ℹ️",
    layout="wide"
)

# Load custom CSS
css_file = Path(__file__).parent.parent / "assets" / "style.css"
if css_file.exists():
    with open(css_file) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def main():
    """Main about page."""

    st.title("ℹ️ About CARD Catalog")

    # Introduction
    st.markdown(
        """
        ## Overview

        The **CARD Catalog** (Collaborative Alzheimer's and Related Dementias Data Catalog)
        is a comprehensive resource for discovering datasets, publications, and code repositories
        related to Alzheimer's Disease and Related Dementias (ADRD) research.

        Our mission is to improve data sharing, reproducibility, and collaboration in
        dementia research by providing a centralized, searchable catalog of research resources
        with quality assessments and relationship mapping.
        """
    )

    st.markdown("---")

    # User Stories
    st.markdown("## 👥 User Stories")

    st.markdown(
        """
        ### Story 1: Biomedical Researcher - From Hypothesis to Publication

        **Dr. Sarah Chen** is investigating the role of microglial dysfunction in early-stage Alzheimer's disease progression.

        **Discovery Phase:**
        1. **Datasets Page**: Sarah searches for datasets combining single-cell RNA-seq data with neuroimaging in Alzheimer's patients. The knowledge graph reveals three connected datasets she hadn't considered: ROSMAP, AMP-AD, and a newer spatial transcriptomics study.

        2. **AI Analysis**: She uses the AI-powered analysis to compare these datasets, identifying that ROSMAP has the most comprehensive microglial profiling, while the spatial study provides critical tissue context.

        **Methods Development:**
        3. **Code Repositories Page**: Sarah explores the Code page, filtering for single-cell analysis tools and microglial markers. The Code Deep Dive feature scores repositories on code quality and identifies two highly-rated pipelines with excellent documentation. She finds one specifically designed for microglial subtype classification.

        4. **FAIR Compliance Check**: Before committing to a pipeline, she checks FAIR compliance scores, ensuring the code has proper dependencies, versioning, and reproducible environments.

        **Literature Review:**
        5. **Publications Page**: Using the knowledge graph on the Publications page, Sarah connects datasets to their associated papers. She discovers a network of 12 publications linking microglial subtypes to Aβ plaque proximity, providing theoretical framework for her hypothesis.

        6. **Gap Analysis**: The AI analysis identifies that most publications focus on late-stage disease. This confirms her hypothesis about early-stage microglial dysfunction represents an understudied area with high impact potential.

        **Validation Planning:**
        7. **Cellular Models Page**: Sarah needs to validate findings experimentally. She searches for iPSC lines with APP or PSEN1 mutations. The AI analysis provides PubMed search links showing recent studies using these specific cell lines for microglial differentiation protocols.

        8. **Model Selection**: She identifies three cell lines with appropriate mutations and checks procurement links to order from repositories.

        **Outcome**: Sarah has discovered relevant datasets, adopted validated analysis code, grounded her work in existing literature, identified a novel research gap, and selected appropriate cellular models for validation—all within a single integrated platform. She exports her filtered datasets, code repositories, and publication lists to include in her grant proposal and methods section.

        ---

        ### Story 2: Program Officer - Portfolio Analysis and Strategic Planning

        **Dr. Michael Torres** is a program officer at a funding agency responsible for ADRD research portfolio management and identifying strategic investment opportunities.

        **Portfolio Assessment:**
        1. **Datasets Page**: Michael filters datasets by funding agency to see current portfolio coverage. The knowledge graph reveals strong investment in genomics and proteomics, but limited coverage of metabolomics and electrophysiology data types.

        2. **Gap Analysis**: Using AI-powered analysis, he compares his agency's funded datasets against the full catalog. The analysis quantifies that only 15% of agency-funded datasets include longitudinal imaging, compared to 35% in the broader field—a clear coverage gap.

        **FAIR Compliance Monitoring:**
        3. **Code Repositories Page**: Michael switches to the Code page to assess reproducibility across funded projects. The FAIR compliance dashboard shows that 40% of repositories lack proper dependency specifications, and 25% have no README files.

        4. **Best Practices Review**: The Code Deep Dive feature provides aggregate quality scores. He discovers that documentation completeness averages 6.2/10 across the portfolio—below the field average of 7.1/10. This indicates a need for enhanced reproducibility requirements in future funding calls.

        5. **Exemplar Identification**: The analysis highlights five repositories with exceptional FAIR compliance and usability scores. Michael bookmarks these as examples for future applicants.

        **Strategic Investment Opportunities:**
        6. **Publications Page**: Michael uses the Publications page to analyze research trends. The AI analysis identifies emerging themes: inflammasome activation, microbiome-gut-brain axis, and vascular contributions to dementia are growing rapidly but have limited dataset availability in his agency's portfolio.

        7. **Collaboration Networks**: The knowledge graph connected by author affiliations reveals that certain institutions are highly collaborative hubs, while others remain isolated. This informs his strategy for encouraging collaborative consortia.

        **Cell Model Resource Planning:**
        8. **Cellular Models Page**: Michael examines the iNDI collection to assess model system availability. The AI analysis shows that while APP and PSEN1 mutations are well-represented, TREM2 and APOE variants have fewer available lines despite growing research interest.

        9. **Publications of Interest**: The AI-generated PubMed links confirm increasing publication rates for TREM2 and APOE, validating the need for expanded cell line resources.

        **Decision Making:**
        10. **Synthesis**: Michael exports comprehensive reports:
            - Dataset gap analysis showing metabolomics and longitudinal imaging needs
            - FAIR compliance summary for portfolio review with agency leadership
            - Code quality benchmarks for updating funding requirements
            - Emerging research themes requiring new data collection initiatives
            - Cell model availability gaps for resource planning

        **Outcome**: Michael has quantified portfolio gaps in data coverage, identified reproducibility challenges requiring policy intervention, spotted emerging research areas for strategic investment, and gathered evidence-based insights for the next funding cycle—all derived from systematic analysis of integrated research resources with AI-powered synthesis.
        """
    )

    st.markdown("---")

    # Data Sources
    st.markdown("## 📊 Data Sources")

    st.markdown(
        """
        The CARD Catalog aggregates data from multiple sources:

        ### Datasets
        - **Source**: Curated inventory of neuroscience research datasets
        - **Content**: Study names, data modalities, diseases, sample sizes, access information
        - **Updates**: Regularly updated from institutional repositories and data sharing platforms

        ### Publications
        - **Source**: PubMed Central (PMC)
        - **Content**: Scientific articles, abstracts, author information, keywords
        - **Linking**: Automatically linked to associated datasets based on study names and metadata
        - **Updates**: Continuous scraping and indexing of new publications

        ### Code Repositories
        - **Source**: GitHub
        - **Content**: Research code, analysis pipelines, tools, and software
        - **Linking**: Associated with datasets and studies based on repository metadata
        - **Updates**: Regular scraping of biomedical research repositories

        ### Human Cellular Models
        - **Source**: iNDI (iPSC Neurodegenerative Disease Initiative)
        - **Content**: 626 iPSC cell lines for neurodegenerative disease research
        - **Information**: Gene variants, conditions, parental lines, procurement links
        - **AI Analysis**: Comprehensive cellular models analysis including:
          - Disease & gene distribution
          - Gene function and pathway analysis
          - Protein interaction predictions
          - **Recent publications of interest with clickable PubMed search links**
          - Functional & precision medicine utility
        - **Updates**: Synchronized with iNDI inventory releases
        """
    )

    st.markdown("---")

    # FAIR Compliance
    st.markdown("## ✅ FAIR Compliance Tracking")

    st.markdown(HELP_TEXT["fair_compliance"])

    st.markdown(
        """
        ### How FAIR Compliance is Tracked

        FAIR compliance is assessed through automated checks and manual review:

        #### Automated Checks
        - **README presence**: Does the repository have a README file?
        - **License information**: Is there a clear license specified?
        - **Documentation**: Are there docs or usage instructions?
        - **Dependencies**: Are dependencies clearly specified?
        - **Examples**: Are there usage examples or test data?

        #### FAIR Score Calculation
        - Score ranges from 0-10 (10 being perfect compliance)
        - Each issue identified reduces the score by 1 point
        - Repositories with no identified issues receive a perfect score of 10
        - Common issues tracked:
          - Missing README
          - No LICENSE file
          - Insufficient documentation
          - Unclear dependencies
          - No usage examples

        ### FAIR Compliance Logs
        All FAIR compliance checks are logged with timestamps and stored in the scrapers directory.
        These logs track:
        - Repository URL
        - Associated study
        - Issue type
        - Detailed description
        - Timestamp of assessment
        """
    )

    st.markdown("---")

    # LLM-Generated Content
    st.markdown("## 🤖 AI-Generated Content")

    st.markdown(HELP_TEXT["llm_generated"])

    st.markdown(
        f"""
        ### LLM Model Used
        - **Model**: {ANTHROPIC_MODEL}
        - **Provider**: Anthropic Claude

        ### Generated Fields

        #### Code Repositories
        1. **Code Summary**
           - AI-generated description of repository purpose and functionality
           - Based on README, file structure, and code content
           - Helps users quickly understand what the code does

        2. **Biomedical Relevance**
           - Assessment of whether the repository is relevant to biomedical research
           - Values: YES, NO, UNCLEAR
           - Helps filter out non-biomedical repositories

        3. **Data Types**
           - Identified types of data the code works with
           - Examples: MRI, genomics, clinical data, etc.
           - Extracted from code analysis and documentation

        4. **Tooling**
           - Identified tools, frameworks, and libraries used
           - Examples: TensorFlow, scikit-learn, FSL, etc.
           - Helps users find code using specific technologies

        5. **Code Deep Dive** (Optional, generated on-demand)
           - Comprehensive quality analysis covering three dimensions:
             - **Code Cleanliness**: Organization, structure, style consistency, readability
             - **Documentation & Completeness**: README quality, tests, dependencies, examples
             - **Usability & Runnability**: Setup instructions, configuration, ease of use
           - Provides detailed text analysis with:
             - Repository-specific findings with names and quantification
             - Average scores (1-10) for each dimension
             - Identification of exemplary repositories
             - Actionable recommendations for improvement
           - Single downloadable comprehensive report

        #### Dataset Analysis
        - AI-powered analysis of dataset collections
        - Identifies patterns, trends, and gaps
        - Provides recommendations for researchers

        #### Publication Analysis
        - AI-powered analysis of research literature
        - Identifies major themes and trends
        - Highlights key findings and directions

        #### Cellular Models Analysis
        - AI-powered analysis of iPSC cell line collections
        - Disease & gene distribution analysis
        - Pathway and protein interaction predictions
        - **Recent publication recommendations with clickable PubMed links**
          - Gene-specific search queries for recent literature (2020-2025)
          - Direct links to PubMed searches
          - Neurodegenerative disease context
        - Functional and precision medicine insights

        #### Knowledge Graph Summaries
        - AI interpretation of dataset relationship networks
        - Explains clusters and connection patterns
        - Identifies central and bridging datasets

        ### Important Notes
        - All AI-generated content should be verified by users
        - Scores and assessments are meant to assist discovery, not replace human judgment
        - LLM analysis may have limitations or biases
        - Always review original sources for critical decisions
        """
    )

    st.markdown("---")

    # Methodology
    st.markdown("## 🔬 Methodology")

    st.markdown(
        """
        ### Data Collection

        #### 1. Dataset Inventory
        - Manual curation from literature and data sharing platforms
        - Validation of access URLs and metadata
        - Regular updates to sample sizes and access information

        #### 2. Publication Scraping
        - Automated PubMed Central API queries
        - Search terms based on study names and diseases
        - Metadata extraction: authors, abstracts, keywords
        - URL normalization to fix duplicate PMC identifiers

        #### 3. Code Repository Scraping
        - GitHub API search using biomedical keywords
        - Repository metadata extraction
        - README and documentation parsing
        - LLM-based content analysis and categorization

        #### 4. FAIR Compliance Assessment
        - Automated repository structure analysis
        - Presence checks for key files (README, LICENSE, etc.)
        - Documentation quality assessment
        - Issue logging and score calculation

        ### Data Processing

        #### Normalization
        - **Author names**: Standardized to handle variations (e.g., "Mike Nalls" vs "Mike A Nalls")
        - **PMC links**: Fixed duplicate prefixes (PMCPMC → PMC)
        - **List fields**: Deduplicated and sorted (diseases, modalities, etc.)
        - **Data types/tooling**: Grouped similar terms for better searching

        #### Deduplication
        - Removal of duplicate entries within list fields
        - Fuzzy matching for similar terms
        - Preservation of unique information

        #### Linking
        - Datasets ↔ Publications: Linked by study name and diseases
        - Datasets ↔ Code: Linked by study name and data types
        - Code ↔ FAIR Compliance: Linked by repository URL

        ### Knowledge Graph Generation

        Knowledge graphs are built dynamically based on shared features:

        1. **Node Creation**: Each dataset becomes a node with all its attributes
        2. **Edge Creation**: Connections created when datasets share:
           - Diseases studied
           - Data modalities
           - Dataset type
           - Other selected features
        3. **Layout Calculation**: Spring layout algorithm for optimal positioning
        4. **Filtering**: Optional minimum connection threshold to reduce clutter
        5. **Interactivity**: Plotly-based visualization with drag, zoom, and hover

        ### Export Capabilities

        All data can be exported in multiple formats:
        - **CSV**: Comma-separated for spreadsheet applications
        - **TSV**: Tab-separated for some analysis tools
        - **JSON**: Structured format for programming
        - **Text**: Human-readable formatted summaries
        - **Adjacency Matrix**: Graph structure for network analysis
        """
    )

    st.markdown("---")

    # Usage Guidelines
    st.markdown("## 📖 Usage Guidelines")

    st.markdown(
        """
        ### Browsing and Filtering

        1. **Table View**: View filtered data in an interactive sortable table
        2. **Browse View**: Explore data as expandable cards with detailed information
        3. **Use the sidebar** on each page to filter by various criteria
        4. **Keyword search** works across all columns (case-insensitive, partial matching)
        5. **Multiple selections** in filters work as OR logic (match any)
        6. **Combine filters** for precise results

        ### Knowledge Graphs

        1. **Select features** to control which attributes create connections
        2. **Adjust minimum connections** to reduce visual clutter
        3. **Hover over nodes** to see dataset details
        4. **Click and drag** to rearrange the graph
        5. **Download adjacency matrix** for network analysis in other tools

        ### AI Analysis

        1. **Filter data first** to analyze specific subsets
        2. **Click analyze button** to generate AI insights
        3. **Results persist** until you analyze again
        4. **Token limits** may require truncating large datasets

        ### Code Deep Dive

        1. **Requires API key** (see setup below)
        2. **Comprehensive analysis** in single operation
        3. **Generates detailed text report** covering:
           - Code cleanliness patterns
           - Documentation & completeness trends
           - Usability & runnability assessment
           - Average scores and recommendations
        4. **Results persist** in session until page reload
        5. **Downloadable report** as single text file
        6. **Use responsibly** (API costs apply)

        ### Exporting Data

        1. **All export buttons** work without page reload
        2. **Export respects filters** (only filtered data is exported)
        3. **Choose format** based on your analysis tool
        4. **Text summaries** are human-readable reports
        """
    )

    st.markdown("---")

    # Setup and Configuration
    st.markdown("## ⚙️ Setup and Configuration")

    st.markdown(
        """
        ### API Key Setup (Required for AI Features)

        To use AI-powered features, you need to configure an Anthropic API key in `.streamlit/secrets.toml`:

        1. **Get an API key** from [Anthropic Console](https://console.anthropic.com/)
        2. **Configure locally:**
           ```bash
           # Copy the template
           cp .streamlit/secrets.toml.template .streamlit/secrets.toml

           # Edit .streamlit/secrets.toml and add your actual API key
           # ANTHROPIC_API_KEY = "sk-ant-api03-..."
           ```
        3. **For Streamlit Cloud deployment:**
           - Push your code to GitHub (secrets are automatically excluded)
           - Connect to Streamlit Cloud
           - Add secrets via App Settings → Secrets in the Streamlit Cloud UI

        **Important:** The `.streamlit/secrets.toml` file is protected by `.gitignore` and will never be committed to GitHub.

        ### Running the Application

        ```bash
        streamlit run app/Home.py
        ```

        ### Data Files Location

        The application expects data files in `tables/` directory (relative to project root).

        See the project README for the complete list of required data files and their locations.

        ### Repository Security

        The following are protected by `.gitignore` and will never be committed:
        - `.streamlit/secrets.toml` (your API keys)
        - `scrapers/` directory (data collection scripts)
        - `.env` files (environment variables)

        Template files (`.streamlit/secrets.toml.template`) are safe to commit and show the required format.
        """
    )

    st.markdown("---")

    # Technical Details
    st.markdown("## 🛠️ Technical Details")

    st.markdown(
        """
        ### Technology Stack

        - **Framework**: Streamlit (Python web framework)
        - **Data Processing**: Pandas
        - **Visualization**: Plotly (interactive graphs)
        - **Network Analysis**: NetworkX
        - **AI/LLM**: Anthropic Claude API
        - **Export**: CSV, JSON, Excel (openpyxl)

        ### Performance Optimizations

        - **Data caching**: All data loads are cached (1 hour TTL)
        - **Lazy loading**: AI features only run on demand
        - **No graph size limits**: Optimized graph builder handles full datasets
        - **Token checks**: Input size validation before LLM calls
        - **Session state**: Preserves analysis results and filters
        - **Unicode normalization**: NFKC normalization with apostrophe standardization
        - **Stopword filtering**: Automatic common word removal for knowledge graph text fields

        ### Project Structure

        ```
        CARD_catalog/
        ├── README.md                      # Project documentation
        ├── requirements.txt               # Python dependencies
        ├── .gitignore                     # Protects secrets
        │
        ├── app/                           # Streamlit application
        │   ├── Home.py                    # Main entry point
        │   ├── config.py                  # Configuration and prompts
        │   ├── pages/                     # Page modules
        │   │   ├── 1_Datasets.py
        │   │   ├── 2_Publications.py
        │   │   ├── 3_Code.py
        │   │   ├── 5_Human_Cellular_Models.py
        │   │   └── 6_About.py
        │   ├── utils/                     # Utility modules
        │   │   ├── data_loader.py
        │   │   ├── graph_builder.py
        │   │   ├── llm_utils.py
        │   │   └── export_utils.py
        │   └── assets/
        │       └── style.css
        │
        ├── .streamlit/
        │   ├── config.toml
        │   ├── secrets.toml               # Your API keys (gitignored)
        │   └── secrets.toml.template      # Template (safe to commit)
        │
        ├── tables/                        # Data files
        │   ├── dataset-inventory-*.tab
        │   ├── pubmed_central_*.tsv
        │   ├── gits_to_reannotate_*.tsv
        │   └── iNDI_inventory_*.tab
        │
        └── scrapers/                      # Data collection (gitignored)
            └── (excluded from repository)
        ```

        ### Color Scheme

        The CARD Catalog uses a minimal, professional color palette:
        - **Black** (#000000): Primary text and headers
        - **White** (#FFFFFF): Background
        - **Grey** (#808080): Secondary text and borders
        - **Mint** (#98FF98): Accent color and highlights

        Designed to work in both light and dark mode.
        """
    )

    st.markdown("---")

    # Contact and Support
    st.markdown("## 📧 Contact and Support")

    st.markdown(
        """
        ### Contact

        Mike A. Nalls PhD via nallsm@nih.gov | mike@datatecnica.com | find us on GitHub.

        ### Questions or Issues?

        For questions, issues, or contributions:
        - Check the project README for documentation
        - Review this About page for methodology details
        - Contact the CARD initiative for data-related questions

        ### Data Updates

        - Dataset inventory: Updated quarterly
        - Publications: Scraped monthly
        - Code repositories: Scraped monthly
        - FAIR compliance: Assessed with each code scrape

        ### Attribution

        When using data from the CARD Catalog, please cite:
        - Original dataset sources (see Access URLs)
        - Original publications (see PubMed Central links)
        - Original code repositories (see GitHub links)

        ### Acknowledgments

        The CARD Catalog is developed as part of the Center for Alzheimer's
        and Related Dementias (CARD) initiative to improve data sharing and
        collaboration in dementia research.
        """
    )

    st.markdown("---")

    # Footer
    st.markdown(
        f"""
        <div style='text-align: center; color: {COLORS["grey"]}; padding: 20px;'>
            <p><small>
                CARD Catalog | Version 0.1 | Last Updated: December 3rd, 2025<br>
                Features: Knowledge Graphs • AI Analysis • Code Deep Dive • FAIR Compliance Tracking
            </small></p>
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
