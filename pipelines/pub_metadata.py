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
        *,
        anthropic_key: str | None = None,
        verbose: bool = False,
        log_file: Path | None = None,
    ) -> Path:
        from data_gatherer.data_gatherer import DataGatherer
        from data_gatherer.llm.response_schema import (
            supplementary_files_keywords_schema,
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
        logger.info(f"{len(pmc_links)} PMC links to process")

        if not pmc_links:
            logger.warning("no PMC links found — skipping")
            return output_path

        log_file_str = str(log_file) if log_file else None

        # --- Dataset mentions ---
        logger.info("extracting dataset mentions")
        dg = DataGatherer(llm_name="claude-haiku-4-5", log_level=log_level, log_file_override=log_file_str, clear_previous_logs=False)
        datasets_raw = dg.process_articles(
            pmc_links,
            response_format=dataset_response_schema_with_use_description_and_short,
            prompt_name="CLAUDE_FDR_FewShot_shortDescr",
            full_document_read=True,
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

        return output_path
