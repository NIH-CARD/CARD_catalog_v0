"""Assemble the CARD Catalog data package for a Zenodo release.

Collects the same tables web/scripts/sync-data.sh serves to the app (newest by
mtime), renames them to stable names, gzips the large SciLite table, and writes
a README.md (with data dictionary) and checksums.sha256 into paper_v0/zenodo_release/.

Run: venv/bin/python paper_v0/build_zenodo_release.py [--version 1.0.0]
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))
from staging.normalizer import FAIR_ASSESSED_MARKER, load_fair_issues  # noqa: E402

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
TABLES_DIR = PROJECT_ROOT / "tables"
FINAL_DIR = TABLES_DIR / "final"
HITS_DIR = TABLES_DIR / "hits"
REGISTRY_TS = PROJECT_ROOT / "web" / "src" / "lib" / "tableRegistry.ts"
OUTPUT_DIR = Path(__file__).parent / "zenodo_release"
REPO_URL = "https://github.com/NIH-CARD/CARD_catalog_v0"
APP_URL = "https://alzheimersdatahub.org"

# (release file, source dir, source glob, app table name, description, join keys)
TABLES = [
    ("resources.tsv", TABLES_DIR, "resources-inventory-*", "Resources",
     "Curated inventory of AD/ADRD research resources (cohorts, biobanks, data platforms).",
     "`Resource Name`"),
    ("publications.tsv", FINAL_DIR, "misc_publications_*.tsv", "Publications",
     "Papers that use a cataloged resource, one row per paper (verified matches only).",
     "`Resource Name` → resources; `PubMed Central Link` (PMC ID, DOI fallback) → paper-level tables"),
    ("code_repositories.tsv", FINAL_DIR, "gits_to_reannotate_completed_*.tsv", "Code Repositories",
     "GitHub repositories linked to a resource, via GitHub search or software mentions in papers; "
     "AI-generated summary and FAIR assessment.",
     "`Resource Name` → resources"),
    ("human_cellular_models.tsv", FINAL_DIR, "cellular_models_*.tsv", "Human Cellular Models",
     "iPSC lines from the iNDI collection with gene/variant annotation.",
     "`Linked Publications` (PMC IDs) → publications; `Linked Studies` → resources; "
     "`dbSNP` / `Gene` → SciLite `Tag Name` / `Exact`"),
    ("cited_datasets.tsv", FINAL_DIR, "pub_datasets_*.tsv", "Cited Datasets",
     "Datasets cited in a paper's full text.", "`source_url` → publications"),
    ("supplementary_files.tsv", FINAL_DIR, "pub_supplementary_*.tsv", "Supplementary Files",
     "Supplementary files deposited with a paper.", "`source_url` → publications"),
    ("grants.tsv", FINAL_DIR, "pub_grants_*.tsv", "Grants",
     "Funding acknowledged in a paper.", "`source_url` → publications"),
    ("software_mentions.tsv", FINAL_DIR, "pub_software_*.tsv", "Software Mentions",
     "Software used in a paper.", "`source_url` → publications"),
    ("models.tsv", FINAL_DIR, "pub_models_*.tsv", "Models",
     "ML/AI models used in a paper.", "`source_url` → publications"),
    ("scilite_annotations.tsv.gz", FINAL_DIR, "scilite_annotations_*.tsv", "SciLite Annotations",
     "Europe PMC SciLite text-mined entity annotations (gzip-compressed TSV).",
     "`PMC ID` → publications"),
    ("fair_compliance.tsv", None, None, None,
     "FAIR issues per repository (newest assessment across all pipeline runs), behind Code Repositories' "
     "`FAIR Score` / `FAIR Issues`; repositories with no issues have no rows.",
     "`Repository` → code_repositories `Repository Link`"),
]

# Scraper artifacts (stray header fragments, raw HTML link attributes), near-empty and undocumented.
DROP_COLUMNS = {
    "cited_datasets.tsv": ["I", "II", "dataset_context_context_from_paper", "dataset_context_about_paper"],
    "grants.tsv": ["following", "V", "PI", "grants", "Union.", "ID"],
    "software_mentions.tsv": ["software_mentions"],
    "supplementary_files.tsv": ["a_attr_href", "a_attr_class", "a_attr_data-ga-action", "a_attr_target",
                                "a_attr_rel"],
}


def _latest(directory: Path, pattern: str) -> Path:
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No {pattern} in {directory}")
    return files[-1]


def _multivalue_registry() -> dict[str, dict[str, str]]:
    """Parse tableRegistry.ts into {table: {column: delimiter}} for multivalue columns."""
    registry: dict[str, dict[str, str]] = {}
    table = None
    for line in REGISTRY_TS.read_text(encoding="utf-8").splitlines():
        if m := re.match(r'\s*name: "([^"]+)"', line):
            table = registry.setdefault(m.group(1), {})
        elif table is not None and (m := re.search(r'col\("([^"]+)",\s*true(?:,\s*"([^"]*)")?\)', line)):
            table[m.group(1)] = m.group(2) or ";"
    return registry


def _git_ref() -> str:
    """Commit (and tag, if HEAD is tagged) the package is built from."""
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True).stdout.strip()

    commit = git("rev-parse", "HEAD")
    tag = git("tag", "--points-at", "HEAD")
    return f"tag `{tag.splitlines()[0]}`, commit `{commit}`" if tag else f"commit `{commit}`"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _readme(version: str, entries: list[dict], multivalue: dict[str, dict[str, str]]) -> str:
    today = dt.date.today().isoformat()
    lines = [
        "# CARD Catalog data package",
        "",
        f"Version {version} · snapshot built {today} from {REPO_URL} ({_git_ref()})",
        "",
        "Tables behind the CARD Catalog, which connects Alzheimer's disease and related "
        "dementias (AD/ADRD) research resources with the publications, code repositories, "
        f"cellular models and paper-level annotations that use them. Live app: {APP_URL}. "
        f"Pipeline and app source: {REPO_URL}.",
        "",
        "## Files",
        "",
        "| File | Rows | Columns | Description |",
        "|---|---:|---:|---|",
    ]
    lines += [f"| `{e['file']}` | {e['rows']:,} | {len(e['columns'])} | {e['description']} |" for e in entries]
    lines += [
        "",
        "`checksums.sha256` holds a SHA-256 for every file (`sha256sum -c checksums.sha256`).",
        "",
        "## Format",
        "",
        "- Tab-separated, UTF-8, one header row; read every column as a string.",
        "- Empty cells are empty strings.",
        "- Multi-value columns (listed per table below) are delimited lists, mostly `;`.",
        "",
        "## How the tables connect",
        "",
        "Publications is the hub. Three join keys link the tables:",
        "",
        "- **Resource Name** - Resources ↔ Publications, Code Repositories, Human Cellular Models (`Linked Studies`).",
        "- **Publication ID** - the PMC ID from Publications' `PubMed Central Link` (DOI when no PMC ID) ↔ "
        "the `source_url` of the paper-level tables, SciLite `PMC ID`, and Human Cellular Models' `Linked Publications`.",
        "- **Variant / gene** - Human Cellular Models' `dbSNP` ↔ SciLite `Tag Name` (subType RefSNP), and "
        "`Gene` ↔ SciLite `Exact` (Type Gene_Proteins).",
        "",
        "Human Cellular Models' `Linked Publications` and `Linked Studies` are precomputed: a model's `dbSNP` "
        "is matched to SciLite RefSNP annotations, giving PMC IDs, which map to resources through Publications.",
        "",
        "## Data dictionary",
        "",
    ]
    for e in entries:
        mv = multivalue.get(e["app_table"] or "", {})
        lines += [f"### `{e['file']}`", "", e["description"], "", f"Join keys: {e['join_keys']}", "",
                  "| Column | Multi-value |", "|---|---|"]
        lines += [f"| `{c}` | {'yes (`' + mv[c] + '`)' if c in mv else ''} |" for c in e["columns"]]
        lines.append("")
    lines += [
        "## Provenance notes",
        "",
        "- Code Repositories' `Code Summary`, `Biomedical Relevance`, `Relevance Rationale`, `Data Types` and "
        "`Tooling` are AI-generated from repository contents; verify them against the original sources and do "
        "not treat them as human-curated annotations.",
        "- Paper-level tables (cited datasets, supplementary files, grants, software, models) are extracted "
        "from open-access full text.",
        "- SciLite annotations come from the Europe PMC Annotations API.",
        "",
        "## License",
        "",
        "CC BY 4.0. Bibliographic metadata and annotations derive from PubMed, PubMed Central and Europe PMC.",
        "",
    ]
    return "\n".join(lines)


def build(version: str) -> Path:
    """Write the release folder.

    Args:
        version: Release version string recorded in the README.

    Returns:
        The output directory.
    """
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    entries = []
    for file, src_dir, pattern, app_table, description, join_keys in TABLES:
        dst = OUTPUT_DIR / file
        if src_dir is None:  # FAIR issues: merged across every log, as the normalizer scores them
            df = load_fair_issues(HITS_DIR)
            df = df.loc[df["Issue Type"] != FAIR_ASSESSED_MARKER, ["Repository", "Issue Type"]]
            src = Path("fair_compliance_log_*.tsv (merged)")
            df.to_csv(dst, sep="\t", index=False)
        elif file.endswith(".gz"):
            src = _latest(src_dir, pattern)
            df = pd.read_csv(src, sep="\t", dtype=str, keep_default_na=False)
            with src.open("rb") as fin, gzip.open(dst, "wb", compresslevel=9) as fout:
                shutil.copyfileobj(fin, fout)
        else:
            src = _latest(src_dir, pattern)
            df = pd.read_csv(src, sep="\t", dtype=str, keep_default_na=False)
            if file in DROP_COLUMNS:
                df = df.drop(columns=DROP_COLUMNS[file])
                df.to_csv(dst, sep="\t", index=False)
            else:
                shutil.copyfile(src, dst)
        logger.info(f"{src.name} ({len(df):,} rows) → {file}")
        entries.append({"file": file, "rows": len(df), "columns": list(df.columns), "app_table": app_table,
                        "description": description, "join_keys": join_keys, "source": src.name})

    (OUTPUT_DIR / "README.md").write_text(_readme(version, entries, _multivalue_registry()), encoding="utf-8")
    files = sorted(p for p in OUTPUT_DIR.iterdir() if p.name != "checksums.sha256")
    (OUTPUT_DIR / "checksums.sha256").write_text("".join(f"{_sha256(p)}  {p.name}\n" for p in files))
    pd.DataFrame(entries)[["file", "source", "rows"]].to_csv(OUTPUT_DIR.parent / "zenodo_release_sources.tsv",
                                                             sep="\t", index=False)
    logger.info(f"Wrote {len(files) + 1} files → {OUTPUT_DIR}")
    return OUTPUT_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", default="1.0.0", help="Release version recorded in the README.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build(args.version)


if __name__ == "__main__":
    main()
