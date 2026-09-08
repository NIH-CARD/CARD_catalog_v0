"""
Generate Figure 1: CARD Catalog User Stories (ASCII Art)

Three panels:
A. User Story 1 - New Hire Onboarding (introductory; every number comes
   from an actual run against tables/final/, not an illustrative placeholder)
B. User Story 2 - Biomedical Researcher
C. User Story 3 - Program Officer

B and C converge on the same real blind spot from opposite directions, not
by design - it surfaced independently while verifying each panel: Panel B's
researcher finds that TREM2 (a major AD microglial risk gene) is studied
almost entirely after symptoms appear, not before; Panel C's program
officer finds that a peer funder (Gates Ventures) is doing the opposite -
concentrating specifically on presymptomatic/preclinical screening, at 6x
the catalog's baseline rate. Panel C's OUTCOME calls this out explicitly,
so the figure argues one coherent point (the field underweights the
preclinical/presymptomatic window) from two independent angles, rather than
reading as three unrelated anecdotes.
"""

def generate_workflow_panel():
    """Panel A: CARD Catalog Development Workflow"""
    workflow = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    PANEL A: CARD CATALOG DEVELOPMENT WORKFLOW                 ║
╚═══════════════════════════════════════════════════════════════════════════════╝

┌─────────────────┐         ┌─────────────────────┐         ┌──────────────────┐
│  DATA SOURCES   │         │  DATA COLLECTION    │         │   DATA CURATION  │
│                 │         │                     │         │                  │
│  • Datasets     │─────────│  • PubMed API       │─────────│  • Normalize     │
│  • Publications │         │  • GitHub API       │         │  • Validate      │
│  • Code Repos   │         │  • Manual curation  │         │  • Enrich        │
│  • Cell Lines   │         │  • AI Summarization │         │  • FAIR Assess   │
└─────────────────┘         └─────────────────────┘         └──────────────────┘
        │                            │                            │
        │                            │                            │
        ▼                            ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          STRUCTURED DATA TABLES                             │
│  • 99 Datasets  • 860 Publications  • 568 Code Repos  • 626 Cell Lines      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │
                                      ▼
        ┌─────────────────────────────────────────────────────────┐
        │            STREAMLIT WEB APPLICATION                    │
        │                                                         │
        │  ┌────────────┐  ┌────────────┐  ┌────────────┐         │
        │  │  BROWSE &  │  │ KNOWLEDGE  │  │  AI-POWERED│         │
        │  │   FILTER   │  │   GRAPHS   │  │  ANALYSIS  │         │
        │  │            │  │            │  │            │         │
        │  │ Interactive│  │ Visualize  │  │Claude 4.5  │         │
        │  │   Tables   │  │Connections │  │ Insights   │         │
        │  └────────────┘  └────────────┘  └────────────┘         │
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
    """Panel B: User Story 2 - Biomedical Researcher.

    Every number comes from an actual run against tables/final/ - see the
    HOW lines to reproduce each phase. Found via a 500-experiment screen
    (see the session's experiment-fork reports for the rejected alternatives:
    tautological gene x disease-stage results, a mis-tagged "Parkinson"
    organism entity, AD-genetics authors whose gene focus wasn't surprising,
    and a resource-mediated join-fanout artifact that had to be excluded and
    re-ranked around).

    Phase 3 was rewritten once already: the original fork's "Kampmann
    Martin, 13 papers" claim did not survive user reproduction in the app
    (his name doesn't appear in the top-15 authors of even the narrower,
    real 84-paper TREM2+Software subset) or a direct recount against
    tables/final/ (2 papers, not 13). Replaced with the MIBI-TOF spatial-
    proteomics finding, which the user verified directly in-app. The
    original Phase 4 (checking whether the method already covers her
    preclinical-AD angle) was folded into the OUTCOME instead, since a
    3-phase story was already carrying enough for one panel.
    """
    story = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║            PANEL B: USER STORY 2 - BIOMEDICAL RESEARCHER WORKFLOW             ║
║              Dr. Sarah Chen: From Hypothesis to Publication                   ║
╚═══════════════════════════════════════════════════════════════════════════════╝

RESEARCH QUESTION: Role of microglial dysfunction in early-stage Alzheimer's?

    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 1: DISCOVERY - IS THERE ACTUALLY A GAP?                      │
    │  HOW: Connections -> +Join SciLite Annotations (facet:              │
    │       Type=Gene_Proteins, Exact=TREM2) onto Publications -> +Join   │
    │       Resources (join key: Resource Name, facet: Diseases           │
    │       Included = Alzheimer's Disease or Preclinical AD) -> Freeze   │
    │       -> read the Scientific Read's own Contrastive section         │
    │                                                                     │
    │  219 AD/Preclinical-linked TREM2 papers - dominated by postmortem-  │
    │  tissue and genomics infrastructure (AMP-AD, ROS/MAP family, ADGC,  │
    │  ADSP). Swedish BioFINDER-2 - the catalog's 2nd-largest resource    │
    │  overall - doesn't even crack the top 15 here.                      │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 2: IS THIS TREM2-SPECIFIC, OR IS BIOFINDER RARE FOR EVERY    │
    │  GENE?                                                              │
    │  HOW: repeat the Phase 1 join for APOE -> compare                   │
    │                                                                     │
    │  Same query, same disease restriction, 1,254 APOE papers: BioFINDER-│
    │  2 IS the #1 resource here, at 9% of the subset. Same catalog, same │
    │  cohort - APOE uses it constantly, TREM2 doesn't use it at all.     │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 3: LOOKING FOR A METHOD, NOT JUST A GAP                      │
    │  HOW: same TREM2/AD papers -> +Join Software (join key:             │
    │       Publication) -> read the AI Read's "Notable Outliers"         │
    │                                                                     │
    │  2 papers (same tissue bank, overlapping author team) use MIBI-TOF  │
    │  spatial proteomics (Angelo lab's open-source toffy + ark-analysis) │
    │  to image TREM2 protein directly in postmortem microglia - seeing   │
    │  the receptor a GWAS/transcriptomics literature can only infer.     │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  OUTCOME (Dr. Chen): TREM2 showed the gap; these two papers showed  │
    │    a way to close it. My proposal isn't "build new infrastructure"  │
    │    - it's "borrow this pipeline, point it two years earlier."       │
    └─────────────────────────────────────────────────────────────────────┘
"""
    return story


def generate_program_officer_story():
    """Panel C: User Story 3 - Program Officer.

    Every number comes from an actual run against tables/final/ - see the
    HOW line to reproduce it. The original 500-experiment fork's picks
    (Zetterberg's cross-funder exposure, ASAP's infrastructure-funding
    pattern, the Swedish funders' BioFINDER concentration) were replaced:
    the Zetterberg grant-row counts (42/19/67/115) did not survive user
    reproduction in the app or a direct recount against tables/final/ under
    several reasonable interpretations (19-192 depending on method, never
    42) - same failure mode as Panel B's original Kampmann claim. Gates
    Ventures was found and verified live in-session instead: a single
    Connections query (Grants + Resources joined in one pass, not staged
    across phases) surfaces a 6x Preclinical-AD enrichment and a below-
    baseline transcriptomics rate, both confirmed independently against
    tables/final/.
    """
    story = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║          PANEL C: USER STORY 3 - PROGRAM OFFICER WORKFLOW                     ║
║         Dr. Michael Torres: Portfolio Analysis & Strategic Planning           ║
╚═══════════════════════════════════════════════════════════════════════════════╝

GOAL: A peer philanthropic funder just entered this space - a research
direction worth tracking, or a sign we're behind?

    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 1: WHAT IS GATES VENTURES ACTUALLY INTERESTED IN?            │
    │  HOW: Connections -> +Join Grants (facet: funder_name = Gates       │
    │       Ventures) -> +Join Resources (facet: Diseases Included =      │
    │       Alzheimer's Disease or Preclinical AD) -> Freeze -> AI Read   │
    │                                                                     │
    │  25 papers, all from 2025, zero NIH-style grant numbers (100%) - a  │
    │  private philanthropic initiative, not a federal program. The       │
    │  Preclinical AD tag appears 6x the catalog baseline (24% vs. 3.8%); │
    │  transcriptomics is LOWER than baseline (28% vs. 38%) despite       │
    │  genetics and proteomics both being elevated - a specific tilt      │
    │  toward fluid and digital biomarkers in presymptomatic populations, │
    │  not the postmortem-tissue transcriptomics that dominates the field.│
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  OUTCOME (Torres): Gates is interested in presymptomatic screening  │
    │    while the field's own baseline still leans postmortem-tissue     │
    │    transcriptomics - the same blind spot a researcher independently │
    │    found from the science side (Panel B).                           │
    │    Peer to track, sign we're behind? Our portfolio - unchecked      │
    └─────────────────────────────────────────────────────────────────────┘
"""
    return story


def generate_new_hire_story():
    """Panel A: User Story 1 - New Lab Hire (introductory story).

    Unlike Panels B/C, every number here comes from an actual run against
    tables/final/ - see the HOW lines to reproduce each phase. Phase 1 comes
    from a Connections freeze (Publications filtered to Resource Name =
    Religious Orders Study, 205 rows - was 211 before scripts/dedup_
    publications_preprints.py collapsed 6 preprint/published-version
    duplicate pairs out of the ROS subset) and its AI Read. Phase 2 mirrors
    the original GP2 story's own structure - +Join SciLite Annotations
    (facet Type=Gene_Proteins) on those same 205 papers, count per gene
    (Exact) - 157/205 tag >=1 gene; top raw Exact values are tau 105, APOE
    95, Aβ 70, APP 48, antibody 45, amyloid-β 37, antibodies 34, TDP-43 30,
    GFAP 28, apolipoprotein E 28, Tau 27, TREM2 26 (generic non-gene terms
    like "antibody"/"antibodies"/"transcription factor" and case/synonym
    fragments of the same entity - tau/Tau, Aβ/amyloid-β/amyloid beta -
    excluded from the panel's six-item summary; kept as the field's own
    canonical AD axis: tau, APOE, APP, TDP-43, GFAP, TREM2). Was previously
    the GP2/Jordan-Reyes-onboarding story; swapped to Religious Orders Study
    (ROS) - see the session's pasted Connections output for the source
    numbers.
    """
    story = """
╔═══════════════════════════════════════════════════════════════════════════════╗
║              PANEL A: USER STORY 1 - NEW HIRE ONBOARDING WORKFLOW             ║
║                     Jordan Reyes: Getting Oriented on ROS                     ║
╚═══════════════════════════════════════════════════════════════════════════════╝

GOAL: First week at a new lab - ROS comes up constantly. Figure out,
in plain terms, what it actually is, and how it fits the field's other
major post-mortem brain-bank studies.

    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 1: CRYSTALLIZE - WHAT IS ROS?                                │
    │  HOW: Publications -> filter Resource Name = Religious Orders       │
    │       Study -> Freeze -> AI Read                                    │
    │                                                                     │
    │  ┌────────────────┐                   ┌─────────────────────────┐   │
    │  │  Publications  │──────  > Freeze   │  205 papers - 58% also  │   │
    │  │      Page      │        (205 rows) │  tag Memory and Aging.  │   │
    │  │  5,086 papers  │                   │  Top co-resource: MAP.  │   │
    │  └────────────────┘                   └─────────────────────────┘   │
    │         │                                                           │
    │         └────── > Scientific Read ──────────────┘                   │
    │         ┌──────────────────────────────────┐                        │
    │         │  ROS and MAP are near-identical  │                        │
    │         │  sister cohorts - routinely      │                        │
    │         │  analyzed together as ROSMAP.    │                        │
    │         └──────────────────────────────────┘                        │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  PHASE 2: STRATIFY BY GENE (Scientific Read's next step B)          │
    │  HOW: Connections -> +Join SciLite Annotations on the 205 ROS       │
    │       papers (facet: Type=Gene_Proteins) -> count per gene (Exact)  │
    │                                                                     │
    │  ┌──────────────┐                   ┌───────────────────────────┐   │
    │  │  ROS papers  │──── > Join        │  157/205 papers tag a     │   │
    │  │  (205, from  │      by PMC ID    │  gene: tau 105 · APOE     │   │
    │  │   Phase 1)   │      (Gene facet) │  95 · APP 48 · TDP-43     │   │
    │  │              │                   │  30 · GFAP 28 · TREM2 26  │   │
    │  └──────────────┘                   └───────────────────────────┘   │
    └─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │  OUTCOME: ROS's gene/protein signal is the canonical AD molecular   │
    │    axis - tau and APOE lead, with APP, TDP-43, GFAP and TREM2       │
    │    close behind. The new hire now knows ROS reads as post-mortem    │
    │    neuropathology evidence, not a living-cohort biomarker signal.   │
    └─────────────────────────────────────────────────────────────────────┘
"""
    return story


def main():
    """Generate Figure 1 with all three panels."""
    print("Generating Figure 1: CARD Catalog Workflow and User Stories\n")

    # Generate all panels
    panel_a = generate_new_hire_story()
    panel_b = generate_researcher_story()
    panel_c = generate_program_officer_story()

    # Combine into single figure
    figure1 = f"""
{'='*80}
FIGURE 1: CARD CATALOG USER STORIES
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
