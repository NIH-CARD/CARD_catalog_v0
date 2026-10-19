"""
Generate Figure 7: the FAIR Compliance Assessment Scoring Rubric (Good / Strong /
Excellent), one numbered criterion per row, as submitted - with the cells that had
been split mid-sentence restored from the manuscript's rubric text (see
figure_fair_compliance_table.py for the same criteria grouped by FAIR dimension).

Writes paper_v0/v0.4/figure7_fair_rubric.{png,pdf} and FAIR_Compliance_Rubric.xlsx.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT_DIR = Path(__file__).parent / "v0.4"

HEADERS = ["Criteria #", "Good", "Strong", "Excellent"]
ROWS = [
    ("1",
     "Data available through formal access request procedures with documented application process",
     "Standardized data collection protocols ensuring consistency across sites and timepoints",
     "Mandatory open science policies requiring public data deposition within specified timeframes"),
    ("2",
     "Basic metadata documentation describing core variables and study design",
     "Well-documented metadata schemas with defined data dictionaries",
     "Rapid data sharing through multiple established platforms"),
    ("3",
     "Standard file formats enabling broad software compatibility, but lacking comprehensive standardization across all data types",
     "Data sharing through established repositories with defined access procedures",
     "Comprehensive standardized metadata schemas conforming to domain standards"),
    ("4",
     "—",
     "Adherence to community data standards for at least one major data modality",
     "Integration with established data ecosystems enabling cross-study harmonization"),
    ("5",
     "—",
     "Frozen standardized analysis sets available to researchers",
     "Extensive publicly accessible data dictionaries and documentation enabling secondary use"),
    ("6",
     "—",
     "Clear data governance documentation",
     "Proactive outreach and user support facilitating data access"),
    ("Category Description",
     "Includes resources with functional data sharing mechanisms but limited metadata standards or restricted to single-platform access.",
     "Includes resources with robust infrastructure and metadata but lacking proactive open science mandates.",
     "Examples include resources with enforced data sharing timelines, harmonized data models across multi-site studies, and comprehensive data use documentation."),
]



FONT_SIZE = 8.5            # pt; journal optimum is 8 pt at print size
COL_WIDTHS_PT = [78, 132, 132, 138]  # 480 pt ≈ 6.7 in, fits A4 page width
PAD_X, PAD_Y = 7, 6        # pt of padding inside each cell
LINE_HEIGHT = FONT_SIZE * 1.4


def save_figure() -> None:
    # Laid out by hand (not ax.table) so padding and line spacing are explicit: text is
    # wrapped by its measured width and each row is sized to its tallest cell.
    from matplotlib.font_manager import FontProperties
    from matplotlib.patches import Rectangle

    plt.rcParams["font.family"] = ["Arial", "Helvetica", "DejaVu Sans"]
    regular = FontProperties(size=FONT_SIZE)
    bold = FontProperties(size=FONT_SIZE, weight="bold")
    fig = plt.figure(dpi=72)  # 1 px = 1 pt while measuring
    renderer = fig.canvas.get_renderer()

    def text_width(s, prop):
        return renderer.get_text_width_height_descent(s, prop, ismath=False)[0]

    def wrap(text, max_width, prop):
        lines, current = [], ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if current and text_width(candidate, prop) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        return lines + [current]

    grid = [HEADERS] + [list(row) for row in ROWS]
    props = [[bold if r == 0 or c == 0 else regular for c in range(len(HEADERS))] for r in range(len(grid))]
    wrapped = [[wrap(v, w - 2 * PAD_X, props[r][c]) for c, (v, w) in enumerate(zip(row, COL_WIDTHS_PT))]
               for r, row in enumerate(grid)]
    heights = [max(len(cell) for cell in row) * LINE_HEIGHT + 2 * PAD_Y for row in wrapped]
    total_w, total_h = sum(COL_WIDTHS_PT), sum(heights)

    fig.set_size_inches(total_w / 72, total_h / 72)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, total_w)
    ax.set_ylim(total_h, 0)
    ax.axis("off")
    y = 0
    for r, row in enumerate(wrapped):
        x = 0
        for c, lines in enumerate(row):
            ax.add_patch(Rectangle((x, y), COL_WIDTHS_PT[c], heights[r], clip_on=False,
                                   facecolor="#eef0f3" if r == 0 else "white",
                                   edgecolor="#b8bec7", linewidth=0.6))
            for i, line in enumerate(lines):
                ax.text(x + PAD_X, y + PAD_Y + i * LINE_HEIGHT, line, fontproperties=props[r][c],
                        va="top", ha="left", color="#111827")
            x += COL_WIDTHS_PT[c]
        y += heights[r]
    for ext in ("png", "pdf"):
        fig.savefig(OUTPUT_DIR / f"figure7_fair_rubric.{ext}", dpi=300, facecolor="white",
                    bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def save_xlsx() -> None:
    try:
        import openpyxl
    except ImportError:
        print("openpyxl not installed - skipped FAIR_Compliance_Rubric.xlsx")
        return
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "FAIR Compliance Rubric"
    ws.append(HEADERS)
    for row in ROWS:
        ws.append(list(row))
    wb.save(OUTPUT_DIR / "FAIR_Compliance_Rubric.xlsx")


if __name__ == "__main__":
    save_figure()
    save_xlsx()
    print(f"Figure 7 written to {OUTPUT_DIR}")
