#!/usr/bin/env python3
"""
CARD Catalog Pipeline Orchestrator

Coordinates two run modes:

  update        — Incremental PubMed update (last 7 days).
                  Validates and writes new TSV to tables/final/.

  full_rebuild  — Full rebuild from scratch:
                    PubMed (3-year window) + publication metadata (datasets +
                    supplementary + grants + software mentions, run
                    concurrently) + SciLite annotations (Europe PMC) +
                    GitHub search + AI repo analysis + study page navigation.

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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
TABLES_DIR = PROJECT_ROOT / "tables"
HITS_DIR = TABLES_DIR / "hits"
FINAL_DIR = TABLES_DIR / "final"
CACHE_DIR = TABLES_DIR / "cache"
LOGS_DIR = PROJECT_ROOT / "logs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

def _add_file_handler(log_file: Path, verbose: bool = False) -> None:
    """Attach a file handler to the root logger."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logging.getLogger().addHandler(handler)
    for noisy in ("httpx", "urllib3", "httpcore", "hpack", "h2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logger.info(f"Logging to file: {log_file}")



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest(directory: Path, pattern: str) -> Path | None:
    """Return most recently modified file matching pattern in directory."""
    matches = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _today_file(directory: Path, pattern: str) -> Path | None:
      today = date.today().strftime("%Y%m%d")   # was .isoformat()
      today_midnight = datetime.combine(date.today(), datetime.min.time()).timestamp()
      for f in sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True):
          if today in f.name or f.stat().st_mtime >= today_midnight:
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
    ext = Path(hits_pattern).suffix or ".tsv"
    stem = hits_pattern.replace("*", "").replace(ext, "")
    output_path = HITS_DIR / f"{stem}{timestamp}{ext}"

    try:
        result = stage.run(input_path, output_path, **stage_kwargs)
        return result
    except Exception as e:
        logger.error(f"[{stage_name}] failed: {e}")
        return None


def run_stages_concurrently(
    specs: list[tuple[str, object, str, dict]],
    input_path: Path,
    skip_stages: list[str],
    force: bool = False,
) -> dict[str, Path | None]:
    """
    Run several independent stages concurrently via a thread pool.

    Each stage here just blocks on its own network I/O (submitting an
    Anthropic Batch job and polling for completion), so threads give real
    wall-clock savings — three stages waiting on their own batches in
    parallel instead of one after another — without needing subprocess or
    asyncio machinery.

    Args:
        specs: list of (stage_name, stage_instance, hits_pattern, stage_kwargs),
            one tuple per stage to run — same shape as individual run_stage() calls.
        input_path: shared input file passed to every stage.
        skip_stages: stage names to skip (same semantics as run_stage).
        force: re-run even if today's hits file exists (same semantics as run_stage).

    Returns:
        dict mapping stage_name -> output Path, or None if skipped/failed.
    """
    results: dict[str, Path | None] = {}
    to_run: list[tuple[str, object, Path, dict]] = []

    for stage_name, stage, hits_pattern, stage_kwargs in specs:
        if stage_name in skip_stages:
            logger.info(f"[{stage_name}] skipped (--skip flag)")
            results[stage_name] = _latest(HITS_DIR, hits_pattern)
            continue

        if not force:
            existing = _today_file(HITS_DIR, hits_pattern)
            if existing:
                logger.info(f"[{stage_name}] today's hits file exists — skipping: {existing.name}")
                results[stage_name] = existing
                continue

        timestamp = _ts()
        ext = Path(hits_pattern).suffix or ".tsv"
        stem = hits_pattern.replace("*", "").replace(ext, "")
        output_path = HITS_DIR / f"{stem}{timestamp}{ext}"
        to_run.append((stage_name, stage, output_path, stage_kwargs))

    if to_run:
        with ThreadPoolExecutor(max_workers=len(to_run)) as executor:
            future_to_name = {
                executor.submit(stage.run, input_path, output_path, **stage_kwargs): stage_name
                for stage_name, stage, output_path, stage_kwargs in to_run
            }
            for future in as_completed(future_to_name):
                stage_name = future_to_name[future]
                try:
                    results[stage_name] = future.result()
                except Exception as e:
                    logger.error(f"[{stage_name}] failed: {e}")
                    results[stage_name] = None

    return results


# ---------------------------------------------------------------------------
# Normalize helper
# ---------------------------------------------------------------------------

def run_normalizer(
    hits_path: Path,
    target: str,
    final_pattern: str,
    skip_if_exists: bool = True,
    force: bool = False,
) -> Path | None:
    """Normalize a hits file and write to FINAL_DIR."""
    if skip_if_exists and not force:
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
    force: bool = False,
    log_file: Path | None = None,
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
            log_file=log_file,
        ),
        skip_stages=skip_stages,
        force=force,
    )
    if not hits_path or not hits_path.exists():
        logger.error("Weekly PubMed scrape produced no output — aborting.")
        return

    # 2. Normalize hits directly → tables/final/
    run_normalizer(hits_path, "publications", "pubmed_central_*.tsv", skip_if_exists=False, force=force)


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
    force: bool = False,
    log_file: Path | None = None,
    use_cache: bool = True,
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
            log_file=log_file,
        ),
        skip_stages=skip_stages,
        force=force,
    )
    if pubmed_hits and pubmed_hits.exists():
        run_normalizer(pubmed_hits, "publications", "pubmed_central_*.tsv", force=force)

    # --- Stage 4: Publication metadata — datasets/supplementary/grants/software (needs pubmed_hits) ---
    # These four are fully independent (separate DataGatherer calls, separate
    # output files, separate caches) and each just blocks on its own Anthropic
    # Batch job, so they run concurrently rather than one after another.
    extra_repos_path: Path | None = None  # GitHub repos discovered via pub_software, fed to github_search below
    if pubmed_hits and pubmed_hits.exists():
        from pipelines.pub_datasets import PubDatasetsStage
        from pipelines.pub_supplementary import PubSupplementaryStage
        from pipelines.pub_grants import PubGrantsStage
        from pipelines.pub_software import PubSoftwareStage
        from pipelines.pub_metadata_shared import load_pmc_links, prefetch_articles

        # Fetch each article's full text once, up front, so the four stages below
        # (which all need the same PMC full text) read from a shared cache instead
        # of each independently re-fetching the same ~1000 articles over the network.
        # Stable filename (no per-run timestamp) — prefetch_articles reads-and-updates
        # this same file every run, so already-fetched articles are never refetched.
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fetch_cache_path = CACHE_DIR / "pub_fulltext_cache.parquet"
        prefetch_articles(
            load_pmc_links(pubmed_hits), fetch_cache_path,
            log_level="DEBUG" if verbose else "INFO",
            log_file_str=str(log_file) if log_file else None,
        )

        pub_metadata_kwargs = dict(
            anthropic_key=anthropic_key, verbose=verbose, log_file=log_file,
            use_cache=use_cache, fetch_cache_path=fetch_cache_path,
        )
        pub_metadata_results = run_stages_concurrently(
            specs=[
                ("pub_datasets", PubDatasetsStage(), "pub_datasets_*.tsv", pub_metadata_kwargs),
                ("pub_supplementary", PubSupplementaryStage(), "pub_supplementary_*.tsv", pub_metadata_kwargs),
                ("pub_grants", PubGrantsStage(), "pub_grants_*.tsv", pub_metadata_kwargs),
                ("pub_software", PubSoftwareStage(), "pub_software_*.tsv", pub_metadata_kwargs),
            ],
            input_path=pubmed_hits,
            skip_stages=skip_stages,
            force=force,
        )

        pub_datasets_hits = pub_metadata_results["pub_datasets"]
        if pub_datasets_hits and pub_datasets_hits.exists():
            run_normalizer(pub_datasets_hits, "pub_datasets", "pub_datasets_*.tsv", force=force)

        supp_hits = pub_metadata_results["pub_supplementary"]
        if supp_hits and supp_hits.exists():
            run_normalizer(supp_hits, "supplementary", "pub_supplementary_*.tsv", force=force)

        grants_hits = pub_metadata_results["pub_grants"]
        if grants_hits and grants_hits.exists():
            run_normalizer(grants_hits, "pub_grants", "pub_grants_*.tsv", force=force)

        software_hits = pub_metadata_results["pub_software"]
        if software_hits and software_hits.exists():
            run_normalizer(software_hits, "pub_software", "pub_software_*.tsv", force=force)

            # GitHub repos mentioned in papers (found by pub_software) don't go straight
            # into "code" — they need the same tree-walk/README/FAIR-check enrichment as
            # repos found via GitHub Code Search, so they're handed to github_search
            # (via --extra-repos) and get concatenated in before repo_analysis runs.
            import pandas as pd
            sw_df = pd.read_csv(software_hits, sep="\t", dtype=str).fillna("")
            if "url" in sw_df.columns:
                gh_matches = sw_df[sw_df["url"].str.contains(r"github\.com/[\w.-]+/[\w.-]+", regex=True, na=False)]
                if not gh_matches.empty:
                    pubs_df = pd.read_csv(pubmed_hits, sep="\t", dtype=str).fillna("")
                    joined = gh_matches.merge(
                        pubs_df[["PubMed Central Link", "Resource Name", "Abbreviation", "Diseases Included"]],
                        left_on="source_url", right_on="PubMed Central Link", how="left",
                    )
                    candidates = joined[["Resource Name", "Abbreviation", "Diseases Included", "url"]].rename(
                        columns={"url": "Repository Link"}
                    )
                    extra_repos_path = HITS_DIR / f"extra_repos_from_software_{_ts()}.tsv"
                    candidates.to_csv(extra_repos_path, sep="\t", index=False)
                    logger.info(f"{len(candidates)} GitHub repo(s) from pub_software → {extra_repos_path.name}")
    else:
        logger.warning("Skipping pub_datasets/pub_supplementary/pub_grants/pub_software: no pubmed_hits available")

    # --- Stage 6: SciLite annotations (Europe PMC) ---
    if pubmed_hits and pubmed_hits.exists():
        from pipelines.scilite import SciLiteStage
        run_stage(
            "scilite", SciLiteStage(),
            input_path=pubmed_hits,
            hits_pattern="annotations_*.json",
            stage_kwargs=dict(verbose=verbose, log_file=log_file),
            skip_stages=skip_stages,
            force=force,
        )
        scilite_hits = _latest(HITS_DIR, "scilite_annotations_*.tsv")
        if scilite_hits:
            run_normalizer(scilite_hits, "scilite", "scilite_annotations_*.tsv", force=force)
    else:
        logger.warning("Skipping scilite: no pubmed_hits available")

    # --- Stage 2: GitHub search ---
    if not github_token:
        logger.warning("GITHUB_TOKEN not set — skipping github_search and repo_analysis")
    else:
        from pipelines.github_search import GithubSearchStage
        github_hits = run_stage(
            "github_search", GithubSearchStage(),
            input_path=inventory,
            hits_pattern="github_hits_*.tsv",
            stage_kwargs=dict(
                github_token=github_token, verbose=verbose, log_file=log_file,
                extra_repos_path=extra_repos_path,
            ),
            skip_stages=skip_stages,
            force=force,
        )

        # --- Stage 3: Repo AI analysis ---
        if github_hits and github_hits.exists():
            from pipelines.repo_analysis import RepoAnalysisStage
            analyzed_hits = run_stage(
                "repo_analysis", RepoAnalysisStage(),
                input_path=github_hits,
                hits_pattern="github_analyzed_*.tsv",
                stage_kwargs=dict(anthropic_key=anthropic_key, verbose=verbose, log_file=log_file, use_cache=use_cache),
                skip_stages=skip_stages,
                force=force,
            )
            if analyzed_hits and analyzed_hits.exists():
                run_normalizer(analyzed_hits, "code", "gits_to_reannotate_completed_*.tsv", force=force)

    # --- Stage 5: Page navigation ---
    if "page_navigation" not in skip_stages:
        from pipelines.page_navigation import _setup_profile, PROFILE_ENV_VAR
        default_profile = os.path.expanduser("~/.card-catalog-firefox-profile")
        firefox_profile_dir = firefox_profile_dir or os.getenv(PROFILE_ENV_VAR) or (
            default_profile if Path(default_profile).exists() else None
        )
        if not firefox_profile_dir:
            logger.info("No Firefox profile found — launching interactive setup...")
            try:
                _setup_profile()
                firefox_profile_dir = default_profile
            except Exception as e:
                logger.warning(f"Firefox profile setup failed ({e}) — skipping page_navigation")

        if not firefox_profile_dir:
            logger.warning("No Firefox profile available — skipping page_navigation. "
                           "Run: python -m pipelines.page_navigation --setup-profile")
        else:
            from pipelines.page_navigation import PageNavigationStage
            nav_hits = run_stage(
                "page_navigation", PageNavigationStage(),
                input_path=inventory,
                hits_pattern="new_corpus_*.tsv",
                stage_kwargs=dict(
                    firefox_profile_dir=firefox_profile_dir,
                    anthropic_key=anthropic_key,
                    verbose=verbose,
                    log_file=log_file,
                    use_cache=use_cache,
                ),
                skip_stages=skip_stages,
                force=force,
            )
            if nav_hits and nav_hits.exists():
                run_normalizer(nav_hits, "new_corpus", "new_corpus_*.tsv", force=force)

    # --- Final step: join SciLite annotations and cited datasets into publications ---
    from staging.join_annotations import join_annotations
    logger.info("Joining SciLite annotations and cited datasets into publications…")
    join_annotations()

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
        help="Path to resource inventory file (default: latest resources-inventory-* in tables/)",
    )
    parser.add_argument(
        "--query-method", choices=["original", "v2", "v3"], default="v3",
        help="PubMed query method (default: v3)",
    )
    parser.add_argument(
        "--max-results", "-m", type=int, default=150,
        help="Max PubMed results per resource (default: 150)",
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
        "--no-cache", action="store_true",
        help="Reprocess every item in pub_datasets/pub_supplementary/pub_grants/"
             "pub_software/repo_analysis/page_navigation, ignoring what's already "
             "in tables/final/ (a true full rebuild)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose (DEBUG) logging in scrapers",
    )
    parser.add_argument(
        "--log-file", default=None,
        help="Log file path (default: logs/orchestrator_{timestamp}.log)",
    )

    args = parser.parse_args()

    # Set up file logging
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(args.log_file) if args.log_file else LOGS_DIR / f"orchestrator_{timestamp}.log"
    _add_file_handler(log_file, verbose=args.verbose)

    # Resolve inventory
    if args.inventory:
        inventory = Path(args.inventory)
        if not inventory.exists():
            logger.error(f"Inventory file not found: {inventory}")
            sys.exit(1)
    else:
        import glob as _glob
        pattern = str(TABLES_DIR / "resources-inventory-*")
        logger.info(f"Searching for files with pattern: {pattern}")
        matches = _glob.glob(pattern)
        logger.info(f"Found {len(matches)} files matching pattern(s)")
        if not matches:
            logger.error("No resources-inventory-* file found in tables/. Use --inventory.")
            sys.exit(1)
        inventory = Path(max(matches, key=lambda x: Path(x).stat().st_mtime))
        logger.info(f"Latest file found: {inventory}")

    # Resolve credentials
    ncbi_key = args.ncbi_api_key or os.getenv("NCBI_API_KEY")
    github_token = args.github_token or os.getenv("GITHUB_TOKEN")
    anthropic_key = args.anthropic_key or os.getenv("ANTHROPIC_API_KEY")
    firefox_profile = args.firefox_profile_dir or os.getenv("FIREFOX_PROFILE_DIR")

    skip_stages = args.skip or []

    if args.mode == "update":
        run_incremental_update(inventory, args.query_method, args.max_results, ncbi_key, args.verbose, skip_stages, force=args.force, log_file=log_file)
    elif args.mode == "full_rebuild":
        run_full_rebuild(
            inventory, args.query_method, args.max_results,
            ncbi_key, github_token, anthropic_key, firefox_profile,
            args.verbose, skip_stages, force=args.force, log_file=log_file,
            use_cache=not args.no_cache,
        )


if __name__ == "__main__":
    main()
