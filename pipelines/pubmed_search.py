"""
Stage 1 — PubMed extraction.

Wraps scrapers/scrape_publications.py as a subprocess.
Input:  inventory .tab file
Output: tables/hits/pubmed_hits_{ts}.tsv
"""
import logging
import subprocess
import sys
from pathlib import Path

from pipelines.base import PipelineStage, redact_secrets

logger = logging.getLogger(__name__)

SCRAPERS_DIR = Path(__file__).parent.parent / "scrapers"
LOGS_DIR = Path(__file__).parent.parent / "logs"


class PubmedStage(PipelineStage):
    def run(
        self,
        input_path: Path,
        output_path: Path,
        *,
        query_method: str = "v3",
        years: float = 3,
        max_results: int = 100,
        ncbi_api_key: str | None = None,
        verbose: bool = False,
        log_file: Path | None = None,
    ) -> Path:
        args = {k: v for k, v in locals().items() if k not in ("self", "input_path", "output_path")}
        logger.info(f"run called with input_path={input_path}, output_path={output_path}, args={redact_secrets(args)}")
        cmd = [
            sys.executable, str(SCRAPERS_DIR / "scrape_publications.py"),
            "--input", str(input_path),
            "--output", str(output_path),
            "--query-method", query_method,
            "--years", str(years),
            "--max-results", str(max_results),
        ]
        if ncbi_api_key:
            cmd += ["--ncbi-api-key", ncbi_api_key]
        if verbose:
            cmd += ["--verbose"]
        if log_file:
            cmd += ["--log-file", str(log_file)]

        logger.info(f"Running scraper → {output_path.name}")
        try:
            subprocess.run(cmd, cwd=str(SCRAPERS_DIR), check=True, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "(no stderr captured)")[-2000:]
            logger.error(f"PubMed scraper exited with code {e.returncode}: {stderr}")
            raise RuntimeError(f"PubMed scraper exited with code {e.returncode}") from e

        # Log output schema and row count
        try:
            import pandas as pd
            from staging.schemas import PUBMED_HITS_COLUMNS
            df = pd.read_csv(output_path, sep="\t", nrows=0)
            actual_cols = list(df.columns)
            n_rows = sum(1 for _ in open(output_path)) - 1  # subtract header
            missing = [c for c in PUBMED_HITS_COLUMNS if c not in actual_cols]
            extra   = [c for c in actual_cols if c not in PUBMED_HITS_COLUMNS]
            logger.info(f"Hits schema: {actual_cols}")
            logger.info(f"Rows: {n_rows}")
            if missing:
                logger.warning(f"Columns missing vs expected schema: {missing}")
            if extra:
                logger.info(f"Extra columns not in schema: {extra}")
        except Exception as e:
            logger.warning(f"Could not read output for schema check: {e}")

        return output_path
