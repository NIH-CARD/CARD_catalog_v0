"""
Renders build_fair_doi_agreement.py's three FAIR-level x DOI-coverage
cross-tabs (Cited Datasets only, Software Mentions only, Combined) as one
reviewer-response figure - the inter-rater agreement check originally shared
as a plain-text table in Slack, now with the Software Mentions source added
and a proper figure for the paper.

Run from anywhere in the repo (regenerates the underlying counts first):
    python3 paper_v0/figure_fair_doi_agreement_table.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from build_fair_doi_agreement import (
    DATA_DIR,
    cross_tab,
    pmc_to_resources,
    resources_with_doi,
    DATASET_DOI_FIELDS,
    SOFTWARE_DOI_FIELDS,
)

OUTPUT_DIR = Path(__file__).parent / "v0.4"

HEADER_COLOR = "#2c3e50"
ROW_ALT_COLOR = "#f7f7f7"
EDGE_COLOR = "#888888"

FOOTNOTE = (
    "Primary-citation dataset mentions and software mentions are joined to their resource via source_url's PMC ID -> Publications' PubMed Central\n"
    "Link -> Publications' Resource Name (web/src/lib/connectionsGraph.ts's own join). \"With DOI\" flags a resource if any such mention contains a\n"
    "DOI-shaped string in a free-text field - a permissive coverage proxy, not a strict per-mention attribution check. Software Mentions has no\n"
    "citation_type field (Primary/Secondary) like Datasets does, so every software mention row is counted. See build_fair_doi_agreement.py."
)


def build_views() -> dict[str, pd.DataFrame]:
    resources = pd.read_csv(DATA_DIR / "resources.tsv", sep="\t", dtype=str).fillna("")
    pubs = pd.read_csv(DATA_DIR / "publications.tsv", sep="\t", dtype=str).fillna("")
    datasets = pd.read_csv(DATA_DIR / "pub_datasets.tsv", sep="\t", dtype=str).fillna("")
    software = pd.read_csv(DATA_DIR / "pub_software.tsv", sep="\t", dtype=str).fillna("")

    pmc_map = pmc_to_resources(pubs)
    primary_datasets = datasets[datasets["citation_type"].str.strip().str.lower() == "primary"]
    dataset_doi = resources_with_doi(primary_datasets, DATASET_DOI_FIELDS, pmc_map)
    software_doi = resources_with_doi(software, SOFTWARE_DOI_FIELDS, pmc_map)
    combined_doi = dataset_doi | software_doi

    return {
        "Cited Datasets only": cross_tab(resources, dataset_doi),
        "Software Mentions only": cross_tab(resources, software_doi),
        "Combined (Cited Datasets OR Software Mentions)": cross_tab(resources, combined_doi),
    }


def draw_table(ax, df: pd.DataFrame, title: str):
    ax.axis("off")
    ax.set_title(title, fontsize=12, fontweight="bold", loc="left", pad=6)

    cell_text = [
        [str(v) if c != "% With DOI" else f"{v:.1f}%" for c, v in zip(df.columns, row)]
        for row in df.itertuples(index=False)
    ]
    table = ax.table(
        cellText=cell_text,
        colLabels=list(df.columns),
        cellLoc="center",
        colWidths=[0.22, 0.19, 0.22, 0.15, 0.22],
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10.5)
    table.scale(1, 1.6)

    n_rows = len(df) + 1
    is_total_row = len(df) - 1
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor(EDGE_COLOR)
        if r == 0:
            cell.set_facecolor(HEADER_COLOR)
            cell.get_text().set_color("white")
            cell.get_text().set_fontweight("bold")
        else:
            data_row = r - 1
            if data_row == is_total_row:
                cell.set_facecolor("#e8eef3")
                cell.get_text().set_fontweight("bold")
            else:
                cell.set_facecolor(ROW_ALT_COLOR if data_row % 2 == 0 else "white")
            if c == 0:
                cell.get_text().set_fontweight("bold")


def main():
    views = build_views()

    fig, axes = plt.subplots(3, 1, figsize=(9, 8.5))
    for ax, (title, df) in zip(axes, views.items()):
        draw_table(ax, df, title)

    fig.suptitle(
        "FAIR Compliance Level vs. DOI Coverage (Inter-Rater Agreement Check)",
        fontsize=15, fontweight="bold", y=0.985,
    )
    fig.text(0.5, 0.01, FOOTNOTE, ha="center", va="bottom", fontsize=7.5, style="italic")
    fig.subplots_adjust(hspace=0.55, top=0.90, bottom=0.14)

    output_file = OUTPUT_DIR / "fair_doi_agreement_table.png"
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"Saved: {output_file}")
    plt.close()


if __name__ == "__main__":
    main()
