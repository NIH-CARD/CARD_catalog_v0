"""
Stage 2 — GitHub search (no AI).

Wraps scrapers/scrape_github.py with --batch-call-ai so the AI analysis
step is deferred.  The Content_For_Analysis column in the output is
consumed by repo_analysis.py (stage 3).

Input:  inventory .tab file
Output: tables/hits/github_hits_{ts}.tsv
"""
import logging
import subprocess
import sys
from pathlib import Path

from pipelines.base import PipelineStage

logger = logging.getLogger(__name__)

SCRAPERS_DIR = Path(__file__).parent.parent / "scrapers"


class GithubSearchStage(PipelineStage):
    def run(
        self,
        input_path: Path,
        output_path: Path,
        *,
        github_token: str,
        verbose: bool = False,
    ) -> Path:
        cmd = [
            sys.executable, str(SCRAPERS_DIR / "scrape_github.py"),
            "--input", str(input_path),
            "--output", str(output_path),
            "--github-token", github_token,
            "--batch-call-ai",          # skip inline AI — handled by repo_analysis stage
        ]
        if verbose:
            cmd += ["--verbose"]

        logger.info(f"[github_search] running scraper → {output_path.name}")
        result = subprocess.run(cmd, cwd=str(SCRAPERS_DIR))
        if result.returncode != 0:
            raise RuntimeError(f"GitHub scraper exited with code {result.returncode}")
        return output_path
