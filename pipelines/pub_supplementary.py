"""
Stage 4b — Publication supplementary-file mention extraction.

Uses ``data_gatherer.DataGatherer.process_articles()`` (synchronous path) to
extract supplementary-file mentions from PMC articles.

Input:  ``tables/hits/pubmed_hits_{ts}.tsv`` (reads ``PubMed Central Link`` col)
Output: ``tables/hits/pub_supplementary_{ts}.tsv``

Runs concurrently with pub_datasets/pub_grants/pub_software (see
orchestrator.py::run_stages_concurrently) — each is fully independent so
there's no shared mutable state between them.
"""
import logging
import os
from pathlib import Path

import pandas as pd

from pipelines.base import PipelineStage, redact_secrets
from pipelines.pub_metadata_shared import load_pmc_links
from staging.cache_utils import combine_cached_and_new, latest_final

logger = logging.getLogger(__name__)


class PubSupplementaryStage(PipelineStage):
    def run(
        self,
        input_path: Path,
        output_path: Path,
        *,
        anthropic_key: str | None = None,
        verbose: bool = False,
        log_file: Path | None = None,
        use_cache: bool = True,
        fetch_cache_path: Path | None = None,
    ) -> Path:
        args = {k: v for k, v in locals().items() if k not in ("self", "input_path", "output_path")}
        logger.info(f"run called with input_path={input_path}, output_path={output_path}, args={redact_secrets(args)}")
        from data_gatherer.data_gatherer import DataGatherer
        from data_gatherer.llm.response_schema import supplementary_files_keywords_schema

        if anthropic_key:
            os.environ.setdefault("ANTHROPIC_API_KEY", anthropic_key)

        log_level = "DEBUG" if verbose else "INFO"
        log_file_str = str(log_file) if log_file else None
        fetch_cache_str = str(fetch_cache_path) if fetch_cache_path else None

        pmc_links = load_pmc_links(input_path)
        logger.info(f"{len(pmc_links)} PMC links to process")
        if not pmc_links:
            logger.warning("no PMC links found — skipping")
            return output_path

        logger.info("Extracting supplementary file mentions")
        cached_supp_df = None
        if use_cache:
            prev = latest_final("pub_supplementary_*.tsv")
            if prev:
                cached_supp_df = pd.read_csv(prev, sep="\t", dtype=str).fillna("")
        known_urls = set(cached_supp_df["source_url"].unique()) if cached_supp_df is not None else set()
        new_pmc_links = [u for u in pmc_links if u not in known_urls]
        if cached_supp_df is not None:
            logger.info(
                f"supplementary: {len(pmc_links) - len(new_pmc_links)} PMC links already cached, "
                f"{len(new_pmc_links)} new"
            )

        supp_raw = None
        if new_pmc_links:
            dg_supp = DataGatherer(llm_name="claude-haiku-4-5", log_level=log_level, log_file_override=log_file_str,
            clear_previous_logs=False, raw_data_df_parquet_filepath=fetch_cache_str)
            supp_raw = dg_supp.process_articles(
                new_pmc_links,
                response_format=supplementary_files_keywords_schema,
                section_filter="supplementary_material",
                return_df_joint=True,
            )
            if supp_raw is not None and not supp_raw.empty:
                supp_raw["_schema"] = "SupplementaryFileKeywords"

        combined_supp = combine_cached_and_new(cached_supp_df, supp_raw)
        if combined_supp is not None:
            combined_supp.to_csv(output_path, sep="\t", index=False)
            logger.info(f"Supplementary → {output_path.name} ({len(combined_supp)} rows)")
        else:
            logger.warning("No supplementary file mentions found")

        return output_path
