"""
Generate a reviewer-response figure: the FAIR Compliance rubric (Good /
Strong / Excellent), currently three paragraphs of prose in the manuscript,
reorganized into a comparison table by FAIR dimension so criteria across
tiers can be scanned side by side.

Content is a faithful reorganization of the manuscript's own criteria text
(no new criteria invented) - each tier's numbered points are grouped by the
dimension they address; a tier with no stated criterion for a dimension
shows an em dash, not an invented entry.
"""
import matplotlib.pyplot as plt
import textwrap
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "v0.4"

HEADERS = ["FAIR Dimension", "Good", "Strong", "Excellent"]

ROWS = [
    ("Access Mechanism",
     "Formal access request procedures with documented application processes",
     "Data sharing through established repositories with defined access procedures",
     "Mandatory open science policies requiring public deposition within specified timeframes; rapid sharing through multiple established platforms"),
    ("Metadata Documentation",
     "Basic metadata documentation describing core variables and study design",
     "Well-documented metadata schemas with defined data dictionaries",
     "Comprehensive standardized metadata schemas conforming to domain standards; extensive publicly accessible data dictionaries enabling secondary use"),
    ("Data Standardization",
     "Standard file formats enabling broad software compatibility",
     "Standardized data collection protocols ensuring consistency across sites/timepoints; adherence to community data standards for ≥ 1 major modality",
     "Builds on Strong; standardization spans the ecosystem integration below"),
    ("Governance & Analysis-Ready Resources",
     "—",
     "Frozen standardized analysis sets available to researchers; clear data governance documentation",
     "Builds on Strong's governance and analysis-set criteria"),
    ("Ecosystem Integration",
     "Explicitly lacking: no integration with broader data-sharing ecosystems across all data types",
     "Not addressed (limited to ≥ 1 modality, not full-ecosystem integration)",
     "Integration with established data ecosystems enabling cross-study harmonization"),
    ("User Support & Outreach",
     "—",
     "—",
     "Proactive outreach and user support facilitating data access"),
    ("Illustrative Character",
     "Functional data-sharing mechanism but limited metadata standards or single-platform access",
     "Robust infrastructure and metadata but lacking proactive open-science mandates",
     "Enforced data-sharing timelines; harmonized data models across multi-site studies; comprehensive data-use documentation"),
]

FOOTNOTE = (
    "Tiers are cumulative (Good → Strong → Excellent); criteria are drawn verbatim from the manuscript's FAIR Compliance Scoring rubric text.\n"
    "Ratings reflect point-in-time manual assessment (AI-assisted extraction, human-determined ratings) as of March 4, 2026, per publicly accessible\n"
    "documentation; synthetic data is rated one tier below equivalent actual participant-level data."
)

COL_WIDTHS = [0.16, 0.28, 0.28, 0.28]
WRAP_CHARS = [22, 40, 40, 40]


def wrap_cell(text, width):
    return "\n".join(textwrap.wrap(text, width=width)) if text != "—" else "—"


def main():
    fig_w = 17
    fig, ax = plt.subplots(figsize=(fig_w, 10.5))
    ax.axis("off")

    cell_text = []
    for row in ROWS:
        cell_text.append([wrap_cell(row[i], WRAP_CHARS[i]) for i in range(4)])

    table = ax.table(
        cellText=cell_text,
        colLabels=HEADERS,
        colWidths=COL_WIDTHS,
        cellLoc="left",
        loc="upper center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10.5)

    n_rows = len(ROWS) + 1
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#888888")
        cell.PAD = 0.015
        text_obj = cell.get_text()
        text_obj.set_wrap(True)
        if r == 0:
            cell.set_facecolor("#2c3e50")
            text_obj.set_color("white")
            text_obj.set_fontweight("bold")
            cell.set_height(0.055)
        else:
            cell.set_facecolor("#f7f7f7" if r % 2 == 0 else "white")
            if c == 0:
                text_obj.set_fontweight("bold")
            n_lines = cell_text[r - 1][c].count("\n") + 1
            cell.set_height(max(0.075, 0.028 * n_lines))

    fig.suptitle("FAIR Compliance Scoring Rubric by Tier", fontsize=15, fontweight="bold", y=0.97)

    fig.text(0.5, 0.035, FOOTNOTE, ha="center", va="bottom", fontsize=9, style="italic")

    output_file = OUTPUT_DIR / "fair_compliance_table.png"
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"Saved: {output_file}")
    plt.close()


if __name__ == "__main__":
    main()
