"""
Publication glue: "publications as glue for scientific artefacts" (see
staging/validate_fetched_publications.py's verification prompt) - this module
enriches an already publication-shaped table with columns computed by a
separate downstream process, keyed by (resource, doc). Several such joins
live here:

- build_misc_publications(): joins pub_verification's vLLM-based verdicts
  into a copy of combine_hits.tsv (misc_publications_*.tsv), leaving the
  original combine_hits file untouched.
- extract_new_corpus_publications(): explodes a new_corpus table (page
  navigation's discovered-publication columns) into combine_hits-shaped rows,
  so they can be folded into the same misc_publications pipeline.
- resolve_missing_pmcids(): fills in PubMed Central Link for DOI-only rows via
  NCBI's ID Converter API (falling back to an exact-title match) - both
  pub_jobs (full-text fetch prefers PMC) and scilite (Europe PMC's own
  annotation API is PMC-ID-keyed) need one to do anything with these rows.
- build_annotation_summary(): row counts per pub-metadata stage table plus
  SciLite's top annotation types, written as a small JSON. Exists because
  scilite_annotations_*.tsv is ~270MB - the web app's Home page needs a type
  breakdown but must never fetch that file itself to get one.
- build_scilite_type_aggregate(): per-(PMC ID, Type) annotation counts, for
  the same reason - the Connections page needs to draw a Publication <->
  annotation-type edge without ever loading the raw SciLite table.

Not staging/combine_hits.py's job: that one deduplicates/collapses multiple
raw hits files sharing the same schema (Union-Find row-matching) before
anything is finalized - a different operation from enriching an
already-shaped table with derived columns.

Called automatically by the orchestrator as the final pipeline step, or
manually via::

    python -m staging.publication_glue
"""
from __future__ import annotations

import ast
import html
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_FINAL_DIR = Path(__file__).parent.parent / "tables" / "final"
_HITS_DIR = Path(__file__).parent.parent / "tables" / "hits"

def _latest(pattern: str) -> Path | None:
    files = sorted(_FINAL_DIR.glob(pattern))
    return files[-1] if files else None


def _latest_hits(pattern: str) -> Path | None:
    files = sorted(_HITS_DIR.glob(pattern))
    return files[-1] if files else None


def _latest_tables_root(pattern: str) -> Path | None:
    """Like _latest(), but searches tables/ itself rather than tables/final/ - for
    manually-maintained root-level inputs (e.g. iNDI_inventory_*) that aren't pipeline
    output."""
    files = sorted(_FINAL_DIR.parent.glob(pattern))
    return files[-1] if files else None


def _pmcid_from(s: str) -> str:
    m = re.search(r"PMC\d+", str(s))
    return m.group(0) if m else ""



def join_cellular_model_publications(
    indi_pattern: str = "iNDI_inventory_*",
    scilite_pattern: str = "scilite_annotations_*.tsv",
    pub_pattern: str = "misc_publications_*.tsv",
) -> Path | None:
    """Join cellular models to the publications that mention their variant, via SciLite's
    rs-number annotations, and from there to the study/resource each publication is tied to.

    iNDI inventory's own "dbSNP" column (e.g. "rs387906627") is the join key against
    SciLite's "Accession Numbers" / subType "RefSNP" annotations (Tag Name is the same rs
    number, PMC-ID-scoped) - a match means that paper's text mentions this cell model's
    variant. From the matched PMC ID, Resource Name is then looked up via the publications
    table's own PMC link, giving the study/resource that publication is tied to.

    Adds two columns to a copy of the iNDI inventory (written to tables/final/, the
    original root-level file is never modified):
        - ``Linked Publications`` — semicolon-delimited PMC IDs whose SciLite annotations
          mention this row's dbSNP rs number
        - ``Linked Studies``      — semicolon-delimited Resource Name(s) those publications
          are tied to (via pub_pattern), when resolvable

    Args:
        indi_pattern: Glob (in tables/, not tables/final/ - it's a manually-maintained
            root-level file, not pipeline output) for the cell models inventory.
        scilite_pattern: Glob (in tables/final/) for the SciLite annotations table.
        pub_pattern: Glob (in tables/final/) for the publications-shaped table to resolve
            Resource Name from (default: misc_publications).

    Returns:
        Path to the written cellular_models TSV, or None if the iNDI inventory or SciLite
        annotations weren't found.
    """
    indi_path = _latest_tables_root(indi_pattern)
    if not indi_path:
        logger.error(f"No TSV matching '{indi_pattern}' found in tables/")
        return None

    scilite_path = _latest(scilite_pattern)
    if not scilite_path:
        logger.error(f"No TSV matching '{scilite_pattern}' found in tables/final/")
        return None

    logger.info(f"Loading cell models: {indi_path.name}")
    models = pd.read_csv(indi_path, sep="\t", dtype=str).fillna("")
    logger.info(f"  {len(models)} cell model(s) loaded")

    logger.info(f"Loading SciLite annotations: {scilite_path.name}")
    sc = pd.read_csv(scilite_path, sep="\t", dtype=str).fillna("")
    rs_hits = sc[(sc.get("Type", "") == "Accession Numbers") & (sc.get("subType", "") == "RefSNP")]
    logger.info(f"  {len(rs_hits)} RefSNP annotation row(s) found")

    rs_to_pmcs: dict[str, list[str]] = {}
    for _, row in rs_hits.iterrows():
        rs = row.get("Tag Name", "").strip()
        pmc = row.get("PMC ID", "").strip()
        if not rs or not pmc:
            continue
        pmcs = rs_to_pmcs.setdefault(rs, [])
        if pmc not in pmcs:
            pmcs.append(pmc)

    pmc_to_resources: dict[str, list[str]] = {}
    pub_path = _latest(pub_pattern)
    if pub_path:
        logger.info(f"Loading publications: {pub_path.name}")
        pubs = pd.read_csv(pub_path, sep="\t", dtype=str).fillna("")
        pmc_col = "PubMed Central Link" if "PubMed Central Link" in pubs.columns else "PubMed_Central_Link"
        for _, row in pubs.iterrows():
            pmc = _pmcid_from(row.get(pmc_col, ""))
            resource = row.get("Resource Name", "").strip()
            if not pmc or not resource:
                continue
            # Resource Name is semicolon-multi-valued in misc_publications (one publication
            # can be tied to more than one study) - split it back out.
            for name in (n.strip() for n in resource.split(";")):
                if not name:
                    continue
                names = pmc_to_resources.setdefault(pmc, [])
                if name not in names:
                    names.append(name)
    else:
        logger.warning(f"No TSV matching '{pub_pattern}' found in tables/final/ — "
                        "Linked Studies will be empty")

    def _linked_publications(dbsnp: str) -> str:
        return ";".join(rs_to_pmcs.get(dbsnp.strip(), []))

    def _linked_studies(dbsnp: str) -> str:
        pmcs = rs_to_pmcs.get(dbsnp.strip(), [])
        names: list[str] = []
        for pmc in pmcs:
            for name in pmc_to_resources.get(pmc, []):
                if name not in names:
                    names.append(name)
        return ";".join(names)

    models["Linked Publications"] = models["dbSNP"].apply(_linked_publications)
    models["Linked Studies"] = models["dbSNP"].apply(_linked_studies)
    n_linked = (models["Linked Publications"] != "").sum()
    logger.info(f"[cell-models] {n_linked}/{len(models)} cell model(s) linked to at least one publication")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = _FINAL_DIR / f"cellular_models_{ts}.tsv"
    models.to_csv(output_path, sep="\t", index=False)
    logger.info(f"Cellular models with publication links written → {output_path.name}")
    return output_path


_ANNOTATION_STAGE_TABLES: dict[str, str] = {
    "Datasets": "pub_datasets_*.tsv",
    "Supplementary Files": "pub_supplementary_*.tsv",
    "Grants": "pub_grants_*.tsv",
    "Software": "pub_software_*.tsv",
    "Models": "pub_models_*.tsv",
}


def build_annotation_summary(
    scilite_pattern: str = "scilite_annotations_*.tsv",
    top_n_types: int = 5,
) -> Path:
    """Row counts per pub-metadata stage table, plus SciLite's top annotation types.

    Written as a small fixed-name JSON (not timestamped - always overwritten) so the web
    app's Home page can show an Annotations breakdown without ever fetching the ~270MB
    scilite_annotations table itself just to count it.

    Args:
        scilite_pattern: Glob (in tables/final/) for the SciLite annotations table.
        top_n_types: How many of SciLite's most frequent annotation Types to keep.

    Returns:
        Path to the written annotation_summary.json (stage counts / types default to
        empty when a source table is missing - never raises).
    """
    stages: dict[str, int] = {}
    for label, pattern in _ANNOTATION_STAGE_TABLES.items():
        path = _latest(pattern)
        if not path:
            logger.warning(f"[annotation-summary] no TSV matching '{pattern}' found in tables/final/")
            continue
        stages[label] = sum(1 for _ in open(path, encoding="utf-8")) - 1  # header

    scilite_path = _latest(scilite_pattern)
    scilite_total = 0
    top_types: list[dict] = []
    if scilite_path:
        logger.info(f"[annotation-summary] loading SciLite Type column: {scilite_path.name}")
        types = pd.read_csv(scilite_path, sep="\t", usecols=["Type"], dtype=str)["Type"].fillna("")
        scilite_total = len(types)
        counts = types[types != ""].value_counts().head(top_n_types)
        top_types = [{"type": t, "count": int(n)} for t, n in counts.items()]
    else:
        logger.warning(f"[annotation-summary] no TSV matching '{scilite_pattern}' found in tables/final/")

    summary = {
        "stages": stages,
        "scilite_total": scilite_total,
        "scilite_top_types": top_types,
    }
    output_path = _FINAL_DIR / "annotation_summary.json"
    output_path.write_text(json.dumps(summary, indent=2))
    logger.info(f"[annotation-summary] written -> {output_path.name}: "
                f"stages={stages}, scilite_total={scilite_total}, top_types={top_types}")
    return output_path


_SCILITE_AGGREGATE_DIMENSIONS = ["PMC ID", "Type", "Tag Name", "Exact", "Section", "Provider", "Tag URI"]


def build_scilite_type_aggregate(scilite_pattern: str = "scilite_annotations_*.tsv") -> Path | None:
    """Per-annotation-concept counts, written as a small fixed-name TSV.

    The Connections page needs to filter/connect on SciLite annotations without ever loading
    scilite_annotations_*.tsv itself (~270MB, ~956k rows). This aggregate (grouped by
    _SCILITE_AGGREGATE_DIMENSIONS - ~400k rows, ~65MB) is what it loads instead: one row per
    distinct (PMC ID, Type, Tag Name, Exact, Section, Provider, Tag URI) combination actually
    seen, with a Count of how many raw rows collapsed into it. Prefix/Postfix/Annotation ID
    are deliberately excluded - Prefix/Postfix are the literal free-text sentence context
    around each mention (near-unique per row, so keeping them would balloon this back toward
    the full raw table with none of the size saved), and Annotation ID is a per-mention URL
    that's unique by construction.

    Args:
        scilite_pattern: Glob (in tables/final/) for the SciLite annotations table.

    Returns:
        Path to the written scilite_pmc_type_counts.tsv, or None if no SciLite table
        was found.
    """
    scilite_path = _latest(scilite_pattern)
    if not scilite_path:
        logger.error(f"No TSV matching '{scilite_pattern}' found in tables/final/")
        return None

    logger.info(f"[scilite-aggregate] loading {_SCILITE_AGGREGATE_DIMENSIONS} columns: {scilite_path.name}")
    sc = pd.read_csv(scilite_path, sep="\t", usecols=_SCILITE_AGGREGATE_DIMENSIONS, dtype=str).fillna("")
    sc = sc[(sc["PMC ID"] != "") & (sc["Type"] != "")]
    agg = sc.groupby(_SCILITE_AGGREGATE_DIMENSIONS).size().reset_index(name="Count")

    output_path = _FINAL_DIR / "scilite_pmc_type_counts.tsv"
    agg.to_csv(output_path, sep="\t", index=False)
    logger.info(f"[scilite-aggregate] {len(agg)} row(s) written -> {output_path.name}")
    return output_path


def build_misc_publications(combine_hits_path: Path | None = None,
                             pub_verification_path: Path | None = None) -> Path | None:
    """Join pub_verification's vLLM-based verdicts into a copy of combine_hits.tsv.

    Overwrites Verification Status/Rationale with the new verdicts - Claim Text is left
    untouched (from whichever earlier method populated it; pub_verification's own claim_text
    isn't merged in, only verification_status/rationale, per how this table's meant to be
    used). The original combine_hits file is never modified; this writes a new
    tables/hits/misc_publications_{ts}.tsv, reusing the Publications row shape.

    Args:
        combine_hits_path: combine_hits_*.tsv to enrich (default: latest in tables/hits/).
        pub_verification_path: pub_verification_*.tsv to join in (default: latest in
            tables/hits/).

    Returns:
        Path to the written misc_publications TSV, or None if either input is missing.
    """
    from staging.validate_fetched_publications import _resolve_doc_id

    combine_hits_path = combine_hits_path or _latest_hits("combine_hits_*.tsv")
    pub_verification_path = pub_verification_path or _latest_hits("pub_verification_*.tsv")
    if not combine_hits_path:
        logger.error("No combine_hits TSV found in tables/hits/")
        return None
    if not pub_verification_path:
        logger.error("No pub_verification TSV found in tables/hits/")
        return None

    logger.info(f"Loading combine_hits: {combine_hits_path.name}")
    combine_hits = pd.read_csv(combine_hits_path, sep="\t", dtype=str).fillna("")
    logger.info(f"  {len(combine_hits)} rows loaded")

    logger.info(f"Loading pub_verification: {pub_verification_path.name}")
    verification = pd.read_csv(pub_verification_path, sep="\t", dtype=str).fillna("")
    logger.info(f"  {len(verification)} rows loaded")

    v_lookup = {
        (row["resource_name"], row["doc_id"]): row
        for row in verification.to_dict("records")
    }

    result = combine_hits.copy()
    n_matched = 0
    for idx, row in result.iterrows():
        doc_id = _resolve_doc_id(row.to_dict())
        if not doc_id:
            continue
        v = v_lookup.get((row.get("Resource Name", ""), doc_id))
        if v:
            result.at[idx, "Verification Status"] = v["verification_status"]
            result.at[idx, "Rationale"] = v["rationale"]
            n_matched += 1
    logger.info(f"Matched {n_matched}/{len(result)} combine_hits row(s) to a verification verdict")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = _HITS_DIR / f"misc_publications_{ts}.tsv"
    result.to_csv(output_path, sep="\t", index=False)
    logger.info(f"misc_publications written → {output_path.name}")

    _log_query_method_performance(result)
    return output_path


_NEW_CORPUS_FAMILY_RE = re.compile(r"^new_corpus\.(.+)\[\d+\]$")
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+")


_BARE_PMID_RE = re.compile(r"^\d{7,9}$")


def _extract_doc_ref(cell: str) -> dict | None:
    """Best-effort PMC ID / DOI / PMID extraction from one new_corpus.<page>[i] cell.

    Cells are inconsistently shaped across scraped sites - a bare PMC ID, a bare DOI, a
    bare numeric PMID, or (for sites whose citation JSON got flattened into a scalar by
    data_gatherer) an HTML-entity-escaped fragment that can contain a DOI and a pubmed URL
    together. DOI is checked before treating anything as a bare PMID - reversed, a garbled
    cell with both would be misclassified as PMID-only.

    Returns:
        {"PubMed Central Link": ...} or {"DOI": ...} for an immediately fetchable cell;
        {"PMID": ...} for a bare PMID - not directly fetchable (_row_fetch_url() in
        validate_fetched_publications.py has no PMID branch), so the caller batches these
        through _fetch_pmid_metadata() to resolve a DOI/PMC link (or, failing that, at
        least an Abstract) before deciding whether to keep the row; None if nothing usable
        matches, so the caller can drop the cell.
    """
    value = html.unescape(str(cell)).strip()
    if not value:
        return None
    pmcid = _pmcid_from(value)
    if pmcid:
        return {"PubMed Central Link": f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"}
    m = _DOI_RE.search(value)
    if m:
        return {"DOI": m.group(0).rstrip(".,;\"')<")}
    if _BARE_PMID_RE.match(value):
        return {"PMID": value}
    return None


def _fetch_pmid_metadata(pmids: list[str], ncbi_api_key: str | None = None) -> dict[str, dict]:
    """Batch-resolve bare PMIDs via NCBI efetch, reusing scrape_publications.py's own
    standard pubmed_search machinery (_fetch_and_parse_batch/extract_article_details -
    the same efetch call that already backs the original/v2/v3/v4 query methods).

    Lets a PMID-only new_corpus reference upgrade to a DOI- or PMC-linked row (so it merges
    correctly with any other row for the same paper via combine_query_method_hits' identity
    matching, rather than surviving as an untethered duplicate) or, when PubMed has neither
    on file, at least attaches an Abstract so fetch_abstract_only()'s own fallback has real
    text to verify against instead of nothing.

    Args:
        pmids: Distinct bare PMIDs to resolve.
        ncbi_api_key: Raises the NCBI rate limit from 3/s to 10/s if given.

    Returns:
        {pmid: {"PMID", "Title", "Abstract", "Authors", "Affiliations", "Keywords",
        "PubMed Central Link", "DOI", "Publication Date"}} - only for PMIDs PubMed
        actually has a record for.
    """
    if not pmids:
        return {}
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scrapers"))
    from scrape_publications import _fetch_and_parse_batch

    suffix = f"&api_key={ncbi_api_key}" if ncbi_api_key else ""
    records = _fetch_and_parse_batch(pmids, suffix)
    logger.info(f"[new_corpus] efetch'd {len(records)}/{len(pmids)} bare-PMID reference(s)")
    return {r["PMID"]: r for r in records if r.get("PMID")}


def _build_url_to_resource_map(inventory_path: Path) -> dict[str, dict]:
    """Map every Access URL / Alternative URL (trailing slash stripped) to its resource's
    Name/Abbreviation - the fallback join for new_corpus tables predating
    pipelines/page_navigation.py's own Resource Name/Abbreviation pass-through fix."""
    inv = pd.read_csv(inventory_path, sep="\t", dtype=str).fillna("")
    mapping: dict[str, dict] = {}
    for _, row in inv.iterrows():
        info = {"Resource Name": row.get("Resource Name", ""), "Abbreviation": row.get("Abbreviation", "")}
        access = row.get("Access URL", "").strip().rstrip("/")
        if access:
            mapping[access] = info
        alt_raw = row.get("Alternative URLs", "").strip()
        if alt_raw:
            try:
                alt_list = ast.literal_eval(alt_raw) if isinstance(alt_raw, str) else []
            except (ValueError, SyntaxError):
                alt_list = []
            for u in alt_list:
                u = str(u).strip().rstrip("/")
                if u:
                    mapping[u] = info
    return mapping


def resolve_missing_pmcids(df: pd.DataFrame, ncbi_api_key: str | None = None) -> pd.DataFrame:
    """Fill in PubMed Central Link for every row that has a DOI but no PMC link, via NCBI's
    ID Converter API - the purpose-built DOI/PMID/PMCID crosswalk (unlike
    _fetch_pmid_metadata's efetch, which only accepts a PMID). Both pub_jobs (full-text
    fetch prefers PMC) and scilite (Europe PMC's own annotation API is PMC-ID-keyed) need a
    PMC ID to do anything useful with these rows.

    Falls back to an exact, normalized-Title match against another row in the same
    DataFrame that already has a PMC link, for DOIs idconv has nothing for (e.g. a preprint
    with no PMC deposit) - deliberately not fuzzy/partial matching, and only for titles long
    enough (>20 normalized chars) to not risk collapsing two different papers that happen to
    share a short, generic title.

    Resolving into the same "PubMed Central Link" field _row_identity_keys() (in
    combine_hits.py) already matches on - rather than a bespoke lookup - means a row found
    only by its DOI and another row already carrying that same paper's real PMC ID collapse
    into one the next time combine_query_method_hits() runs, instead of surviving as an
    untethered duplicate.

    Args:
        df: combine_hits-shaped rows (needs DOI, PubMed Central Link, Title columns).
        ncbi_api_key: Passed through to the idconv query (raises the NCBI rate limit).

    Returns:
        Copy of df with PubMed Central Link filled in wherever resolvable.
    """
    if "DOI" not in df.columns or "PubMed Central Link" not in df.columns:
        return df

    df = df.copy()
    has_pmc = df["PubMed Central Link"].fillna("").str.strip() != ""
    has_doi = df["DOI"].fillna("").str.strip() != ""
    needs_lookup = df[~has_pmc & has_doi]
    dois = sorted(needs_lookup["DOI"].unique())
    if not dois:
        logger.info("[pmcid-resolve] no DOI-only rows to resolve")
        return df

    import requests
    suffix = f"&api_key={ncbi_api_key}" if ncbi_api_key else ""
    doi_to_pmcid: dict[str, str] = {}
    batch_size = 200  # idconv's documented per-request cap
    for i in range(0, len(dois), batch_size):
        batch = dois[i:i + batch_size]
        url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={','.join(batch)}&format=json{suffix}"
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            for rec in resp.json().get("records", []):
                if rec.get("pmcid") and rec.get("doi"):
                    doi_to_pmcid[rec["doi"]] = rec["pmcid"]
        except Exception as e:
            logger.warning(f"[pmcid-resolve] idconv batch {i}-{i + len(batch)} failed: {e}")

    n_via_doi = 0
    for idx in needs_lookup.index:
        pmcid = doi_to_pmcid.get(df.at[idx, "DOI"])
        if pmcid:
            df.at[idx, "PubMed Central Link"] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
            n_via_doi += 1
    logger.info(f"[pmcid-resolve] resolved {n_via_doi}/{len(dois)} DOI(s) -> PMC ID via idconv")

    if "Title" in df.columns:
        def _norm_title(t: str) -> str:
            return re.sub(r"[^a-z0-9]+", "", str(t).lower())

        title_to_pmc = {}
        for _, row in df.iterrows():
            link = str(row.get("PubMed Central Link", "")).strip()
            key = _norm_title(row.get("Title", ""))
            if link and len(key) > 20:
                title_to_pmc.setdefault(key, link)

        has_pmc = df["PubMed Central Link"].fillna("").str.strip() != ""
        still_missing = df[~has_pmc & has_doi]
        n_via_title = 0
        for idx in still_missing.index:
            key = _norm_title(df.at[idx, "Title"]) if "Title" in df.columns else ""
            if len(key) > 20 and key in title_to_pmc:
                df.at[idx, "PubMed Central Link"] = title_to_pmc[key]
                n_via_title += 1
        logger.info(f"[pmcid-resolve] resolved {n_via_title} more via exact title match")

    return df


def extract_new_corpus_publications(
    new_corpus_path: Path | None = None,
    inventory_path: Path | None = None,
    ncbi_api_key: str | None = None,
) -> pd.DataFrame:
    """Explode a new_corpus table's per-page ``new_corpus.<url>[i]`` columns into one row
    per (resource, discovered publication reference), in combine_hits shape, tagged
    ``Fetched With = "page navigation: <page url>"`` - the specific page the reference was
    found on (not source_url_for_metadata, which is the resource's own entry-point page and
    typically a different, less specific URL).

    Resource Name/Abbreviation are read directly if the table already has them (added going
    forward by pipelines/page_navigation.py); otherwise falls back to joining
    source_url_for_metadata/dataset_webpage against the resource inventory's Access URL/
    Alternative URLs. Cells with no extractable doc identifier are dropped and counted; for
    legacy tables (no Resource Name column), rows with no inventory match are also dropped
    and counted - both are logged, never silently absorbed into "covered everything".

    Bare PMIDs (no PMC/DOI directly in the cell - confirmed on real data to be ~29% of
    everything page navigation finds, not noise) are batch-resolved via
    _fetch_pmid_metadata() rather than dropped: a PMID that PubMed also lists a DOI or PMC
    ID for is upgraded to that identifier, so it naturally merges with any other row for the
    same paper once this table is combined via combine_query_method_hits() (matching on
    shared PMID/DOI/PMC ID/Paperclip Doc ID - the dedup already happens there, not here).
    Only a PMID efetch can't resolve at all (not in PubMed) is dropped.

    Args:
        new_corpus_path: new_corpus_*.tsv to read (default: latest in tables/final/).
        inventory_path: resources-inventory-* file for the legacy URL->resource fallback
            join (default: latest in tables/, via validate_fetched_publications' own finder).
        ncbi_api_key: Passed through to _fetch_pmid_metadata (raises the NCBI rate limit).

    Returns:
        DataFrame with Resource Name, Abbreviation, Diseases Included, Coarse/Granular Data
        Modality, Fetched With, PMID/DOI/PubMed Central Link (whichever were resolved), and
        - for efetch-resolved rows only - Title/Abstract/Authors/Affiliations/Keywords/
        Publication Date. One row per discovered reference. Empty if nothing extractable.
    """
    new_corpus_path = new_corpus_path or _latest("new_corpus_*.tsv")
    if not new_corpus_path:
        logger.error("No new_corpus TSV found in tables/final/")
        return pd.DataFrame()

    df = pd.read_csv(new_corpus_path, sep="\t", dtype=str).fillna("")
    logger.info(f"[new_corpus] loaded {len(df)} rows from {new_corpus_path.name}")

    has_resource_name = "Resource Name" in df.columns
    url_to_resource: dict[str, dict] = {}
    if not has_resource_name:
        from staging.validate_fetched_publications import _find_latest_inventory
        inventory_path = inventory_path or _find_latest_inventory()
        if inventory_path:
            url_to_resource = _build_url_to_resource_map(inventory_path)
        else:
            logger.warning("[new_corpus] no Resource Name column and no inventory found - "
                            "every row will be dropped for missing resource identity")

    family_cols: dict[str, list[str]] = {}
    for col in df.columns:
        m = _NEW_CORPUS_FAMILY_RE.match(col)
        if m:
            family_cols.setdefault(m.group(1), []).append(col)

    lookup_col = "source_url_for_metadata" if "source_url_for_metadata" in df.columns else (
        "dataset_webpage" if "dataset_webpage" in df.columns else None
    )

    rows = []
    pending_pmid_rows = []  # rows still needing efetch resolution before being kept/dropped
    n_no_ref = 0
    n_no_resource = 0
    for _, row in df.iterrows():
        if has_resource_name:
            resource_name = row.get("Resource Name", "")
            abbreviation = row.get("Abbreviation", "")
        else:
            key = row.get(lookup_col, "").strip().rstrip("/") if lookup_col else ""
            match = url_to_resource.get(key)
            if not match:
                n_no_resource += 1
                continue
            resource_name = match.get("Resource Name", "")
            abbreviation = match.get("Abbreviation", "")

        base = {
            "Resource Name": resource_name,
            "Abbreviation": abbreviation,
            "Diseases Included": row.get("diseases_included", ""),
            "Coarse Data Modality": row.get("coarse_data_modality", ""),
            "Granular Data Modality": row.get("granular_data_modality", ""),
        }
        for page_url, cols in family_cols.items():
            for col in cols:
                cell = row.get(col, "")
                if not cell.strip():
                    continue
                ref = _extract_doc_ref(cell)
                if ref is None:
                    n_no_ref += 1
                    continue
                out = {**base, "Fetched With": f"page navigation: {page_url}", **ref}
                if "PMID" in ref and len(ref) == 1:
                    pending_pmid_rows.append(out)
                else:
                    rows.append(out)

    if pending_pmid_rows:
        distinct_pmids = sorted({r["PMID"] for r in pending_pmid_rows})
        metadata = _fetch_pmid_metadata(distinct_pmids, ncbi_api_key=ncbi_api_key)
        n_unresolved = 0
        for pending in pending_pmid_rows:
            fetched = metadata.get(pending["PMID"])
            if not fetched:
                n_unresolved += 1
                continue
            resolved = dict(pending)
            for key in ("PubMed Central Link", "DOI", "Title", "Abstract",
                        "Authors", "Affiliations", "Keywords", "Publication Date"):
                if fetched.get(key):
                    resolved[key] = fetched[key]
            rows.append(resolved)
        logger.info(f"[new_corpus] resolved {len(pending_pmid_rows) - n_unresolved}/{len(pending_pmid_rows)} "
                    f"bare-PMID reference(s) via efetch ({n_unresolved} not found in PubMed - dropped)")

    result = pd.DataFrame(rows)
    msg = f"[new_corpus] extracted {len(result)} publication reference(s); dropped {n_no_ref} unparseable cell(s)"
    if not has_resource_name:
        msg += f", {n_no_resource} row(s) with no resource match"
    logger.info(msg)
    return result


_REAL_VERDICTS = {"confirmed", "not_confirmed", "insufficient_evidence"}


def compute_query_method_performance(df: pd.DataFrame) -> pd.DataFrame:
    """Per-query-method performance from an already-built misc_publications DataFrame
    (Fetched With + Verification Status columns required) - the single source of truth
    for both the logged summary table and any chart built from it.

    Query methods are recovered from Fetched With via
    validate_fetched_publications._query_methods, with "other"-tagged rows (predating the
    tagging fix) resolved against the pre-merge q1-q4 experiment files.

    Returns:
        DataFrame with one row per method:
        - candidates: total (resource, doc) pairs this method surfaced (requiring
          validation), including ones that never got a real verdict (error/blank/PENDING).
        - adjudicated: of those, how many actually got a real verdict (confirmed /
          not_confirmed / insufficient_evidence) - excludes failed LLM calls and rows this
          join never matched, which never got a chance to be confirmed at all.
        - confirmed: distinct confirmed publications this method retrieved.
        - precision_pct: confirmed / adjudicated (NOT / candidates - a method with a lot of
          failed-call noise shouldn't look less precise for it).
        - pooled_recall_pct: confirmed / (confirmed-by-any-method union) - this method's
          share of the total discoverable confirmed set.
        - exclusive_confirmed: confirmed pairs *no other method* also confirmed - this
          method's non-redundant contribution, lost entirely if it were dropped. Not
          comparable to pooled_recall_pct's numerator (confirmed) - it's a much stricter
          subset, by design.
        - resource_coverage_pct: % of all resources this method confirmed at least one
          publication for.
    """
    from staging.validate_fetched_publications import _query_methods, _load_pre_merge_method_index, _EXPERIMENTS_DIR
    from staging.combine_hits import _row_identity_keys

    pre_merge_index = _load_pre_merge_method_index(_EXPERIMENTS_DIR)
    total_resources = df["Resource Name"].nunique()

    records = []
    for row in df.to_dict("records"):
        methods = _query_methods(row.get("Fetched With", ""))
        if "other" in methods:
            resolved = set()
            for key in _row_identity_keys(row):
                resolved.update(pre_merge_index.get(key, set()))
            if resolved:
                methods = (methods - {"other"}) | resolved
        records.append({
            "resource": row.get("Resource Name", ""),
            "status": row.get("Verification Status", ""),
            "methods": methods,
        })

    confirmed = [r for r in records if r["status"] == "confirmed"]
    total_confirmed = len(confirmed)
    methods_all = sorted({m for r in records for m in r["methods"]})

    rows = []
    for m in methods_all:
        resources_confirmed_by_m = {r["resource"] for r in confirmed if m in r["methods"]}
        res_cov = 100 * len(resources_confirmed_by_m) / total_resources if total_resources else 0

        found_by_m = [r for r in confirmed if m in r["methods"]]
        pooled_recall = 100 * len(found_by_m) / total_confirmed if total_confirmed else 0

        exclusive_confirmed = sum(1 for r in confirmed if r["methods"] == {m})

        m_total = sum(1 for r in records if m in r["methods"])
        m_adjudicated = sum(1 for r in records if m in r["methods"] and r["status"] in _REAL_VERDICTS)
        precision = 100 * len(found_by_m) / m_adjudicated if m_adjudicated else 0

        rows.append({
            "method": m,
            "candidates": m_total,
            "adjudicated": m_adjudicated,
            "confirmed": len(found_by_m),
            "precision_pct": precision,
            "pooled_recall_pct": pooled_recall,
            "exclusive_confirmed": exclusive_confirmed,
            "resources_covered": len(resources_confirmed_by_m),
            "resource_coverage_pct": res_cov,
        })

    return pd.DataFrame(rows)


def _log_query_method_performance(df: pd.DataFrame) -> None:
    """Log compute_query_method_performance()'s table in decision-oriented column order."""
    perf = compute_query_method_performance(df)
    total_resources = df["Resource Name"].nunique()

    logger.info("Query method performance (decision-oriented):")
    header = (f"{'Method':12s}{'ResCoverage%':>13s}{'PooledRecall%':>15s}"
              f"{'ExclConf':>10s}{'Precision%':>12s}{'Confirmed':>11s}"
              f"{'Adjudicat.':>11s}{'Candidates':>12s}")
    logger.info(header)
    for row in perf.to_dict("records"):
        logger.info(f"{row['method']:12s}{row['resource_coverage_pct']:>12.1f}%"
                    f"{row['pooled_recall_pct']:>14.1f}%{row['exclusive_confirmed']:>10d}"
                    f"{row['precision_pct']:>11.1f}%{row['confirmed']:>11d}"
                    f"{row['adjudicated']:>11d}{row['candidates']:>12d}")

    logger.info(f"{total_resources} distinct resource(s) total")
