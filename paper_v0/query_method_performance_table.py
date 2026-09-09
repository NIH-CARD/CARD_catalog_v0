"""
Export per-query-method retrieval performance (candidates, adjudicated, confirmed,
precision, coverage, pooled recall, exclusive confirmed) to CSV/TSV/TXT for the paper,
plus the precision-vs-coverage bubble chart built from that same table.

Reuses staging/publication_glue.py::compute_query_method_performance() - the single
source of truth for the underlying numbers - rather than recomputing anything here.
That function only returns a DataFrame; the chart is built here.
"""

import sys
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# Add parent directory to path for imports (matches this dir's existing scripts)
sys.path.append(str(Path(__file__).parent.parent))

from staging.publication_glue import compute_query_method_performance, _REAL_VERDICTS

# Frozen source snapshot the published table/chart were generated from - override to
# re-run against a newer misc_publications hits file. Bumped to the 0824 hits file to
# add page_navigation as a tracked method (see _TAGGED_METHOD_RE in
# staging/validate_fetched_publications.py) - the 0819 snapshot predates that fix and
# would bucket every page_navigation row as "other" (silently excluded below).
INPUT_PATH = Path(__file__).parent.parent / "tables" / "hits" / "misc_publications_20260824_080447.tsv"
OUTPUT_DIR = Path(__file__).parent / "v0.4"

# Display column order/labels matching the published table. Raw "candidates" (every
# surfaced pair, including ones that never got a real verdict at all) is dropped in
# favor of "adjudicated" alone, relabeled "Candidates (non-null)" - the count that
# actually matters for Precision's denominator, without a separate raw-candidates
# column implying a comparison that isn't the one being made here.
COLUMN_LABELS = {
    "method": "Method",
    "adjudicated": "Candidates (non-null)",
    "confirmed": "Confirmed",
    "precision_pct": "Precision",
    "resources_covered": "Resources covered",
    "resource_coverage_pct": "Coverage rate",
    "pooled_recall_pct": "Pooled recall",
    "exclusive_confirmed": "Exclusive confirmed",
}
# Row order matching the published table - kept explicit so re-runs against new data
# don't reorder silently.
METHOD_ORDER = ["paperclip", "v5", "v4", "v2", "original", "v3", "page navigation"]

# Bubble fill/stroke color matching the published chart's accent color.
ACCENT_COLOR = "#2a78d6"

# paperclip and page navigation aren't PMC-query-string variants like v2-v5/
# original - paperclip searches across pmc/biorxiv/medrxiv/arxiv/trials/
# patents/proteins, and page navigation crawls a resource's own public site
# directly - so both get their own "open web" color rather than being lumped
# in with the PMC-query series they otherwise share an axis with.
OPEN_WEB_COLOR = "#3d9a4f"
OPEN_WEB_METHODS = {"paperclip", "page navigation"}

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


# DB abbreviations matching the chart's own legend (PubMed Central / PubMed / Misc),
# just shortened to PMC/PM for the table's second index level.
DB_PMC = "PubMed Central"
DB_PM = "PubMed"
DB_MISC = "Miscellaneous"


def build_combined_performance(perf: pd.DataFrame, pm_perf: pd.DataFrame) -> pd.DataFrame:
    """Interleave each main method's row with its PubMed-only counterpart (if any),
    grouped by method - this is every point the bubble chart actually plots (PMC/Misc
    from `perf`, PM from `pm_perf`), which build_display_table's old perf-only input
    silently omitted (the PubMed-only q1-q4 points never made it into the table,
    only the chart).

    Returns:
        Raw (unformatted) rows with a "method" and "db" column, PM rows carrying NaN
        for pooled_recall_pct/exclusive_confirmed (not computed for that series - see
        compute_pubmed_only_performance's docstring).
    """
    pm_by_method = {row["label"]: row for _, row in pm_perf.iterrows()}
    rows = []
    for _, row in perf.iterrows():
        method = row["method"]
        db = DB_MISC if method in OPEN_WEB_METHODS else DB_PMC
        rows.append({**row.to_dict(), "db": db})
        pm_row = pm_by_method.get(method)
        if pm_row is not None:
            rows.append({
                "method": method, "db": DB_PM,
                "candidates": pm_row["candidates"], "adjudicated": pm_row["adjudicated"],
                "confirmed": pm_row["confirmed"], "precision_pct": pm_row["precision_pct"],
                "resources_covered": pm_row["resources_covered"],
                "resource_coverage_pct": pm_row["coverage_pct"],
                "pooled_recall_pct": float("nan"), "exclusive_confirmed": float("nan"),
            })
    return pd.DataFrame(rows)


def build_display_table(combined: pd.DataFrame) -> pd.DataFrame:
    """Format build_combined_performance()'s raw output into the published table's
    display form, indexed by (Method, DB) - a true two-level index, not just an extra
    flat column, so a method's PMC/PM rows visually group under one Method label."""
    display = combined.copy()
    for col in ("precision_pct", "resource_coverage_pct", "pooled_recall_pct"):
        display[col] = display[col].map(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
    display["exclusive_confirmed"] = display["exclusive_confirmed"].map(
        lambda v: "—" if pd.isna(v) else str(int(v))
    )
    display = display.rename(columns=COLUMN_LABELS).rename(columns={"db": "DB"})
    ordered_cols = ["Method", "DB"] + [v for k, v in COLUMN_LABELS.items() if k != "method"]
    return display[ordered_cols].set_index(["Method", "DB"])


def write_table(combined: pd.DataFrame) -> None:
    """Write the display table to CSV/TSV/TXT in OUTPUT_DIR."""
    table = build_display_table(combined)
    for suffix, sep in ((".csv", ","), (".tsv", "\t")):
        out_path = OUTPUT_DIR / f"query_method_performance{suffix}"
        table.to_csv(out_path, sep=sep)
        print(f"Wrote {out_path}")

    txt_path = OUTPUT_DIR / "query_method_performance.txt"
    txt_path.write_text(table.to_string())
    print(f"Wrote {txt_path}")

    write_table_latex(table)


def write_table_latex(table: pd.DataFrame) -> None:
    """Write a booktabs/multirow LaTeX table (the (Method, DB) two-level index
    rendered as \\multirow-spanned Method cells, not a flat repeated-label CSV) to
    OUTPUT_DIR/query_method_performance.tex - a \\input{}-able snippet, not a full
    document. Requires \\usepackage{booktabs,multirow} in the including document's
    preamble."""
    latex = table.to_latex(
        multirow=True, escape=True,
        caption="Query method performance by source database (PMC = PubMed Central "
                "full text, PM = PubMed title/abstract only, Miscellaneous = paperclip/"
                "page navigation). See figure legend for column definitions.",
        label="tab:query_method_performance",
        position="htbp",
    )
    tex_path = OUTPUT_DIR / "query_method_performance.tex"
    tex_path.write_text(
        "% Requires \\usepackage{booktabs,multirow} in the including document.\n" + latex
    )
    print(f"Wrote {tex_path}")


# Method, DB, then the 7 metric columns - DB needs enough room for "PubMed Central",
# the longest value in that column; sums to 1.0.
TABLE_IMAGE_COL_WIDTHS = [0.12, 0.14] + [0.74 / 7] * 7


def write_table_image(combined: pd.DataFrame) -> None:
    """Render the display table as a styled PNG/PDF, matching this paper's other
    figure_*_table.py house style (dark header row, alternating row shading). The
    (Method, DB) two-level index is flattened into two plain columns for matplotlib's
    table artist, with Method left blank on a group's second row (its PM row directly
    below its PMC/Misc row) - the same "don't repeat the group label" convention
    pandas' own MultiIndex to_string() uses, applied here since matplotlib's table
    doesn't understand a MultiIndex directly."""
    print("Building table image...")
    table_df = build_display_table(combined).reset_index()
    # Method/DB headers are short enough as-is; the metric headers ("Candidates
    # (non-null)", "Resources covered", "Exclusive confirmed", ...) are wider than
    # their column at this font size, so wrap those onto two lines rather than
    # letting them overflow into the neighboring cell.
    headers = [
        h if h in ("Method", "DB") else "\n".join(textwrap.wrap(h, width=13))
        for h in table_df.columns
    ]

    cell_text = []
    last_method = None
    for _, row in table_df.iterrows():
        method = row["Method"]
        display_method = "" if method == last_method else method
        last_method = method
        cell_text.append([display_method] + list(row.drop("Method")))

    fig, ax = plt.subplots(figsize=(15, 0.55 * (len(cell_text) + 1) + 0.8))
    ax.axis("off")

    table = ax.table(
        cellText=cell_text,
        colLabels=headers,
        colWidths=TABLE_IMAGE_COL_WIDTHS,
        cellLoc="center",
        loc="upper center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10.5)

    n_rows = len(cell_text) + 1
    # Every header cell shares one row height (driven by the tallest wrapped label),
    # not its own line count - mixing heights within one header row left the
    # single-line headers ("Method", "Confirmed", ...) looking sunken below the
    # two-line ones.
    header_height = 0.14 * (max(h.count("\n") for h in headers) + 1)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#888888")
        cell.PAD = 0.02
        text_obj = cell.get_text()
        if r == 0:
            cell.set_facecolor("#2c3e50")
            text_obj.set_color("white")
            text_obj.set_fontweight("bold")
            text_obj.set_fontsize(9.5)
            cell.set_height(header_height)
        else:
            # Group rows (a method's PMC + PM pair) share one shade so the grouping
            # reads visually even with the blanked repeat label.
            group_idx = sum(1 for cr in cell_text[:r] if cr[0] != "")
            cell.set_facecolor("#f7f7f7" if group_idx % 2 == 0 else "white")
            if c == 0:
                text_obj.set_fontweight("bold")
                cell.set_text_props(ha="left")
            cell.set_height(0.14)

    fig.suptitle("Query Method Performance", fontsize=14, fontweight="bold", y=0.98)

    png_path = OUTPUT_DIR / "query_method_performance_table.png"
    plt.savefig(png_path, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"Wrote {png_path}")

    pdf_path = OUTPUT_DIR / "query_method_performance_table.pdf"
    plt.savefig(pdf_path, bbox_inches="tight", facecolor="white")
    print(f"Wrote {pdf_path}")

    plt.close(fig)


def write_chart(perf: pd.DataFrame, total_resources: int, pm_perf: pd.DataFrame) -> None:
    """Build and save the precision-vs-coverage bubble chart (PNG + PDF).

    Bubble area is proportional to confirmed hits, zero-anchored (a method with zero
    confirmed hits would have zero area) - matches the published chart's scale. Both
    series (main pipeline methods and PubMed-only) use real, verified precision/coverage
    - no assumed/placeholder values.
    """
    print("Building chart...")
    # Shared size scale across all series so bubble areas stay comparable.
    max_confirmed = max(perf["confirmed"].max(), pm_perf["confirmed"].max())

    is_open_web = perf["method"].isin(OPEN_WEB_METHODS)
    perf_pmc = perf[~is_open_web]
    perf_open_web = perf[is_open_web]

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(
        perf_pmc["precision_pct"], perf_pmc["resource_coverage_pct"],
        s=800 * (perf_pmc["confirmed"] / max_confirmed), alpha=0.35,
        edgecolors=ACCENT_COLOR, facecolors=ACCENT_COLOR, linewidths=2,
        zorder=3,
    )
    ax.scatter(
        perf_open_web["precision_pct"], perf_open_web["resource_coverage_pct"],
        s=800 * (perf_open_web["confirmed"] / max_confirmed), alpha=0.35,
        edgecolors=OPEN_WEB_COLOR, facecolors=OPEN_WEB_COLOR, linewidths=2,
        zorder=3,
    )
    ax.scatter(
        pm_perf["precision_pct"], pm_perf["coverage_pct"],
        s=800 * (pm_perf["confirmed"] / max_confirmed), alpha=0.35,
        edgecolors=PUBMED_ONLY_COLOR, facecolors=PUBMED_ONLY_COLOR,
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
        "page navigation": (0, 28),
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
                   linewidths=2, label="PubMed Central"),
        ax.scatter([], [], s=110, alpha=0.35, edgecolors=PUBMED_ONLY_COLOR, facecolors=PUBMED_ONLY_COLOR,
                   linewidths=2, label="PubMed"),
        ax.scatter([], [], s=110, alpha=0.35, edgecolors=OPEN_WEB_COLOR, facecolors=OPEN_WEB_COLOR,
                   linewidths=2, label="Miscellaneous"),
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
    # Invisible trailing entry (no marker, empty label) purely to push the
    # legend box's bottom edge further down - it occupies a row's worth of
    # space without being seen or shifting the three real entries above it.
    size_handles.append(ax.scatter([], [], s=0, facecolors="none", edgecolors="none", label=" "))
    size_legend = ax.legend(
        handles=size_handles, title="Confirmed hits", loc="upper left",
        bbox_to_anchor=(1.02, 0.62), fontsize=9, title_fontsize=9, framealpha=0.9,
        labelspacing=2.2,
    )

    # bbox_inches="tight" doesn't reliably measure a legend re-added via
    # ax.add_artist() (color_legend here) unless it's listed explicitly -
    # without this, wider labels like "PubMed Central" get clipped at the
    # figure edge instead of the canvas expanding to fit them.
    extra_artists = (color_legend, size_legend)

    png_path = OUTPUT_DIR / "query_method_performance_chart.png"
    plt.savefig(png_path, dpi=500, bbox_inches="tight", bbox_extra_artists=extra_artists, facecolor="white")
    print(f"Wrote {png_path}")

    pdf_path = OUTPUT_DIR / "query_method_performance_chart.pdf"
    plt.savefig(pdf_path, bbox_inches="tight", bbox_extra_artists=extra_artists, facecolor="white")
    print(f"Wrote {pdf_path}")

    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    perf, total_resources = compute_performance(INPUT_PATH)
    pm_perf = compute_pubmed_only_performance(total_resources)
    combined = build_combined_performance(perf, pm_perf)
    write_table(combined)
    write_table_image(combined)
    write_chart(perf, total_resources, pm_perf)


if __name__ == "__main__":
    main()