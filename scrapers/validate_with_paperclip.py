#!/usr/bin/env python3
"""
CARD Catalog - Post-retrieval paperclip validation
Checks any query method's output TSV against paperclip's own full-text
verification, as an independent relevance oracle over rows that were never
verified at retrieval time (q1-q4, v5), or committed with --paperclip-skip-verify.
"""
import argparse
import json
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv

from logging_config import setup_logger, get_default_log_file
from scrape_publications import (
    _paperclip_cli, _paperclip_cli_raw, _paperclip_repo_name,
    _commit_with_retry, _find_stale_doc_ids, _classify_claim,
)

try:
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

PMC_LINK_RE = re.compile(r'/(PMC\d+)/?')
DEFAULT_CACHE_PATH = Path(__file__).parent / ".paperclip_validation_cache.json"


def load_cache(path: Path) -> Dict[str, str]:
    if path.exists():
        try:
            with open(path) as f:
                cache = json.load(f)
            logger.info(f"Loaded validation cache: {len(cache)} entries from {path}")
            return cache
        except Exception as e:
            logger.warning(f"Failed to load cache {path}: {e}")
    return {}


def save_cache(path: Path, cache: Dict[str, str]) -> None:
    # dict(cache) snapshots at a single GIL-protected C-level copy, so a worker
    # thread inserting a new key concurrently can't trigger "dictionary changed
    # size during iteration" during json.dump's iteration over the live dict.
    snapshot = dict(cache)
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)
    logger.info(f"Saved validation cache: {len(snapshot)} entries to {path}")


def cache_key(resource_name: str, doc_id: str) -> str:
    return f"{resource_name}|||{doc_id}"


def _resolve_doc_id(row: Dict[str, str], sources: str) -> Optional[str]:
    """Prefer an explicit Paperclip Doc ID column, then PMC ID (from PubMed Central
    Link), then fall back to a paperclip search by DOI."""
    explicit = (row.get("Paperclip Doc ID") or "").strip()
    if explicit:
        return explicit

    link = row.get("PubMed Central Link", "") or ""
    m = PMC_LINK_RE.search(link)
    if m:
        return m.group(1)

    doi = (row.get("DOI") or "").strip()
    if not doi:
        return None
    out = _paperclip_cli_raw("search", "-s", sources, "-e", doi)
    for line in out.splitlines():
        m = re.search(r'\b(PMC\d+|[a-z]{3}_[0-9a-f]{12})\b', line)
        if m:
            return m.group(1)
    return None


def _find_latest_inventory() -> Optional[Path]:
    """Mirrors orchestrator.py's inventory-resolution pattern (inlined there too, not importable)."""
    matches = list((Path(__file__).parent.parent / "tables").glob("resources-inventory-*"))
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def load_sample_sizes(inventory_path: Optional[Path]) -> Dict[str, str]:
    """Resource Name -> Sample Size, for claim context — not carried in query-method output TSVs."""
    if not inventory_path:
        return {}
    try:
        inv = pd.read_csv(inventory_path, sep="\t", dtype=str).fillna("")
        return dict(zip(inv["Resource Name"], inv["Sample Size"]))
    except Exception as e:
        logger.warning(f"Could not load sample sizes from {inventory_path}: {e}")
        return {}


def _build_claim(resource_name: str, row: Dict[str, str], sample_size: str) -> str:
    """Core assertion stays simple; disease/modality/sample-size are disambiguating
    context, not separate hard requirements a real match must all restate."""
    abbreviation = (row.get("Abbreviation") or "").strip()
    claim = f"This paper describes or uses data from the '{resource_name}' study"
    if abbreviation and abbreviation != resource_name:
        claim += f" (also known as '{abbreviation}')"
    claim += "."

    context = []
    diseases = (row.get("Diseases Included") or "").strip()
    if diseases:
        context.append(f"diseases studied: {diseases}")
    modality = "; ".join(m for m in (
        (row.get("Coarse Data Modality") or "").strip(),
        (row.get("Granular Data Modality") or "").strip(),
    ) if m)
    if modality:
        context.append(f"data modalities: {modality}")
    if sample_size:
        context.append(f"approximate sample size: {sample_size}")
    if context:
        claim += " Context for disambiguation only: " + "; ".join(context) + "."
    return claim


def validate_group(resource_name: str, rows: List[Dict[str, str]], sources: str, jobs: int,
                    cache: Dict[str, str], sample_size: str = "", row_id=None) -> List[str]:
    """Validate one resource's rows against paperclip; return a status string per row."""
    doc_ids = [_resolve_doc_id(row, sources) for row in rows]
    resolved = sum(1 for d in doc_ids if d)
    logger.info(f"[validate] '{resource_name}': {resolved}/{len(rows)} rows resolved to a paperclip doc_id")
    if resolved == 0:
        return ["not_in_corpus"] * len(rows)

    # Dedup: unique (resource, doc_id) pairs, skipping anything already cached
    # from a prior run or an earlier group in this one.
    unique_new_doc_ids = []
    seen = set()
    for doc_id in doc_ids:
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        if cache_key(resource_name, doc_id) not in cache:
            unique_new_doc_ids.append(doc_id)

    n_cached = len(seen) - len(unique_new_doc_ids)
    if n_cached:
        logger.info(f"[validate] '{resource_name}': {n_cached}/{len(seen)} unique doc_ids already cached, skipping")

    if unique_new_doc_ids:
        existing_repos = {r.get("Paperclip Repo", "") for r in rows if r.get("Paperclip Repo")}
        candidate_reuse = list(existing_repos)[0] if len(existing_repos) == 1 else None
        # paperclip repos aren't permanent — confirmed live that repos from an older
        # run can simply be gone. Trusting a dead reuse target skips init+add
        # entirely and silently classifies everything "not_committed".
        # (Keep candidate_reuse — a string — separate from this boolean check: an
        # `and`/`or` chain here would collapse repo_name to a bare True/False on
        # the reuse-valid path instead of preserving the actual repo name string.)
        can_reuse = bool(candidate_reuse) and "not found" not in _paperclip_cli(candidate_reuse, "repo", "status")
        reuse = candidate_reuse if can_reuse else None
        # row_id (the groupby position) only guarantees uniqueness within this run —
        # two genuinely different resources sharing an identical Resource Name string
        # are already merged into one group by df.groupby before this function runs,
        # so this can't undo that; it protects against hash collisions, not that.
        repo_name = reuse or _paperclip_repo_name("validate", resource_name, rows[0].get("Abbreviation", ""), row_id)

        if not reuse:
            init_out = _paperclip_cli_raw("repo", "init", repo_name, f"Validate: {resource_name}"[:200])
            logger.debug(f"[validate] repo init {repo_name}: {init_out[:200]}")

        # Always add, whether reusing or not — a reused repo (e.g. one created by
        # _search_paperclip's own discovery run) was populated for a different,
        # usually much smaller candidate set. Assuming "repo exists" means "already
        # has what we need" silently skipped verifying most of unique_new_doc_ids.
        # repo add on an already-present doc_id is harmless (adds a second claim,
        # not an error), so this is safe to run unconditionally.
        claim = _build_claim(resource_name, rows[0], sample_size)
        for doc_id in unique_new_doc_ids:
            _paperclip_cli(repo_name, "repo", "add", doc_id, claim)

        # Large resources can have hundreds of unique docs — a flat -j 8 would need
        # dozens of rounds to work through them. Paperclip's own CLI docs say
        # over-shooting the server's per-user cap is safe (429s retried internally),
        # so scale jobs with the batch size instead of leaving it fixed.
        effective_jobs = max(jobs, min(len(unique_new_doc_ids), 64))
        commit_out = _commit_with_retry(repo_name, f"Validate {resource_name}", effective_jobs)
        logger.debug(f"[validate] commit {repo_name}: {commit_out[:300]}")

        claims_out = _paperclip_cli(repo_name, "repo", "claims")
        try:
            claims = json.loads(claims_out)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[validate] '{resource_name}': repo claims returned non-JSON output: {claims_out[:200]}")
            claims = []
        # A reused repo can carry >1 claim per doc_id (this run's own add, plus
        # whatever a prior process — e.g. _search_paperclip's own discovery —
        # already committed there). A plain dict comprehension would keep only
        # the last claim in the array; reduce properly instead so a real True
        # verdict from either claim isn't silently dropped by a later None/False.
        claims_by_doc: Dict[str, List[dict]] = {}
        for c in claims:
            claims_by_doc.setdefault(c.get("paperclip_doc_id"), []).append(c)
        verified_map = {}
        for doc_id, doc_claims in claims_by_doc.items():
            if any(c.get("verified") is True for c in doc_claims):
                verified_map[doc_id] = True
            elif any(c.get("verified") is False for c in doc_claims):
                verified_map[doc_id] = False
            else:
                verified_map[doc_id] = None

        stale_doc_ids = _find_stale_doc_ids(repo_name)
        if stale_doc_ids:
            logger.info(f"[validate] '{resource_name}': {len(stale_doc_ids)} doc_id(s) permanently unavailable (no loadable full text), not a verdict")

        for doc_id in unique_new_doc_ids:
            status = _classify_claim(doc_id, verified_map, stale_doc_ids)
            # not_committed isn't a real verdict — it means paperclip hasn't
            # finished checking yet, not that the check came back negative.
            # Caching it would permanently mask genuine progress on a retry.
            if status != "not_committed":
                cache[cache_key(resource_name, doc_id)] = status

    statuses = []
    for doc_id in doc_ids:
        if not doc_id:
            statuses.append("not_in_corpus")
        else:
            statuses.append(cache.get(cache_key(resource_name, doc_id), "not_committed"))
    return statuses


def main():
    parser = argparse.ArgumentParser(description='Validate any query-method output TSV against paperclip full-text verification')
    parser.add_argument('--input', '-i', required=True, help='Input TSV to validate')
    parser.add_argument('--output', '-o', default=None, help='Output TSV (default: <input>_validated.tsv)')
    parser.add_argument('--resource-col', default='Resource Name', help='Column to group rows by (default: "Resource Name")')
    parser.add_argument('--sources', default='pmc,biorxiv,medrxiv,arxiv,trials',
                       help='Comma-separated paperclip -s/--source value(s) for DOI-fallback lookup (default: pmc,biorxiv,medrxiv,arxiv,trials)')
    parser.add_argument('--jobs', '-j', type=int, default=8, help='Concurrent paperclip verify jobs per repo commit (default: 8)')
    parser.add_argument('--workers', type=int, default=None,
                       help='Concurrent resource validations (default: min(16, cpu_count-2), matching _search_paperclip)')
    parser.add_argument('--inventory', default=None,
                       help='Resource inventory TSV, for Sample Size claim context (default: latest tables/resources-inventory-* by mtime)')
    parser.add_argument('--cache-file', default=str(DEFAULT_CACHE_PATH),
                       help=f'Cache of already-verified (resource, doc_id) pairs, shared across runs (default: {DEFAULT_CACHE_PATH})')
    parser.add_argument('--no-cache', action='store_true', help='Ignore and do not update the cache (always re-verify)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose (DEBUG) logging')
    parser.add_argument('--quiet', '-q', action='store_true', help='Show only warnings and errors')
    parser.add_argument('--log-file', default=None, help='Log file path')
    parser.add_argument('--clear-log', action='store_true', help='Clear log file before writing (default: append)')
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else (logging.WARNING if args.quiet else logging.INFO)
    log_file = args.log_file or get_default_log_file("paperclip_validation")
    setup_logger(__name__, log_file=log_file, level=level, clear=args.clear_log)
    logger.info(f"Logging initialized. Log file: {log_file}")

    if not os.getenv("PAPERCLIP_API_KEY"):
        logger.warning("PAPERCLIP_API_KEY not set; paperclip CLI calls will fail unless "
                        "already signed in via `paperclip login`")

    try:
        df = pd.read_csv(args.input, sep="\t", dtype=str).fillna("")
        logger.info(f"Loaded {len(df)} rows from {args.input}")
    except Exception as e:
        logger.error(f"Error reading input: {e}")
        sys.exit(1)

    if args.resource_col not in df.columns:
        logger.error(f"Column '{args.resource_col}' not found in {args.input}. Columns: {', '.join(df.columns)}")
        sys.exit(1)

    inventory_path = Path(args.inventory) if args.inventory else _find_latest_inventory()
    logger.info(f"Using inventory for claim context: {inventory_path}")
    sample_sizes = load_sample_sizes(inventory_path)

    cache_path = Path(args.cache_file)
    cache = {} if args.no_cache else load_cache(cache_path)

    max_workers = args.workers or min(16, max(1, (os.cpu_count() or 4) - 2))
    groups = list(enumerate(df.groupby(args.resource_col)))
    logger.info(f"Validating {len(groups)} resources with {max_workers} concurrent workers")

    statuses = [""] * len(df)
    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(validate_group, resource_name, group.to_dict("records"), args.sources, args.jobs,
                             cache, sample_sizes.get(resource_name, ""), group_idx): (resource_name, group)
            for group_idx, (resource_name, group) in groups
        }
        for future in as_completed(futures):
            resource_name, group = futures[future]
            completed += 1
            try:
                group_statuses = future.result()
            except Exception as e:
                logger.error(f"[validate] Resource '{resource_name}' failed: {e}", exc_info=True)
                continue
            for idx, status in zip(group.index, group_statuses):
                statuses[df.index.get_loc(idx)] = status
            logger.info(f"[validate] [{completed}/{len(groups)}] '{resource_name}' done")
            if not args.no_cache and completed % 10 == 0:
                save_cache(cache_path, cache)

    if not args.no_cache:
        save_cache(cache_path, cache)

    df["Paperclip Verified"] = statuses

    output_path = args.output or args.input.rsplit(".", 1)[0] + "_validated.tsv"
    df.to_csv(output_path, sep="\t", index=False)

    n_ok = statuses.count("OK")
    n_x = statuses.count("X")
    n_not_committed = statuses.count("not_committed")
    n_not_in_corpus = statuses.count("not_in_corpus")
    n_stale = statuses.count("stale_content")
    # stale_content = paperclip confirmed the doc_id but its full text isn't
    # loadable right now — neither a true nor false verdict, excluded either way.
    n_resolved = n_ok + n_x + n_not_committed
    precision = f"{n_ok / n_resolved * 100:.1f}%" if n_resolved else "N/A"

    logger.info("=" * 60)
    logger.info(f"SUCCESS: Results saved to {output_path}")
    logger.info(f"OK: {n_ok}  X: {n_x}  not_committed: {n_not_committed}  stale_content: {n_stale}  not_in_corpus: {n_not_in_corpus}")
    logger.info(f"Precision (OK / resolved, excludes stale_content/not_in_corpus): {precision}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
