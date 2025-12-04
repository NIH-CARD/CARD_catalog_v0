# CARD Catalog v0.1

## Overview

The **CARD Catalog** (Collaborative Alzheimer's and Related Dementias Data Catalog) is an interactive web application that brings together datasets, publications, code repositories, and cellular models for Alzheimer's Disease and Related Dementias (ADRD) research. Built on Streamlit and powered by Claude Sonnet 4.5, it enables researchers and program staff to discover resources, identify connections, and leverage AI-driven insights to accelerate research and inform funding decisions to cover programmatic gaps.

**What makes CARD Catalog unique:**
- **Unified Access**: Browse 99 datasets, 860 publications, 568 code repositories, and 626 iPSC cell lines in one place
- **Interactive Knowledge Graphs**: Visualize relationships between research resources based on shared features
- **AI-Powered Insights**: Generate comparative analyses, identify research gaps, and assess code quality using Claude Sonnet 4.5
- **FAIR Compliance Tracking**: Monitor and improve research reproducibility and best practices
- **Export Everything**: Download filtered data and analysis results in multiple formats

**What's New in v0.1:**
- ✨ **GNPC Dataset**: Global Neurodegeneration Proteomics Consortium with 35,000+ biofluid samples across 23 cohorts and 250+ million protein measurements
- 📊 **Table Views**: Interactive data tables with sorting and search on all main pages
- 🔍 **Coarse & Granular Data Types**: Filter by high-level categories or detailed modalities
- 🏷️ **Multi-Study Datasets**: 18 datasets tagged as Multi-study for easier filtering
- 🤖 **Claude Sonnet 4.5**: Latest AI model for enhanced analysis, synthesis and insights

## Capabilities by Page

### 📊 Datasets Page

Explore 99 neuroscience research datasets with comprehensive study-level metadata and relationship mapping.

**Features:**
- **Interactive table view** with sorting, filtering, and search across all columns
- **Knowledge graphs** showing dataset relationships based on shared diseases, data types, and other features
  - Drag-and-drop interactive nodes
  - FAIR compliance color-coding
  - Downloadable adjacency matrices for network analysis
- **AI-powered comparative analysis**: Compare filtered subsets to the full catalog to identify trends and gaps
- **Multi-level filtering**: Coarse and granular data type categories
- **Keyword search**: Fuzzy matching across all metadata fields
- **Export options**: CSV, TSV, JSON, or formatted text summaries

**Use cases:**
- Find datasets matching specific disease/modality combinations
- Discover related datasets through knowledge graph connections
- Compare FAIR compliance across different research areas
- Identify gaps in data coverage or code reproducability for specific research questions

### 📚 Publications Page

Search and analyze 860 recent scientific publications from PubMed Central linked to ADRD research datasets.

**Features:**
- **Interactive table view** with complete publication metadata
- **Fixed PMC links** and normalized author names for consistency
- **Knowledge graph with 8 connection types**: Study Name, Diseases, Data Types, Authors, Affiliations, Keywords, Abstract similarity
- **Data completeness tracking**: Visual indicators for PMC links, abstracts, keywords, and affiliations
- **AI-powered literature analysis**: Identify research themes, gaps, and funding opportunities
- **Publication statistics and trends**: Synthesis from AI-assistants
- **Multi-format export**: Download filtered publications with full metadata

**Use cases:**
- Find publications associated with specific datasets or diseases
- Discover collaborative networks through author/affiliation connections
- Identify literature gaps in specific research areas
- Track publication completeness and metadata quality for enhanced discoverability

### 💻 Code Repositories Page

Discover and evaluate 568 GitHub repositories with AI-generated summaries and quality assessments.

**Features:**
- **Interactive table view** with AI-generated repository summaries
- **Knowledge graph** with automatic stopword filtering for Languages, Data Types, Tooling, FAIR Issues, and Diseases
- **Code Deep Dive**: On-demand comprehensive quality analysis
  - Code cleanliness (organization, style, readability)
  - Documentation & completeness (README, tests, dependencies)
  - Usability & runnability (setup, configuration, reproducibility)
  - Average scores (1-10) for each dimension
  - Repository-specific recommendations
  - Single downloadable comprehensive report
- **FAIR compliance tracking**: Identify repositories missing READMEs, licenses, dependencies, or documentation
- **Creative search**: Fuzzy matching across code summaries, languages, and tooling
- **Repository statistics dashboard**: Rapid summarization of findings

**Use cases:**
- Find reusable code for specific analyses or data types to accelerate your research, why re-invent the wheel?
- Assess code quality before adopting methods
- Identify FAIR compliance gaps in research software
- Discover tools and frameworks used in ADRD research to enhance reproducability

### 🧬 Human Cellular Models Page

Browse 626 iNDI iPSC cell lines for neurodegenerative disease research.

**Features:**
- **Interactive table view** with comprehensive cell line information
- **Filter by gene, condition, and parental line**
- **Expandable details**: Gene variants, conditions, and procurement information
- **Procurement links** for ordering cell lines
- **AI Analysis**: Comprehensive cellular models insights
  - Disease & gene distribution comparisons
  - Gene function analysis from descriptions
  - Pathway & protein interaction predictions
  - **Publications of interest**: Clickable PubMed search links for recent literature (2020-2025) on specific genes and diseases
  - Utility assessments for functional genomics and precision medicine
  - Downloadable analysis reports
- **Statistics dashboard**: Rapid insight synthesis

**Use cases:**
- Find cell lines with specific genetic variants for experimental validation
- Identify appropriate model systems for disease mechanisms
- Connect cell models to relevant recent publications
- Assess cellular model utility for CRISPR studies or drug screening

### ℹ️ About Page

Complete documentation including:
- Data sources and collection methodology
- FAIR compliance principles and assessment criteria
- AI feature descriptions and limitations
- Setup and troubleshooting instructions
- Contact information and support resources

## User Stories

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

## Quick Start For Future Updates to the Tooling and Datasets

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup API Keys

The application requires an Anthropic API key for AI-powered features.

```bash
# Copy the template
cp .streamlit/secrets.toml.template .streamlit/secrets.toml

# Edit .streamlit/secrets.toml and add your API key:
# ANTHROPIC_API_KEY = "sk-ant-api03-..."
```

**Get an API key:** https://console.anthropic.com/

### 3. Run the Application

```bash
streamlit run app/Home.py
```

The app opens at http://localhost:8501

## Using the Application

### Filtering and Search
- Use **sidebar filters** on each page to narrow down data
- **Keyword search** works across all columns (case-insensitive, fuzzy matching)
- **Multiple selections** work as OR logic (match any)
- **Combine filters** for precise results

### Knowledge Graphs
- **Select features** to control which attributes create connections between items
- **Adjust minimum connections** threshold to reduce visual clutter
- **Hover over nodes** to see item details
- **Click and drag** nodes to rearrange the graph layout
- **Zoom and pan** to explore large graphs
- **Download adjacency matrix** for network analysis in external tools (R, Python, etc.)

### AI Features
- **Filter data first** to analyze specific subsets (saves tokens and improves relevance)
- **Click analyze button** to generate AI insights
- **Results persist** in your session until you analyze again
- **Requires Anthropic API key** configured in `.streamlit/secrets.toml`
- **Token limits** are checked before LLM calls to prevent errors

### Code Deep Dive
- **On-demand generation** (not pre-computed to save costs)
- May take time for many repositories
- Scores persist in session until page reload
- **Use responsibly** - API costs apply based on usage
- Results are downloadable as comprehensive text reports

### Exporting Data
- **All export buttons** work without page reload
- **Exports respect current filters** - only filtered data is exported
- **Choose format** based on your needs:
  - **CSV** - For Excel and spreadsheet applications
  - **TSV** - For tab-separated tools
  - **JSON** - For programmatic access and web applications
  - **Text Summary** - Human-readable formatted reports

### Performance Tips
- Data loads are cached (1 hour TTL) for faster subsequent access
- Use filters to reduce dataset size before generating knowledge graphs
- Clear cache using sidebar button if data seems stale
- Session state preserves your filters and analysis results

## Project Structure

```
CARD_catalog/
├── README.md                          # This file
├── QUICK_START.md                     # 5-minute quick start guide
├── SETUP_SECRETS.md                   # API key setup guide
├── requirements.txt                   # Python dependencies
├── .gitignore                         # Protects secrets
│
├── app/                               # Streamlit web application
│   ├── Home.py                        # Landing page
│   ├── config.py                      # Configuration and prompts
│   ├── pages/
│   │   ├── 1_Datasets.py             # Dataset browsing with KG and AI analysis
│   │   ├── 2_Publications.py         # Publication browsing with KG and AI analysis
│   │   ├── 3_Code.py                 # Code repository browsing with KG and AI analysis
│   │   ├── 5_Human_Cellular_Models.py
│   │   └── 6_About.py
│   ├── utils/
│   │   ├── data_loader.py            # Data loading and normalization
│   │   ├── graph_builder.py          # Knowledge graph generation
│   │   ├── llm_utils.py              # AI analysis functions
│   │   └── export_utils.py           # Export functionality
│   └── assets/
│       └── style.css                  # Custom styling
│
├── .streamlit/
│   ├── secrets.toml                   # Streamlit secrets (gitignored)
│   └── secrets.toml.template          # Template
│
├── tables/                            # Data tables
│   ├── dataset-inventory-*.tab       # Dataset inventories
│   ├── pubmed_central_*.tsv          # Publications data
│   ├── gits_to_reannotate_*.tsv      # Code repositories
│   └── iNDI_inventory_*.tab          # iNDI data
│
└── scrapers/                          # Data collection scrapers (gitignored)
    └── (excluded from repository)
```

## Data Collection (Advanced)

The `scrapers/` directory contains data collection scripts but is excluded from the repository. If you have local access and want to collect new data:

- **Publications scraper**: Queries PubMed Central API for publications linked to datasets
- **GitHub scraper**: Searches GitHub for biomedical research code with AI-powered analysis
- **FAIR compliance logging**: Automatically tracks repositories lacking proper documentation

See `scrapers/README.md` (if available locally) for detailed instructions.

**For most users:** The provided data files in `tables/` are sufficient - no scraping needed!

## FAIR Compliance Tracking

The CARD Catalog tracks FAIR (Findable, Accessible, Interoperable, Reusable) principles for datasets and code repositories.

### Compliance Levels

| Level | Keywords | Graph Color | Description |
|-------|----------|-------------|-------------|
| **Strong** | Strong, Excellent | Dark Green | Exemplary FAIR compliance with comprehensive standards |
| **Good** | Good | Medium Green | Solid FAIR compliance with established standards |
| **Moderate** | Moderate, Fair | Light Green | Adequate FAIR compliance with room for improvement |
| **Limited** | Limited, Poor, Weak | Yellow | Minimal FAIR compliance, significant gaps |

### In Knowledge Graphs
- **Node colors** indicate FAIR compliance level
- **Hover over nodes** to see full FAIR compliance notes
- **Color legend** shows the compliance scale

### Assessment Methodology
1. Automated checks for metadata completeness, accessibility, and standard formats
2. Manual review of documentation, licensing, and citation information
3. AI-assisted analysis to extract standardized compliance keywords

## Security

🔒 **API Key Protection:**
- All API keys must be stored in `.streamlit/secrets.toml` (gitignored, never committed)
- The `scrapers/` directory is excluded from the repository
- Template files show required format without exposing secrets

**For Streamlit Cloud deployment:**
1. Push code to GitHub (secrets are excluded automatically)
2. Connect repository to Streamlit Cloud
3. Add secrets via Streamlit Cloud UI (App Settings → Secrets)

## Requirements

```bash
pip install -r requirements.txt
```

**API Key Required:**
- Anthropic API Key (for AI-powered analysis features)

See [SETUP_SECRETS.md](SETUP_SECRETS.md) for detailed setup instructions.

## Documentation

- **[QUICK_START.md](QUICK_START.md)** - Get started in 5 minutes
- **[SETUP_SECRETS.md](SETUP_SECRETS.md)** - API key configuration guide
- **[STRUCTURE.md](STRUCTURE.md)** - Project organization details
- **About Page** (in app) - Comprehensive methodology and feature documentation

## Streamlit Cloud Deployment

1. Push repository to GitHub
2. Connect to Streamlit Cloud at https://streamlit.io/cloud
3. Set main file path: `app/Home.py`
4. Add secrets via App Settings → Secrets:
   ```toml
   ANTHROPIC_API_KEY = "your-key-here"
   ```
5. Deploy!

## Support

For questions or issues:
- **Quick Start**: See [QUICK_START.md](QUICK_START.md)
- **API Setup**: See [SETUP_SECRETS.md](SETUP_SECRETS.md)
- **In-App Documentation**: Visit the About page

## Acknowledgments

CARD Catalog is part of the **Center for Alzheimer's and Related Dementias (CARD at NIH)** initiative to improve data sharing and collaboration in dementia research.

**Additional support from:**
- Alzheimer's Disease Data Initiative (ADDI)
- DataTecnica team
- Workshop participants throughout 2024

**Data updates:** Quarterly scrapes ensure the catalog stays current with the latest research resources.

## Contact

Mike A. Nalls PhD via nallsm@nih.gov | mike@datatecnica.com | find us on GitHub.

## License

CARD Catalog is licensed under **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**.

- ✅ Free for academic, research, and non-profit use
- ✅ Share and adapt with attribution
- ❌ Commercial use prohibited without permission

See [LICENSE.md](LICENSE.md) for full details.

## Version

CARD Catalog v0.1 | Last Updated: December 3rd, 2025

**Powered by Claude Sonnet 4.5** for AI-driven insights and analysis.
