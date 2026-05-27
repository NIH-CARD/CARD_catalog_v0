"""
Post-normalization annotation join: joins SciLite bioentity annotations
(diseases, genes, chemicals) and cited dataset identifiers from pub_datasets
into the publications table.

Called automatically by the orchestrator as the final pipeline step, or
manually via::

    python -m staging.join_annotations
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_FINAL_DIR = Path(__file__).parent.parent / "tables" / "final"

_SCILITE_TYPE_TO_COLUMN = {
    "Diseases": "Diseases (Annotated)",
    "Gene_Proteins": "Genes / Proteins",
    "Chemicals": "Chemicals",
}


def _latest(pattern: str) -> Path | None:
    files = sorted(_FINAL_DIR.glob(pattern))
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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    join_annotations()
