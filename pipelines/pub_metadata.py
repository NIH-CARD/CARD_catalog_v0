"""
Stage 4 — Publication metadata extraction (datasets + supplementary files).

Uses ``data_gatherer.DataGatherer.process_articles()`` to extract dataset
mentions and supplementary file mentions from PMC articles.

- Dataset mentions → ``tables/hits/pub_datasets_{ts}.tsv``
- Supplementary files → ``tables/hits/pub_supplementary_{ts}.tsv``

The ``output_path`` arg is the datasets output; the supplementary path is
derived by replacing ``pub_datasets`` with ``pub_supplementary`` in the stem.

Input: ``tables/hits/pubmed_hits_{ts}.tsv`` (reads ``PubMed Central Link`` col)
"""
import logging
import os
from pathlib import Path

import pandas as pd

from pipelines.base import PipelineStage

logger = logging.getLogger(__name__)


class PubMetadataStage(PipelineStage):
    def run(
        self,
        input_path: Path,
        output_path: Path,
        *,
        anthropic_key: str | None = None,
        verbose: bool = False,
    ) -> Path:
        from data_gatherer.data_gatherer import DataGatherer
        from data_gatherer.llm.response_schema import (
            Dataset_w_Context,
            SupplementaryFileKeywords,
        )

        if anthropic_key:
            os.environ.setdefault("ANTHROPIC_API_KEY", anthropic_key)

        log_level = "DEBUG" if verbose else "INFO"

        # Derive supplementary output path from datasets output path
        supp_path = output_path.parent / output_path.name.replace(
            "pub_datasets", "pub_supplementary"
        )

        # Load PMC links from pubmed hits
        pubs_df = pd.read_csv(input_path, sep="\t")
        pmc_links = (
            pubs_df["PubMed Central Link"]
            .dropna()
            .loc[lambda s: s.str.strip() != ""]
            .unique()
            .tolist()
        )
        logger.info(f"[pub_metadata] {len(pmc_links)} PMC links to process")

        if not pmc_links:
            logger.warning("[pub_metadata] no PMC links found — skipping")
            return output_path

        # --- Dataset mentions ---
        logger.info("[pub_metadata] extracting dataset mentions")
        dg = DataGatherer(log_level=log_level)
        datasets_raw = dg.process_articles(
            pmc_links,
            response_format=Dataset_w_Context,
            return_df_joint=True,
        )
        if datasets_raw is not None and not datasets_raw.empty:
            datasets_raw["_schema"] = "Dataset_w_Context"
            datasets_raw.to_csv(output_path, sep="\t", index=False)
            logger.info(f"[pub_metadata] datasets → {output_path.name} ({len(datasets_raw)} rows)")
        else:
            logger.warning("[pub_metadata] no dataset mentions found")

        # --- Supplementary files ---
        logger.info("[pub_metadata] extracting supplementary file mentions")
        dg_supp = DataGatherer(log_level=log_level)
        supp_raw = dg_supp.process_articles(
            pmc_links,
            response_format=SupplementaryFileKeywords,
            section_filter="supplementary_material",
            return_df_joint=True,
        )
        if supp_raw is not None and not supp_raw.empty:
            supp_raw["_schema"] = "SupplementaryFileKeywords"
            supp_raw.to_csv(supp_path, sep="\t", index=False)
            logger.info(f"[pub_metadata] supplementary → {supp_path.name} ({len(supp_raw)} rows)")
        else:
            logger.warning("[pub_metadata] no supplementary file mentions found")

        return output_path
