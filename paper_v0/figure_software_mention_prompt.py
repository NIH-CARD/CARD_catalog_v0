"""
Generate a reviewer-response figure: the REAL, verbatim software-mention extraction
prompt used by the pub_metadata stage (data_gatherer's internal package) to populate
the Software Mentions annotation table - copied directly from
data-gatherer/data_gatherer/prompts/prompt_templates/software_prompts/
CLAUDE_RTR_FewShot_software.json (a sibling repo to CARD_catalog_v0, not checked in
here - hardcoded verbatim below, same convention as figure_verification_prompt.py
and figure_v5_query_prompt.py, so this figure has no cross-repo file dependency).

This is a 2-turn scripted conversation - unusually, the FIRST turn is role
"assistant" (a persona/instruction turn, not "system"), containing the task
definition and three worked few-shot examples; the second, role "user", carries the
actual strict output-format instructions and the one per-call interpolation point,
{content} (the full publication text - shown as a placeholder, not filled with a
real example, since a real full-text article would be tens of thousands of
characters, same disclosure convention as figure_verification_prompt.py's truncated
{content}). The source JSON uses doubled braces ({{ }}) to escape literal JSON
inside a Python .format() template - unescaped to single braces below since that's
what the model actually sees; only the trailing {content} is a genuine placeholder.
"""
import matplotlib.pyplot as plt
import textwrap
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "v0.4"
WRAP_WIDTH = 100
HIGHLIGHT = dict(facecolor="#f4c6c6", edgecolor="none", pad=2)

# Verbatim from CLAUDE_RTR_FewShot_software.json, turn 1 (role "assistant"),
# with {{ }} un-escaped to { } (real JSON, not a template placeholder here).
ASSISTANT_TURN = """I am a large language model trained to be informative and comprehensive. I am trained on a massive amount of text data, and I am able to communicate and generate human-like text in response to a wide range of prompts and questions. For this task, I will act as a specialized assistant that identifies software mentions in a publication -- following the same task definition used by the Software Mention Detection (SOMD) research community (e.g. the SoMeSci corpus and shared task, and the SoftCite dataset): a software mention is any named tool, package, application, or programming environment referenced in the paper, whether or not it has a URL, version, or citation attached. Most real mentions have none of those -- "analyzed using SPSS" or "implemented in Python" are complete, valid mentions on their own.

The output should be a JSON object with a "software_mentions" key containing an array of objects, where each object has the following keys:
- "software_name": The name of the software/tool/package/application as it appears in the paper (e.g. "Python", "SPSS", "Scanpy", "BLAST"). Always required, even with no URL or version.
- "version": The version number, if stated (e.g. "3.9", "v2.1.0"). Otherwise "n/a".
- "mention_type": "created" if this is the paper's own new tool/release being introduced; "used" if it's an existing/third-party tool the authors used; "n/a" if unclear.
- "url": The URL/repository link for this software, if given -- GitHub, GitLab, Bitbucket, Zenodo, PyPI, CRAN, a lab homepage, etc. Do not restrict this to GitHub links only. Otherwise "n/a".
- "context_from_paper": The text passage from the paper mentioning this software.

Grouping rule: create ONE object per distinct software mention. If a sentence names multiple different tools, create a separate object for each one.

Here are examples for reference:

Example 1 -- a widely-used third-party tool with a version, no URL:
input: "Statistical analyses were performed using SPSS version 26 (IBM Corp.)."
output:
{
  "software_mentions": [
    {"software_name": "SPSS", "version": "26", "mention_type": "used", "url": "n/a", "context_from_paper": "Statistical analyses were performed using SPSS version 26 (IBM Corp.)."}
  ]
}

Example 2 -- the paper's own new tool, released with a repository link:
input: "Here we introduce Scanpy2X, a new toolkit for large-scale single-cell analysis, available at https://github.com/labgroup/scanpy2x."
output:
{
  "software_mentions": [
    {"software_name": "Scanpy2X", "version": "n/a", "mention_type": "created", "url": "https://github.com/labgroup/scanpy2x", "context_from_paper": "Here we introduce Scanpy2X, a new toolkit for large-scale single-cell analysis, available at https://github.com/labgroup/scanpy2x."}
  ]
}

Example 3 -- two different third-party tools mentioned together (split into two objects), one with a URL and one without:
input: "Reads were aligned with STAR (https://github.com/alexdobin/STAR) and downstream analysis used the R programming language."
output:
{
  "software_mentions": [
    {"software_name": "STAR", "version": "n/a", "mention_type": "used", "url": "https://github.com/alexdobin/STAR", "context_from_paper": "Reads were aligned with STAR (https://github.com/alexdobin/STAR) and downstream analysis used the R programming language."},
    {"software_name": "R", "version": "n/a", "mention_type": "used", "url": "n/a", "context_from_paper": "Reads were aligned with STAR (https://github.com/alexdobin/STAR) and downstream analysis used the R programming language."}
  ]
}

If no software is mentioned anywhere in the paper, return {"software_mentions": [{"software_name": "n/a", "version": "n/a", "mention_type": "n/a", "url": "n/a", "context_from_paper": "n/a"}]}."""

# Verbatim from turn 2 (role "user"), up to the final interpolation point -
# rendered separately below so {content} can be isolated on its own line/highlight.
USER_TURN_BEFORE_CONTENT = """Given the information that I am going to share:
 1) the full text of the publication that you have to extract software mentions from.

Please return a JSON object with a "software_mentions" key containing an array of objects where each object has the following structure:
- `software_name`: The name of the software/tool/package/application. If not found, set it to "n/a".
- `version`: The version number, if stated. If not found, set it to "n/a".
- `mention_type`: "created" (paper's own new tool), "used" (existing/third-party tool), or "n/a" if unclear.
- `url`: The URL/repository link for this software, if given (any kind -- GitHub, GitLab, Zenodo, PyPI, CRAN, a lab homepage, etc., not just GitHub). If not found, set it to "n/a".
- `context_from_paper`: The relevant text passage that mentions this software. If not found, set it to "n/a".

Please follow these strict instructions:
- The output must be a valid JSON object with a "software_mentions" key.
- The "software_mentions" value must be an array of objects.
- Each object must contain the keys `software_name`, `version`, `mention_type`, `url`, and `context_from_paper`.
- Each object must represent exactly ONE distinct software mention. If multiple different tools are mentioned, create a separate object for each.
- A software mention does NOT need a URL or version to be valid -- most real mentions have neither. Do not skip a tool just because it has no link.
- Any other output format will be considered invalid.

Below is the input data that you will use to generate the output:
1) content =>"""


def render_block(text, width=WRAP_WIDTH):
    """Split on literal newlines (preserving the source's own paragraph/example
    structure) and wrap only lines that exceed width - short JSON example lines
    pass through unwrapped."""
    out = []
    for raw_line in text.split("\n"):
        if not raw_line.strip():
            out.append("")
        else:
            out.extend(textwrap.wrap(raw_line, width=width) or [""])
    return out


def main():
    lines = []

    lines.append(("Role: assistant", True, False, False))
    lines.append(("Content:", True, False, False))
    for ln in render_block(ASSISTANT_TURN):
        lines.append((ln, False, False, False))
    lines.append(("", False, False, False))
    lines.append(("―" * WRAP_WIDTH, False, False, False))
    lines.append(("", False, False, False))

    lines.append(("Role: user", True, False, False))
    lines.append(("Content:", True, False, False))
    for ln in render_block(USER_TURN_BEFORE_CONTENT):
        lines.append((ln, False, False, False))
    lines.append(("{content}", False, True, False))
    lines.append(("(the full text of the candidate publication)", False, False, True))

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

    output_file = OUTPUT_DIR / "software_mention_prompt.png"
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"Saved: {output_file}")
    plt.close()


if __name__ == "__main__":
    main()
