"""
Export per-query-method retrieval performance (candidates, adjudicated, confirmed,
precision, coverage, pooled recall, exclusive confirmed) to CSV/TSV/TXT for the paper,
plus the precision-vs-coverage bubble chart built from that same table.

Reuses staging/publication_glue.py::compute_query_method_performance() - the single
source of truth for the underlying numbers - rather than recomputing anything here.
That function only returns a DataFrame; the chart is built here.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# Add parent directory to path for imports (matches this dir's existing scripts)
sys.path.append(str(Path(__file__).parent.parent))

from staging.publication_glue import compute_query_method_performance, _REAL_VERDICTS

# Frozen source snapshot the published table/chart were generated from - override to
# re-run against a newer misc_publications hits file.
INPUT_PATH = Path(__file__).parent.parent / "tables" / "hits" / "misc_publications_20260819_154636.tsv"
OUTPUT_DIR = Path(__file__).parent / "v0.4"

# Display column order/labels matching the published table.
COLUMN_LABELS = {
    "method": "Method",
    "candidates": "Candidates",
    "adjudicated": "Adjudicated",
    "confirmed": "Confirmed",
    "precision_pct": "Precision",
    "resources_covered": "Resources covered",
    "resource_coverage_pct": "Coverage rate",
    "pooled_recall_pct": "Pooled recall",
    "exclusive_confirmed": "Exclusive confirmed",
}
# Row order matching the published table - kept explicit so re-runs against new data
# don't reorder silently.
METHOD_ORDER = ["paperclip", "v5", "v4", "v2", "original", "v3"]

# Bubble fill/stroke color matching the published chart's accent color.
ACCENT_COLOR = "#2a78d6"

# PubMed-only (title/abstract search, no PMC full text) results from a separate
# diagnostic experiment (docs/plans/paperclip/experiments/coverage_comparison_queries.ipynb,
# run ~2 weeks before this table). q1-q4 are that experiment's names for the same
# original(v1)/v2/v3/v4 query strategies plotted above (renamed since). These files
# originally had no verification (100% NaN Verification Status - the notebook covers
# recall/coverage only) but candidates against papers already seen elsewhere in the
# pipeline are ~99% cache hits (same (resource, doc_id, method) cache key regardless of
# which query surfaced them), so real verification was run on them - see the
# _verified.tsv siblings alongside each _full.tsv here - rather than assuming precision.
# Labels intentionally duplicate the main series' ("original"/"v2"/"v3"/"v4") - the
# legend, not the label text, distinguishes PubMed-only from the full pipeline.
PUBMED_ONLY_FILES = {
    "original": "q1_pubmed_full_verified.tsv",
    "v2": "q2_pubmed_full_verified.tsv",
    "v3": "q3_pubmed_full_verified.tsv",
    "v4": "q4_pubmed_full_verified.tsv",
}
PUBMED_ONLY_DIR = Path(__file__).parent.parent / "docs" / "plans" / "paperclip" / "experiments"
PUBMED_ONLY_COLOR = "#d9534f"


def compute_pubmed_only_performance(total_resources: int) -> pd.DataFrame:
    """Compute candidates/adjudicated/confirmed/precision/coverage for each PubMed-only
    experiment file, the same way compute_query_method_performance() does for the main
    table, since these live outside that function's normal (Fetched With-tagged) input.
    """
    rows = []
    for label, fname in PUBMED_ONLY_FILES.items():
        df = pd.read_csv(PUBMED_ONLY_DIR / fname, sep="\t", dtype=str).fillna("")
        adjudicated = df["Verification Status"].isin(_REAL_VERDICTS).sum()
        confirmed_df = df[df["Verification Status"] == "confirmed"]
        confirmed = len(confirmed_df)
        resources_covered = confirmed_df["Resource Name"].nunique()
        rows.append({
            "label": label,
            "candidates": len(df),
            "adjudicated": adjudicated,
            "confirmed": confirmed,
            "precision_pct": 100 * confirmed / adjudicated if adjudicated else 0,
            "resources_covered": resources_covered,
            "coverage_pct": 100 * resources_covered / total_resources,
        })
    return pd.DataFrame(rows)


def compute_performance(input_path: Path) -> tuple[pd.DataFrame, int]:
    """Load a misc_publications hits TSV and compute per-method performance.

    Args:
        input_path: Path to a misc_publications hits TSV (Fetched With + Verification
            Status columns required).

    Returns:
        (perf, total_resources) - perf has raw numeric columns (see
        compute_query_method_performance's docstring), in METHOD_ORDER row order;
        total_resources is the distinct resource count used for coverage-rate context.
    """
    print(f"Loading {input_path.name}...")
    df = pd.read_csv(input_path, sep="\t", dtype=str).fillna("")
    print(f"  {len(df)} rows loaded")

    print("Computing per-method performance...")
    perf = compute_query_method_performance(df)
    perf = perf.set_index("method").loc[METHOD_ORDER].reset_index()
    total_resources = df["Resource Name"].nunique()
    return perf, total_resources


def build_display_table(perf: pd.DataFrame) -> pd.DataFrame:
    """Format compute_performance()'s raw output into the published table's display form."""
    display = perf.copy()
    for col in ("precision_pct", "resource_coverage_pct", "pooled_recall_pct"):
        display[col] = display[col].map(lambda v: f"{v:.1f}%")
    return display.rename(columns=COLUMN_LABELS)[list(COLUMN_LABELS.values())]


def write_table(perf: pd.DataFrame) -> None:
    """Write the display table to CSV/TSV/TXT in OUTPUT_DIR."""
    table = build_display_table(perf)
    for suffix, sep in ((".csv", ","), (".tsv", "\t")):
        out_path = OUTPUT_DIR / f"query_method_performance{suffix}"
        table.to_csv(out_path, sep=sep, index=False)
        print(f"Wrote {out_path}")

    txt_path = OUTPUT_DIR / "query_method_performance.txt"
    txt_path.write_text(table.to_string(index=False))
    print(f"Wrote {txt_path}")


def write_chart(perf: pd.DataFrame, total_resources: int, pm_perf: pd.DataFrame) -> None:
    """Build and save the precision-vs-coverage bubble chart (PNG + PDF).

    Bubble area is proportional to confirmed hits, zero-anchored (a method with zero
    confirmed hits would have zero area) - matches the published chart's scale. Both
    series (main pipeline methods and PubMed-only) use real, verified precision/coverage
    - no assumed/placeholder values.
    """
    print("Building chart...")
    # Shared size scale across both series so bubble areas stay comparable.
    max_confirmed = max(perf["confirmed"].max(), pm_perf["confirmed"].max())
    sizes = 800 * (perf["confirmed"] / max_confirmed)
    pm_sizes = 800 * (pm_perf["confirmed"] / max_confirmed)

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(
        perf["precision_pct"], perf["resource_coverage_pct"],
        s=sizes, alpha=0.35, edgecolors=ACCENT_COLOR, facecolors=ACCENT_COLOR, linewidths=2,
        zorder=3,
    )
    ax.scatter(
        pm_perf["precision_pct"], pm_perf["coverage_pct"],
        s=pm_sizes, alpha=0.35, edgecolors=PUBMED_ONLY_COLOR, facecolors=PUBMED_ONLY_COLOR,
        linewidths=2, zorder=3,
    )

    # Every label sits just outside its own bubble with a leader line back to the
    # point, rather than centered inside - consistent treatment across all points, not
    # just the ones that happen to collide. Directions/distances are hand-tuned for
    # this dataset's specific layout.
    label_offsets = {
        "paperclip": (-38, 18),
        "v5": (0, 32),
        "v4": (38, 22),
        "v2": (-38, 22),
        "v3": (0, -32),
        "original": (0, -36),
    }
    for _, row in perf.iterrows():
        dx, dy = label_offsets[row["method"]]
        ax.annotate(
            row["method"], (row["precision_pct"], row["resource_coverage_pct"]),
            xytext=(dx, dy), textcoords="offset points",
            ha="center", va="center", fontsize=10, fontweight="bold",
            arrowprops=dict(arrowstyle="-", color="#888888", lw=0.8, shrinkA=0, shrinkB=4),
        )

    pm_label_offsets = {
        "original": (-8, 20),
        "v2": (8, -20),
        "v3": (0, -22),
        "v4": (27, 13),
    }
    for _, row in pm_perf.iterrows():
        dx, dy = pm_label_offsets[row["label"]]
        ax.annotate(
            row["label"], (row["precision_pct"], row["coverage_pct"]),
            xytext=(dx, dy), textcoords="offset points",
            ha="center", va="center", fontsize=9, fontweight="bold", color=PUBMED_ONLY_COLOR,
            arrowprops=dict(arrowstyle="-", color=PUBMED_ONLY_COLOR, lw=0.8, alpha=0.6, shrinkA=0, shrinkB=4),
        )

    ax.set_xlabel("Precision (confirmed / adjudicated)")
    ax.set_ylabel(f"Resource coverage rate (% of {total_resources} resources)")
    ax.set_title("Precision vs. resource coverage rate, sized by total confirmed hits")
    ax.grid(True, linestyle=":", linewidth=0.8, alpha=0.5)
    x_max = max(perf["precision_pct"].max(), pm_perf["precision_pct"].max())
    ax.set_xlim(0, max(x_max * 1.15, 60))
    ax.set_ylim(0, 100)
    # Two separate legends: color (source DB) at a fixed swatch size unrelated to any
    # real bubble, and bubble size (confirmed hits) as its own reference below it -
    # conflating the two in one legend would misrepresent color-swatch size as meaningful.
    color_handles = [
        ax.scatter([], [], s=110, alpha=0.35, edgecolors=ACCENT_COLOR, facecolors=ACCENT_COLOR,
                   linewidths=2, label="PMC"),
        ax.scatter([], [], s=110, alpha=0.35, edgecolors=PUBMED_ONLY_COLOR, facecolors=PUBMED_ONLY_COLOR,
                   linewidths=2, label="PM"),
    ]
    # Both legends sit fully outside the axes (right side, stacked), so neither
    # overlaps plotted data or each other.
    color_legend = ax.legend(
        handles=color_handles, title="Source DB", loc="upper left",
        bbox_to_anchor=(1.02, 1.0), fontsize=9, title_fontsize=9, framealpha=0.9,
    )
    ax.add_artist(color_legend)

    size_values = [500, 2000, 4000]
    size_handles = [
        ax.scatter([], [], s=800 * v / max_confirmed, alpha=0.35, edgecolors="#888888",
                   facecolors="none", linewidths=1.2, label=f"{v:,}")
        for v in size_values
    ]
    ax.legend(
        handles=size_handles, title="Confirmed hits", loc="upper left",
        bbox_to_anchor=(1.02, 0.62), fontsize=9, title_fontsize=9, framealpha=0.9,
        labelspacing=1.3,
    )

    png_path = OUTPUT_DIR / "query_method_performance_chart.png"
    plt.savefig(png_path, dpi=500, bbox_inches="tight", facecolor="white")
    print(f"Wrote {png_path}")

    pdf_path = OUTPUT_DIR / "query_method_performance_chart.pdf"
    plt.savefig(pdf_path, bbox_inches="tight", facecolor="white")
    print(f"Wrote {pdf_path}")

    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    perf, total_resources = compute_performance(INPUT_PATH)
    write_table(perf)
    pm_perf = compute_pubmed_only_performance(total_resources)
    write_chart(perf, total_resources, pm_perf)


if __name__ == "__main__":
    main()