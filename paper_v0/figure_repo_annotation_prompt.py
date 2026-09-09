"""
Generate a reviewer-response figure: the REAL, verbatim GitHub repository
annotation prompt - copied directly from scrapers/batch_ai_analysis.py's
create_analysis_prompt() (identical to scrape_github.py's synchronous
get_ai_analysis(), per that function's own docstring), which populates the
Code Repositories table's Biomedical Relevance, Code Summary, Data Types, and
Tooling columns (staging/schemas.py::CodeRepoRow) via the Anthropic Batch API
(model "claude-sonnet-4-5-20250929", temperature 0.0).

Single user turn, no system/assistant persona turn. Two interpolation points:
{repo_name} and {repo_content[:8000]} - filled here with a real repository from
an actual batch request (scrapers/batch_requests_20260824_152052.jsonl):
"Cognitive-Load-Estimation-using-EEG-and-Eye-Blink-Multimodal-Neuro-AI-System-",
content shown truncated with an honest disclosure, matching the convention used
for the other prompt figures with a long per-call {content} field. One emoji
(a pushpin, U+1F4CC) in the real README is dropped from the excerpt below - the
monospace figure font has no glyph for it - no other change from the verbatim
batch request.
"""
import matplotlib.pyplot as plt
import textwrap
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "v0.4"
WRAP_WIDTH = 100
HIGHLIGHT = dict(facecolor="#f4c6c6", edgecolor="none", pad=2)

REPO_NAME = "Cognitive-Load-Estimation-using-EEG-and-Eye-Blink-Multimodal-Neuro-AI-System-"
REPO_CONTENT_EXCERPT = (
    "README:\n"
    "# Here are your Instructions\n"
    "# Cognitive Load Estimation using Eye Blink and EEG Fusion\n\n"
    "## Project Overview\n\n"
    "This project focuses on **estimating a person's cognitive load (mental effort)** by "
    "combining **eye blink behavior** and **EEG (brain signal) data**. The system uses "
    "**Artificial Intelligence and Machine Learning** techniques to determine whether a "
    "person is **relaxed, focused, or mentally overloaded**."
)

# Each item: (text, is_placeholder). Verbatim from create_analysis_prompt's f-string,
# split at the two interpolation points ({repo_name}, {repo_content[:8000]}) plus the
# fixed trailing section-header template - never reassembled into one literal string,
# so each piece can be wrapped/highlighted independently (see other figure_*.py scripts).
SEGMENTS = [
    ("Analyze this GitHub repository and provide:", False),
    ("1. BIOMEDICAL RELEVANCE: Answer YES or NO with a brief explanation. The repository is "
     "biomedically relevant if it relates to:\n"
     "   - Neurodegenerative diseases (Alzheimer's, Parkinson's, dementia, ALS, etc.)\n"
     "   - Brain imaging, neuroimaging, or brain analysis\n"
     "   - Medical/clinical data analysis for brain disorders\n"
     "   - Bioinformatics related to neuroscience\n"
     "   - Healthcare applications for neurological conditions\n"
     "   Answer NO if it's a general software project, web app, game, or unrelated to "
     "biomedical research.", False),
    ("2. CODE SUMMARY: Provide a concise 2-3 sentence summary of what the code does and its "
     "purpose.", False),
    ("3. DATA TYPES: List the data types and modalities mentioned (e.g., MRI, clinical data, "
     "genomics, etc.). If none are clearly specified, state \"Not specified in the available "
     "repository information.\"", False),
    ("4. TOOLING: List the packages, tools, frameworks, and technologies used.", False),
    ("Repository:", False),
    (REPO_NAME, True),
    ("Content (first 8000 chars):", False),
    (REPO_CONTENT_EXCERPT, True),
    ("[... repository README/file content continues - up to 8,000 characters per repository, "
     "not shown in full here ...]", "italic"),
    ("Format your response EXACTLY as follows (use these exact section headers):", False),
    ("BIOMEDICAL RELEVANCE:\n[Your YES/NO answer with explanation]\n\n"
     "CODE SUMMARY:\n[Your 2-3 sentence summary]\n\n"
     "DATA TYPES:\n[Your data types list or \"Not specified\"]\n\n"
     "TOOLING:\n[Your tools list]", False),
]


def render_block(text, width=WRAP_WIDTH):
    out = []
    for raw_line in text.split("\n"):
        if not raw_line.strip():
            out.append("")
        else:
            out.extend(textwrap.wrap(raw_line, width=width) or [""])
    return out


def main():
    lines = [("Role: user", True, False, False), ("Content:", True, False, False)]
    for text, kind in SEGMENTS:
        hl = kind is True
        italic = kind == "italic"
        for ln in render_block(text):
            lines.append((ln, False, hl, italic))

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

    output_file = OUTPUT_DIR / "repo_annotation_prompt.png"
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white")
    print(f"Saved: {output_file}")
    plt.close()


if __name__ == "__main__":
    main()
