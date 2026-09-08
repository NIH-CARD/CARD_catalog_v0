"""Backfill blank 'Source' values in the code repos table from orchestrator logs.

scrapers/scrape_github.py had a bug (now fixed) that dropped the Source
column for a stretch of runs, and repo_analysis's cache-by-Repository-Link
means already-cached blank rows don't self-heal just because the scraper
bug got fixed later. staging/normalizer.py's _backfill_source_from_pub_
software() already recovers the subset of blanks that are also cited as a
software mention elsewhere; this recovers the rest by replaying each
orchestrator log's github_search phase and matching each repo to the search
query that was active when it was processed - the same "GitHub search:
<query>" value scrape_github.py would have written at scrape time.

Run from anywhere in the repo:
    python3 scripts/backfill_code_source_from_logs.py [--dry-run]

After a real (non-dry-run) run, re-sync the app's copy:
    cd web && npm run sync-data
"""
import argparse
import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
FINAL_DIR = PROJECT_ROOT / "tables" / "final"

# The github_search stage's own log markers - see pipelines/github_search.py
# (phase start) and scrapers/scrape_github.py's extra_repos-from-software
# enrichment (phase end): that later phase reuses the same "Checking FAIR
# compliance for X" line for a different discovery path (a software mention,
# not a search query), so it must not be attributed to the last query seen.
SEARCH_PHASE_START_RE = re.compile(r"\[github_search\] starting")
EXTRA_REPOS_PHASE_RE = re.compile(r"Enriching \d+ externally-discovered repo candidate")
QUERY_RE = re.compile(r"Constructed search query: (.+)$")
FAIR_CHECK_RE = re.compile(r"Checking FAIR compliance for ([\w.\-]+/[\w.\-]+)")

GITHUB_URL_RE = re.compile(r"github\.com/([\w.\-]+)/([\w.\-]+)", re.IGNORECASE)


def normalize_repo_url(url: str) -> str:
    """Extract a lowercase 'owner/repo' key from a GitHub URL for matching."""
    m = GITHUB_URL_RE.search(str(url or "").strip().lower())
    if not m:
        return ""
    owner, repo = m.group(1), m.group(2)
    return f"{owner}/{repo[:-4] if repo.endswith('.git') else repo}"


def build_query_map(log_paths: list[Path]) -> dict[str, str]:
    """Replay each log's github_search phase, mapping repo -> 'GitHub search: <query>'.

    First-seen wins across chronologically-sorted logs, since the earliest
    log is closest to how the repo was actually first discovered.

    Args:
        log_paths: orchestrator_*.log files to replay, any order.

    Returns:
        Normalized 'owner/repo' -> 'GitHub search: <query>' mapping.
    """
    query_map: dict[str, str] = {}
    for log_path in sorted(log_paths):
        in_search_phase = False
        current_query = None
        with log_path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if SEARCH_PHASE_START_RE.search(line):
                    in_search_phase = True
                    current_query = None
                    continue
                if EXTRA_REPOS_PHASE_RE.search(line):
                    in_search_phase = False
                    continue
                if not in_search_phase:
                    continue
                m = QUERY_RE.search(line)
                if m:
                    current_query = m.group(1).strip()
                    continue
                m = FAIR_CHECK_RE.search(line)
                if m and current_query:
                    key = normalize_repo_url(f"github.com/{m.group(1)}")
                    query_map.setdefault(key, f"GitHub search: {current_query}")
    logger.info(f"Built query map for {len(query_map)} repo(s) from {len(log_paths)} log file(s)")
    return query_map


def latest_final(pattern: str) -> Path | None:
    matches = sorted(FINAL_DIR.glob(pattern))
    return matches[-1] if matches else None


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()

    code_path = latest_final("gits_to_reannotate_completed_*.tsv")
    if not code_path:
        logger.error("No gits_to_reannotate_completed_*.tsv found in tables/final/")
        return
    df = pd.read_csv(code_path, sep="\t", dtype=str).fillna("")
    logger.info(f"Loaded {len(df)} rows from {code_path.name}")

    blank_mask = df["Source"].str.strip() == ""
    n_blank = int(blank_mask.sum())
    logger.info(f"{n_blank} row(s) with blank Source")

    log_paths = list(LOGS_DIR.glob("orchestrator_*.log"))
    query_map = build_query_map(log_paths)

    keys = df["Repository Link"].apply(normalize_repo_url)
    resolved = keys.map(query_map)
    fillable = blank_mask & resolved.notna()

    logger.info(f"Resolved {int(fillable.sum())} of {n_blank} blank Source value(s) from logs")
    still_blank = blank_mask & ~fillable
    if still_blank.any():
        logger.warning(f"{int(still_blank.sum())} row(s) remain unresolved - no matching log evidence found")
        for link in df.loc[still_blank, "Repository Link"]:
            logger.warning(f"  unresolved: {link}")

    if args.dry_run:
        logger.info("Dry run - not writing changes")
        return

    df.loc[fillable, "Source"] = resolved[fillable]
    df.to_csv(code_path, sep="\t", index=False)
    logger.info(f"Wrote {len(df)} rows → {code_path.name} - run `npm run sync-data` in web/ to refresh the app's copy")


if __name__ == "__main__":
    main()
