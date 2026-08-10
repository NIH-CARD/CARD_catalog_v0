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
    with open(path, "w") as f:
        json.dump(cache, f, indent=2)
    logger.info(f"Saved validation cache: {len(cache)} entries to {path}")


def cache_key(resource_name: str, doc_id: str) -> str:
    return f"{resource_name}|||{doc_id}"


def _resolve_doc_id(row: Dict[str, str], sources: str) -> Optional[str]:
    """Prefer PMC ID (from PubMed Central Link); fall back to a paperclip search by DOI."""
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


def validate_group(resource_name: str, rows: List[Dict[str, str]], sources: str, jobs: int,
                    cache: Dict[str, str]) -> List[str]:
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
        reuse = len(existing_repos) == 1 and list(existing_repos)[0]
        repo_name = reuse or _paperclip_repo_name("validate", resource_name, rows[0].get("Abbreviation", ""))

        if not reuse:
            init_out = _paperclip_cli_raw("repo", "init", repo_name, f"Validate: {resource_name}"[:200])
            logger.debug(f"[validate] repo init {repo_name}: {init_out[:200]}")
            claim = f"This paper describes or uses data from the '{resource_name}' study."
            for doc_id in unique_new_doc_ids:
                _paperclip_cli(repo_name, "repo", "add", doc_id, claim)

        commit_out = _commit_with_retry(repo_name, f"Validate {resource_name}", jobs)
        logger.debug(f"[validate] commit {repo_name}: {commit_out[:300]}")

        claims_out = _paperclip_cli(repo_name, "repo", "claims")
        try:
            claims = json.loads(claims_out)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[validate] '{resource_name}': repo claims returned non-JSON output: {claims_out[:200]}")
            claims = []
        verified_map = {c.get("paperclip_doc_id"): c.get("verified") for c in claims}

        stale_doc_ids = _find_stale_doc_ids(repo_name)
        if stale_doc_ids:
            logger.info(f"[validate] '{resource_name}': {len(stale_doc_ids)} doc_id(s) permanently unavailable (no loadable full text), not a verdict")

        for doc_id in unique_new_doc_ids:
            status = _classify_claim(doc_id, verified_map, stale_doc_ids)
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

    cache_path = Path(args.cache_file)
    cache = {} if args.no_cache else load_cache(cache_path)

    statuses = [""] * len(df)
    for resource_name, group in df.groupby(args.resource_col):
        rows = group.to_dict("records")
        group_statuses = validate_group(resource_name, rows, args.sources, args.jobs, cache)
        for idx, status in zip(group.index, group_statuses):
            statuses[df.index.get_loc(idx)] = status

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
