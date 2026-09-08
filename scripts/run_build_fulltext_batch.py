#!/usr/bin/env python3
"""One-off driver for validate_fetched_publications.build_fulltext_batch_jsonl - not wired
into main() since it builds a batch JSONL for later offline submission, not a live verdict TSV.
run with command:

    python3 scripts/run_build_fulltext_batch.py
"""
import logging
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scrapers"))
sys.path.insert(0, str(_REPO_ROOT / "staging"))
from logging_config import setup_logger, get_default_log_file
from validate_fetched_publications import (
    build_fulltext_batch_jsonl, load_sample_sizes, _find_latest_inventory, DEFAULT_DG_PROMPT_NAME,
)

INPUT_TSV = Path("tables/hits/combine_hits_20260812_194049.tsv")
RESOURCE_COL = "Resource Name"
SOURCES = "pmc,biorxiv,medrxiv,arxiv,trials"


def main():
    log_file = get_default_log_file("build_fulltext_batch")
    setup_logger("run_build_fulltext_batch", log_file=log_file, level=logging.INFO, clear=False)
    logger = logging.getLogger("run_build_fulltext_batch")
    logger.info(f"Log file: {log_file}")

    df = pd.read_csv(INPUT_TSV, sep="\t", dtype=str).fillna("")
    logger.info(f"Loaded {len(df)} rows from {INPUT_TSV}")

    inventory_path = _find_latest_inventory()
    logger.info(f"Using inventory for prompt context: {inventory_path}")
    sample_sizes = load_sample_sizes(inventory_path)

    n_batches = 10
    batch_size = len(df)//n_batches + 1

    for i in range(1, n_batches + 1):
        df_batch = df.iloc[(i-1)*batch_size:i*batch_size]

        output_path = build_fulltext_batch_jsonl(
            df=df_batch,
            resource_col=RESOURCE_COL,
            output_path=Path(f"prompts/validate_fetched_publications/fulltext_batch_{i}.jsonl"),
            sources=SOURCES,
            sample_sizes=sample_sizes,
            prompt_name=DEFAULT_DG_PROMPT_NAME,
        )
        logger.info(f"Done. Batch JSONL written to {output_path}")


if __name__ == "__main__":
    main()
