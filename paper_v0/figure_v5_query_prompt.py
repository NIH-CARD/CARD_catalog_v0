"""
Generate a reviewer-response figure: the REAL, verbatim Q5 query-generation prompt
- copied directly from scrapers/scrape_publications.py's _generate_pmc_queries(),
the function search_pubmed() calls when query_method == "v5". Unlike the fulltext
verification prompt (figure_verification_prompt.py, a 4-turn scripted
conversation), this is a single user turn with a forced tool call
(tool_choice={"type": "tool", "name": "return_queries"}) - Claude cannot reply
with free text, only a structured list of query strings via the return_queries
tool, shown at the bottom.

Filled with a real inventory row (Brain & Body Donation Program / BBDP) - same
resource used in figure_verification_prompt.py for continuity across figures.

Follows the same convention as figure_verification_prompt.py: a label and its
interpolated value are never rendered on the same wrapped line (matplotlib can't
bbox-highlight part of a text() call), so a sentence that interpolates a value
mid-sentence is split into plain / highlighted / plain segments, each wrapped
and laid out independently - not reassembled into literal single sentences.
"""
import matplotlib.pyplot as plt
import textwrap
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "v0.4"
WRAP_WIDTH = 100
HIGHLIGHT = dict(facecolor="#f4c6c6", edgecolor="none", pad=2)

STUDY_NAME = "Brain & Body Donation Program"
ABBREVIATION = "BBDP"
DISEASES = ("Alzheimer's Disease; Parkinson's Disease; Dementia with Lewy Bodies; Multiple System "
            "Atrophy; Progressive Supranuclear Palsy; Corticobasal Degeneration; Frontotemporal "
            "Dementia; Vascular Dementia; Normal Aging Controls")
DATA_MODALITY = ("clinical, genetics, transcriptomics, Clinical assessments, Neuropathological "
                  "assessments, Genomics, Postmortem brain tissue, Body tissue samples, Frozen and "
                  "fixed specimens")
MAX_QUERIES = "10"

# Each item: (text, is_placeholder). Verbatim from _generate_pmc_queries's
# f-string template, split at every interpolation point into plain/highlighted
# segments - never reassembled into one literal sentence, so each piece can be
# wrapped and colored independently (see module docstring).
SEGMENTS = [
    ("Generate full-text search queries (up to", False),
    (MAX_QUERIES, True),
    (") to find PMC (PubMed Central) papers that describe or use data from this catalog resource:",
     False),
    ("Resource Name:", False),
    (STUDY_NAME, True),
    ("Abbreviation:", False),
    (ABBREVIATION, True),
    ("Diseases:", False),
    (DISEASES, True),
    ("Data modality:", False),
    (DATA_MODALITY, True),
    ("These queries run against PMC's full-text index — the entire paper, not just title/abstract "
     "— so they can find mentions anywhere in the text, not any particular section.", False),
    ("Precision matters more than recall here: there is no downstream verification step, so "
     "whatever a query returns becomes a result directly. Each query must be specific enough that "
     "a match is actually likely to be about this resource, not just topically related — avoid "
     "single generic disease/modality terms alone, which return large volumes of loosely-related "
     "noise. Prefer quoted exact phrases and specific term combinations over broad keyword-only "
     "queries.", False),
    ("Use your judgment on how many queries this resource actually needs — likely well under",
     False),
    (MAX_QUERIES, True),
    (". Generate more only if the resource genuinely has multiple distinct real, "
     "independently-searchable identifiers worth querying separately (e.g. the exact "
     "name/abbreviation as a phrase, and separately its real underlying entities — gene/protein, "
     "technique/assay, cohort/consortium name — when the catalog display name is an invented "
     "compound label unlikely to appear verbatim in any paper). Do not pad the list with "
     "near-duplicate rewordings or overly broad queries just to generate more of them.", False),
    ("Call return_queries with the query strings.", False),
]


def wrap_block(text, width=WRAP_WIDTH):
    if not text.strip():
        return [""]
    return textwrap.wrap(text, width=width) or [""]


def main():
    lines = [("Role: user", True, False, False), ("Content:", True, False, False)]
    for text, hl in SEGMENTS:
        for ln in wrap_block(text):
            lines.append((ln, False, hl, False))

    lines.append(("", False, False, False))
    lines.append(("―" * WRAP_WIDTH, False, False, False))
    lines.append(("", False, False, False))
    lines.append(("Tool (forced — tool_choice pins this call, Claude cannot reply with free text):",
                   True, False, False))
    for ln in wrap_block(
        'return_queries(queries: string[]) — "Full-text search query strings for NCBI PMC (db=pmc). '
        'No field tags needed — PMC\'s default search already covers full text."'):
        lines.append((ln, False, False, True))

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

    output_file = OUTPUT_DIR / "v5_query_prompt.png"
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"Saved: {output_file}")
    plt.close()


if __name__ == "__main__":
    main()
