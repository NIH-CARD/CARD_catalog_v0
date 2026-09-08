"""
CARD Catalog - multi-query hits combiner.

Preliminary step, run before staging.normalizer.normalize(): scrape_publications.py's
various --query-method/--target-db combinations (and the separate paperclip method) are
run independently against the same inventory, each writing its own hits file. The same
(resource, paper) pair is routinely rediscovered by more than one of them, but no single
field is populated consistently across all methods to key a merge on - pubmed-baseline
runs never populate DOI, some pmc-target runs are missing PMID, and paperclip's own
oa_/bio_-prefixed doc_ids have no PMID/DOI/PMC link at all. Matching therefore falls back
across whichever identifiers a given pair of rows actually share, not one canonical key.

Can be called programmatically or as a CLI::

    python -m staging.combine_hits \\
        --inputs tables/experiments/q1_pubmed_full.tsv tables/experiments/q3_pmc_full.tsv
    # writes tables/hits/combine_hits_<YYYYMMDD_HHMMSS>.tsv by default; pass --output to override.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from staging.normalizer import _fix_pmc_link, _normalize_list_field

logger = logging.getLogger(__name__)

_PMC_ID_RE = re.compile(r"(PMC\d+)")
# Matches every pipeline stage's intermediate-output convention (tables/hits/<stage>_<ts>.tsv,
# ts = %Y%m%d_%H%M%S) - see orchestrator.py's _ts() and any file under tables/hits/.
HITS_DIR = Path(__file__).parent.parent / "tables" / "hits"


def _row_identity_keys(row: "pd.Series") -> list[tuple[str, str]]:
    """(key_type, value) pairs usable to match this row to another row of the same paper -
    a row can carry more than one, and only needs to share a single one with another row
    for the two to be merged (see _UnionFind usage in combine_query_method_hits)."""
    keys = []
    pmid = str(row.get("PMID", "") or "").strip()
    if pmid:
        keys.append(("pmid", pmid))
    doi = str(row.get("DOI", "") or "").strip().lower()
    if doi:
        keys.append(("doi", doi))
    link = _fix_pmc_link(str(row.get("PubMed Central Link", "") or ""))
    m = _PMC_ID_RE.search(link)
    if m:
        keys.append(("pmcid", m.group(1)))
    doc_id = str(row.get("Paperclip Doc ID", "") or "").strip()
    if doc_id:
        keys.append(("doc_id", doc_id))
    return keys


class _UnionFind:
    """Standard disjoint-set with path compression, keyed on arbitrary hashable items
    (here, DataFrame index values) - lets two rows merge on any shared identifier even
    when they don't share all of them (row A ~ row B via PMID, row B ~ row C via PMC ID
    => A, B, C are one paper, though A and C alone share nothing)."""

    def __init__(self):
        self.parent: dict = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def combine_query_method_hits(paths: list[Path], resource_col: str = "Resource Name") -> pd.DataFrame:
    """Combine several query-method hits files into one row per (resource, paper).

    Matches rows sharing a resource plus any one identifier in common (PMID, DOI, PMC ID
    extracted from PubMed Central Link, or Paperclip Doc ID). For each collapsed group,
    ``Fetched With`` becomes the semicolon-joined union of every method's value - the point
    is to keep every method's provenance, not pick one - and every other column takes the
    longest non-empty value in the group (favors whichever source row was most complete).

    Args:
        paths: Hits TSV paths to combine, one per query-method run (see
            docs/plans/paperclip/ for the exact scrape_publications.py invocations).
        resource_col: Column identifying the resource (default "Resource Name").

    Returns:
        DataFrame with exactly one row per (resource, paper) pair.
    """
    frames = []
    for p in paths:
        df = pd.read_csv(p, sep="\t", dtype=str).fillna("")
        frames.append(df)
        logger.info(f"[combine] loaded {len(df)} rows from {p.name}")

    combined = pd.concat(frames, ignore_index=True, sort=False).fillna("")
    logger.info(f"[combine] {len(combined)} rows total across {len(paths)} file(s)")

    output_rows = []
    for _, group in combined.groupby(resource_col, sort=False):
        uf = _UnionFind()
        by_key: dict[tuple, list] = {}
        for i in group.index:
            for key in _row_identity_keys(group.loc[i]):
                by_key.setdefault(key, []).append(i)
        for members in by_key.values():
            for m in members[1:]:
                uf.union(members[0], m)

        merged_groups: dict = {}
        for i in group.index:
            merged_groups.setdefault(uf.find(i), []).append(i)

        for member_indices in merged_groups.values():
            rows = group.loc[member_indices]
            merged = {}
            for col in combined.columns:
                if col == "Fetched With":
                    # Escape any literal ';' inside one query before joining - confirmed live,
                    # 2/62706 rows have one (paperclip grep patterns can be arbitrary free text,
                    # e.g. a citation string containing "; "). Without this, splitting the stored
                    # field back apart on ';' would silently fragment that one query into two.
                    values = [str(v).strip().replace(";", ",") for v in rows[col] if str(v).strip()]
                    merged[col] = _normalize_list_field(";".join(values))
                else:
                    values = [str(v) for v in rows[col] if str(v).strip()]
                    merged[col] = max(values, key=len) if values else ""
            output_rows.append(merged)

    result = pd.DataFrame(output_rows, columns=list(combined.columns))
    logger.info(f"[combine] collapsed {len(combined)} rows -> {len(result)} unique (resource, paper) row(s)")
    return result


def _cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    parser = argparse.ArgumentParser(
        description="Combine multiple query-method hits files into one row per (resource, paper)"
    )
    parser.add_argument("--inputs", "-i", nargs="+", required=True, help="Hits TSV paths to combine")
    parser.add_argument("--output", "-o", default=None,
                       help="Output TSV path (default: tables/hits/combine_hits_<YYYYMMDD_HHMMSS>.tsv)")
    parser.add_argument("--resource-col", default="Resource Name", help='Column identifying the resource (default: "Resource Name")')
    args = parser.parse_args()

    result = combine_query_method_hits([Path(p) for p in args.inputs], resource_col=args.resource_col)
    if args.output:
        output_path = Path(args.output)
    else:
        HITS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = HITS_DIR / f"combine_hits_{ts}.tsv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, sep="\t", index=False)
    logger.info(f"[combine] wrote {len(result)} rows -> {output_path}")


if __name__ == "__main__":
    _cli()
