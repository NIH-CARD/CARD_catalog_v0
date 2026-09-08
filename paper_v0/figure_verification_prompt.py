"""
Generate a reviewer-response figure: the REAL, verbatim publication-verification
prompt actually used to build the batch JSONL files under
prompts/validate_fetched_publications/*.jsonl - copied directly from
prompts/sufficient_usage.json (the DEFAULT_DG_PROMPT_NAME template
staging/validate_fetched_publications.py's build_fulltext_batch_jsonl() renders
via data_gatherer's PromptManager - see scripts/run_build_fulltext_batch.py).

This is a 4-turn scripted conversation (system/user/system/user), NOT a single
system-prompt-with-placeholders design - the first three turns are fixed,
verbatim template text; only the final user turn's {resource_info}/{n_queries}/
{query_context}/{content} are interpolated per candidate paper. Filled here with
the real first record of fulltext_batch_2.jsonl (Brain & Body Donation Program /
PMC13378813) - {content} is the full article XML in the real batch file (tens of
thousands of characters); shown truncated here with an honest disclosure, not
fabricated, matching how large content is already disclosed elsewhere in this
pipeline's own reports (e.g. buildAbstractSample's "showing first N of M" note).
"""
import matplotlib.pyplot as plt
import textwrap
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "v0.4"
WRAP_WIDTH = 100
HIGHLIGHT = dict(facecolor="#f4c6c6", edgecolor="none", pad=2)

RESOURCE_INFO = (
    "Resource Name: Brain & Body Donation Program; Abbreviation: BBDP; Diseases Included: "
    "Alzheimer's Disease; Parkinson's Disease; Dementia with Lewy Bodies; Multiple System "
    "Atrophy; Progressive Supranuclear Palsy; Corticobasal Degeneration; Frontotemporal "
    "Dementia; Vascular Dementia; Normal Aging Controls; Coarse Data Modality: clinical, "
    "genetics, transcriptomics; Granular Data Modality: Clinical assessments; Neuropathological "
    "assessments; Genomics; Postmortem brain tissue; Body tissue samples; Frozen and fixed "
    "specimens; Sample Size: 1077 participants."
)
N_QUERIES = "1"
QUERY_CONTEXT = "v5:Arizona Study of Aging and Neurodegenerative Disorders"
CONTENT_EXCERPT = (
    "<?xml version='1.0' encoding='UTF-8'?>\n<pmc-articleset><article ...><article-meta>"
    "<article-id pub-id-type=\"pmcid\">PMC13378813</article-id> ... <article-id pub-id-type=\"doi\">"
    "10.4103/NRR.NRR-D-25-00432</article-id> ... <article-title>Palmitic acid-induced autolysosomal "
    "dysfunction and lipotoxicity in neuroinflammation and neurodegeneration</article-title> ..."
)

# Each item: (role, text, [(substr, is_placeholder), ...] override for mixed-highlight lines)
# Turns 1-3 are verbatim, fixed template text from prompts/sufficient_usage.json - never
# interpolated per call. Only turn 4 (the last user turn) contains real substitutions.
TURNS = [
    ("system", "How can I help you today?", False),
    ("user",
     "I need to use scientific publications as glue for scientific artefacts like code, datasets, "
     "and cellular models because often such scholarly documents are the only place where these "
     "artefacts are defined, used, or discussed. Since many scientific papers are open access, we "
     "were able to fetch a large set of them to populate the Catalog of Alzheimer's and Related "
     "Dementias. For that scope we will limit our focus to relevant publications by filtering those "
     "connected to the specific resource of interest (e.g. a cohort, consortium, dataset, or "
     "research network). I need your help to discriminate between two cases and verify whether the "
     "publication under scrutiny is genuinely grounded in the resource - either by using some of its "
     "participants, data, samples, or other materials, or by reporting substantive information about "
     "the resource itself - versus merely mentioning it in passing as an external reference.", False),
    ("system",
     "Sounds good! Before we proceed, I need to understand how this candidate paper was originally "
     "surfaced during discovery. Was it retrieved through a search query, a specific accession ID, "
     "an exact-phrase match, or a broader keyword search? Please provide: (1) the resource we are "
     "trying to verify, (2) the search/grep queries that matched it, and (3) the publication content "
     "(full text or abstract). With this information, I will be able to verify whether the "
     "publication is genuinely grounded in the resource - either by using it or by reporting "
     "substantive information about it - versus merely mentioning or referencing it in passing, and "
     'provide a JSON object with exactly the keys "verification_status", "claim_text", and '
     '"rationale".', False),
    ("user", "FINAL_TURN", True),
]


def wrap_block(text, width=WRAP_WIDTH):
    if not text.strip():
        return [""]
    return textwrap.wrap(text, width=width) or [""]


def main():
    lines = []  # (text, bold, highlight, italic)

    for role, text, is_final in TURNS:
        lines.append((f"Role: {role}", True, False, False))
        lines.append(("Content:", True, False, False))
        if not is_final:
            for ln in wrap_block(text):
                lines.append((ln, False, False, False))
        else:
            # Exactly the four {..} placeholders from prompts/sufficient_usage.json's
            # final turn get highlighted - every other word here is fixed template
            # text, identical on every run, so it stays plain black.
            lines.append(("The resource to verify is:", False, False, False))
            for ln in wrap_block(RESOURCE_INFO):
                lines.append((ln, False, True, False))
            lines.append(("The publication was matched by", False, False, False))
            lines.append((N_QUERIES, False, True, False))
            lines.append(("query(ies):", False, False, False))
            for ln in wrap_block(QUERY_CONTEXT):
                lines.append((ln, False, True, False))
            lines.append(("The candidate publication has the following content:", False, False, False))
            for ln in wrap_block(CONTENT_EXCERPT):
                lines.append((ln, False, True, False))
            # Not template text and not itself a per-run value - an editorial note
            # explaining the truncation, so italic (like the annotation convention
            # used in figure_ai_prompt_snippet.py) rather than highlighted.
            for ln in wrap_block("[... full article XML continues - ~30-60K tokens per paper for "
                                  "real full-text articles, not shown in full here ...]"):
                lines.append((ln, False, False, True))
        lines.append(("", False, False, False))
        lines.append(("―" * WRAP_WIDTH, False, False, False))
        lines.append(("", False, False, False))
    lines.pop()  # drop the trailing separator + blank after the last turn
    lines.pop()

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

    output_file = OUTPUT_DIR / "verification_prompt.png"
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"Saved: {output_file}")
    plt.close()


if __name__ == "__main__":
    main()
