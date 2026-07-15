"""
Stage 4 — Publication metadata extraction (datasets + supplementary files + grants).

Uses ``data_gatherer.DataGatherer`` to extract dataset mentions, supplementary
file mentions, and grant/funding mentions from PMC articles.

- Dataset mentions → ``tables/hits/pub_datasets_{ts}.tsv``
- Supplementary files → ``tables/hits/pub_supplementary_{ts}.tsv``
- Grant/funding mentions → ``tables/hits/pub_grants_{ts}.tsv``

The ``output_path`` arg is the datasets output; the supplementary and grants
paths are derived by replacing ``pub_datasets`` with ``pub_supplementary`` /
``pub_grants`` in the stem.

Input: ``tables/hits/pubmed_hits_{ts}.tsv`` (reads ``PubMed Central Link`` col)
"""
import logging
import os
from pathlib import Path

import pandas as pd

from pipelines.base import PipelineStage

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


class PubMetadataStage(PipelineStage):
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
        targets: tuple[str, ...] = ("datasets", "supplementary", "grants"),
    ) -> Path:
        from data_gatherer.data_gatherer import DataGatherer
        from data_gatherer.llm.response_schema import (
            supplementary_files_keywords_schema,
            grant_response_schema_gpt,
        )

        if anthropic_key:
            os.environ.setdefault("ANTHROPIC_API_KEY", anthropic_key)

        log_level = "DEBUG" if verbose else "INFO"

        # Derive supplementary/grants output paths from datasets output path
        supp_path = output_path.parent / output_path.name.replace(
            "pub_datasets", "pub_supplementary"
        )
        grants_path = output_path.parent / output_path.name.replace(
            "pub_datasets", "pub_grants"
        )
        batch_output_path = str(output_path.with_suffix(".batch.tsv"))

        # Load PMC links from pubmed hits
        pubs_df = pd.read_csv(input_path, sep="\t")
        pmc_links = (
            pubs_df["PubMed Central Link"]
            .dropna()
            .loc[lambda s: s.str.strip() != ""]
            .unique()
            .tolist()
        )
        logger.info(f"{len(pmc_links)} PMC links to process")

        if not pmc_links:
            logger.warning("no PMC links found — skipping")
            return output_path

        log_file_str = str(log_file) if log_file else None

        # --- Dataset mentions ---
        if "datasets" in targets:
            logger.info("extracting dataset mentions")
            dg = DataGatherer(llm_name="claude-haiku-4-5", log_level=log_level, log_file_override=log_file_str, 
            clear_previous_logs=False, process_entire_document=full_document_read)
            if batch_mode:
                batch_result = dg.run_integrated_batch_processing(
                    url_list=pmc_links,
                    batch_file_path='',
                    output_file_path=batch_output_path,
                    section_filter="data_availability_statement",
                    prompt_name="CLAUDE_FDR_FewShot_shortDescr",
                    response_format=dataset_response_schema_with_use_description_and_short,
                    semantic_retrieval=True,
                    api_provider="anthropic",
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
                    pmc_links,
                    response_format=dataset_response_schema_with_use_description_and_short,
                    prompt_name="CLAUDE_FDR_FewShot_shortDescr",
                    full_document_read=full_document_read,
                    semantic_retrieval=True,
                    return_df_joint=True,
                    section_filter="data_availability_statement",
                )
            if datasets_raw is not None and not datasets_raw.empty:
                datasets_raw["_schema"] = "Dataset_w_Context"
                datasets_raw.to_csv(output_path, sep="\t", index=False)
                logger.info(f"Datasets → {output_path.name} ({len(datasets_raw)} rows)")
            else:
                logger.warning("No dataset mentions found")

        # --- Supplementary files ---
        if "supplementary" in targets:
            logger.info("Extracting supplementary file mentions")
            dg_supp = DataGatherer(llm_name="claude-haiku-4-5", log_level=log_level, log_file_override=log_file_str, clear_previous_logs=False)
            supp_raw = dg_supp.process_articles(
                pmc_links,
                response_format=supplementary_files_keywords_schema,
                section_filter="supplementary_material",
                return_df_joint=True,
            )
            if supp_raw is not None and not supp_raw.empty:
                supp_raw["_schema"] = "SupplementaryFileKeywords"
                supp_raw.to_csv(supp_path, sep="\t", index=False)
                logger.info(f"Supplementary → {supp_path.name} ({len(supp_raw)} rows)")
            else:
                logger.warning("No supplementary file mentions found")

        # --- Grant / funding mentions ---
        if "grants" in targets:
            logger.info("Extracting grant/funding mentions")
            dg_grants = DataGatherer(
                llm_name="claude-haiku-4-5-20251001",
                process_entire_document=False,  # funding sections are short — rule-based retrieval only
                log_level=log_level, log_file_override=log_file_str, clear_previous_logs=False,
            )
            grants_batch_output_path = str(grants_path.with_suffix(".batch.jsonl"))
            grants_result = dg_grants.run_integrated_batch_processing(
                url_list=pmc_links,
                batch_file_path='',
                output_file_path=grants_batch_output_path,
                prompt_name="CLAUDE_FDR_FewShot_grant",
                prompts_subdir="funding_prompts",
                relevant_content_flag="FUND",
                relevant_cont_fmt="text",
                response_format=grant_response_schema_gpt,
                api_provider="anthropic",
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
                    grants_df.to_csv(grants_path, sep="\t", index=False)
                    logger.info(f"Grants → {grants_path.name} ({len(grants_df)} rows)")
                else:
                    logger.warning("No grant mentions found")
            else:
                logger.error(f"Grants batch did not complete successfully: {grants_result}")

        return output_path
