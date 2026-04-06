#!/usr/bin/env python3
"""
CARD Catalog Pipeline Orchestrator

Coordinates two run modes:

  update        — Incremental PubMed update (last 7 days).
                  Validates and writes new TSV to tables/final/.

  full_rebuild  — Full rebuild from scratch:
                    PubMed (3-year window) + publication metadata (datasets +
                    supplementary) + GitHub search + AI repo analysis +
                    study page navigation.

Usage:
    python orchestrator.py update
    python orchestrator.py full_rebuild
    python orchestrator.py update --query-method v2 --verbose
    python orchestrator.py full_rebuild --skip page_navigation

Each stage writes intermediate output to tables/hits/.
The normalizer then validates and writes app-ready files to tables/final/.
Both subdirectories are committed to the repo.
"""

import argparse
import logging
import os
import sys
from datetime import datetime, date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
TABLES_DIR = PROJECT_ROOT / "tables"
HITS_DIR = TABLES_DIR / "hits"
FINAL_DIR = TABLES_DIR / "final"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest(directory: Path, pattern: str) -> Path | None:
    """Return most recently modified file matching pattern in directory."""
    matches = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _today_file(directory: Path, pattern: str) -> Path | None:
    """Return a file matching pattern that was last modified today, if any."""
    today = date.today().isoformat()
    for f in sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True):
        if today in f.name or f.stat().st_mtime >= datetime.combine(date.today(), datetime.min.time()).timestamp():
            return f
    return None


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# Stage runner with skip-if-fresh logic
# ---------------------------------------------------------------------------

def run_stage(
    stage_name: str,
    stage,                     # PipelineStage instance
    input_path: Path,
    hits_pattern: str,
    stage_kwargs: dict,
    skip_stages: list[str],
    force: bool = False,
) -> Path | None:
    """
    Run a pipeline stage, writing output to HITS_DIR.
    Skips if a today-dated hits file already exists (restartability).

    Returns the output path, or None if skipped/failed.
    """
    if stage_name in skip_stages:
        logger.info(f"[{stage_name}] skipped (--skip flag)")
        return _latest(HITS_DIR, hits_pattern)

    if not force:
        existing = _today_file(HITS_DIR, hits_pattern)
        if existing:
            logger.info(f"[{stage_name}] today's hits file exists — skipping: {existing.name}")
            return existing

    timestamp = _ts()
    stem = hits_pattern.replace("*", "").replace(".tsv", "")
    output_path = HITS_DIR / f"{stem}{timestamp}.tsv"

    try:
        result = stage.run(input_path, output_path, **stage_kwargs)
        return result
    except Exception as e:
        logger.error(f"[{stage_name}] failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Normalize helper
# ---------------------------------------------------------------------------

def run_normalizer(
    hits_path: Path,
    target: str,
    final_pattern: str,
    skip_if_exists: bool = True,
) -> Path | None:
    """Normalize a hits file and write to FINAL_DIR."""
    if skip_if_exists:
        existing = _today_file(FINAL_DIR, final_pattern)
        if existing:
            logger.info(f"[normalizer/{target}] today's final file exists — skipping: {existing.name}")
            return existing

    timestamp = _ts()
    stem = final_pattern.replace("*", "").replace(".tsv", "")
    output_path = FINAL_DIR / f"{stem}{timestamp}.tsv"

    try:
        from staging.normalizer import normalize
        return normalize(hits_path, target, output_path)
    except Exception as e:
        logger.error(f"[normalizer/{target}] failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Update mode (incremental)
# ---------------------------------------------------------------------------

def run_incremental_update(
    inventory: Path,
    query_method: str,
    max_results: int,
    ncbi_api_key: str | None,
    verbose: bool,
    skip_stages: list[str],
) -> None:
    logger.info("=" * 60)
    logger.info("UPDATE")
    logger.info("=" * 60)

    from pipelines.pubmed_search import PubmedStage

    # 1. Scrape last 7 days
    hits_path = run_stage(
        "pubmed_search", PubmedStage(),
        input_path=inventory,
        hits_pattern="pubmed_hits_*.tsv",
        stage_kwargs=dict(
            query_method=query_method,
            years=0.02,
            max_results=max_results,
            ncbi_api_key=ncbi_api_key,
            verbose=verbose,
        ),
        skip_stages=skip_stages,
    )
    if not hits_path or not hits_path.exists():
        logger.error("Weekly PubMed scrape produced no output — aborting.")
        return

    # 2. Normalize hits directly → tables/final/
    run_normalizer(hits_path, "publications", "pubmed_central_*.tsv", skip_if_exists=False)


# ---------------------------------------------------------------------------
# Quarterly mode
# ---------------------------------------------------------------------------

def run_full_rebuild(
    inventory: Path,
    query_method: str,
    max_results: int,
    ncbi_api_key: str | None,
    github_token: str | None,
    anthropic_key: str | None,
    firefox_profile_dir: str | None,
    verbose: bool,
    skip_stages: list[str],
) -> None:
    logger.info("=" * 60)
    logger.info("FULL REBUILD")
    logger.info("=" * 60)

    # --- Stage 1: PubMed ---
    from pipelines.pubmed_search import PubmedStage
    pubmed_hits = run_stage(
        "pubmed_search", PubmedStage(),
        input_path=inventory,
        hits_pattern="pubmed_hits_*.tsv",
        stage_kwargs=dict(
            query_method=query_method,
            years=3,
            max_results=max_results,
            ncbi_api_key=ncbi_api_key,
            verbose=verbose,
        ),
        skip_stages=skip_stages,
    )
    if pubmed_hits and pubmed_hits.exists():
        run_normalizer(pubmed_hits, "publications", "pubmed_central_*.tsv")

    # --- Stage 4: Publication metadata (needs pubmed_hits) ---
    if pubmed_hits and pubmed_hits.exists():
        from pipelines.pub_metadata import PubMetadataStage
        pub_datasets_hits = run_stage(
            "pub_metadata", PubMetadataStage(),
            input_path=pubmed_hits,
            hits_pattern="pub_datasets_*.tsv",
            stage_kwargs=dict(anthropic_key=anthropic_key, verbose=verbose),
            skip_stages=skip_stages,
        )
        if pub_datasets_hits and pub_datasets_hits.exists():
            run_normalizer(pub_datasets_hits, "pub_datasets", "pub_datasets_*.tsv")
        # Supplementary is written as side-effect by pub_metadata stage
        supp_hits = _latest(HITS_DIR, "pub_supplementary_*.tsv")
        if supp_hits:
            run_normalizer(supp_hits, "supplementary", "pub_supplementary_*.tsv")
    else:
        logger.warning("Skipping pub_metadata: no pubmed_hits available")

    # --- Stage 2: GitHub search ---
    if not github_token:
        logger.warning("GITHUB_TOKEN not set — skipping github_search and repo_analysis")
    else:
        from pipelines.github_search import GithubSearchStage
        github_hits = run_stage(
            "github_search", GithubSearchStage(),
            input_path=inventory,
            hits_pattern="github_hits_*.tsv",
            stage_kwargs=dict(github_token=github_token, verbose=verbose),
            skip_stages=skip_stages,
        )

        # --- Stage 3: Repo AI analysis ---
        if github_hits and github_hits.exists():
            from pipelines.repo_analysis import RepoAnalysisStage
            analyzed_hits = run_stage(
                "repo_analysis", RepoAnalysisStage(),
                input_path=github_hits,
                hits_pattern="github_analyzed_*.tsv",
                stage_kwargs=dict(anthropic_key=anthropic_key, verbose=verbose),
                skip_stages=skip_stages,
            )
            if analyzed_hits and analyzed_hits.exists():
                run_normalizer(analyzed_hits, "code", "gits_to_reannotate_completed_*.tsv")

    # --- Stage 5: Page navigation ---
    from pipelines.page_navigation import PageNavigationStage
    nav_hits = run_stage(
        "page_navigation", PageNavigationStage(),
        input_path=inventory,
        hits_pattern="new_corpus_*.tsv",
        stage_kwargs=dict(
            firefox_profile_dir=firefox_profile_dir,
            anthropic_key=anthropic_key,
            verbose=verbose,
        ),
        skip_stages=skip_stages,
    )
    if nav_hits and nav_hits.exists():
        run_normalizer(nav_hits, "new_corpus", "new_corpus_*.tsv")

    logger.info("=" * 60)
    logger.info("FULL REBUILD COMPLETE")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="CARD Catalog pipeline orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "mode", choices=["update", "full_rebuild"],
        help="'update' for incremental 7-day PubMed update; 'full_rebuild' for all stages",
    )
    parser.add_argument(
        "--inventory", "-i", default=None,
        help="Path to resource inventory TSV (default: latest resources-inventory*.tab in tables/)",
    )
    parser.add_argument(
        "--query-method", choices=["original", "v2", "v3"], default="v3",
        help="PubMed query method (default: v3)",
    )
    parser.add_argument(
        "--max-results", "-m", type=int, default=100,
        help="Max PubMed results per resource (default: 100)",
    )
    parser.add_argument(
        "--ncbi-api-key", default=None,
        help="NCBI API key (default: NCBI_API_KEY env var)",
    )
    parser.add_argument(
        "--github-token", default=None,
        help="GitHub token for quarterly GitHub scrape (default: GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--anthropic-key", default=None,
        help="Anthropic API key for AI stages (default: ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--firefox-profile-dir", default=None,
        help="Pre-authenticated Firefox profile dir for page_navigation stage "
             "(default: FIREFOX_PROFILE_DIR env var)",
    )
    parser.add_argument(
        "--skip", nargs="*", default=[],
        metavar="STAGE",
        help="Stage names to skip, e.g. --skip page_navigation repo_analysis",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-run stages even if today's hits file already exists",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose (DEBUG) logging in scrapers",
    )

    args = parser.parse_args()

    # Resolve inventory
    if args.inventory:
        inventory = Path(args.inventory)
        if not inventory.exists():
            logger.error(f"Inventory file not found: {inventory}")
            sys.exit(1)
    else:
        inventory = _latest(TABLES_DIR, "resources-inventory*")
        if inventory is None:
            logger.error("No resources-inventory file found in tables/. Use --inventory.")
            sys.exit(1)
        logger.info(f"Using inventory: {inventory.name}")

    # Resolve credentials
    ncbi_key = args.ncbi_api_key or os.getenv("NCBI_API_KEY")
    github_token = args.github_token or os.getenv("GITHUB_TOKEN")
    anthropic_key = args.anthropic_key or os.getenv("ANTHROPIC_API_KEY")
    firefox_profile = args.firefox_profile_dir or os.getenv("FIREFOX_PROFILE_DIR")

    skip_stages = args.skip or []

    if args.mode == "update":
        run_incremental_update(inventory, args.query_method, args.max_results, ncbi_key, args.verbose, skip_stages)
    elif args.mode == "full_rebuild":
        run_full_rebuild(
            inventory, args.query_method, args.max_results,
            ncbi_key, github_token, anthropic_key, firefox_profile,
            args.verbose, skip_stages,
        )


if __name__ == "__main__":
    main()
