"""
Configuration and constants for CARD Catalog application.
Contains color schemes, paths, LLM prompts, and other settings.
"""

import os
from pathlib import Path

# Base paths
APP_DIR = Path(__file__).parent
PROJECT_DIR = APP_DIR.parent
TABLES_DIR = PROJECT_DIR / "tables"
LOGOS_DIR = PROJECT_DIR / "logos"
SCRAPERS_DIR = PROJECT_DIR / "scrapers"

# Color palette
COLORS = {
    "black": "#000000",
    "white": "#FFFFFF",
    "grey": "#808080",
    "mint": "#98FF98",
    "mint_light": "#D4FFD4",
    "mint_dark": "#7FE67F",
}

# Data file paths
DATA_FILES = {
    "datasets": "dataset-inventory-Dec_02_2025.tab",
    "code_repos": "gits_to_reannotate_completed_20251202_121816.tsv",
    "publications": "pubmed_central_20251128_124602.tsv",
    "indi": "iNDI_inventory_20250620_122423.tsv",
}

# FAIR compliance log pattern
FAIR_LOG_PATTERN = "fair_compliance_log_*.tsv"

# LLM Configuration
ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS_ANALYSIS = 4000
MAX_TOKENS_SCORING = 2000
TEMPERATURE = 0.7

# Token limits for safety
MAX_INPUT_TOKENS = 180000  # Leave buffer for response
MAX_GRAPH_NODES = 100  # Maximum nodes for KG generation

# LLM Prompts
PROMPTS = {
    "dataset_analysis": """You are analyzing a collection of neuroscience and brain disorder research datasets.

Dataset Information:
{dataset_info}

Based on these datasets, provide:
1. **Key Patterns & Trends**: Identify patterns across the collection
2. **Common Modalities & Diseases**: Most frequent data types and disease focuses
3. **Gaps & Opportunities**: Notable gaps in the dataset landscape
4. **Recommendations**: Actionable guidance for researchers

5. **Comparative Analysis** (if comparative context provided above):
   - How does this selection differ from the full catalog?
   - What makes this subset unique or specialized?
   - How does it align with current research trends in the field?

Keep your response concise, insightful, and actionable. Use bullet points and clear section headers.""",

    "knowledge_graph_summary": """You have a knowledge graph representing relationships between neuroscience datasets.

Graph Statistics:
- Number of datasets: {num_nodes}
- Number of connections: {num_edges}
- Connection drivers: {edge_types}

Top connected datasets:
{top_nodes}

Provide a detailed summary with these sections:
1. **Network Overview**: What the main clusters or groups represent
2. **Central Nodes**: Which datasets are most connected and why (mention specific connection strengths)
3. **Connection Drivers**: What features/characteristics are driving the connections (based on the connection drivers listed above)
4. **Notable Patterns**: Interesting patterns in how datasets relate to each other
5. **Comparative Insights** (if comparative context provided): How this graph compares to the full catalog

Use clear section headers and bullet points. Be specific about connection strengths and drivers.""",

    "publication_analysis": """You are analyzing a collection of scientific publications related to neuroscience and brain disorders.

Publication Information:
{publication_info}

IMPORTANT: Clearly distinguish in your analysis between:
- **THIS FILTERED SUBSET** (quantify with exact counts and percentages)
- **THE FULL CATALOG** (when comparative context provided)
- **GENERAL FIELD TRENDS** (broader research landscape)

Based on these publications, provide:

1. **Major Research Themes & Topics** (in THIS subset):
   - Specify: "In this subset of N publications..."
   - Quantify themes with percentages

2. **Most Active Research Areas** (in THIS subset vs full catalog):
   - Specify: "X% of this subset focuses on..."
   - Compare: "Compared to Y% in full catalog..."

3. **Authorship & Collaboration Trends** (THIS subset):
   - Quantify: "N unique authors", "Top institutions represent X%..."
   - Note if different from full catalog patterns

4. **Key Findings & Emerging Directions**:
   - Subset-specific: "These N publications show..."
   - Field context: "This aligns with/diverges from general trends in..."

5. **Research Gaps & Funding Opportunities**:
   - Identify underrepresented areas in THIS subset
   - Highlight programmatic gaps that could benefit from future funding
   - Suggest strategic research directions based on the data

Use exact numbers and percentages. Always clarify scope: "this subset", "the full catalog", or "general field trends".""",

    "code_cleanliness_score": """Analyze the following GitHub repository for code quality and cleanliness.

Repository: {repo_name}
Languages: {languages}
Summary: {summary}

Rate the repository on a scale of 1-10 for:
1. Code cleanliness (organization, style consistency, readability)

Provide ONLY a single number (1-10) for cleanliness score, no explanation.
If insufficient information, return "N/A".""",

    "code_completeness_score": """Analyze the following GitHub repository for completeness.

Repository: {repo_name}
Languages: {languages}
Summary: {summary}

Rate the repository on a scale of 1-10 for:
1. Completeness (documentation, tests, dependencies specified, examples)

Provide ONLY a single number (1-10) for completeness score, no explanation.
If insufficient information, return "N/A".""",

    "code_runnable_score": """Analyze the following GitHub repository for how easily it can be run out-of-the-box.

Repository: {repo_name}
Languages: {languages}
Summary: {summary}

Rate the repository on a scale of 1-10 for:
1. Run-out-of-box score (setup instructions, dependencies, configuration, ease of getting started)

Provide ONLY a single number (1-10) for runnable score, no explanation.
If insufficient information, return "N/A".""",

    "repository_analysis": """You are analyzing a collection of code repositories related to neuroscience and brain disorder research.

Repository Information:
{repository_info}

Based on these repositories, provide:

1. **Programming Languages & Technologies**: Most commonly used languages and frameworks
2. **Data Types & Research Focus**: Types of data processed and research domains
3. **Code Quality & FAIR Compliance**: Patterns in biomedical relevance, FAIR scores, and tooling maturity
4. **Collaboration & Reusability**: Insights into code sharing, documentation quality, and potential for reuse
5. **Gaps & Opportunities**: Underrepresented areas or technologies that could benefit from more development

6. **Comparative Analysis** (if comparative context provided above):
   - How does this selection differ from the full catalog?
   - What makes this subset unique in terms of technology or research focus?
   - How does it align with current trends in computational neuroscience?

Keep your response concise, insightful, and actionable. Use bullet points and clear section headers.""",

    "cellular_models_analysis": """You are analyzing a collection of human iPSC cellular models from the iNDI (iPSC Neurodegenerative Disease Initiative) collection.

Cellular Model Information:
{summary}

{comparison}

Provide a comprehensive analysis with the following sections:

## 1. Disease & Gene Distribution
- Quantify gene representation in this subset vs full catalog (if comparison provided)
- Identify most represented conditions/diseases
- Note any specialized disease focus in this subset
- Specify exact counts and percentages

## 2. Gene Function Analysis
- Based on the "About this gene" and "About this variant" information provided
- Summarize key biological functions and pathways represented
- Identify common disease mechanisms across the gene panel
- Highlight genes involved in neurodegeneration-specific processes (protein aggregation, neuronal function, synaptic activity, etc.)

## 3. Pathway & Interaction Analysis
- Analyze potential biological pathways represented by these genes
- Identify likely protein-protein interactions between genes in this panel
- Highlight pathway convergence points (genes that may interact or affect common pathways)
- Note any potential gaps in pathway coverage (missing key interactors)
- Focus on neurodegenerative disease mechanisms: protein homeostasis, mitochondrial function, synaptic function, inflammation, etc.

## 4. Publications of Interest
- For each key gene in this collection, provide:
  - Specific PubMed search query (e.g., "GENE_NAME[Title/Abstract] AND (Alzheimer OR neurodegeneration) AND (2020:2025[pdat])")
  - Direct PubMed search link: https://pubmed.ncbi.nlm.nih.gov/?term=YOUR_SEARCH_QUERY
  - Brief explanation of why this search is relevant
- Focus on: recent papers (2020-2025), neurodegenerative disease context, functional studies
- Highlight genes with emerging therapeutic relevance
- Format as clickable markdown links: [Search: GENE_NAME neurodegeneration 2020-2025](https://pubmed.ncbi.nlm.nih.gov/?term=...)

## 5. Utility for Functional & Precision Medicine
- **CRISPR Model Utility**: How these engineered lines enable functional studies of disease variants
- **Clinical Insights**: What patient-relevant biology can be studied with these models
- **Therapeutic Development**: Potential for drug screening, mechanism studies, and personalized medicine approaches
- **Comparative Advantage**: What makes this collection valuable vs other model systems

## 6. Comparative Analysis (if comparison context provided)
- How does this subset differ from the full catalog?
- What makes this selection unique or specialized?
- Are there focused research questions this subset is particularly suited for?

Be specific with gene names, disease mechanisms, and pathway details. Use exact counts and percentages. Focus on actionable insights for neurodegenerative disease research.""",
}

# Column mappings and aliases
DATASET_COLUMNS = {
    "Study Name": "study_name",
    "Abbreviation": "abbreviation",
    "Data Modalities": "data_modalities",
    "Diseases Included": "diseases",
    "Sample Size": "sample_size",
    "Access URL": "access_url",
    "FAIR Compliance Notes": "fair_notes",
    "Dataset Type": "dataset_type",
}

CODE_COLUMNS = {
    "Study Name": "study_name",
    "Abbreviation": "abbreviation",
    "Diseases Included": "diseases",
    "Repository Link": "repo_link",
    "Owner": "owner",
    "Contributors": "contributors",
    "Languages": "languages",
    "Biomedical Relevance": "biomedical_relevance",
    "Code Summary": "summary",
    "Data Types": "data_types",
    "Tooling": "tooling",
}

PUBLICATION_COLUMNS = {
    "Study Name": "study_name",
    "Abbreviation": "abbreviation",
    "Diseases Included": "diseases",
    "Data Modalities": "data_modalities",
    "PubMed Central Link": "pmc_link",
    "Authors": "authors",
    "Affiliations": "affiliations",
    "Title": "title",
    "Abstract": "abstract",
    "Keywords": "keywords",
}

# Fuzzy matching terms for deduplication
DATA_TYPE_GROUPS = {
    "Amyloid PET": ["Amyloid PET", "Amyloid-PET", "Amyloid_PET", "AmyloidPET"],
    "Tau PET": ["Tau PET", "Tau-PET", "Tau_PET", "TauPET"],
    "MRI": ["MRI", "Structural MRI", "sMRI", "T1-weighted MRI"],
    "fMRI": ["fMRI", "Functional MRI", "functional MRI", "resting-state fMRI", "rs-fMRI"],
    "DTI": ["DTI", "Diffusion Tensor Imaging", "diffusion MRI"],
    "Clinical": ["Clinical", "clinical assessments", "Clinical assessments"],
    "Cognitive": ["Cognitive", "cognitive testing", "Cognitive testing"],
    "Genetic": ["Genetic", "genetics", "Genomic", "genomics"],
    "Neuropathology": ["Neuropathology", "neuropathological"],
}

TOOLING_GROUPS = {
    "Python": ["Python", "python"],
    "R": ["R", "r"],
    "MATLAB": ["MATLAB", "Matlab", "matlab"],
    "C++": ["C++", "c++", "cpp"],
    "Java": ["Java", "java"],
    "JavaScript": ["JavaScript", "javascript", "JS", "js"],
    "Shell": ["Shell", "shell", "Bash", "bash"],
}

# Disease name normalization
DISEASE_ALIASES = {
    "Alzheimer's Disease": ["Alzheimer's Disease", "Alzheimers Disease", "AD", "Alzheimer"],
    "Parkinson's Disease": ["Parkinson's Disease", "Parkinsons Disease", "PD", "Parkinson"],
    "Multiple Sclerosis": ["Multiple Sclerosis", "MS"],
    "ALS": ["ALS", "Amyotrophic Lateral Sclerosis"],
    "Lewy Body Dementia": ["Lewy Body Dementia", "LBD", "Dementia with Lewy Bodies", "DLB"],
}

# Streamlit page configuration
PAGE_CONFIG = {
    "page_title": "CARD Catalog",
    "page_icon": "brain",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

# Graph visualization settings
GRAPH_LAYOUT_SETTINGS = {
    "k": 2.5,  # Optimal distance between nodes
    "iterations": 50,  # Layout iterations
    "scale": 1000,  # Scale factor
}

GRAPH_NODE_SETTINGS = {
    "node_size_min": 10,
    "node_size_max": 30,
    "node_opacity": 0.8,
}

GRAPH_EDGE_SETTINGS = {
    "edge_width_min": 0.5,
    "edge_width_max": 3,
    "edge_opacity": 0.3,
}

# Export settings
EXPORT_FORMATS = ["CSV", "TSV", "JSON", "Excel"]

# Session state keys
SESSION_KEYS = {
    "datasets_filtered": "datasets_filtered_df",
    "code_filtered": "code_filtered_df",
    "pubs_filtered": "pubs_filtered_df",
    "graph_data": "current_graph_data",
    "analysis_result": "llm_analysis_result",
}

# Help text
HELP_TEXT = {
    "fair_compliance": """
**FAIR Compliance** refers to how well a dataset or repository follows FAIR principles:
- **F**indable: Easy to find for both humans and computers
- **A**ccessible: Clear access conditions and procedures
- **I**nteroperable: Uses standard formats and vocabularies
- **R**eusable: Well-documented with clear licensing

Scores and notes are generated through automated checks and manual review.
""",
    "llm_generated": """
The following columns are generated using Large Language Models (LLMs):
- **Code Summary**: AI-generated description of repository purpose
- **Biomedical Relevance**: Assessment of relevance to biomedical research
- **Data Types**: Identified data types from repository content
- **Tooling**: Identified tools and frameworks used
- **Code Scores**: Cleanliness, completeness, and run-out-of-box ratings

These are meant to assist discovery but should be verified by users.
""",
    "knowledge_graph": """
**Knowledge Graphs** show relationships between datasets based on shared attributes:
- **Nodes**: Individual datasets
- **Edges**: Connections based on shared diseases, modalities, or other features
- **Node Size**: Indicates number of connections
- **Interactive**: Click and drag nodes, hover for details

Use feature selection to control which attributes create connections.
""",
}
