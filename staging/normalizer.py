"""
CARD Catalog normalizer / staging layer.

Converts raw hits TSV files → cleaned TSVs in ``tables/final/``.

Responsibilities:

1. Column rename — map scraper/data_gatherer column names to readable names
2. Field normalization — semicolon-sort lists, fix PMC links, deduplicate authors
3. Output — write ``tables/final/<target>_<ts>.tsv``

Can be called programmatically (from orchestrator) or as a CLI::

    python -m staging.normalizer \\
        --input  tables/hits/pubmed_hits_20260329.tsv \\
        --target publications \\
        --output tables/final/pubmed_central_20260329.tsv
"""
from __future__ import annotations

import argparse
import ast
import logging
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
HITS_DIR = PROJECT_ROOT / "tables" / "hits"
FINAL_DIR = PROJECT_ROOT / "tables" / "final"

# ---------------------------------------------------------------------------
# Column rename maps  (scraper column → schema field name with underscores)
# These only need entries where the name differs from schema field name.
# ---------------------------------------------------------------------------
_RENAME: dict[str, dict[str, str]] = {
    "scilite": {
        "pmcid": "PMC ID",
        "type": "Type",
        "exact": "Exact",
        "prefix": "Prefix",
        "postfix": "Postfix",
        "section": "Section",
        "provider": "Provider",
        "id": "Annotation ID",
        "tag_name": "Tag Name",
        "tag_uri": "Tag URI",
    },
    # "publications": {
    #     "Resource Name": "Resource_Name",
    #     "Diseases Included": "Diseases_Included",
    #     "Coarse Data Modality": "Coarse_Data_Modality",
    #     "Granular Data Modality": "Granular_Data_Modality",
    #     "PubMed Central Link": "PubMed_Central_Link",
    # },
    # "code": {
    #     "Resource Name": "Resource_Name",
    #     "Diseases Included": "Diseases_Included",
    #     "Repository Link": "Repository_Link",
    #     "Biomedical Relevance": "Biomedical_Relevance",
    #     "Code Summary": "Code_Summary",
    #     "Data Types": "Data_Types",
    # },
    # "pub_datasets": {
    #     "dataset_identifier": "Dataset_Identifier",
    #     "data_repository": "Data_Repository",
    #     "dataset_webpage": "Dataset_Webpage",
    #     "citation_type": "Citation_Type",
    #     "dataset_context_from_paper": "Usage_Description",
    #     "dataset_keywords": "Decision_Rationale",
    #     "pub_title": "Source_Resource_Name",
    # },
    # "supplementary": {
    #     "download_link": "File_URL",
    #     "link": "File_Name",
    #     "file_extension": "File_Extension",
    #     "raw_data_format": "File_Format",
    #     "description": "Keywords",
    #     "pub_title": "Source_Resource_Name",
    # },
    # "new_corpus": {
    #     "diseases_included": "Diseases_Included",
    #     "coarse_data_modality": "Coarse_Data_Modality",
    #     "granular_data_modality": "Granular_Data_Modality",
    #     "sample_size": "Sample_Size",
    #     "dataset_urls": "Access_URL",        # take first element of list
    #     "publication_urls": "Publication_URLs",
    # },
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


def _fmt_month_year(raw: str) -> str:
    """Convert any date string to 'Mon YYYY' (e.g. 'Jan 2024'). Returns raw on failure."""
    if not raw or not raw.strip():
        return ""
    s = raw.strip()
    # "2024-00" — month was empty, padded to "00"; treat as year-only
    if re.match(r"^\d{4}-00", s):
        return s[:4]
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y/%m/%d", "%Y/%m",
                "%Y-%b-%d", "%Y-%b",  # month stored as abbrev (e.g. "2026-Apr")
                "%b %Y", "%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%b %Y")
        except ValueError:
            continue
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
    if "Publication Date" in df.columns:
        df["Publication Date"] = df["Publication Date"].apply(_fmt_month_year)
    completeness_fields = [
        "PubMed_Central_Link", "Abstract", "Keywords", "Authors", "Affiliations",
    ]
    present = [c for c in completeness_fields if c in df.columns]
    if present:
        df["Data Completeness"] = df[present].apply(
            lambda row: str(round(
                sum(bool(str(v).strip()) for v in row) / len(present) * 100
            )),
            axis=1,
        )
    return df


_RELEVANCE_VERDICT_PATTERN = re.compile(
    r"^\s*(YES|NO|UNCLEAR|INSUFFICIENT INFORMATION)\b[.:\-\s]*",
    re.IGNORECASE,
)


def _split_relevance_verdict(df: pd.DataFrame) -> pd.DataFrame:
    """Split 'Biomedical Relevance' into a clean verdict + a separate rationale -
    the LLM returns them glued together as one sentence ("YES. This repo is...").
    Biomedical Relevance becomes just the verdict token; Relevance Rationale gets
    the rest."""
    if "Biomedical Relevance" not in df.columns:
        return df

    def split(text: str) -> tuple[str, str]:
        text = (text or "").strip()
        if not text:
            return "", ""
        m = _RELEVANCE_VERDICT_PATTERN.match(text)
        if not m:
            return "", text
        return m.group(1).upper(), text[m.end():].strip()

    parts = df["Biomedical Relevance"].apply(split)
    df["Biomedical Relevance"] = parts.apply(lambda t: t[0])
    df["Relevance Rationale"] = parts.apply(lambda t: t[1])
    return df


def _commas_to_semicolons_outside_parens(text: str) -> str:
    """Convert stray ',' list-separators to the app-wide ';' convention, but leave
    commas inside parentheses alone (e.g. 'Genetic PD (LRRK2, GBA, SNCA mutations)'
    is one term, not three) - the resource inventory mixes both separators for
    Diseases Included inconsistently."""
    out = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        out.append(";" if ch == "," and depth == 0 else ch)
    return "".join(out)


def _dedup_repos(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse duplicate rows for the same repo (github_search matches once per
    resource whose search terms it hits) into one row per Repository Link.
    Resource Name/Abbreviation/Diseases Included merge into semicolon-joined lists
    - a repo can genuinely relate to several resources; everything else describes
    the repo itself and takes the first non-empty value across the group."""
    if "Repository Link" not in df.columns:
        return df

    multi_value_cols = [c for c in ("Resource Name", "Abbreviation", "Diseases Included") if c in df.columns]
    other_cols = [c for c in df.columns if c not in multi_value_cols and c != "Repository Link"]

    def merge_group(group: pd.DataFrame) -> "pd.Series[str]":
        out = {}
        for col in multi_value_cols:
            out[col] = _normalize_list_field(";".join(v for v in group[col] if v.strip()))
        for col in other_cols:
            out[col] = next((v for v in group[col] if v.strip()), "")
        return pd.Series(out)

    before = len(df)
    deduped = df.groupby("Repository Link", sort=False).apply(merge_group).reset_index()
    after = len(deduped)
    if before != after:
        logger.info(f"code: collapsed {before} rows → {after} unique repos ({before - after} duplicate resource-links merged)")
    return deduped


_PLACEHOLDER_LEADING_SENTENCE = re.compile(
    r"^(not specified|not mentioned|not available|not provided|no specific|"
    r"none specified|no information)\b[^.]*\.?\s*",
    re.IGNORECASE,
)
_PLACEHOLDER_BARE_TERMS = {"n/a", "na", "none", "unknown", "unclear", "not specified", "not applicable"}


def _split_flattened_list(text: str) -> list[str]:
    """Split a cell that's actually a flattened bullet list ('- item1 - item2') into
    real items - the LLM writes these as one string with ' - ' bullet separators
    instead of the app's usual ';'-delimited multi-value convention."""
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?:^|\s)-\s+", text)
    return [p.strip().rstrip(".").strip() for p in parts if p.strip()]


def _strip_placeholder_item(item: str) -> str:
    """Strip a leading 'not specified...' disclaimer sentence from one item, or drop
    the item entirely if that's all it says (a bare non-answer like 'N/A', or a
    disclaimer sentence with nothing real after it)."""
    if item.lower() in _PLACEHOLDER_BARE_TERMS:
        return ""
    return _PLACEHOLDER_LEADING_SENTENCE.sub("", item).strip()


def _normalize_flattened_list_column(series: pd.Series) -> pd.Series:
    """Undo the LLM's flattened-bullet-list formatting and drop placeholder
    non-answers, producing a real ';'-delimited multi-value field."""
    def process(text: str) -> str:
        items = [_strip_placeholder_item(i) for i in _split_flattened_list(text)]
        return _normalize_list_field(";".join(i for i in items if i))
    return series.apply(process)


def _normalize_code(df: pd.DataFrame) -> pd.DataFrame:
    if "Diseases Included" in df.columns:
        df["Diseases Included"] = df["Diseases Included"].apply(_commas_to_semicolons_outside_parens)

    df = _split_relevance_verdict(df)
    df = _dedup_repos(df)

    for col in ["Data Types", "Tooling"]:
        if col in df.columns:
            df[col] = _normalize_flattened_list_column(df[col])
    for col in ["Languages", "Diseases Included"]:
        if col in df.columns:
            df[col] = df[col].apply(_normalize_list_field)

    # Merge FAIR compliance log — adds FAIR Score and FAIR Issues columns
    hits_dir = Path(__file__).parent.parent / "tables" / "hits"
    fair_files = sorted(hits_dir.glob("fair_compliance_log_*.tsv"))
    if fair_files:
        fair_df = pd.read_csv(fair_files[-1], sep="\t", dtype=str).fillna("")
        by_repo = (
            fair_df.groupby("Repository")["Issue Type"]
            .apply(list)
            .reset_index()
        )
        by_repo.columns = pd.Index(["Repository Link", "issues"])
        by_repo["FAIR Issues"] = by_repo["issues"].apply(lambda x: "; ".join(x))
        by_repo["FAIR Score"] = by_repo["issues"].apply(
            lambda x: str(max(0, 10 - len(x)))
        )
        repo_col = "Repository_Link" if "Repository_Link" in df.columns else "Repository Link"
        by_repo = by_repo.rename(columns={"Repository Link": repo_col})
        df = df.merge(
            by_repo[[repo_col, "FAIR Issues", "FAIR Score"]],
            on=repo_col,
            how="left",
        )
        df["FAIR Issues"] = df["FAIR Issues"].fillna("")
        df["FAIR Score"] = df["FAIR Score"].fillna("10")
    else:
        logger.warning("No FAIR compliance log found — setting default scores")
        df["FAIR Issues"] = ""
        df["FAIR Score"] = "10"

    return df


def _normalize_pub_datasets(df: pd.DataFrame) -> pd.DataFrame:
    return df


def _normalize_supplementary(df: pd.DataFrame) -> pd.DataFrame:
    return df


# Ordered (pattern, canonical) pairs for collapsing funder_name variants — the LLM
# extracts funder names as written in each paper, which vary a lot for the same real
# funder (typos, acronym vs spelled-out, "/NIH" suffixes, etc.). Specific institutes
# are listed before the generic "National Institutes of Health" pattern so a compound
# mention (e.g. "...Institute of Biomedical Imaging and Bioengineering of the National
# Institutes of Health") attributes to the specific institute, not the generic parent.
# Not exhaustive — only the high-frequency variant clusters found in the real data;
# unmatched names pass through unchanged rather than being forced into a bucket.
_FUNDER_NAME_PATTERNS: list[tuple[str, str]] = [
    (r"\bnational\s+institutes?\s+(on|of)\s+aging\b", "National Institute on Aging (NIA)"),
    (r"\bnational\s+institutes?\s+of\s+neurological\s+(disorders|diseases)\s+and\s+stroke\b",
     "National Institute of Neurological Disorders and Stroke (NINDS)"),
    (r"\bnational\s+institutes?\s+of\s+mental\s+health\b", "National Institute of Mental Health (NIMH)"),
    (r"\bnational\s+heart,?\s+lung,?\s+and\s+blood\s+institute\b",
     "National Heart, Lung, and Blood Institute (NHLBI)"),
    (r"\bnational\s+institutes?\s+of\s+biomedical\s+imaging\s+and\s+bioengineering\b",
     "National Institute of Biomedical Imaging and Bioengineering (NIBIB)"),
    (r"\bnational\s+human\s+genome\s+research\s+institute\b", "National Human Genome Research Institute (NHGRI)"),
    (r"\bnational\s+institutes?\s+of\s+general\s+medical\s+sciences\b",
     "National Institute of General Medical Sciences (NIGMS)"),
    (r"\bnational\s+center\s+for\s+advancing\s+translational\s+sciences\b",
     "National Center for Advancing Translational Sciences (NCATS)"),
    (r"\bnational\s+cancer\s+institute\b", "National Cancer Institute (NCI)"),
    (r"\bnational\s+center\s+for\s+research\s+resources\b", "National Center for Research Resources (NCRR)"),
    (r"\bnational\s+institutes?\s+of\s+health\b(?!\s*\(?nia)", "National Institutes of Health (NIH)"),
    (r"\bmichael\s+j\.?\s*fox\s+foundation\b", "Michael J. Fox Foundation for Parkinson's Research"),
    (r"\bcure\s+alzheimer'?s\s+fund\b", "Cure Alzheimer's Fund"),
    (r"\bknut\s+and\s+alice\s+wallenberg\s+foundation\b", "Knut and Alice Wallenberg Foundation"),
    (r"\baligning\s+science\s+across\s+parkinson'?s\b", "Aligning Science Across Parkinson's (ASAP)"),
    (r"\binstituto\s+de\s+salud\s+carlos\s+iii\b", "Instituto de Salud Carlos III (ISCIII)"),
    (r"\bnational\s+health\s+and\s+medical\s+research\s+council\b",
     "National Health and Medical Research Council (NHMRC)"),
    (r"\balzheimer'?s?\s+drug\s+discovery\s+foundation\b", "Alzheimer's Drug Discovery Foundation"),
    (r"\bnational\s+institute\s+for\s+health\s+(and\s+care\s+)?research\b",
     "National Institute for Health and Care Research (NIHR)"),
    (r"^nihr$", "National Institute for Health and Care Research (NIHR)"),
    (r"^hj[aä]rnfonden\b", "Hjärnfonden"),
    (r"\bparkinson\s+foundation\s+of\s+sweden\b", "Parkinson Foundation of Sweden"),
]
_COMPILED_FUNDER_PATTERNS = [(re.compile(p, re.IGNORECASE), canon) for p, canon in _FUNDER_NAME_PATTERNS]


def _normalize_funder_name(name: str) -> str:
    """Collapse known funder-name variants to one canonical form; passes through unmatched names."""
    n = str(name).strip()
    for pattern, canonical in _COMPILED_FUNDER_PATTERNS:
        if pattern.search(n):
            return canonical
    return n


def _normalize_pub_grants(df: pd.DataFrame) -> pd.DataFrame:
    if "funder_name" in df.columns:
        df["funder_name"] = df["funder_name"].apply(_normalize_funder_name)
    return df


_GENERIC_GIT_HOST_NAMES = {"github", "gitlab", "bitbucket"}


def _repo_name_from_git_url(url: str) -> str:
    """Extract the repo segment ('<owner>/<repo>' -> '<repo>') from a GitHub/
    GitLab/Bitbucket URL. Returns '' if url isn't a repo link on one of those
    hosts (e.g. a bare user/org page with no repo segment)."""
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not any(h in host for h in ("github.com", "gitlab", "bitbucket")):
        return ""
    segments = [s for s in parsed.path.strip("/").split("/") if s]
    if len(segments) < 2:
        return ""
    repo = segments[1]
    return repo[:-4] if repo.endswith(".git") else repo


def _normalize_pub_software(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with no extracted software mention (only source_url populated) -
    same class of no-op placeholder rows as _normalize_pub_models, see there.
    Also: when software_name is just the generic host name ("GitHub"/"GitLab"/
    "Bitbucket") but url is an actual repo link, replace it with the repo name
    parsed from url - the host name alone isn't a useful software identifier
    when the real repo name is sitting right there in the url."""
    before = len(df)
    out = df[df["software_name"].str.strip() != ""].reset_index(drop=True)
    dropped = before - len(out)
    if dropped:
        logger.warning(f"{dropped} pub_software rows dropped — no software mention extracted (only source_url populated)")

    generic_mask = out["software_name"].str.strip().str.lower().isin(_GENERIC_GIT_HOST_NAMES)
    repo_names = out["url"].map(_repo_name_from_git_url)
    fillable = generic_mask & (repo_names != "")
    if fillable.any():
        out.loc[fillable, "software_name"] = repo_names[fillable]
        logger.info(f"{fillable.sum()} pub_software rows renamed from generic host name to repo name")

    return out


def _normalize_pub_models(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with no extracted model mention (only source_url populated) -
    these carry no information and data_gatherer's own process_model_response
    already drops them for freshly-extracted rows; older cached rows from before
    that filter existed can still slip through pipelines/pub_models.py's
    source_url-based cache union, so they're caught here too."""
    before = len(df)
    out = df[df["model_name"].str.strip() != ""].reset_index(drop=True)
    dropped = before - len(out)
    if dropped:
        logger.warning(f"{dropped} pub_models rows dropped — no model mention extracted (only source_url populated)")
    return out


def _normalize_pub_verification(df: pd.DataFrame) -> pd.DataFrame:
    return df


_MISC_PUB_MULTIVALUE_COLS = [
    "Resource Name", "Abbreviation", "Diseases Included",
    "Coarse Data Modality", "Granular Data Modality", "Fetched With",
]
# These two are already ';'-delimited per resource (the app-wide multi-value convention) -
# unlike Resource Name/Abbreviation/Fetched With (single tokens per resource) and Coarse
# Data Modality (comma-delimited natively) - so escaping their internal ';' to ',' before
# the cross-resource join (below) would destroy real item separators, not protect against
# stray ones. They get comma-to-semicolon normalization instead (the inventory mixes both
# separators inconsistently - see _commas_to_semicolons_outside_parens).
_MISC_PUB_ALREADY_SEMICOLON_DELIMITED = {"Diseases Included", "Granular Data Modality"}
_MISC_PUB_SINGLEVALUE_COLS = [
    "PMID", "DOI", "PubMed Central Link", "Authors", "Affiliations",
    "Title", "Abstract", "Keywords", "Publication Date",
    "Verification Status", "Paperclip Repo", "Paperclip Doc ID",
]
_MISC_PUB_RESOURCE_PREFIXED_COLS = [("Rationale", "Inclusion Criteria"), ("Claim Text", "Claim Text")]


def _normalize_misc_publications(df: pd.DataFrame) -> pd.DataFrame:
    """Filter combine_hits + vLLM-verification rows to confirmed (resource, publication)
    links only, then collapse to one row per publication - the same paper linked to
    several resources becomes one row instead of several.

    Resource-specific columns (Resource Name, Diseases Included, Coarse/Granular Data
    Modality, Abbreviation, Fetched With) become semicolon-joined multi-value fields
    across the group, deduplicated via _normalize_list_field. Rationale becomes
    "Inclusion Criteria" and, together with Claim Text, is prefixed per-resource
    ("<Resource Name>: <text>") rather than deduplicated - each resource's inclusion was
    judged independently by the LLM, so one resource's rationale must stay attached to
    it, not merged away. Any literal ';' inside free text is escaped to ',' first (same
    fix staging/combine_hits.py applies to Fetched With) so joining/splitting on ';'
    doesn't fragment one entry into two.

    Publication-specific columns (Title, Abstract, Authors, PMID, DOI, ...) take the
    longest non-empty value across the group's rows - same paper, so these should already
    agree; the longest wins if one copy is more complete than another (same convention
    staging/combine_hits.py uses for its own non-list columns).
    """
    from staging.validate_fetched_publications import _resolve_doc_id

    if "Verification Status" not in df.columns:
        logger.error("misc_publications: no Verification Status column — cannot filter")
        return df

    confirmed = df[df["Verification Status"] == "confirmed"].copy()
    logger.info(f"misc_publications: {len(confirmed)}/{len(df)} row(s) are confirmed")
    if confirmed.empty:
        return confirmed

    confirmed["_doc_id"] = confirmed.apply(lambda row: _resolve_doc_id(row.to_dict()), axis=1)
    confirmed = confirmed[confirmed["_doc_id"].astype(bool)]

    rows = []
    for _, group in confirmed.groupby("_doc_id", sort=False):
        merged = {}
        for col in _MISC_PUB_SINGLEVALUE_COLS:
            if col not in group.columns:
                continue
            values = [str(v) for v in group[col] if str(v).strip()]
            merged[col] = max(values, key=len) if values else ""
        for col in _MISC_PUB_MULTIVALUE_COLS:
            if col not in group.columns:
                continue
            if col in _MISC_PUB_ALREADY_SEMICOLON_DELIMITED:
                values = [
                    _commas_to_semicolons_outside_parens(str(v).strip())
                    for v in group[col] if str(v).strip()
                ]
            else:
                values = [str(v).strip().replace(";", ",") for v in group[col] if str(v).strip()]
            merged[col] = _normalize_list_field(";".join(values))
        for src_col, out_col in _MISC_PUB_RESOURCE_PREFIXED_COLS:
            if src_col not in group.columns:
                continue
            parts = []
            for _, row in group.iterrows():
                text = str(row.get(src_col, "")).strip()
                if not text:
                    continue
                resource = str(row.get("Resource Name", "")).strip().replace(";", ",")
                safe_text = text.replace(";", ",")
                parts.append(f"{resource}: {safe_text}" if resource else safe_text)
            merged[out_col] = ";".join(parts)
        rows.append(merged)

    result = pd.DataFrame(rows)
    logger.info(f"misc_publications: {len(confirmed)} confirmed (resource, publication) row(s) "
                f"-> {len(result)} unique publication(s)")
    return result


def _normalize_new_corpus(df: pd.DataFrame) -> pd.DataFrame:
    if "Access_URL" in df.columns:
        df["Access_URL"] = df["Access_URL"].apply(_first_url_from_list)
    if "Publication_URLs" in df.columns:
        df["Publication_URLs"] = df["Publication_URLs"].apply(_join_url_list)
    for col in ["Diseases_Included", "Coarse_Data_Modality", "Granular_Data_Modality"]:
        if col in df.columns:
            df[col] = df[col].apply(_normalize_list_field)
    return df


def _fetch_go_aspects(go_ids: list[str], chunk_size: int = 200) -> dict[str, str]:
    """Fetch GO term aspects from QuickGO in batched requests.

    Args:
        go_ids: List of GO IDs e.g. ["GO:0006915", "GO:0007568"].
        chunk_size: Number of IDs per request (QuickGO handles up to ~200).

    Returns:
        Mapping of GO ID → aspect string (e.g. "biological_process").
    """
    import requests

    aspects: dict[str, str] = {}
    for i in range(0, len(go_ids), chunk_size):
        batch = go_ids[i : i + chunk_size]
        url = "https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/" + ",".join(batch)
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            for term in r.json().get("results", []):
                aspects[term["id"]] = term.get("aspect", "")
        except Exception as exc:
            logger.warning(f"QuickGO batch {i}–{i+len(batch)} failed: {exc}")
    return aspects


def _normalize_scilite(df: pd.DataFrame) -> pd.DataFrame:
    """Replace Type 'Gene Ontology' with the term's GO aspect from QuickGO."""
    if "Type" not in df.columns or "Tag URI" not in df.columns:
        return df

    go_mask = df["Type"] == "Gene Ontology"
    if not go_mask.any():
        return df

    go_ids = list({
        m.group(1)
        for uri in df.loc[go_mask, "Tag URI"]
        if (m := re.search(r"(GO:\d+)", uri))
    })
    logger.info(f"Fetching aspects for {len(go_ids)} unique GO terms from QuickGO…")
    aspects = _fetch_go_aspects(go_ids)
    logger.info(f"Received aspects for {len(aspects)} GO terms")

    mapped = df.loc[go_mask, "Tag URI"].map(
        lambda uri: aspects.get(m.group(1), "") if (m := re.search(r"(GO:\d+)", uri)) else ""
    )
    df.loc[go_mask, "Type"] = mapped.where(mapped != "", other="Gene Ontology")
    return df


_NORMALIZERS = {
    "publications": _normalize_publications,
    "misc_publications": _normalize_misc_publications,
    "code": _normalize_code,
    "pub_datasets": _normalize_pub_datasets,
    "supplementary": _normalize_supplementary,
    "pub_grants": _normalize_pub_grants,
    "pub_software": _normalize_pub_software,
    "pub_models": _normalize_pub_models,
    "pub_verification": _normalize_pub_verification,
    "new_corpus": _normalize_new_corpus,
    "scilite": _normalize_scilite,
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
        target:      Normalizer target name (must be in _RENAME / _NORMALIZERS).
        output_path: Destination path (tables/final/).

    Returns:
        output_path if successful.
    """
    if target not in _NORMALIZERS:
        raise KeyError(f"Unknown target '{target}'. Available: {list(_NORMALIZERS)}")

    rename_map = _RENAME.get(target, {})
    normalizer_fn = _NORMALIZERS[target]

    logger.info(f"{target}: loading {input_path.name}")
    df = pd.read_csv(input_path, sep="\t", dtype=str).fillna("")

    # Drop internal pipeline columns
    df = df.drop(columns=[c for c in ["_schema", "Content_For_Analysis"] if c in df.columns])

    # Rename columns
    df = df.rename(columns=rename_map)

    # Field-level normalization
    df = normalizer_fn(df)

    logger.info(f"[normalizer] {target}: {len(df)} rows")

    if df.empty:
        logger.warning(f"No rows for {target} — output not written")
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, sep="\t", index=False)
    logger.info(f"{target}: wrote {len(df)} rows → {output_path.name}")

    # Remove older files for this target, keeping only the one just written
    stem = output_path.stem.rsplit("_", 2)[0]  # strip timestamp suffix
    for old_file in sorted(output_path.parent.glob(f"{stem}_*.tsv")):
        if old_file != output_path:
            old_file.unlink()
            logger.info(f"Removed old file: {old_file.name}")

    return output_path


# ---------------------------------------------------------------------------




# Inventory enrichment helpers
# ---------------------------------------------------------------------------

def _parse_urls(row: "pd.Series", url_col: str, alt_col: str) -> set[str]:
    """Return the set of non-empty URLs for a row (Access URL + Alternative URLs)."""
    urls: set[str] = set()

    raw_access = str(row.get(url_col, "") or "").strip()
    if raw_access:
        urls.add(raw_access.rstrip("/"))

    raw_alt = str(row.get(alt_col, "") or "").strip()
    if raw_alt:
        try:
            candidates = ast.literal_eval(raw_alt)
            if isinstance(candidates, (list, tuple)):
                for u in candidates:
                    u = str(u).strip().rstrip("/")
                    if u:
                        urls.add(u)
        except (ValueError, SyntaxError):
            pass

    return urls


def compute_part_of(
    df: "pd.DataFrame",
    url_col: str = "Access URL",
    alt_url_col: str = "Alternative URLs",
    id_col: str = "Abbreviation",
) -> "pd.Series":
    """Compute an 'Is Part Of' column for an inventory DataFrame.

    For each row B, finds every row A whose URL set contains a URL that is a
    proper substring of any URL in B's URL set.  When that holds, B is
    considered *part of* A (e.g. B is a sub-portal of A's domain).

    The result is a semicolon-delimited string of ``id_col`` values from the
    matching parent rows, or an empty string when no match is found.

    Args:
        df: Inventory DataFrame with at least ``url_col``, ``alt_url_col``,
            and ``id_col`` columns.
        url_col: Column name for the primary access URL.
        alt_url_col: Column name for the alternative URLs (stringified list).
        id_col: Column whose value identifies each resource in the output
            (e.g. ``"Abbreviation"`` or ``"Resource Name"``).

    Returns:
        A Series of the same index as ``df``, one entry per row.
    """
    import pandas as pd  # local import so the rest of the module stays light

    # Pre-compute URL sets once
    url_sets: dict[int, set[str]] = {
        i: _parse_urls(row, url_col, alt_url_col) for i, row in df.iterrows()
    }
    ids: dict[int, str] = df[id_col].fillna("").to_dict()

    results: dict[int, str] = {}

    for i in df.index:
        urls_b = url_sets[i]
        parents: list[str] = []

        for j in df.index:
            if i == j:
                continue
            urls_a = url_sets[j]
            # B is part of A if any url_a is a proper substring of any url_b
            if any(
                url_a and url_b and url_a in url_b and url_a != url_b
                for url_a in urls_a
                for url_b in urls_b
            ):
                parent_id = ids[j]
                if parent_id:
                    parents.append(parent_id)

        results[i] = "; ".join(sorted(set(parents)))

    return pd.Series(results, name="Is Part Of")


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
        choices=list(_NORMALIZERS),
        help="Target normalizer (publications, code, pub_datasets, supplementary, new_corpus)",
    )
    parser.add_argument("--output", "-o", required=True, help="Output TSV path")
    args = parser.parse_args()

    normalize(Path(args.input), args.target, Path(args.output))


if __name__ == "__main__":
    _cli()
