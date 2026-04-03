"""
Stage 3 — GitHub repository AI analysis.

Wraps scrapers/batch_ai_analysis.py (Batch API).
Input:  tables/hits/github_hits_{ts}.tsv  (from github_search stage)
Output: tables/hits/github_analyzed_{ts}.tsv
"""
import logging
import subprocess
import sys
from pathlib import Path

from pipelines.base import PipelineStage

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
    ) -> Path:
        cmd = [
            sys.executable, str(SCRAPERS_DIR / "batch_ai_analysis.py"),
            "--input", str(input_path),
            "--output", str(output_path),
        ]
        if anthropic_key:
            cmd += ["--anthropic-key", anthropic_key]
        if verbose:
            cmd += ["--verbose"]

        logger.info(f"[repo_analysis] running batch AI analysis → {output_path.name}")
        result = subprocess.run(cmd, cwd=str(SCRAPERS_DIR))
        if result.returncode != 0:
            raise RuntimeError(f"Batch AI analysis exited with code {result.returncode}")
        return output_path
