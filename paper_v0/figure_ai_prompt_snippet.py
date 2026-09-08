"""
Generate a reviewer-response figure: the REAL, verbatim system + user prompt
template for the AI Analysis "cross_table" type (the Cross-Table page's AI
Analysis, newly added) - copied directly from web/netlify/functions/
analyze.mjs (crossTableSystem, buildPrompt's "cross_table" case). The only
thing not literal source text is the highlight on ${report}, the one
dynamic insertion point, and a short note on what composes it.
"""
import matplotlib.pyplot as plt
import textwrap
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "v0.4"
WRAP_WIDTH = 100
HIGHLIGHT = dict(facecolor="#f4c6c6", edgecolor="none", pad=2)

# Verbatim from analyze.mjs, crossTableSystem().
SYSTEM_PARAS = [
    "You are a senior neurodegenerative-disease researcher - a geneticist and biologist first, not a database engineer - doing exploratory discovery on a custom cross-table view of the CARD Catalog. Today's date is ${todayIso()}.",
    'Read this the way a domain expert reads a cohort/consortium landscape, not the way a data engineer reads a table dump. When you see a cohort name (BioFINDER, ADNI, ROSMAP...), a gene, a variant, or a biomarker modality, say what it means scientifically - which disease mechanism, which biomarker class, which patient population, which consortium\'s known research focus - not just that it appears N times. You\'re given two aligned pictures for the same columns - the full catalog\'s baseline distribution and the current subset\'s - so ground comparative claims like "this subset skews toward X relative to the catalog as a whole" in that contrast, not just in raw counts from one side alone.',
    'State comparisons directly and confidently once the evidence supports them - do not hedge every observation as "worth investigating further." Extraction artifacts, naming-variant fragmentation, and normalization issues are not your focus - mention one only in passing if it\'s clearly blocking a real scientific read, never as a headline finding.',
    'A recent or even near-future publication year is completely normal in a routinely-refreshed catalog - today is ${todayIso()}, so never flag a value merely for being "in the future" relative to your own training data.',
]

# Verbatim from analyze.mjs, buildPrompt's "cross_table" case.
# Tuple: (text, bold, highlight, italic). Only the explanatory note under
# ${report} (not literal source text) is italicized, to visually set it
# apart from the real prompt content.
USER_LINES = [
    ("Today's date is ${todayIso()}. Below is a merged cross-table view of the CARD Catalog, built from "
     "Publications joined with other tables via verified keys (PMC ID/DOI, Resource Name, or gene/bioentity "
     "matching): a full-catalog baseline for every column involved, followed by the same columns' value "
     "counts within the current (filtered/merged) subset.", False, False, False),
    ("", False, False, False),
    ("${report}", False, True, False),
    ("  (→ markdown report -- built in ConnectionsPage.tsx's freezeTable() -- composed by: ", False, False, True),
    ("   - The SQL query to reflect the construction of the cross-table view,", False, False, True),
    ("   - A full-catalog baseline per merged column - build-connections-stats.mjs", False, False, True),
    ("   - The samecolumn set's value counts within the current DAG's merged/filtered row set (wideRows).", False, False, True),
    ("", False, False, False),
    ("As a domain expert, not a data auditor, provide:", False, False, False),
    ("", False, False, False),
    ("1. **Key Patterns**: What do the value distributions actually mean scientifically? Name real cohorts, "
     "genes, biomarkers, or modalities and say what they represent in AD/ADRD research - not just that a "
     "value is frequent.", False, False, False),
    ("2. **Contrastive Read**: Compare the subset's distributions against the full-catalog baseline - is "
     "this subset over/under-representing a cohort, modality, or biomarker class relative to the whole "
     "catalog, and what would that mean scientifically?", False, False, False),
    ("3. **Notable Outliers**: Sparse or unusual values worth a second look - framed as scientifically "
     "interesting, not as suspected errors.", False, False, False),
    ("4. **Suggested Next Steps**: One or two concrete follow-up queries or filters a researcher would "
     "want to try next, based on what you found.", False, False, False),
    ("", False, False, False),
    ("Be direct and specific - name real values, real counts, and real comparisons.", False, False, False),
]


def wrap_block(text, width=WRAP_WIDTH):
    if not text.strip():
        return [""]
    indent = "  " if text.startswith("  ") else ""
    return textwrap.wrap(text, width=width, subsequent_indent=indent) or [""]


def main():
    lines = [("Role: system", True, False, False), ("Content:", True, False, False)]
    for i, para in enumerate(SYSTEM_PARAS):
        for ln in wrap_block(para):
            lines.append((ln, False, False, False))
        if i < len(SYSTEM_PARAS) - 1:
            lines.append(("", False, False, False))
    lines.append(("", False, False, False))
    lines.append(("―" * WRAP_WIDTH, False, False, False))
    lines.append(("", False, False, False))
    lines.append(("Role: user", True, False, False))
    lines.append(("Content:", True, False, False))
    for text, bold, hl, italic in USER_LINES:
        for ln in wrap_block(text):
            lines.append((ln, bold, hl, italic))

    n_lines = len(lines)
    line_height_in = 0.205
    fig_h = n_lines * line_height_in + 1.0
    fig_w = 12.5

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    top_margin = 0.4 / fig_h
    left_margin = 0.35 / fig_w
    y = 1 - top_margin
    dy = line_height_in / fig_h

    for text, bold, hl, italic in lines:
        kwargs = dict(fontsize=10.5, family="monospace",
                      fontweight="bold" if bold else "normal",
                      fontstyle="italic" if italic else "normal",
                      va="top", transform=ax.transAxes)
        if hl and text.strip():
            kwargs["bbox"] = HIGHLIGHT
        safe_text = (text if text else " ").replace("$", "\\$")
        ax.text(left_margin, y, safe_text, **kwargs)
        y -= dy

    box = plt.Rectangle(
        (left_margin * 0.4, y - 0.15 / fig_h), 1 - left_margin * 0.8, 1 - (y - 0.15 / fig_h) - top_margin * 0.3,
        transform=ax.transAxes, fill=True, facecolor="#f7f7f7", edgecolor="black", linewidth=1.2, zorder=-1,
    )
    ax.add_patch(box)

    output_file = OUTPUT_DIR / "ai_prompt_snippet.png"
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"Saved: {output_file}")
    plt.close()


if __name__ == "__main__":
    main()
