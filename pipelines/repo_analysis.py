"""
Stage 3 — GitHub repository AI analysis.

Wraps scrapers/batch_ai_analysis.py (Batch API).
Input:  tables/hits/github_hits_{ts}.tsv  (from github_search stage)
Output: tables/hits/github_analyzed_{ts}.tsv

When use_cache is True (default), repos already present in the latest
tables/final/gits_to_reannotate_completed_*.tsv are skipped — only newly
discovered repos are sent through the (paid) Anthropic Batch API. Cached
rows are merged back into the output so nothing already analyzed is lost.
"""
import logging
import subprocess
import sys
from pathlib import Path

import pandas as pd

from pipelines.base import PipelineStage, redact_secrets
from staging.cache_utils import combine_cached_and_new, latest_final

logger = logging.getLogger(__name__)

SCRAPERS_DIR = Path(__file__).parent.parent / "scrapers"


class RepoAnalysisStage(PipelineStage):
    def run(
        self,
        input_path: Path,
        output_path: Path,
        *,
        anthropic_key: str | None = None,
        verbose: bool = False,
        log_file: Path | None = None,
        use_cache: bool = True,
    ) -> Path:
        args = {k: v for k, v in locals().items() if k not in ("self", "input_path", "output_path")}
        logger.info(f"run called with input_path={input_path}, output_path={output_path}, args={redact_secrets(args)}")
        github_df = pd.read_csv(input_path, sep="\t", dtype=str).fillna("")

        cached_df = None
        if use_cache:
            prev = latest_final("gits_to_reannotate_completed_*.tsv")
            if prev:
                cached_df = pd.read_csv(prev, sep="\t", dtype=str).fillna("")
                # FAIR Score/Issues are added by the normalizer's FAIR-log join, not
                # part of the AI analysis being cached — drop so the next normalize()
                # pass recomputes them fresh instead of colliding with a stale merge.
                cached_df = cached_df.drop(columns=["FAIR Score", "FAIR Issues"], errors="ignore")

        known_repos = set(cached_df["Repository Link"].unique()) if cached_df is not None else set()
        new_repos_df = github_df[~github_df["Repository Link"].isin(known_repos)]
        if cached_df is not None:
            logger.info(
                f"{len(github_df) - len(new_repos_df)} repos already cached, {len(new_repos_df)} new"
            )

        analyzed_df = None
        if not new_repos_df.empty:
            new_input_path = output_path.with_suffix(".new_input.tsv")
            new_repos_df.to_csv(new_input_path, sep="\t", index=False)

            cmd = [
                sys.executable, str(SCRAPERS_DIR / "batch_ai_analysis.py"),
                "--input", str(new_input_path),
                "--output", str(output_path),
            ]
            if anthropic_key:
                cmd += ["--anthropic-key", anthropic_key]
            if verbose:
                cmd += ["--verbose"]
            if log_file:
                cmd += ["--log-file", str(log_file)]

            logger.info(f"Running batch AI analysis on {len(new_repos_df)} new repos → {output_path.name}")
            result = subprocess.run(cmd, cwd=str(SCRAPERS_DIR))
            new_input_path.unlink(missing_ok=True)
            if result.returncode != 0:
                raise RuntimeError(f"Batch AI analysis exited with code {result.returncode}")
            if output_path.exists():
                analyzed_df = pd.read_csv(output_path, sep="\t", dtype=str).fillna("")

        combined = combine_cached_and_new(cached_df, analyzed_df)
        if combined is not None:
            combined.to_csv(output_path, sep="\t", index=False)
            logger.info(f"Repo analysis → {output_path.name} ({len(combined)} rows)")
        else:
            logger.warning("No repos analyzed")

        return output_path
