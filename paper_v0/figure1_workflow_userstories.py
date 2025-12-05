"""
Generate Figure 1: CARD Catalog Workflow and User Stories (ASCII Art)

Three panels:
1. Workflow - How the app was built
2. User Story 1 - Biomedical Researcher
3. User Story 2 - Program Officer
"""

def generate_workflow_panel():
    """Panel A: CARD Catalog Development Workflow"""
    workflow = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    PANEL A: CARD CATALOG DEVELOPMENT WORKFLOW                 ║
╚═══════════════════════════════════════════════════════════════════════════════╝

┌─────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│  DATA SOURCES   │         │  DATA COLLECTION │         │   DATA CURATION  │
│                 │         │                  │         │                  │
│  • Datasets     │─────────│  • PubMed API    │─────────│  • Normalize     │
│  • Publications │         │  • GitHub API    │         │  • Validate      │
│  • Code Repos   │         │  • Manual curation│         │  • Enrich        │
│  • Cell Lines   │         │  • AI Summarization│        │  • FAIR Assess   │
└─────────────────┘         └──────────────────┘         └──────────────────┘
        │                            │                            │
        │                            │                            │
        ▼                            ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          STRUCTURED DATA TABLES                             │
│  • 99 Datasets  • 860 Publications  • 568 Code Repos  • 626 Cell Lines     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │
                                      ▼
        ┌─────────────────────────────────────────────────────────┐
        │            STREAMLIT WEB APPLICATION                    │
        │                                                         │
        │  ┌────────────┐  ┌────────────┐  ┌────────────┐       │
        │  │  BROWSE &  │  │ KNOWLEDGE  │  │  AI-POWERED│       │
        │  │   FILTER   │  │   GRAPHS   │  │  ANALYSIS  │       │
        │  │            │  │            │  │            │       │
        │  │ Interactive│  │ Visualize  │  │Claude 4.5  │       │
        │  │   Tables   │  │Connections │  │ Insights   │       │
        │  └────────────┘  └────────────┘  └────────────┘       │
        └─────────────────────────────────────────────────────────┘
                                      │
                                      │
                                      ▼
        ┌─────────────────────────────────────────────────────────┐
        │                    END USERS                            │
        │                                                         │
        │  Researchers  •  Program Officers  •  Funders  •  PIs   │
        └─────────────────────────────────────────────────────────┘
"""
    return workflow


def generate_researcher_story():
    """Panel B: User Story 1 - Biomedical Researcher"""
    story = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║            PANEL B: USER STORY 1 - BIOMEDICAL RESEARCHER WORKFLOW             ║
║              Dr. Sarah Chen: From Hypothesis to Publication                   ║
╚═══════════════════════════════════════════════════════════════════════════════╝

RESEARCH QUESTION: Role of microglial dysfunction in early-stage Alzheimer's?

    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 1: DISCOVERY                                                 │
    │                                                                     │
    │  ┌──────────────┐                  ┌─────────────────────────┐    │
    │  │   Datasets   │────── > Filter   │  • ROSMAP               │    │
    │  │     Page     │        by        │  • AMP-AD               │    │
    │  │              │     scRNA-seq +  │  • Spatial Trans Study  │    │
    │  │ 99 datasets  │     Neuroimaging │                         │    │
    │  └──────────────┘                  └─────────────────────────┘    │
    │         │                                      │                    │
    │         └────── > Knowledge Graph ──────────────┘                    │
    │                  Shows connections                                  │
    │         ┌────────────────────────────────────────┐                 │
    │         │  AI Analysis: ROSMAP has best          │                 │
    │         │  microglial profiling vs spatial study │                 │
    │         └────────────────────────────────────────┘                 │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 2: METHODS DEVELOPMENT                                       │
    │                                                                     │
    │  ┌──────────────┐                  ┌─────────────────────────┐    │
    │  │     Code     │────── > Filter   │  • High FAIR Score      │    │
    │  │     Page     │        scRNA-seq │  • Good Documentation   │    │
    │  │              │        + microglial│  • Microglial subtype │    │
    │  │ 568 repos    │        markers    │    classification      │    │
    │  └──────────────┘                  └─────────────────────────┘    │
    │         │                                      │                    │
    │         └────── > Deep Dive Quality ───────────┘                    │
    │                  Assessment Scores                                  │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 3: LITERATURE REVIEW                                         │
    │                                                                     │
    │  ┌──────────────┐                  ┌─────────────────────────┐    │
    │  │Publications  │────── > Knowledge │  12 papers linking      │    │
    │  │     Page     │        Graph by  │  microglial subtypes to │    │
    │  │              │        Authors   │  Aβ plaque proximity    │    │
    │  │ 860 papers   │      + Datasets  │                         │    │
    │  └──────────────┘                  └─────────────────────────┘    │
    │         │                                      │                    │
    │         └────── > AI Gap Analysis ──────────────┘                    │
    │                  "Early-stage understudied"                         │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 4: VALIDATION PLANNING                                       │
    │                                                                     │
    │  ┌──────────────┐                  ┌─────────────────────────┐    │
    │  │ Cell Models  │────── > Filter   │  • APP mutation lines   │    │
    │  │     Page     │        APP/PSEN1 │  • PSEN1 mutation lines │    │
    │  │              │        mutations  │  • PubMed links for     │    │
    │  │ 626 lines    │                  │    differentiation      │    │
    │  └──────────────┘                  └─────────────────────────┘    │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  OUTCOME: Complete grant proposal with datasets, methods,        │
    │    literature review, identified research gap, and validation plan  │
    └─────────────────────────────────────────────────────────────────────┘
"""
    return story


def generate_program_officer_story():
    """Panel C: User Story 2 - Program Officer"""
    story = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║          PANEL C: USER STORY 2 - PROGRAM OFFICER WORKFLOW                     ║
║         Dr. Michael Torres: Portfolio Analysis & Strategic Planning           ║
╚═══════════════════════════════════════════════════════════════════════════════╝

GOAL: Assess portfolio gaps and identify strategic investment opportunities

    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 1: PORTFOLIO ASSESSMENT                                      │
    │                                                                     │
    │  ┌──────────────┐                  ┌─────────────────────────┐    │
    │  │   Datasets   │────── > Filter   │  Agency's 30 datasets   │    │
    │  │     Page     │        by Funding│  vs 99 total            │    │
    │  │              │        Agency    │                         │    │
    │  │ 99 datasets  │                  └─────────────────────────┘    │
    │  └──────────────┘                             │                    │
    │         │                                      │                    │
    │         └────── > Knowledge Graph Analysis ────┘                    │
    │                  Strong in genomics/proteomics                      │
    │                  Limited metabolomics/electrophysiology             │
    │         ┌────────────────────────────────────────┐                 │
    │         │  AI Gap Analysis:                      │                 │
    │         │  • Only 15% have longitudinal imaging  │                 │
    │         │  • Field average: 35%                  │                 │
    │         └────────────────────────────────────────┘                 │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 2: FAIR COMPLIANCE MONITORING                                │
    │                                                                     │
    │  ┌──────────────┐                  ┌─────────────────────────┐    │
    │  │     Code     │────── > Filter   │  Portfolio Issues:      │    │
    │  │     Page     │        by Funded │  • 40% missing deps     │    │
    │  │              │        Projects  │  • 25% no README        │    │
    │  │ 568 repos    │                  │  • Avg quality: 6.2/10  │    │
    │  └──────────────┘                  │  • Field avg: 7.1/10    │    │
    │         │                           └─────────────────────────┘    │
    │         └────── > Deep Dive on All Portfolio Repos                  │
    │                  Identify 5 exemplar repositories                   │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 3: STRATEGIC INVESTMENT OPPORTUNITIES                        │
    │                                                                     │
    │  ┌──────────────┐                  ┌─────────────────────────┐    │
    │  │Publications  │────── > AI Trend  │  Emerging themes:       │    │
    │  │     Page     │        Analysis  │  • Inflammasome         │    │
    │  │              │                  │  • Gut-brain axis       │    │
    │  │ 860 papers   │                  │  • Vascular dementia    │    │
    │  └──────────────┘                  └─────────────────────────┘    │
    │         │                                      │                    │
    │         └────── > Author Network Analysis ──────┘                    │
    │                  Identify collaborative hubs vs isolated groups     │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 4: RESOURCE PLANNING                                         │
    │                                                                     │
    │  ┌──────────────┐                  ┌─────────────────────────┐    │
    │  │ Cell Models  │────── > AI       │  Gaps identified:       │    │
    │  │     Page     │        Analysis  │  • TREM2 variants needed│    │
    │  │              │        + PubMed  │  • APOE variants limited│    │
    │  │ 626 lines    │        Links     │  • Growing pub interest │    │
    │  └──────────────┘                  └─────────────────────────┘    │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  OUTCOME: Comprehensive reports exported                         │
    │    • Dataset coverage gaps (metabolomics, longitudinal imaging)     │
    │    • FAIR compliance needs (updated funding requirements)           │
    │    • Code quality benchmarks for policy updates                     │
    │    • Emerging research themes for strategic funding                 │
    │    • Cell line resource gaps for infrastructure planning            │
    └─────────────────────────────────────────────────────────────────────┘
"""
    return story


def main():
    """Generate Figure 1 with all three panels."""
    print("Generating Figure 1: CARD Catalog Workflow and User Stories\n")

    # Generate all panels
    panel_a = generate_workflow_panel()
    panel_b = generate_researcher_story()
    panel_c = generate_program_officer_story()

    # Combine into single figure
    figure1 = f"""
{'='*80}
FIGURE 1: CARD CATALOG WORKFLOW AND USER STORIES
{'='*80}

{panel_a}

{panel_b}

{panel_c}

{'='*80}
"""

    # Save to file
    output_file = "paper_v0/figure1_workflow_userstories.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(figure1)

    print(f"Figure 1 saved to: {output_file}\n")
    print(figure1)


if __name__ == "__main__":
    main()
