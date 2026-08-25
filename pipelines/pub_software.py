"""
Stage 4d — Publication software/tool mention extraction.

Uses ``data_gatherer.DataGatherer`` to extract software mentions from PMC
articles via the Anthropic Batch API: rule-based retrieval of the
code/software-availability section (plus the references section, which
data_gatherer includes automatically for relevant_content_flag='CODE') and
regex-matched code-hosting URLs (GitHub/GitLab/Bitbucket/Zenodo/SourceForge/
PyPI/CRAN), combined with an LLM pass for unlinked mentions
(process_entire_document=False).

Input:  ``tables/hits/pubmed_hits_{ts}.tsv`` (reads ``PubMed Central Link`` col)
Output: ``tables/hits/pub_software_{ts}.tsv``

Runs concurrently with pub_datasets/pub_supplementary/pub_grants (see
orchestrator.py::run_stages_concurrently) — each is fully independent so
there's no shared mutable state between them.
"""
import logging
import os
import re
from pathlib import Path

import pandas as pd

from pipelines.base import PipelineStage, redact_secrets
from pipelines.pub_metadata_shared import await_batches, chunked, load_pmc_links, submit_batch_chunks
from staging.cache_utils import combine_cached_and_new, latest_final

logger = logging.getLogger(__name__)


def _software_batch_results_to_df(dg, batch_results_file: str) -> pd.DataFrame:
    """Convert a software-mentions batch results file to a DataFrame.

    Reimplements DataGatherer.from_batch_resp_file_to_df's logic rather than
    calling it directly: that method's generic metadata merge does
    ``record[key] = value`` unconditionally for every metadata key, including
    'url' (the source article's URL) — but the software_mention schema's own
    per-record field is *also* named 'url' (the software's own URL), so the
    merge would silently overwrite every extracted software URL with the
    article URL. Datasets/grants schemas don't hit this since neither uses
    'url' as a field name. Worked around here by renaming the metadata's url
    to 'article_url' before merging.
    """
    batch_raw_resps = dg.parser.llm_client.process_batch_responses(
        batch_results_file=batch_results_file, expected_key="software_mentions",
    )
    rows = []
    for batch_item in batch_raw_resps["processed_results"]:
        custom_id = batch_item.get("custom_id", "N/A")
        if batch_item.get("status") != "success":
            continue
        metadata = batch_item.get("metadata", {})
        records = dg.parser.process_software_response(batch_item.get("processed_response", []))
        for record in records:
            record["custom_id"] = custom_id
            for key, value in metadata.items():
                record["article_url" if key == "url" else key] = value
            if re.search(r"_PMC\d+", custom_id, re.IGNORECASE):
                pmc_match = re.search(r"PMC(\d+)", custom_id, re.IGNORECASE)
                if pmc_match:
                    record["source_url"] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_match.group(1)}/"
            elif custom_id in dg.custom_id_to_source_url:
                record["source_url"] = dg.custom_id_to_source_url[custom_id]
            rows.append(record)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


class PubSoftwareStage(PipelineStage):
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
        from data_gatherer.llm.response_schema import software_mention_response_schema_gpt

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

        logger.info("Extracting software mentions")
        cached_software_df = None
        if use_cache:
            prev = latest_final("pub_software_*.tsv")
            if prev:
                cached_software_df = pd.read_csv(prev, sep="\t", dtype=str).fillna("")
        known_urls = set(cached_software_df["source_url"].unique()) if cached_software_df is not None else set()
        new_pmc_links = [u for u in pmc_links if u not in known_urls]
        if cached_software_df is not None:
            logger.info(
                f"software: {len(pmc_links) - len(new_pmc_links)} PMC links already cached, "
                f"{len(new_pmc_links)} new"
            )

        software_df = None
        if new_pmc_links:
            dg_software = DataGatherer(
                llm_name="claude-haiku-4-5-20251001",
                process_entire_document=False,  # rule-based + regex retrieval, not full-document read
                log_level=log_level, log_file_override=log_file_str, clear_previous_logs=False,
                raw_data_df_parquet_filepath=fetch_cache_str,
            )
            # dg.parser is None until a fetch happens — explicitly initialize it so
            # get_code_hosting_id_patterns() has something to call.
            dg_software.init_parser_by_input_type('XML')
            code_id_patterns = dg_software.parser.get_code_hosting_id_patterns()

            software_batch_output_path = str(output_path.with_suffix(".batch.jsonl"))
            software_result = dg_software.run_integrated_batch_processing(
                url_list=new_pmc_links,
                batch_file_path='',
                output_file_path=software_batch_output_path,
                prompt_name="CLAUDE_RTR_FewShot_software",
                prompts_subdir="software_prompts",
                relevant_content_flag="CODE",
                relevant_cont_fmt="text",
                response_format=software_mention_response_schema_gpt,
                api_provider="anthropic",
                regex_search_id_patterns=code_id_patterns,
                brute_force_RegEx_ID_ptrs=True,
                local_fetch_file=fetch_cache_str,
                wait_for_completion=True,
            )
            if isinstance(software_result, dict) and software_result.get("output_file_path"):
                software_df = _software_batch_results_to_df(dg_software, software_result["output_file_path"])
                if software_df is not None and not software_df.empty:
                    software_df = software_df.rename(columns={"title": "pub_title"})
                    software_df = software_df.drop(columns=[
                        c for c in ("retrieval_stats", "custom_id", "article_id", "page_id", "article_url")
                        if c in software_df.columns
                    ])
                    software_df["_schema"] = "SoftwareMention"
            else:
                logger.error(f"Software batch did not complete successfully: {software_result}")
                software_df = None

        combined_software = combine_cached_and_new(cached_software_df, software_df)
        if combined_software is not None:
            combined_software.to_csv(output_path, sep="\t", index=False)
            logger.info(f"Software → {output_path.name} ({len(combined_software)} rows)")
        else:
            logger.warning("No software mentions found")

        return output_path
