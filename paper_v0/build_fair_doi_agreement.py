"""
Does a resource's FAIR Compliance Notes level (Excellent / Strong / Good) correlate with
whether it has any DOI-bearing Primary citation?

Cited Datasets + Software Mentions - a resource can earn a DOI through a cited
software/tool mention, or a cited dataset. Reports three views: Cited
Datasets alone (the original), Software Mentions alone, and the two combined
(a resource counts as "With DOI" if either source has one).

Join chain, same as build_resource_persistent_id_counts.py: a mention's
source_url's PMC ID -> Publications' PubMed Central Link -> Publications' own
(multivalue) Resource Name -> Resources' own Resource Name.

DOI extraction is the same permissive proxy as build_resource_persistent_id_
counts.py: flags a mention as "has a DOI" if a DOI-shaped string appears
anywhere in specific free-text fields, without verifying it's actually that
mention's own identifier. Reasonable for a coverage estimate, not a strict
attribution check.

Run from anywhere in the repo:
    python3 paper_v0/build_fair_doi_agreement.py
"""
import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "web" / "public" / "data"
OUTPUT_PATH = Path(__file__).parent / "v0.4" / "fair_doi_agreement.tsv"
MD_OUTPUT_PATH = Path(__file__).parent / "v0.4" / "fair_doi_agreement.md"

PMCID_RE = re.compile(r"PMC\d+")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+")
FAIR_LEVEL_RE = re.compile(r"^(Excellent|Strong|Good|Fair|Poor|Weak)\b")

# citation_type is Datasets-only; Software Mentions has no equivalent field,
# so every row is considered (mention_type is "used"/"created", not a
# primary/secondary distinction).
DATASET_DOI_FIELDS = ["dataset_identifier", "data_repository", "dataset_webpage"]
SOFTWARE_DOI_FIELDS = ["url", "context_from_paper"]


def pmcid_from(value: str) -> str:
    m = PMCID_RE.search(str(value or ""))
    return m.group(0) if m else ""


def has_doi(row: pd.Series, fields: list[str]) -> bool:
    return any(DOI_RE.search(str(row[f] or "")) for f in fields)


def pmc_to_resources(pubs: pd.DataFrame) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for _, p in pubs.iterrows():
        pmcid = pmcid_from(p["PubMed Central Link"])
        if not pmcid:
            continue
        names = [n.strip() for n in str(p["Resource Name"]).split(";") if n.strip()]
        out.setdefault(pmcid, set()).update(names)
    return out


def resources_with_doi(mentions: pd.DataFrame, doi_fields: list[str], pmc_map: dict[str, set[str]]) -> set[str]:
    """Resource names with >=1 DOI-bearing mention in `mentions`."""
    out: set[str] = set()
    for _, row in mentions.iterrows():
        if not has_doi(row, doi_fields):
            continue
        pmcid = pmcid_from(row["source_url"])
        if not pmcid:
            continue
        out.update(pmc_map.get(pmcid, ()))
    return out


def cross_tab(resources: pd.DataFrame, with_doi: set[str]) -> pd.DataFrame:
    levels = resources["FAIR Compliance Notes"].str.extract(FAIR_LEVEL_RE, expand=False)
    unclassified = levels.isna().sum()
    if unclassified:
        print(f"WARN: {unclassified} resource(s) have a FAIR Compliance Notes value "
              "not starting with a known level - excluded from the cross-tab")
    df = pd.DataFrame({"level": levels, "name": resources["Resource Name"]}).dropna(subset=["level"])
    df["has_doi"] = df["name"].isin(with_doi)

    order = ["Excellent", "Strong", "Good", "Fair", "Poor", "Weak"]
    present = [lv for lv in order if lv in df["level"].unique()]
    rows = []
    for level in present:
        sub = df[df["level"] == level]
        with_n = int(sub["has_doi"].sum())
        total = len(sub)
        rows.append({"FAIR Level": level, "With DOI": with_n, "Without DOI": total - with_n, "Total": total})
    total_with = sum(r["With DOI"] for r in rows)
    total_n = sum(r["Total"] for r in rows)
    rows.append({"FAIR Level": "Total", "With DOI": total_with, "Without DOI": total_n - total_with, "Total": total_n})
    out = pd.DataFrame(rows)
    out["% With DOI"] = (out["With DOI"] / out["Total"] * 100).round(1)
    return out


def render_markdown(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    header = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join(" --- " for _ in cols) + "|"
    lines = [header, sep]
    for _, r in df.iterrows():
        values = [f"{v:.1f}%" if c == "% With DOI" else str(v) for c, v in zip(cols, r)]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render_ascii(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    widths = [max(len(c), *(len(str(v)) for v in df[c])) for c in cols]

    def row(values: list[str]) -> str:
        cells = [f" {v.ljust(w)} " for v, w in zip(values, widths)]
        return "│" + "│".join(cells) + "│"

    def rule(left: str, mid: str, right: str) -> str:
        return left + mid.join("─" * (w + 2) for w in widths) + right

    lines = [rule("┌", "┬", "┐"), row(cols), rule("├", "┼", "┤")]
    for i, (_, r) in enumerate(df.iterrows()):
        if i > 0:
            lines.append(rule("├", "┼", "┤"))
        values = [f"{v:.1f}%" if c == "% With DOI" else str(v) for c, v in zip(cols, r)]
        lines.append(row(values))
    lines.append(rule("└", "┴", "┘"))
    return "\n".join(lines)


def main():
    resources = pd.read_csv(DATA_DIR / "resources.tsv", sep="\t", dtype=str).fillna("")
    pubs = pd.read_csv(DATA_DIR / "publications.tsv", sep="\t", dtype=str).fillna("")
    datasets = pd.read_csv(DATA_DIR / "pub_datasets.tsv", sep="\t", dtype=str).fillna("")
    software = pd.read_csv(DATA_DIR / "pub_software.tsv", sep="\t", dtype=str).fillna("")

    pmc_map = pmc_to_resources(pubs)

    primary_datasets = datasets[datasets["citation_type"].str.strip().str.lower() == "primary"]
    dataset_doi_resources = resources_with_doi(primary_datasets, DATASET_DOI_FIELDS, pmc_map)
    software_doi_resources = resources_with_doi(software, SOFTWARE_DOI_FIELDS, pmc_map)
    combined_doi_resources = dataset_doi_resources | software_doi_resources

    views = {
        "Cited Datasets only (original)": dataset_doi_resources,
        "Software Mentions only": software_doi_resources,
        "Combined (Cited Datasets OR Software Mentions)": combined_doi_resources,
    }

    out_lines = []
    md_lines = []
    for title, with_doi in views.items():
        table = cross_tab(resources, with_doi)
        print(f"\n### {title}\n")
        print(render_markdown(table))
        out_lines.append(f"# {title}")
        out_lines.append(table.to_csv(sep="\t", index=False).rstrip("\n"))
        out_lines.append("")
        md_lines.append(f"### {title}\n")
        md_lines.append(render_markdown(table))
        md_lines.append("")

    OUTPUT_PATH.write_text("\n".join(out_lines))
    MD_OUTPUT_PATH.write_text("\n".join(md_lines))
    print(f"\nWrote {OUTPUT_PATH.relative_to(Path.cwd())}")
    print(f"Wrote {MD_OUTPUT_PATH.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
