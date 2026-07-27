"""
Shared helper for the pub_datasets / pub_supplementary / pub_grants /
pub_software stages.

All four read the same input (``tables/hits/pubmed_hits_{ts}.tsv``) and need
the same PMC link list, and all four independently re-fetch the same article
full-text — this module holds what they have in common so it's not
duplicated four times.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def load_pmc_links(input_path: Path) -> list[str]:
    """Load unique, non-empty PMC links from a pubmed_hits TSV.

    Args:
        input_path: Path to tables/hits/pubmed_hits_{ts}.tsv.

    Returns:
        Unique, non-empty values from the "PubMed Central Link" column.
    """
    pubs_df = pd.read_csv(input_path, sep="\t")
    return (
        pubs_df["PubMed Central Link"]
        .dropna()
        .loc[lambda s: s.str.strip() != ""]
        .unique()
        .tolist()
    )


def prefetch_articles(
    pmc_links: list[str],
    cache_path: Path,
    log_level: str = "INFO",
    log_file_str: str | None = None,
    sects_required=5,
) -> None:
    """Fetch every PMC article once and read/update a shared parquet cache.

    Runs before the pub_datasets/pub_supplementary/pub_grants/pub_software
    stages launch, so all four can read from ``cache_path`` (via
    ``DataGatherer(raw_data_df_parquet_filepath=...)`` and, where supported,
    ``run_integrated_batch_processing(local_fetch_file=...)``) instead of each
    independently re-fetching the same articles over the network.

    ``cache_path`` is a stable filename shared across runs (not timestamped) —
    if it already exists, already-cached articles are read from it instead of
    refetched, and the file is rewritten in place with the full merged set
    (old entries + any genuinely new articles this run). Only articles not
    already in the cache ever hit the network.

    ``sects_required`` must match what the four stages themselves use
    (``run_integrated_batch_processing``'s own default is 5, not
    ``fetch_data``'s default of 1) — otherwise an article cached here as
    "complete" at a lower section-count bar fails the stricter re-check
    inside a stage's own fetch call, and that stage falls through the same
    HTTPGetRequest/Selenium fallback chain a second time, concurrently,
    defeating both the cache and the point of prefetching in the first place.

    Args:
        pmc_links: PMC article URLs to fetch.
        cache_path: Stable .parquet path, reused and updated across runs.
        log_level: "DEBUG" or "INFO".
        log_file_str: Optional log file path.
        sects_required: Minimum sections for a fetch to count as complete —
            must match the downstream stages' own requirement.
    """
    from data_gatherer.data_gatherer import DataGatherer

    dg = DataGatherer(
        llm_name="claude-haiku-4-5", log_level=log_level,
        log_file_override=log_file_str, clear_previous_logs=False,
    )
    existing_cache = str(cache_path) if cache_path.exists() else None
    dg.fetch_data(
        pmc_links, local_fetch_file=existing_cache, write_df_to_path=str(cache_path),
        sects_required=sects_required,
    )
    logger.info(f"Prefetched {len(pmc_links)} articles → {cache_path.name}")
