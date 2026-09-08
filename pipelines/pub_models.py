"""
Stage 4e — Publication pretrained-model mention extraction.

Uses ``data_gatherer.DataGatherer`` to extract pretrained-model mentions from
PMC articles via the Anthropic Batch API: rule-based retrieval of the
code/software-availability section (plus the references section, which
data_gatherer includes automatically for relevant_content_flag='CODE') and
regex-matched model-hosting URLs (Hugging Face Hub/TensorFlow Hub/PyTorch Hub/
ModelScope/Civitai), combined with an LLM pass for unlinked mentions
(process_entire_document=False).

Input:  ``tables/hits/pubmed_hits_{ts}.tsv`` (reads ``PubMed Central Link`` col)
Output: ``tables/hits/pub_models_{ts}.tsv``

Runs concurrently with pub_datasets/pub_supplementary/pub_grants/pub_software
(see orchestrator.py::run_stages_concurrently) — each is fully independent so
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


def _model_batch_results_to_df(dg, batch_results_file: str) -> pd.DataFrame:
    """Convert a model-mentions batch results file to a DataFrame.

    Reimplements DataGatherer.from_batch_resp_file_to_df's logic rather than
    calling it directly: that method's generic metadata merge does
    ``record[key] = value`` unconditionally for every metadata key, including
    'url' (the source article's URL) — but the model_mention schema's own
    per-record field is *also* named 'url' (the model's own URL), so the
    merge would silently overwrite every extracted model URL with the
    article URL. Datasets/grants schemas don't hit this since neither uses
    'url' as a field name (same issue pub_software.py works around). Worked
    around here by renaming the metadata's url to 'article_url' before merging.
    """
    batch_raw_resps = dg.parser.llm_client.process_batch_responses(
        batch_results_file=batch_results_file, expected_key="model_mentions",
    )
    rows = []
    for batch_item in batch_raw_resps["processed_results"]:
        custom_id = batch_item.get("custom_id", "N/A")
        if batch_item.get("status") != "success":
            continue
        metadata = batch_item.get("metadata", {})
        records = dg.parser.process_model_response(batch_item.get("processed_response", []))
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


class PubModelsStage(PipelineStage):
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
        from data_gatherer.llm.response_schema import model_mention_response_schema_gpt

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

        logger.info("Extracting model mentions")
        cached_models_df = None
        if use_cache:
            prev = latest_final("pub_models_*.tsv")
            if prev:
                cached_models_df = pd.read_csv(prev, sep="\t", dtype=str).fillna("")
        known_urls = set(cached_models_df["source_url"].unique()) if cached_models_df is not None else set()
        new_pmc_links = [u for u in pmc_links if u not in known_urls]
        if cached_models_df is not None:
            logger.info(
                f"models: {len(pmc_links) - len(new_pmc_links)} PMC links already cached, "
                f"{len(new_pmc_links)} new"
            )

        models_df = None
        if new_pmc_links:
            dg_models = DataGatherer(
                llm_name="claude-haiku-4-5-20251001",
                process_entire_document=False,  # rule-based + regex retrieval, not full-document read
                log_level=log_level, log_file_override=log_file_str, clear_previous_logs=False,
                raw_data_df_parquet_filepath=fetch_cache_str,
            )
            # dg.parser is None until a fetch happens — explicitly initialize it so
            # get_model_hosting_id_patterns() has something to call.
            dg_models.init_parser_by_input_type('XML')
            model_id_patterns = dg_models.parser.get_model_hosting_id_patterns()

            models_batch_output_path = str(output_path.with_suffix(".batch.jsonl"))
            # run_integrated_batch_processing() calls DataGatherer.fetch_data() internally,
            # which holds every fetched/parsed document in memory for the whole call — chunk
            # new_pmc_links so that accumulation is bounded per call, not per full backlog.
            # Submit every chunk's batch job up front (no waiting), then poll them all
            # together — the batch jobs run concurrently on Anthropic's side instead of
            # one chunk waiting on completion before the next is even submitted.
            chunks = chunked(new_pmc_links)
            pending = submit_batch_chunks(
                dg_models, chunks, models_batch_output_path,
                prompt_name="CLAUDE_RTR_FewShot_models",
                prompts_subdir="model_prompts",
                relevant_content_flag="CODE",
                relevant_cont_fmt="text",
                response_format=model_mention_response_schema_gpt,
                api_provider="anthropic",
                regex_search_id_patterns=model_id_patterns,
                brute_force_RegEx_ID_ptrs=True,
                local_fetch_file=fetch_cache_str,
            )
            batch_dfs = []
            for item in await_batches(dg_models, pending):
                if item["output_file_path"]:
                    chunk_df = _model_batch_results_to_df(dg_models, item["output_file_path"])
                    if chunk_df is not None and not chunk_df.empty:
                        batch_dfs.append(chunk_df)
                else:
                    logger.error(f"Model batch {item['batch_id']} did not complete successfully")
            if batch_dfs:
                models_df = pd.concat(batch_dfs, ignore_index=True)
                models_df = models_df.rename(columns={"title": "pub_title"})
                models_df = models_df.drop(columns=[
                    c for c in ("retrieval_stats", "custom_id", "article_id", "page_id", "article_url")
                    if c in models_df.columns
                ])
                models_df["_schema"] = "ModelMention"

        combined_models = combine_cached_and_new(cached_models_df, models_df)
        if combined_models is not None:
            combined_models.to_csv(output_path, sep="\t", index=False)
            logger.info(f"Models → {output_path.name} ({len(combined_models)} rows)")
        else:
            logger.warning("No model mentions found")

        return output_path
