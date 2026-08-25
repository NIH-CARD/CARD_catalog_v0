"""
Stage 4c — Publication grant/funding mention extraction.

Uses ``data_gatherer.DataGatherer`` to extract grant/funding mentions from PMC
articles via the Anthropic Batch API, using rule-based retrieval of the
funding/acknowledgments section only (process_entire_document=False).

Input:  ``tables/hits/pubmed_hits_{ts}.tsv`` (reads ``PubMed Central Link`` col)
Output: ``tables/hits/pub_grants_{ts}.tsv``

Runs concurrently with pub_datasets/pub_supplementary/pub_software (see
orchestrator.py::run_stages_concurrently) — each is fully independent so
there's no shared mutable state between them.
"""
import logging
import os
from pathlib import Path

import pandas as pd

from pipelines.base import PipelineStage, redact_secrets
from pipelines.pub_metadata_shared import await_batches, chunked, load_pmc_links, submit_batch_chunks
from staging.cache_utils import combine_cached_and_new, latest_final

logger = logging.getLogger(__name__)


class PubGrantsStage(PipelineStage):
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
        from data_gatherer.llm.response_schema import grant_response_schema_gpt

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

        logger.info("Extracting grant/funding mentions")
        cached_grants_df = None
        if use_cache:
            prev = latest_final("pub_grants_*.tsv")
            if prev:
                cached_grants_df = pd.read_csv(prev, sep="\t", dtype=str).fillna("")
        known_urls = set(cached_grants_df["source_url"].unique()) if cached_grants_df is not None else set()
        new_pmc_links = [u for u in pmc_links if u not in known_urls]
        if cached_grants_df is not None:
            logger.info(
                f"grants: {len(pmc_links) - len(new_pmc_links)} PMC links already cached, "
                f"{len(new_pmc_links)} new"
            )

        grants_df = None
        if new_pmc_links:
            dg_grants = DataGatherer(
                llm_name="claude-haiku-4-5-20251001",
                process_entire_document=False,  # funding sections are short — rule-based retrieval only
                log_level=log_level, log_file_override=log_file_str, clear_previous_logs=False,
                raw_data_df_parquet_filepath=fetch_cache_str,
            )
            grants_batch_output_path = str(output_path.with_suffix(".batch.jsonl"))
            grants_result = dg_grants.run_integrated_batch_processing(
                url_list=new_pmc_links,
                batch_file_path='',
                output_file_path=grants_batch_output_path,
                prompt_name="CLAUDE_FDR_FewShot_grant",
                prompts_subdir="funding_prompts",
                relevant_content_flag="FUND",
                relevant_cont_fmt="text",
                response_format=grant_response_schema_gpt,
                api_provider="anthropic",
                local_fetch_file=fetch_cache_str,
                wait_for_completion=True,
            )
            if isinstance(grants_result, dict) and grants_result.get("output_file_path"):
                grants_df = dg_grants.from_batch_resp_file_to_df(
                    grants_result["output_file_path"], skip_validation=True, expected_key="grants",
                )
                if grants_df is not None and not grants_df.empty:
                    grants_df = grants_df.rename(columns={"title": "pub_title"})
                    grants_df = grants_df.drop(columns=[
                        c for c in ("retrieval_stats", "custom_id", "article_id", "page_id", "url")
                        if c in grants_df.columns
                    ])
                    grants_df["_schema"] = "GrantRecord"
            else:
                logger.error(f"Grants batch did not complete successfully: {grants_result}")
                grants_df = None

        combined_grants = combine_cached_and_new(cached_grants_df, grants_df)
        if combined_grants is not None:
            combined_grants.to_csv(output_path, sep="\t", index=False)
            logger.info(f"Grants → {output_path.name} ({len(combined_grants)} rows)")
        else:
            logger.warning("No grant mentions found")

        return output_path
