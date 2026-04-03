"""
CARD Catalog normalizer / staging layer.

Converts raw hits TSV files → validated, app-ready TSVs in ``tables/final/``.

Responsibilities:

1. Column rename — map scraper/data_gatherer column names to schema field names
2. Field normalization — semicolon-sort lists, fix PMC links, deduplicate authors
3. Pydantic validation — invalid rows written to ``tables/hits/rejected_<name>_<ts>.tsv``
4. Output — write ``tables/final/<target>_<ts>.tsv``

Can be called programmatically (from orchestrator) or as a CLI::

    python -m staging.normalizer \\
        --input  tables/hits/pubmed_hits_20260329.tsv \\
        --target publications \\
        --output tables/final/pubmed_central_20260329.tsv
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from staging.schemas import SCHEMA_REGISTRY, _Base

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
HITS_DIR = PROJECT_ROOT / "tables" / "hits"
FINAL_DIR = PROJECT_ROOT / "tables" / "final"

# ---------------------------------------------------------------------------
# Column rename maps  (scraper column → schema field name with underscores)
# These only need entries where the name differs from schema field name.
# ---------------------------------------------------------------------------
_RENAME: dict[str, dict[str, str]] = {
    "publications": {
        "Resource Name": "Resource_Name",
        "Diseases Included": "Diseases_Included",
        "Coarse Data Modality": "Coarse_Data_Modality",
        "Granular Data Modality": "Granular_Data_Modality",
        "PubMed Central Link": "PubMed_Central_Link",
    },
    "code": {
        "Resource Name": "Resource_Name",
        "Diseases Included": "Diseases_Included",
        "Repository Link": "Repository_Link",
        "Biomedical Relevance": "Biomedical_Relevance",
        "Code Summary": "Code_Summary",
        "Data Types": "Data_Types",
    },
    "pub_datasets": {
        "dataset_identifier": "Dataset_Identifier",
        "data_repository": "Data_Repository",
        "dataset_webpage": "Dataset_Webpage",
        "citation_type": "Citation_Type",
        "dataset_usage_role": "Citation_Type",       # Dataset_w_Context uses this name
        "usage_description": "Usage_Description",
        "results_relationship": "Results_Relationship",
        "decision_rationale": "Decision_Rationale",
        "dataset_scope": "Dataset_Scope",
    },
    "supplementary": {
        "file_url": "File_URL",
        "file_name": "File_Name",
        "file_extension": "File_Extension",
        "file_format": "File_Format",
        "supplementary_file_keywords": "Keywords",
        "data_repository": "Data_Repository",
        "number_of_files": "Number_Of_Files",
        "file_license": "File_License",
    },
    "new_corpus": {
        "diseases_included": "Diseases_Included",
        "coarse_data_modality": "Coarse_Data_Modality",
        "granular_data_modality": "Granular_Data_Modality",
        "sample_size": "Sample_Size",
        "dataset_urls": "Access_URL",        # take first element of list
        "publication_urls": "Publication_URLs",
    },
}

# ---------------------------------------------------------------------------
# Field-level normalization helpers
# ---------------------------------------------------------------------------

_APOSTROPHE_VARIANTS = ["\u2019", "\u02BC", "\u0060", "\u00B4", "\u2018", "\u201B"]


def _normalize_list_field(value: str, delimiter: str = ";") -> str:
    """Deduplicate, sort, and rejoin a semicolon-delimited field."""
    if not value or pd.isna(value):
        return ""
    parts = [p.strip() for p in str(value).split(delimiter) if p.strip()]
    # Unicode normalization
    cleaned = []
    for p in parts:
        p = unicodedata.normalize("NFKC", p)
        for variant in _APOSTROPHE_VARIANTS:
            p = p.replace(variant, "'")
        cleaned.append(p.strip())
    seen: dict[str, str] = {}
    for item in cleaned:
        key = item.lower()
        if key not in seen:
            seen[key] = item
    return delimiter.join(sorted(seen.values()))


def _fix_pmc_link(link: str) -> str:
    if not link or pd.isna(link):
        return ""
    return re.sub(r"PMCPMC(\d+)", r"PMC\1", str(link))


def _normalize_authors(authors: str) -> str:
    if not authors or pd.isna(authors) or authors == "":
        return ""
    parts = [a.strip() for a in str(authors).split(";") if a.strip()]
    normalized = []
    for a in parts:
        tokens = a.split()
        if not tokens:
            continue
        last = tokens[-1]
        first_mid = " ".join(tokens[:-1])
        normalized.append(f"{last} {first_mid}".strip())
    seen: set[str] = set()
    unique: list[str] = []
    for a in normalized:
        key = re.sub(r"\s+[A-Z]\s+", " ", a).lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return "; ".join(unique)


def _first_url_from_list(value: Any) -> str:
    """Extract first URL from a Python list repr or a plain string."""
    if not value or pd.isna(value):
        return ""
    s = str(value).strip()
    if s.startswith("["):
        try:
            items = eval(s)
            if items:
                return str(items[0])
        except Exception:
            pass
    return s


def _join_url_list(value: Any) -> str:
    """Join a Python list repr of URLs to a semicolon string."""
    if not value or pd.isna(value):
        return ""
    s = str(value).strip()
    if s.startswith("["):
        try:
            items = eval(s)
            return "; ".join(str(u) for u in items if u)
        except Exception:
            pass
    return s


# ---------------------------------------------------------------------------
# Per-target normalization
# ---------------------------------------------------------------------------

def _normalize_publications(df: pd.DataFrame) -> pd.DataFrame:
    if "PubMed_Central_Link" in df.columns:
        df["PubMed_Central_Link"] = df["PubMed_Central_Link"].apply(_fix_pmc_link)
    if "Authors" in df.columns:
        df["Authors"] = df["Authors"].apply(_normalize_authors)
    for col in ["Diseases_Included", "Keywords", "Coarse_Data_Modality", "Granular_Data_Modality"]:
        if col in df.columns:
            df[col] = df[col].apply(_normalize_list_field)
    return df


def _normalize_code(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["Diseases_Included", "Data_Types", "Tooling", "Languages"]:
        if col in df.columns:
            df[col] = df[col].apply(_normalize_list_field)
    return df


def _normalize_pub_datasets(df: pd.DataFrame) -> pd.DataFrame:
    return df


def _normalize_supplementary(df: pd.DataFrame) -> pd.DataFrame:
    return df


def _normalize_new_corpus(df: pd.DataFrame) -> pd.DataFrame:
    if "Access_URL" in df.columns:
        df["Access_URL"] = df["Access_URL"].apply(_first_url_from_list)
    if "Publication_URLs" in df.columns:
        df["Publication_URLs"] = df["Publication_URLs"].apply(_join_url_list)
    for col in ["Diseases_Included", "Coarse_Data_Modality", "Granular_Data_Modality"]:
        if col in df.columns:
            df[col] = df[col].apply(_normalize_list_field)
    return df


_NORMALIZERS = {
    "publications": _normalize_publications,
    "code": _normalize_code,
    "pub_datasets": _normalize_pub_datasets,
    "supplementary": _normalize_supplementary,
    "new_corpus": _normalize_new_corpus,
}

# ---------------------------------------------------------------------------
# Main normalize() function
# ---------------------------------------------------------------------------

def normalize(
    input_path: Path,
    target: str,
    output_path: Path,
) -> Path:
    """
    Normalize a hits TSV and write a validated, app-ready TSV.

    Args:
        input_path:  Path to raw hits file (tables/hits/).
        target:      Schema name from SCHEMA_REGISTRY.
        output_path: Destination path (tables/final/).

    Returns:
        output_path if successful.

    Raises:
        KeyError if target is not in SCHEMA_REGISTRY.
    """
    if target not in SCHEMA_REGISTRY:
        raise KeyError(f"Unknown target '{target}'. Available: {list(SCHEMA_REGISTRY)}")

    model_cls = SCHEMA_REGISTRY[target]
    rename_map = _RENAME.get(target, {})
    normalizer_fn = _NORMALIZERS[target]

    logger.info(f"[normalizer] {target}: loading {input_path.name}")
    df = pd.read_csv(input_path, sep="\t", dtype=str).fillna("")

    # Drop internal pipeline columns
    df = df.drop(columns=[c for c in ["_schema", "Content_For_Analysis"] if c in df.columns])

    # Rename columns
    df = df.rename(columns=rename_map)

    # Field-level normalization
    df = normalizer_fn(df)

    # Pydantic validation — row by row
    valid_rows: list[dict] = []
    rejected_rows: list[dict] = []

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        try:
            validated = model_cls.model_validate(row_dict)
            valid_rows.append(validated.model_dump())
        except ValidationError as e:
            row_dict["_validation_errors"] = str(e)
            rejected_rows.append(row_dict)

    logger.info(
        f"[normalizer] {target}: {len(valid_rows)} valid, {len(rejected_rows)} rejected"
    )

    # Write rejected rows for inspection
    if rejected_rows:
        ts = input_path.stem.split("_")[-1]
        rejected_path = HITS_DIR / f"rejected_{target}_{ts}.tsv"
        pd.DataFrame(rejected_rows).to_csv(rejected_path, sep="\t", index=False)
        logger.warning(f"[normalizer] rejected rows → {rejected_path.name}")

    if not valid_rows:
        logger.warning(f"[normalizer] no valid rows for {target} — output not written")
        return output_path

    # Rename back to app column names (spaces) and select ordered columns
    out_df = pd.DataFrame(valid_rows)
    # model_dump uses field names with underscores; convert back to spaced app names
    out_df = out_df.rename(columns=lambda c: c.replace("_", " "))

    # Preserve only columns defined in the schema's COLUMNS list
    schema_cols = model_cls.COLUMNS
    present = [c for c in schema_cols if c in out_df.columns]
    extra = [c for c in out_df.columns if c not in schema_cols]
    out_df = out_df[present + extra]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_path, sep="\t", index=False)
    logger.info(f"[normalizer] {target}: wrote {len(out_df)} rows → {output_path.name}")

    # Remove older files for this target, keeping only the one just written
    stem = output_path.stem.rsplit("_", 2)[0]  # strip timestamp suffix
    for old_file in sorted(output_path.parent.glob(f"{stem}_*.tsv")):
        if old_file != output_path:
            old_file.unlink()
            logger.info(f"[normalizer] removed old file: {old_file.name}")

    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    parser = argparse.ArgumentParser(
        description="Normalize a CARD Catalog hits file to a final app-ready TSV"
    )
    parser.add_argument("--input", "-i", required=True, help="Input hits TSV path")
    parser.add_argument(
        "--target", "-t", required=True,
        choices=list(SCHEMA_REGISTRY),
        help="Target schema / output table",
    )
    parser.add_argument("--output", "-o", required=True, help="Output TSV path")
    args = parser.parse_args()

    normalize(Path(args.input), args.target, Path(args.output))


if __name__ == "__main__":
    _cli()
