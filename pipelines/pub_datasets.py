"""
Stage 4a — Publication dataset extraction.

Uses ``data_gatherer.DataGatherer`` to extract dataset mentions from PMC
articles via the Anthropic Batch API (or, with ``batch_mode=False``, the
synchronous ``process_articles`` path).

Input:  ``tables/hits/pubmed_hits_{ts}.tsv`` (reads ``PubMed Central Link`` col)
Output: ``tables/hits/pub_datasets_{ts}.tsv``

Runs concurrently with pub_supplementary/pub_grants/pub_software (see
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


dataset_response_schema_with_use_description_and_short = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "datasets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "dataset_identifier": {
                            "type": "string",
                            "description": "A unique identifier or accession code for the dataset.",
                            "maxLength": 64
                        },
                        "data_repository": {
                            "type": "string",
                            "description": "A valid URI or string referring to the repository where the dataset can be found.",
                            "maxLength": 128
                        },
                        "dataset_context_from_paper": {
                            "type": "string",
                            "description": "Relevant text passages from the paper that either describe this dataset and provide context of its use or refer to it more implicitly.",
                            "maxLength": 1024
                        },
                        "dataset_keywords": {
                            "type": "string",
                            "description": "Two or three keywords to help user understand if they want to reuse this dataset (about content and scope).",
                            "maxLength": 128
                        },
                        "citation_type": {
                            "type": "string",
                            "description": "Type of citation used for this dataset. It can be either Primary (firsthand information collected by the researcher for a specific purpose) or Secondary (pre-existing information collected by someone else and then used by another researcher).",
                            "maxLength": 16
                        }
                    },
                    "additionalProperties": False,
                    "required": ["dataset_identifier", "data_repository", "dataset_context_from_paper", "dataset_keywords", "citation_type"]
                },
                "minItems": 1,
                "additionalProperties": False
            }
        },
        "additionalProperties": False,
        "required": ["datasets"]
    }
}


class PubDatasetsStage(PipelineStage):
    def run(
        self,
        input_path: Path,
        output_path: Path,
        batch_mode: bool = True,
        full_document_read: bool = True,
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

        if anthropic_key:
            os.environ.setdefault("ANTHROPIC_API_KEY", anthropic_key)

        log_level = "DEBUG" if verbose else "INFO"
        log_file_str = str(log_file) if log_file else None
        batch_output_path = str(output_path.with_suffix(".batch.tsv"))
        fetch_cache_str = str(fetch_cache_path) if fetch_cache_path else None

        pmc_links = load_pmc_links(input_path)
        logger.info(f"{len(pmc_links)} PMC links to process")
        if not pmc_links:
            logger.warning("no PMC links found — skipping")
            return output_path

        logger.info("extracting dataset mentions")
        cached_datasets_df = None
        if use_cache:
            prev = latest_final("pub_datasets_*.tsv")
            if prev:
                cached_datasets_df = pd.read_csv(prev, sep="\t", dtype=str).fillna("")
        known_urls = set(cached_datasets_df["source_url"].unique()) if cached_datasets_df is not None else set()
        new_pmc_links = [u for u in pmc_links if u not in known_urls]
        if cached_datasets_df is not None:
            logger.info(
                f"datasets: {len(pmc_links) - len(new_pmc_links)} PMC links already cached, "
                f"{len(new_pmc_links)} new"
            )

        datasets_raw = None
        if new_pmc_links:
            dg = DataGatherer(llm_name="claude-haiku-4-5", log_level=log_level, log_file_override=log_file_str,
            clear_previous_logs=False, process_entire_document=full_document_read,
            raw_data_df_parquet_filepath=fetch_cache_str)
            if batch_mode:
                batch_result = dg.run_integrated_batch_processing(
                    url_list=new_pmc_links,
                    batch_file_path='',
                    output_file_path=batch_output_path,
                    section_filter="data_availability_statement",
                    prompt_name="CLAUDE_FDR_FewShot_shortDescr",
                    response_format=dataset_response_schema_with_use_description_and_short,
                    semantic_retrieval=True,
                    api_provider="anthropic",
                    local_fetch_file=fetch_cache_str,
                    wait_for_completion=True,
                )
                # run_integrated_batch_processing returns a dict (not a DataFrame) on the
                # Anthropic batch path, regardless of wait_for_completion — convert explicitly.
                if isinstance(batch_result, dict) and batch_result.get("output_file_path"):
                    datasets_raw = dg.from_batch_resp_file_to_df(
                        batch_result["output_file_path"], skip_validation=True, expected_key="datasets",
                    )
                    if datasets_raw is not None and not datasets_raw.empty:
                        datasets_raw = datasets_raw.rename(columns={"title": "pub_title"})
                        datasets_raw = datasets_raw.drop(columns=[
                            c for c in ("retrieval_stats", "custom_id", "article_id", "page_id", "url")
                            if c in datasets_raw.columns
                        ])
                else:
                    logger.error(f"Dataset batch did not complete successfully: {batch_result}")
                    datasets_raw = None

            else:
                datasets_raw = dg.process_articles(
                    new_pmc_links,
                    response_format=dataset_response_schema_with_use_description_and_short,
                    prompt_name="CLAUDE_FDR_FewShot_shortDescr",
                    full_document_read=full_document_read,
                    semantic_retrieval=True,
                    return_df_joint=True,
                    section_filter="data_availability_statement",
                )
            if datasets_raw is not None and not datasets_raw.empty:
                datasets_raw["_schema"] = "Dataset_w_Context"

        combined_datasets = combine_cached_and_new(cached_datasets_df, datasets_raw)
        if combined_datasets is not None:
            combined_datasets.to_csv(output_path, sep="\t", index=False)
            logger.info(f"Datasets → {output_path.name} ({len(combined_datasets)} rows)")
        else:
            logger.warning("No dataset mentions found")

        return output_path
