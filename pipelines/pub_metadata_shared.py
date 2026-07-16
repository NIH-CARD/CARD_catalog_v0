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
) -> None:
    """Fetch every PMC article once and write the result to a shared parquet cache.

    Runs before the pub_datasets/pub_supplementary/pub_grants/pub_software
    stages launch, so all four can read from ``cache_path`` (via
    ``DataGatherer(raw_data_df_parquet_filepath=...)`` and, where supported,
    ``run_integrated_batch_processing(local_fetch_file=...)``) instead of each
    independently re-fetching the same articles over the network.

    Args:
        pmc_links: PMC article URLs to fetch.
        cache_path: Destination .parquet path for the fetched content.
        log_level: "DEBUG" or "INFO".
        log_file_str: Optional log file path.
    """
    from data_gatherer.data_gatherer import DataGatherer

    dg = DataGatherer(
        llm_name="claude-haiku-4-5", log_level=log_level,
        log_file_override=log_file_str, clear_previous_logs=False,
    )
    dg.fetch_data(pmc_links, write_df_to_path=str(cache_path))
    logger.info(f"Prefetched {len(pmc_links)} articles → {cache_path.name}")
