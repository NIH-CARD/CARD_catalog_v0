"""
Stage 7 — PubTator3 annotations (NCBI).

Fetches normalised entities (NCBI Gene, MeSH, rsID, …) and typed, scored
relations from the PubTator3 API for each publication surfaced by the
pubmed_search stage (by PMID, or by PMC ID when a paper has no PMID).

Input:  ``tables/hits/pubmed_hits_{ts}.tsv`` or ``misc_publications_confirmed_{ts}.tsv``
        (reads ``PMID`` and ``PubMed Central Link``)
Output: ``tables/hits/pubtator_entities_{ts}.tsv`` — one row per (paper, entity)
        ``tables/hits/pubtator_relations_{ts}.tsv`` — one row per relation (sibling file)
"""
import logging
import sys
from pathlib import Path

import pandas as pd

from pipelines.base import PipelineStage, redact_secrets

logger = logging.getLogger(__name__)

SCRAPERS_DIR = Path(__file__).parent.parent / "scrapers"


def relations_path_for(entities_path: Path) -> Path:
    """Sibling relations TSV path for a ``pubtator_entities_{ts}.tsv`` path."""
    return entities_path.with_name(entities_path.name.replace("pubtator_entities_", "pubtator_relations_"))


class PubTatorStage(PipelineStage):
    def run(
        self,
        input_path: Path,
        output_path: Path,
        *,
        full_text: bool = True,
        batch_size: int = 100,
        pause: float = 0.4,
        verbose: bool = False,
        log_file: Path | None = None,
    ) -> Path:
        args = {k: v for k, v in locals().items() if k not in ("self", "input_path", "output_path")}
        logger.info(f"run called with input_path={input_path}, output_path={output_path}, args={redact_secrets(args)}")
        if str(SCRAPERS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRAPERS_DIR))
        from scrape_pubtator import load_ids, pmcid_lookup, scrape

        pubs_df = pd.read_csv(input_path, sep="\t", dtype=str).fillna("")
        pmids, pmc_only = load_ids(pubs_df)
        logger.info(f"Loaded {len(pubs_df)} rows from {input_path.name}: "
                    f"{len(pmids)} PMIDs, {len(pmc_only)} PMC-only papers")
        if not pmids and not pmc_only:
            logger.warning("no PMIDs or PMC IDs found — skipping")
            return output_path

        try:
            entities, relations = scrape(
                pmids, pmc_only, full_text=full_text, batch_size=batch_size, pause=pause,
                pmcids=pmcid_lookup(pubs_df),
            )
        except Exception as e:
            logger.error(f"PubTator3 scrape failed: {e}", exc_info=True)
            return output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        entities.to_csv(output_path, sep="\t", index=False)
        logger.info(f"Wrote {len(entities)} rows → {output_path.name} "
                    f"({entities['PMID'].replace('', pd.NA).nunique()} papers)")

        rel_path = relations_path_for(output_path)
        relations.to_csv(rel_path, sep="\t", index=False)
        logger.info(f"Wrote {len(relations)} rows → {rel_path.name}")

        return output_path
