"""
Shared helper for per-item caching across pipeline stages.

Cache-aware stages (pub_metadata, repo_analysis, page_navigation) diff their
input items against what's already in ``tables/final/`` to skip reprocessing
items that were already extracted in a previous run.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
FINAL_DIR = PROJECT_ROOT / "tables" / "final"


def latest_final(pattern: str) -> Path | None:
    """Most recently modified file in tables/final/ matching pattern, or None.

    Args:
        pattern: Glob pattern, e.g. "pub_datasets_*.tsv".

    Returns:
        Path to the latest matching file, or None if no match exists.
    """
    matches = sorted(FINAL_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def combine_cached_and_new(cached: pd.DataFrame | None, new: pd.DataFrame | None) -> pd.DataFrame | None:
    """Union cached (already-final) rows with freshly-extracted rows, dropping empties."""
    parts = [df for df in (cached, new) if df is not None and not df.empty]
    if not parts:
        return None
    return pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
