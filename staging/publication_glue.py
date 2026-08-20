"""
Publication glue: "publications as glue for scientific artefacts" (see
staging/validate_fetched_publications.py's verification prompt) - this module
enriches an already publication-shaped table with columns computed by a
separate downstream process, keyed by (resource, doc). Two such joins live
here:

- join_annotations(): joins SciLite bioentity annotations (diseases, genes,
  chemicals) and cited dataset identifiers from pub_datasets into the
  publications table, in place.
- build_misc_publications(): joins pub_verification's vLLM-based verdicts
  into a copy of combine_hits.tsv (misc_publications_*.tsv), leaving the
  original combine_hits file untouched.

Not staging/combine_hits.py's job: that one deduplicates/collapses multiple
raw hits files sharing the same schema (Union-Find row-matching) before
anything is finalized - a different operation from enriching an
already-shaped table with derived columns.

Called automatically by the orchestrator as the final pipeline step, or
manually via::

    python -m staging.publication_glue
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_FINAL_DIR = Path(__file__).parent.parent / "tables" / "final"
_HITS_DIR = Path(__file__).parent.parent / "tables" / "hits"

_SCILITE_TYPE_TO_COLUMN = {
    "Diseases": "Diseases (Annotated)",
    "Gene_Proteins": "Genes / Proteins",
    "Chemicals": "Chemicals",
}


def _latest(pattern: str) -> Path | None:
    files = sorted(_FINAL_DIR.glob(pattern))
    return files[-1] if files else None


def _latest_hits(pattern: str) -> Path | None:
    files = sorted(_HITS_DIR.glob(pattern))
    return files[-1] if files else None


def _pmcid_from(s: str) -> str:
    m = re.search(r"PMC\d+", str(s))
    return m.group(0) if m else ""


def join_annotations() -> Path | None:
    """Join SciLite annotations and pub_datasets into the publications TSV.

    Adds columns:
        - ``Diseases (Annotated)`` — semicolon-delimited Tag Names (type=Diseases)
        - ``Genes / Proteins``     — semicolon-delimited Tag Names (type=Gene_Proteins)
        - ``Chemicals``            — semicolon-delimited Tag Names (type=Chemicals)
        - ``Cited Datasets``       — semicolon-delimited dataset identifiers

    Returns:
        Path to the updated publications TSV, or None if publications file not found.
    """
    pub_path = _latest("pubmed_central_*.tsv")
    if not pub_path:
        logger.error("No publications TSV found in tables/final/")
        return None

    logger.info(f"Loading publications: {pub_path.name}")
    pubs = pd.read_csv(pub_path, sep="\t", dtype=str).fillna("")
    logger.info(f"  {len(pubs)} publications loaded")

    # --- SciLite join ---
    scilite_path = _latest("scilite_annotations_*.tsv")
    for col in _SCILITE_TYPE_TO_COLUMN.values():
        pubs[col] = ""

    if scilite_path:
        logger.info(f"Loading SciLite annotations: {scilite_path.name}")
        sc = pd.read_csv(scilite_path, sep="\t", dtype=str).fillna("")
        logger.info(f"  {len(sc)} annotation rows loaded")

        # Build PMC → type → ordered unique Tag Names
        pmc_type_names: dict[str, dict[str, list[str]]] = {}
        for _, row in sc.iterrows():
            pmc = row.get("PMC ID", "")
            ann_type = row.get("Type", "")
            name = row.get("Tag Name", "").strip()
            if not pmc or ann_type not in _SCILITE_TYPE_TO_COLUMN or not name:
                continue
            entry = pmc_type_names.setdefault(pmc, {})
            names_list = entry.setdefault(ann_type, [])
            if name not in names_list:
                names_list.append(name)

        pmc_col = "PubMed Central Link" if "PubMed Central Link" in pubs.columns else "PubMed_Central_Link"
        for col_type, out_col in _SCILITE_TYPE_TO_COLUMN.items():
            pubs[out_col] = pubs[pmc_col].apply(
                lambda link, t=col_type: ";".join(
                    pmc_type_names.get(_pmcid_from(link), {}).get(t, [])
                )
            )
    else:
        logger.warning("No SciLite annotations TSV found — annotation columns will be empty")

    # --- Pub datasets join ---
    datasets_path = _latest("pub_datasets_*.tsv")
    pubs["Cited Datasets"] = ""

    if datasets_path:
        logger.info(f"Loading pub_datasets: {datasets_path.name}")
        ds = pd.read_csv(datasets_path, sep="\t", dtype=str).fillna("")
        logger.info(f"  {len(ds)} dataset rows loaded")

        pmc_datasets: dict[str, list[str]] = {}
        src_col = "source_url" if "source_url" in ds.columns else "Source_URL"
        id_col = "dataset_identifier" if "dataset_identifier" in ds.columns else "Dataset_Identifier"
        for _, row in ds.iterrows():
            pmc = _pmcid_from(row.get(src_col, ""))
            did = str(row.get(id_col, "")).strip()
            if not pmc or not did:
                continue
            ids = pmc_datasets.setdefault(pmc, [])
            if did not in ids:
                ids.append(did)

        pmc_col = "PubMed Central Link" if "PubMed Central Link" in pubs.columns else "PubMed_Central_Link"
        pubs["Cited Datasets"] = pubs[pmc_col].apply(
            lambda link: ";".join(pmc_datasets.get(_pmcid_from(link), []))
        )
    else:
        logger.warning("No pub_datasets TSV found — Cited Datasets column will be empty")

    pubs.to_csv(pub_path, sep="\t", index=False)
    logger.info(f"Enriched publications written → {pub_path.name}")
    return pub_path


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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    join_annotations()
