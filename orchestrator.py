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

    # Multi-method / misc_publications path: runs each method separately, combines
    # via staging/combine_hits.py, verifies (cache-aware) via
    # staging/validate_fetched_publications.py, and writes
    # tables/final/misc_publications_*.tsv instead of the standard publications
    # table. Triggers when more than one method is given, or the single method
    # given is 'paperclip'.
    python orchestrator.py full_rebuild --query-method all
    python orchestrator.py full_rebuild --query-method v3 v4 paperclip
    python orchestrator.py full_rebuild --query-method paperclip
    python orchestrator.py full_rebuild --query-method paperclip --no-cache-verification

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


def _row_count(path: Path) -> str:
    """' (N rows)' for a TSV, '' otherwise (e.g. scilite's own .json hits) - a cheap line
    count, not a full pandas load, so this never becomes the slow part of logging."""
    if path.suffix != ".tsv":
        return ""
    try:
        n = sum(1 for _ in open(path)) - 1  # subtract header
        return f" ({n} rows)"
    except Exception:
        return ""


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

    logger.info(f"[{stage_name}] starting…")
    try:
        result = stage.run(input_path, output_path, **stage_kwargs)
        if result and result.exists():
            logger.info(f"[{stage_name}] finished -> {result.name}{_row_count(result)}")
        else:
            logger.warning(f"[{stage_name}] finished but produced no output file")
        return result
    except Exception as e:
        logger.error(f"[{stage_name}] failed: {e}", exc_info=True)
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
        logger.info(f"Starting {len(to_run)} concurrent stage(s): {[s for s, *_ in to_run]}")
        with ThreadPoolExecutor(max_workers=len(to_run)) as executor:
            future_to_name = {
                executor.submit(stage.run, input_path, output_path, **stage_kwargs): stage_name
                for stage_name, stage, output_path, stage_kwargs in to_run
            }
            for future in as_completed(future_to_name):
                stage_name = future_to_name[future]
                try:
                    result = future.result()
                    results[stage_name] = result
                    if result and result.exists():
                        logger.info(f"[{stage_name}] finished -> {result.name}{_row_count(result)}")
                    else:
                        logger.warning(f"[{stage_name}] finished but produced no output file")
                except Exception as e:
                    logger.error(f"[{stage_name}] failed: {e}", exc_info=True)
                    results[stage_name] = None

    return results


def prefetch_articles(dg, missing_links: list[str], cache_path: Path, sects_required=5) -> None:
    """Fetch PMC articles absent from the shared parquet cache.

    Runs before the pub_datasets/pub_supplementary/pub_grants/pub_software/pub_models
    stages launch, so all five read from ``cache_path`` instead of each independently
    re-fetching the same articles. Only ``missing_links`` — computed by the caller via
    ``dg.data_fetcher.backup_store.has_publication()`` against the already-warmed cache
    — are ever fetched: ``DataGatherer.fetch_data()`` holds every result (cache hit or
    not) in memory for the whole call and flushes only once at the end, so passing it
    links already in the cache would re-inflate memory for nothing (this OOM'd a
    full_rebuild; see the equivalent fix in
    staging/validate_fetched_publications.py::prefetch_fulltext).

    Args:
        dg: DataGatherer constructed with raw_data_df_parquet_filepath=cache_path.
        missing_links: PMC links absent from cache_path (already filtered by the caller).
        cache_path: Stable .parquet path, reused and updated across runs.
        sects_required: Minimum sections for a fetch to count as complete — must
            match the downstream pub_metadata stages' own requirement.
    """
    logger.info(f"prefetch_articles called with {len(missing_links)} missing link(s), cache_path={cache_path}")
    if not missing_links:
        logger.info(f"[prefetch_articles] nothing missing from {cache_path.name}")
        logger.info("prefetch_articles returning (nothing to fetch)")
        return

    existing_cache = str(cache_path) if cache_path.exists() else None
    dg.fetch_data(
        missing_links, local_fetch_file=existing_cache, write_df_to_path=str(cache_path),
        sects_required=sects_required,
    )
    logger.info(f"Prefetched {len(missing_links)} articles → {cache_path.name}")
    logger.info(f"prefetch_articles returning (fetched {len(missing_links)} article(s))")


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

    logger.info(f"[normalizer/{target}] starting…")
    try:
        from staging.normalizer import normalize
        return normalize(hits_path, target, output_path)
    except Exception as e:
        logger.error(f"[normalizer/{target}] failed: {e}", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Update mode (incremental)
# ---------------------------------------------------------------------------

def run_incremental_update(
    inventory: Path,
    query_methods: list[str],
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

    if len(query_methods) > 1:
        logger.warning(f"update mode only supports one query method — using '{query_methods[0]}', "
                        f"ignoring {query_methods[1:]}. Use full_rebuild for multi-method/misc runs.")
    query_method = query_methods[0]

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
# Multi-method PubMed search (misc/combine_hits path)
# ---------------------------------------------------------------------------

def _run_multi_method_pubmed_search(
    inventory: Path,
    query_methods: list[str],
    max_results: int,
    ncbi_api_key: str | None,
    verbose: bool,
    skip_stages: list[str],
    force: bool,
    log_file: Path | None,
) -> Path | None:
    """Run PubmedStage once per query method, then combine into one hits file.

    Used when more than one query method is requested, or the single requested
    method is 'paperclip' — that method is architecturally closer to this
    combine_hits path than the standard single-NCBI-query flow. Each method
    gets its own hits_pattern (pubmed_hits_<method>_*.tsv) so same-day
    restartability doesn't mistake one method's output for another's.

    Returns:
        Path to the combined tables/hits/combine_hits_{ts}.tsv, or None if
        every method's search produced no output.
    """
    if "pubmed_search" in skip_stages:
        logger.info("[pubmed_search] skipped (--skip flag) — using latest combine_hits_*.tsv")
        return _latest(HITS_DIR, "combine_hits_*.tsv")

    from pipelines.pubmed_search import PubmedStage
    method_hits: list[Path] = []
    for method in query_methods:
        hits_path = run_stage(
            f"pubmed_search_{method}", PubmedStage(),
            input_path=inventory,
            hits_pattern=f"pubmed_hits_{method}_*.tsv",
            stage_kwargs=dict(
                query_method=method, years=3, max_results=max_results,
                ncbi_api_key=ncbi_api_key, verbose=verbose, log_file=log_file,
            ),
            skip_stages=[],
            force=force,
        )
        if hits_path and hits_path.exists():
            method_hits.append(hits_path)
        else:
            logger.warning(f"query method '{method}' produced no output — excluded from combine")

    if not method_hits:
        logger.error("All query methods failed — no hits to combine.")
        return None

    from staging.combine_hits import combine_query_method_hits
    combined = combine_query_method_hits(method_hits)
    HITS_DIR.mkdir(parents=True, exist_ok=True)
    combine_hits_path = HITS_DIR / f"combine_hits_{_ts()}.tsv"
    combined.to_csv(combine_hits_path, sep="\t", index=False)
    logger.info(f"[pubmed_search] combined {len(query_methods)} method(s) -> "
                f"{combine_hits_path.name} ({len(combined)} rows)")
    return combine_hits_path


# ---------------------------------------------------------------------------
# Quarterly mode
# ---------------------------------------------------------------------------

def run_full_rebuild(
    inventory: Path,
    query_methods: list[str],
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
    cache_verification: bool = True,
) -> None:
    logger.info("=" * 60)
    logger.info("FULL REBUILD")
    logger.info("=" * 60)

    # paperclip alone is architecturally closer to the misc/combine_hits path than the
    # standard single-NCBI-query flow, so it triggers this branch too - and so does running
    # page_navigation at all, since its discovered publications only have somewhere to land
    # via the misc_publications path (see extract_new_corpus_publications below).
    misc_mode = (
        len(query_methods) > 1
        or query_methods == ["paperclip"]
        or "page_navigation" not in skip_stages
    )
    new_corpus_final_path: Path | None = None

    # Defined here (not down at Stage 4) so the verification step below can warm the same
    # cache pub_datasets/etc. read from - verification's confirmed subset is a subset of
    # what pub_metadata_input ends up being, so fetching it once here means Stage 4 finds
    # it already cached instead of re-fetching the same articles a second time.
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fetch_cache_path = CACHE_DIR / "fetched_fulltext_batch.parquet"

    # Hardcoded, not a CLI flag: when page_navigation is skipped, still fold the latest
    # already-discovered new_corpus table into this run's verification/misc_publications
    # instead of contributing nothing. Flip to False to make a skipped page_navigation
    # mean "no page-navigation data at all this run," e.g. for a quick pub_metadata-only
    # iteration where reusing stale discoveries isn't wanted.
    include_page_navigation_output = True

    # --- Stage 1: PubMed ---
    if misc_mode:
        pubmed_hits = _run_multi_method_pubmed_search(
            inventory, query_methods, max_results, ncbi_api_key, verbose, skip_stages, force, log_file,
        )
        # The standard publications table isn't rebuilt in this mode — misc_publications
        # (built just below, after page_navigation and before pub_metadata) is the source
        # of truth instead.
    else:
        from pipelines.pubmed_search import PubmedStage
        pubmed_hits = run_stage(
            "pubmed_search", PubmedStage(),
            input_path=inventory,
            hits_pattern="pubmed_hits_*.tsv",
            stage_kwargs=dict(
                query_method=query_methods[0],
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

    # --- Stage 5: Page navigation (moved ahead of pub_metadata) ---
    # Only matters in misc_mode - and misc_mode is defined to be True whenever
    # page_navigation isn't skipped, so this block is a guaranteed no-op whenever
    # misc_mode is False (skip_stages necessarily contains "page_navigation" then).
    # Runs here, before pub_metadata/scilite, so its discovered publications can be
    # merged + verified in time to feed pub_metadata's *input*, not just its own
    # separate misc_publications output.
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
                new_corpus_final_path = run_normalizer(nav_hits, "new_corpus", "new_corpus_*.tsv", force=force)
    elif include_page_navigation_output:
        # page_navigation was skipped this run - fall back to the latest already-discovered
        # new_corpus table rather than contributing nothing, same spirit as pubmed_search's
        # own skip falling back to the latest combine_hits instead of an empty corpus.
        new_corpus_final_path = _latest(FINAL_DIR, "new_corpus_*.tsv")
        if new_corpus_final_path:
            logger.info(f"[page_navigation] skipped — reusing existing {new_corpus_final_path.name}")
        else:
            logger.warning("[page_navigation] skipped and no existing new_corpus_*.tsv found — nothing to reuse")
    else:
        logger.info("[page_navigation] skipped and not reusing existing new_corpus_*.tsv")

    # --- Verify (cache-aware) + build misc_publications (moved ahead of pub_metadata) ---
    # pub_metadata_input is what pub_datasets/pub_supplementary/pub_grants/pub_software/
    # pub_models/scilite actually run against below: the raw pubmed_hits in the standard
    # single-method path (unchanged), or - in misc_mode - the confirmed, deduped subset of
    # the verified/merged hits, so those AI-extraction stages spend their budget only on
    # (resource, paper) pairs already confirmed genuine, not the full noisy candidate pool.
    pub_metadata_input = pubmed_hits
    if misc_mode:
        if pubmed_hits and pubmed_hits.exists():
            logger.info("Verifying combined hits (cache-aware) and building misc_publications…")
            import pandas as pd
            from staging.validate_fetched_publications import validate_publications_df, DEFAULT_CACHE_PATH
            from staging.combine_hits import combine_query_method_hits
            from staging.publication_glue import extract_new_corpus_publications, resolve_missing_pmcids

            hits_paths = [pubmed_hits]
            if new_corpus_final_path and new_corpus_final_path.exists():
                nav_pubs = extract_new_corpus_publications(new_corpus_final_path, ncbi_api_key=ncbi_api_key)
                if not nav_pubs.empty:
                    nav_pubs_path = HITS_DIR / f"new_corpus_publications_{_ts()}.tsv"
                    nav_pubs.to_csv(nav_pubs_path, sep="\t", index=False)
                    logger.info(f"[page_navigation] {len(nav_pubs)} publication reference(s) -> {nav_pubs_path.name}")
                    hits_paths.append(nav_pubs_path)

            combined_df = (
                combine_query_method_hits(hits_paths) if len(hits_paths) > 1
                else pd.read_csv(hits_paths[0], sep="\t", dtype=str).fillna("")
            )

            # DOI-only rows get a PMC ID resolved here (pub_jobs/scilite both need one) -
            # then re-combined so a row that turns out to be the same paper as one already
            # carrying that PMC ID collapses into it, instead of surviving as an untethered
            # duplicate (combine_query_method_hits' union-find already ran once above, on
            # the pre-resolution identifiers, so it needs a second pass on the enriched data).
            combined_df = resolve_missing_pmcids(combined_df, ncbi_api_key=ncbi_api_key)
            resolved_path = HITS_DIR / f"combine_hits_pmcid_resolved_{_ts()}.tsv"
            combined_df.to_csv(resolved_path, sep="\t", index=False)
            logger.info("Re-collapsing duplicates after PMC ID resolution…")
            combined_df = combine_query_method_hits([resolved_path])

            # fulltext_dg_prompt (not the plain "fulltext" method) - matches the offline
            # batch backfill's method, so its seeded cache entries (see
            # seed_cache_from_batch_results) actually get hit instead of re-verified live.
            verified = validate_publications_df(
                combined_df, resource_col="Resource Name", methods=["fulltext_dg_prompt"],
                cache_path=DEFAULT_CACHE_PATH, no_cache=not cache_verification,
                fetch_cache_path=fetch_cache_path,
            )
            verified_hits_path = HITS_DIR / f"misc_publications_{_ts()}.tsv"
            verified.to_csv(verified_hits_path, sep="\t", index=False)
            logger.info(f"[pub_verification] wrote {len(verified)} verified row(s) -> {verified_hits_path.name}")
            run_normalizer(verified_hits_path, "misc_publications", "misc_publications_*.tsv", force=force)

            confirmed_df = verified[verified["Verification Status"] == "confirmed"].copy()
            confirmed_hits_path = HITS_DIR / f"misc_publications_confirmed_{_ts()}.tsv"
            confirmed_df.to_csv(confirmed_hits_path, sep="\t", index=False)
            logger.info(f"[pub_verification] {len(confirmed_df)}/{len(verified)} row(s) confirmed -> "
                        f"{confirmed_hits_path.name} (feeds pub_datasets/supplementary/grants/software/models/scilite)")
            pub_metadata_input = confirmed_hits_path
        else:
            logger.warning("Skipping verification/misc_publications: no combined pubmed hits available")
            pub_metadata_input = None

    # --- Stage 4: Publication metadata — datasets/supplementary/grants/software (needs pub_metadata_input) ---
    # These five are fully independent (separate DataGatherer calls, separate
    # output files, separate caches) and each just blocks on its own Anthropic
    # Batch job, so they run concurrently rather than one after another.
    extra_repos_path: Path | None = None  # GitHub repos discovered via pub_software, fed to github_search below
    if pub_metadata_input and pub_metadata_input.exists():
        from pipelines.pub_datasets import PubDatasetsStage
        from pipelines.pub_supplementary import PubSupplementaryStage
        from pipelines.pub_grants import PubGrantsStage
        from pipelines.pub_software import PubSoftwareStage
        from pipelines.pub_models import PubModelsStage
        from pipelines.pub_metadata_shared import load_pmc_links
        from data_gatherer.data_gatherer import DataGatherer

        # Fetch each article's full text once, up front, so the four stages below
        # (which all need the same PMC full text) read from the same shared cache
        # verification's own prefetch already warmed (see fetch_cache_path definition
        # near the top of this function) instead of each independently re-fetching.
        # dg is constructed here (not inside prefetch_articles) so its BackupDataStore
        # is warmed against fetch_cache_path up front, letting us filter pmc_links down
        # to genuinely missing ones before ever calling fetch_data() — see
        # prefetch_articles's docstring for why that filtering matters.
        pmc_links = load_pmc_links(pub_metadata_input)
        existing_cache = str(fetch_cache_path) if fetch_cache_path.exists() else None
        prefetch_dg = DataGatherer(
            llm_name="claude-haiku-4-5",
            log_level="DEBUG" if verbose else "INFO",
            log_file_override=str(log_file) if log_file else None,
            clear_previous_logs=False,
            raw_data_df_parquet_filepath=existing_cache,
        )
        missing_links = [
            url for url in pmc_links if not prefetch_dg.data_fetcher.backup_store.has_publication(url)
        ]
        logger.info(f"[pub_metadata] {len(pmc_links) - len(missing_links)}/{len(pmc_links)} PMC links "
                    f"already cached, fetching {len(missing_links)} missing")
        prefetch_articles(prefetch_dg, missing_links, fetch_cache_path, sects_required=[])

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
                ("pub_models", PubModelsStage(), "pub_models_*.tsv", pub_metadata_kwargs),
            ],
            input_path=pub_metadata_input,
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
                    pubs_df = pd.read_csv(pub_metadata_input, sep="\t", dtype=str).fillna("")
                    joined = gh_matches.merge(
                        pubs_df[["PubMed Central Link", "Resource Name", "Abbreviation", "Diseases Included"]],
                        left_on="source_url", right_on="PubMed Central Link", how="left",
                    )
                    candidates = joined[
                        ["Resource Name", "Abbreviation", "Diseases Included", "url", "source_url"]
                    ].rename(columns={"url": "Repository Link", "source_url": "Source"})
                    extra_repos_path = HITS_DIR / f"extra_repos_from_software_{_ts()}.tsv"
                    candidates.to_csv(extra_repos_path, sep="\t", index=False)
                    logger.info(f"{len(candidates)} GitHub repo(s) from pub_software → {extra_repos_path.name}")

        models_hits = pub_metadata_results["pub_models"]
        if models_hits and models_hits.exists():
            run_normalizer(models_hits, "pub_models", "pub_models_*.tsv", force=force)
    else:
        logger.warning("Skipping pub_datasets/pub_supplementary/pub_grants/pub_software/pub_models: no pub_metadata_input available")

    # --- Stage 6: SciLite annotations (Europe PMC) ---
    if pub_metadata_input and pub_metadata_input.exists():
        from pipelines.scilite import SciLiteStage
        run_stage(
            "scilite", SciLiteStage(),
            input_path=pub_metadata_input,
            hits_pattern="annotations_*.json",
            stage_kwargs=dict(verbose=verbose, log_file=log_file),
            skip_stages=skip_stages,
            force=force,
        )
        scilite_hits = _latest(HITS_DIR, "scilite_annotations_*.tsv")
        if scilite_hits:
            run_normalizer(scilite_hits, "scilite", "scilite_annotations_*.tsv", force=force)
    else:
        logger.warning("Skipping scilite: no pub_metadata_input available")

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

    # --- Final step: join cell models to publications/studies via SciLite data.
    # (Cross-table annotation/dataset columns on Publications itself were removed -
    # that's now handled by the separate Connections precompute, not baked into
    # the publications table.) ---
    from staging.publication_glue import (
        build_annotation_summary,
        build_scilite_type_aggregate,
        join_cellular_model_publications,
    )
    if misc_mode:
        if pub_metadata_input:
            logger.info("Joining cell models to misc_publications via SciLite…")
            join_cellular_model_publications(pub_pattern="misc_publications_*.tsv")
        else:
            logger.warning("Skipping cell-model join: misc_publications was never built this run")
    else:
        logger.info("Joining cell models to publications via SciLite…")
        join_cellular_model_publications(pub_pattern="pubmed_central_*.tsv")

    logger.info("Building annotation summary (stage counts + SciLite top types)…")
    build_annotation_summary()

    logger.info("Building SciLite per-(PMC ID, Type) aggregate for Connections…")
    build_scilite_type_aggregate()

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
        "--query-method", nargs="+", default=["v3"],
        help="One or more PubMed query methods: original, v2, v3, v4, v5, paperclip, or "
             "'all' (expands to all six). Multiple methods (or the single method "
             "'paperclip') run each method separately, combine the results via "
             "staging/combine_hits.py, and route through the cache-aware verification "
             "step into tables/final/misc_publications_*.tsv instead of the standard "
             "publications table (default: v3)",
    )
    parser.add_argument(
        "--no-cache-verification", action="store_true",
        help="For the multi-method/paperclip verification step: re-verify every "
             "(resource, doc_id) pair, ignoring already-cached verdicts",
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
             "pub_software/pub_models/repo_analysis/page_navigation, ignoring what's "
             "already in tables/final/ (a true full rebuild)",
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

    _ALL_QUERY_METHODS = ["original", "v2", "v3", "v4", "v5", "paperclip"]
    query_methods = _ALL_QUERY_METHODS if args.query_method == ["all"] else args.query_method

    if args.mode == "update":
        run_incremental_update(inventory, query_methods, args.max_results, ncbi_key, args.verbose, skip_stages, force=args.force, log_file=log_file)
    elif args.mode == "full_rebuild":
        run_full_rebuild(
            inventory, query_methods, args.max_results,
            ncbi_key, github_token, anthropic_key, firefox_profile,
            args.verbose, skip_stages, force=args.force, log_file=log_file,
            use_cache=not args.no_cache, cache_verification=not args.no_cache_verification,
        )


if __name__ == "__main__":
    main()
