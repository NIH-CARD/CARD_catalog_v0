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

from pipelines.base import PipelineStage, redact_secrets

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
        log_file: Path | None = None,
        extra_repos_path: Path | None = None,
    ) -> Path:
        args = {k: v for k, v in locals().items() if k not in ("self", "input_path", "output_path")}
        logger.info(f"run called with input_path={input_path}, output_path={output_path}, args={redact_secrets(args)}")
        cmd = [
            sys.executable, str(SCRAPERS_DIR / "scrape_github.py"),
            "--input", str(input_path),
            "--output", str(output_path),
            "--github-token", github_token,
            "--batch-call-ai",          # skip inline AI — handled by repo_analysis stage
            "--request-delay", "0.75",  # 3s default is overly conservative; 0.75s stays well under 5k req/hr limit
            "--search-rate-limit", "30", # search API cap is 30/min authenticated; matches scraper default
        ]
        if verbose:
            cmd += ["--verbose"]
        if log_file:
            cmd += ["--log-file", str(log_file)]
        if extra_repos_path:
            cmd += ["--extra-repos", str(extra_repos_path)]

        logger.info(f"running scraper → {output_path.name}")
        try:
            subprocess.run(cmd, cwd=str(SCRAPERS_DIR), check=True, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "(no stderr captured)")[-2000:]
            logger.error(f"GitHub scraper exited with code {e.returncode}: {stderr}")
            raise RuntimeError(f"GitHub scraper exited with code {e.returncode}") from e
        return output_path
