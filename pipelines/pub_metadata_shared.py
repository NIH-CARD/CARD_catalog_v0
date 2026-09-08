"""
Shared helper for the pub_datasets / pub_supplementary / pub_grants /
pub_software / pub_models stages.

All five read the same input (``tables/hits/pubmed_hits_{ts}.tsv``) and need
the same PMC link list — this module holds that shared loading logic so it's
not duplicated five times.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# run_integrated_batch_processing() calls DataGatherer.fetch_data() internally, which
# holds every fetched/parsed document in memory for the whole call and flushes once at
# the end — the same accumulation pattern already fixed for the up-front warming call
# in orchestrator.py::prefetch_articles. Capping each run_integrated_batch_processing()
# call to this many URLs bounds that per-call accumulation for pub_datasets/pub_grants/
# pub_software/pub_models, which all call it with their full new_pmc_links list.
BATCH_SIZE = 1000


def chunked(items: list, size: int = BATCH_SIZE) -> list[list]:
    """Split items into consecutive chunks of at most `size` items each."""
    logger.debug(f"chunked called with {len(items)} item(s), size={size}")
    result = [items[i:i + size] for i in range(0, len(items), size)]
    logger.debug(f"chunked returning {len(result)} chunk(s)")
    return result


def submit_batch_chunks(dg, chunks: list[list[str]], output_path_prefix: str,
                         batch_file_path: str = '', **batch_kwargs) -> list[dict]:
    """Submit one Anthropic batch job per chunk without waiting for completion.

    Each run_integrated_batch_processing() call still does its own fetch_data()
    (bounded by that chunk's size) and batch-request construction, then submits
    and returns immediately (wait_for_completion=False) — waiting for the actual
    results happens later, via await_batches(), against every chunk's batch_id
    together instead of one chunk at a time, so the batch jobs run concurrently
    on Anthropic's side instead of sequentially.

    Args:
        dg: DataGatherer instance.
        chunks: PMC link chunks (see chunked()).
        output_path_prefix: Base path for each chunk's eventual results file —
            suffixed with the chunk index when there's more than one chunk.
        batch_file_path: Forwarded to run_integrated_batch_processing.
        **batch_kwargs: Forwarded to run_integrated_batch_processing (response_format,
            prompt_name, section_filter, api_provider, local_fetch_file, etc.) — must
            not include url_list, output_file_path, batch_file_path, or wait_for_completion.

    Returns:
        List of {"batch_id", "output_file_path", "api_provider"} dicts, one per
        successfully submitted chunk (failed submissions are logged and skipped).
    """
    logger.info(f"submit_batch_chunks called with {len(chunks)} chunk(s), output_path_prefix={output_path_prefix}")
    api_provider = batch_kwargs.get("api_provider", "anthropic")
    pending = []
    for i, chunk in enumerate(chunks):
        chunk_output_path = output_path_prefix if len(chunks) == 1 else f"{output_path_prefix}.{i}"
        logger.info(f"submitting batch {i + 1}/{len(chunks)} ({len(chunk)} links) -> {chunk_output_path}")
        submit_result = dg.run_integrated_batch_processing(
            url_list=chunk, batch_file_path=batch_file_path, output_file_path=chunk_output_path,
            wait_for_completion=False, **batch_kwargs,
        )
        batch_id = (submit_result or {}).get("batch_submission", {}).get("batch_id")
        if batch_id:
            pending.append({"batch_id": batch_id, "output_file_path": chunk_output_path, "api_provider": api_provider})
        else:
            logger.error(f"batch {i + 1}/{len(chunks)} failed to submit: {submit_result}")
    logger.info(f"submit_batch_chunks returning {len(pending)}/{len(chunks)} successfully submitted batch(es)")
    return pending


def await_batches(dg, pending: list[dict], poll_interval: int = 60) -> list[dict]:
    """Poll multiple already-submitted batch jobs together until each completes.

    Downloads each job's results as soon as it finishes rather than waiting for
    the slowest one before checking on any of the others.

    Args:
        dg: DataGatherer instance whose parser.llm_client submitted the jobs.
        pending: Output of submit_batch_chunks().
        poll_interval: Seconds between status sweeps over the still-pending jobs.

    Returns:
        Each input dict, with "output_file_path" set to None for any job that
        failed/expired/was cancelled instead of completing.
    """
    logger.info(f"await_batches called with {len(pending)} pending batch job(s), poll_interval={poll_interval}s")
    remaining = list(pending)
    done = []
    while remaining:
        still_pending = []
        for item in remaining:
            status_info = dg.parser.llm_client.check_batch_status(
                batch_id=item["batch_id"], api_provider=item["api_provider"],
            )
            status = status_info["status"]
            if status in ("completed", "ended"):
                try:
                    dg.parser.llm_client.download_batch_results(
                        batch_id=item["batch_id"], output_file_path=item["output_file_path"],
                        api_provider=item["api_provider"],
                    )
                    logger.info(f"batch {item['batch_id']} completed -> {item['output_file_path']}")
                except Exception as e:
                    # One malformed/errored request inside an otherwise-completed batch must
                    # not take down every other chunk in this stage's run — log and mark this
                    # one batch failed, keep the rest of the stage's results.
                    logger.error(f"batch {item['batch_id']} completed but results download failed: {e}", exc_info=True)
                    item["output_file_path"] = None
                done.append(item)
            elif status in ("failed", "expired", "cancelled"):
                logger.error(f"batch {item['batch_id']} ended with status: {status}")
                item["output_file_path"] = None
                done.append(item)
            else:
                still_pending.append(item)
        remaining = still_pending
        if remaining:
            logger.info(f"{len(remaining)}/{len(pending)} batch job(s) still running — "
                        f"checking again in {poll_interval}s")
            time.sleep(poll_interval)
    n_failed = sum(1 for item in done if not item["output_file_path"])
    logger.info(f"await_batches returning {len(done)} batch(es) done ({n_failed} failed)")
    return done


def load_pmc_links(input_path: Path) -> list[str]:
    """Load unique, non-empty PMC links from a pubmed_hits TSV.

    Args:
        input_path: Path to tables/hits/pubmed_hits_{ts}.tsv.

    Returns:
        Unique, non-empty values from the "PubMed Central Link" column.
    """
    logger.info(f"load_pmc_links called with input_path={input_path}")
    pubs_df = pd.read_csv(input_path, sep="\t")
    links = (
        pubs_df["PubMed Central Link"]
        .dropna()
        .loc[lambda s: s.str.strip() != ""]
        .unique()
        .tolist()
    )
    logger.info(f"load_pmc_links returning {len(links)} unique PMC link(s)")
    return links
